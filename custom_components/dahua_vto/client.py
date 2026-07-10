"""Async client implementing Dahua's DHIP TCP protocol.

The protocol is used by VTO/VTH door stations, DMSS and Dahua NVRs to
exchange JSON-RPC-like messages over a persistent TCP connection
(default port 5000). Every message is prefixed with a fixed binary header:

    <Q magic><L session id><L request id><Q body length><Q body length>

followed by the UTF-8 encoded JSON payload.

Authentication uses a two-step MD5 challenge/response (the same one used
by the DMSS mobile app), after which the client attaches to
``eventManager`` to receive a live stream of device events (doorbell
presses, motion, call status, etc).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import struct
from collections.abc import Callable
from typing import Any

from .const import (
    COMMAND_TIMEOUT,
    DHIP_HEADER_FORMAT,
    DHIP_PROTO_MAGIC,
    DHIP_REALM_CHALLENGE_ERROR_CODE,
    KEEPALIVE_DEFAULT_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

_LOGIN_PARAMS_TEMPLATE = {"clientType": "", "ipAddr": "(null)", "loginType": "Direct"}


class DahuaVtoError(Exception):
    """Base error for the Dahua VTO client."""


class DahuaAuthError(DahuaVtoError):
    """Raised when authentication with the device fails."""


class DahuaConnectionError(DahuaVtoError):
    """Raised when the TCP connection cannot be established or is lost."""


class DahuaVtoClient:
    """Maintains a persistent authenticated connection to a Dahua VTO."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        *,
        event_callback: Callable[[dict[str, Any]], None] | None = None,
        availability_callback: Callable[[bool], None] | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._event_callback = event_callback
        self._availability_callback = availability_callback

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._session_id = 0
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._read_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._keepalive_interval = KEEPALIVE_DEFAULT_INTERVAL
        self._connected = False
        self.device_info: dict[str, Any] = {}
        self._closing = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        """Open the TCP connection and perform the login handshake."""
        self._closing = False
        try:
            self._reader, self._writer = await asyncio.open_connection(
                self._host, self._port
            )
        except OSError as err:
            raise DahuaConnectionError(str(err)) from err

        self._read_task = asyncio.ensure_future(self._read_loop())
        await self._login()
        await self._attach_events()
        self._heartbeat_task = asyncio.ensure_future(self._heartbeat_loop())
        self._connected = True
        if self._availability_callback:
            self._availability_callback(True)

    async def disconnect(self) -> None:
        """Close the connection and cancel background tasks."""
        self._closing = True
        for task in (self._heartbeat_task, self._read_task):
            if task and not task.done():
                task.cancel()
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except OSError:
                pass
        self._connected = False

    async def open_door(self, channel: int = 0, short_number: str = "HA") -> None:
        """Trigger the relay to open the door for the given channel (0-based)."""
        object_id = await self._instance(
            "accessControl.factory.instance", {"channel": channel}
        )
        try:
            await self._call(
                "accessControl.openDoor",
                {"DoorIndex": 0, "ShortNumber": short_number},
                obj=object_id,
            )
        finally:
            await self._call("accessControl.destroy", None, obj=object_id)

    async def get_system_info(self) -> dict[str, Any]:
        result = await self._call("magicBox.getSystemInfo", None)
        return result.get("params", {})

    # -- internal protocol plumbing -------------------------------------------------

    def _hash_password(self, random: str, realm: str) -> str:
        inner = hashlib.md5(
            f"{self._username}:{realm}:{self._password}".encode()
        ).hexdigest().upper()
        return hashlib.md5(f"{self._username}:{random}:{inner}".encode()).hexdigest().upper()

    async def _login(self) -> None:
        login_params = dict(_LOGIN_PARAMS_TEMPLATE)
        try:
            await self._call("global.login", login_params, expect_challenge=True)
        except _AuthChallenge as challenge:
            login_params["userName"] = self._username
            login_params["password"] = self._hash_password(
                challenge.random, challenge.realm
            )
            result = await self._call("global.login", login_params)
            if not result.get("result"):
                raise DahuaAuthError("Invalid username or password")
            keepalive = await self._call(
                "global.keepAlive", {"timeout": KEEPALIVE_DEFAULT_INTERVAL, "action": True}
            )
            self._keepalive_interval = (
                keepalive.get("params", {}).get("keepAliveInterval")
                or KEEPALIVE_DEFAULT_INTERVAL
            )
            return
        raise DahuaAuthError("Device did not present the expected auth challenge")

    async def _attach_events(self) -> None:
        await self._call("eventManager.attach", {"codes": ["All"]})

    async def _instance(self, method: str, params: dict[str, Any]) -> int:
        result = await self._call(method, params)
        return result.get("result")

    async def _heartbeat_loop(self) -> None:
        try:
            self.device_info = await self.get_system_info()
        except DahuaVtoError:
            _LOGGER.debug("Unable to fetch system info from %s", self._host)
        while True:
            await asyncio.sleep(self._keepalive_interval)
            try:
                await self._call(
                    "global.keepAlive",
                    {"timeout": self._keepalive_interval, "action": True},
                )
            except (DahuaVtoError, asyncio.TimeoutError):
                _LOGGER.warning("Keepalive to %s failed, closing connection", self._host)
                await self._handle_connection_lost()
                return

    async def _read_loop(self) -> None:
        header_len = struct.calcsize(DHIP_HEADER_FORMAT)
        buffer = b""
        try:
            while True:
                chunk = await self._reader.read(4096)
                if not chunk:
                    raise DahuaConnectionError("Connection closed by remote host")
                buffer += chunk
                while len(buffer) >= header_len:
                    magic, _session, _req, body_len, _body_len2 = struct.unpack_from(
                        DHIP_HEADER_FORMAT, buffer
                    )
                    if magic != DHIP_PROTO_MAGIC:
                        raise DahuaConnectionError("Unexpected protocol magic in stream")
                    end = header_len + body_len
                    if len(buffer) < end:
                        break
                    payload = buffer[header_len:end]
                    buffer = buffer[end:]
                    self._handle_message(json.loads(payload.decode("utf-8", "ignore")))
        except asyncio.CancelledError:
            raise
        except (DahuaVtoError, OSError, json.JSONDecodeError) as err:
            if not self._closing:
                _LOGGER.debug("Read loop for %s ended: %s", self._host, err)
                await self._handle_connection_lost()

    def _handle_message(self, message: dict[str, Any]) -> None:
        msg_id = message.get("id")
        if msg_id is not None and msg_id in self._pending:
            future = self._pending.pop(msg_id)
            if not future.done():
                future.set_result(message)
            return

        method = message.get("method")
        if method == "client.notifyEventStream" and self._event_callback:
            for event in message.get("params", {}).get("eventList", []):
                self._event_callback(event)

    async def _handle_connection_lost(self) -> None:
        self._connected = False
        for future in self._pending.values():
            if not future.done():
                future.set_exception(DahuaConnectionError("Connection lost"))
        self._pending.clear()
        if self._availability_callback:
            self._availability_callback(False)

    async def _call(
        self,
        method: str,
        params: dict[str, Any] | None,
        *,
        obj: int | None = None,
        expect_challenge: bool = False,
        timeout: float = COMMAND_TIMEOUT,
    ) -> dict[str, Any]:
        self._request_id += 1
        request_id = self._request_id
        message: dict[str, Any] = {
            "method": method,
            "id": request_id,
            "session": self._session_id,
        }
        if params is not None:
            message["params"] = params
        if obj is not None:
            message["object"] = obj

        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        await self._send(message)

        try:
            response = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError as err:
            self._pending.pop(request_id, None)
            raise DahuaConnectionError(f"Timeout waiting for {method}") from err

        error = response.get("error")
        if error:
            if expect_challenge and error.get("code") == DHIP_REALM_CHALLENGE_ERROR_CODE:
                self._session_id = response.get("session", self._session_id)
                challenge_params = response.get("params") or {}
                raise _AuthChallenge(
                    random=challenge_params.get("random", ""),
                    realm=challenge_params.get("realm", ""),
                )
            raise DahuaVtoError(f"{method} failed: {error}")
        return response

    async def _send(self, message: dict[str, Any]) -> None:
        body = json.dumps(message, separators=(",", ":")).encode("utf-8")
        header = struct.pack(
            DHIP_HEADER_FORMAT,
            DHIP_PROTO_MAGIC,
            self._session_id,
            message["id"],
            len(body),
            len(body),
        )
        assert self._writer is not None
        self._writer.write(header + body)
        await self._writer.drain()


class _AuthChallenge(Exception):
    """Internal signal carrying the MD5 challenge parameters."""

    def __init__(self, random: str, realm: str) -> None:
        super().__init__("auth challenge")
        self.random = random
        self.realm = realm
