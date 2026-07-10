"""Tests for the Dahua DHIP protocol client.

These tests spin up a tiny in-process TCP server that speaks the same
binary framing / login challenge handshake as a real Dahua VTO, so the
client can be exercised end-to-end without any Home Assistant or network
dependency.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import struct

import pytest

from dahua_vto.client import (
    DHIP_HEADER_FORMAT,
    DHIP_PROTO_MAGIC,
    DHIP_REALM_CHALLENGE_ERROR_CODE,
    DahuaAuthError,
    DahuaVtoClient,
)

HOST = "127.0.0.1"
USERNAME = "admin"
PASSWORD = "devtest123"
RANDOM = "abc123"
REALM = "Login to 10.0.0.70"


def _pack(session: int, req_id: int, payload: dict) -> bytes:
    body = json.dumps(payload).encode()
    header = struct.pack(
        DHIP_HEADER_FORMAT, DHIP_PROTO_MAGIC, session, req_id, len(body), len(body)
    )
    return header + body


async def _read_message(reader: asyncio.StreamReader) -> dict:
    header_len = struct.calcsize(DHIP_HEADER_FORMAT)
    header = await reader.readexactly(header_len)
    _magic, _session, _req, body_len, _ = struct.unpack(DHIP_HEADER_FORMAT, header)
    body = await reader.readexactly(body_len)
    return json.loads(body.decode())


def _expected_password_hash(username: str, password: str, random: str, realm: str) -> str:
    inner = hashlib.md5(f"{username}:{realm}:{password}".encode()).hexdigest().upper()
    return hashlib.md5(f"{username}:{random}:{inner}".encode()).hexdigest().upper()


async def _fake_vto_server(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    session_id = 42
    # 1) First login attempt: reject with the realm challenge.
    msg = await _read_message(reader)
    writer.write(
        _pack(
            session_id,
            msg["id"],
            {
                "id": msg["id"],
                "session": session_id,
                "params": {"random": RANDOM, "realm": REALM},
                "error": {"code": DHIP_REALM_CHALLENGE_ERROR_CODE, "message": "challenge"},
            },
        )
    )
    await writer.drain()

    # 2) Second login attempt: validate hashed password.
    msg = await _read_message(reader)
    expected = _expected_password_hash(USERNAME, PASSWORD, RANDOM, REALM)
    ok = msg["params"].get("password") == expected
    writer.write(
        _pack(session_id, msg["id"], {"id": msg["id"], "session": session_id, "result": ok})
    )
    await writer.drain()
    if not ok:
        writer.close()
        return

    # 3) keepAlive negotiation.
    msg = await _read_message(reader)
    writer.write(
        _pack(
            session_id,
            msg["id"],
            {
                "id": msg["id"],
                "session": session_id,
                "result": True,
                "params": {"keepAliveInterval": 60},
            },
        )
    )
    await writer.drain()

    # 4) eventManager.attach
    msg = await _read_message(reader)
    writer.write(
        _pack(session_id, msg["id"], {"id": msg["id"], "session": session_id, "result": True})
    )
    await writer.drain()

    # Keep the connection open so the client's heartbeat task doesn't error.
    try:
        while True:
            msg = await _read_message(reader)
            writer.write(
                _pack(
                    session_id, msg["id"], {"id": msg["id"], "session": session_id, "result": True}
                )
            )
            await writer.drain()
    except (asyncio.IncompleteReadError, ConnectionResetError):
        pass
    finally:
        writer.close()


@pytest.mark.asyncio
async def test_login_success_and_disconnect():
    server = await asyncio.start_server(_fake_vto_server, HOST, 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        client = DahuaVtoClient(HOST, port, USERNAME, PASSWORD)
        await client.connect()
        assert client.connected is True
        await client.disconnect()
        assert client.connected is False


@pytest.mark.asyncio
async def test_login_invalid_password_raises_auth_error():
    server = await asyncio.start_server(_fake_vto_server, HOST, 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        client = DahuaVtoClient(HOST, port, USERNAME, "wrong-password")
        with pytest.raises(DahuaAuthError):
            await client.connect()
