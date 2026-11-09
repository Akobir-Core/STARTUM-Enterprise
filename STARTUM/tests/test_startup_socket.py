from __future__ import annotations

import socket
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from startup import ApiPortInUseError, bind_api_listener


def test_bind_api_listener_accepts_available_port() -> None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    listener = bind_api_listener("127.0.0.1", port)
    try:
        assert listener.getsockname()[1] == port
        assert listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) == 1
        assert listener.getblocking() is False
    finally:
        listener.close()


def test_bind_api_listener_reports_port_conflict_without_killing_process() -> None:
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.bind(("127.0.0.1", 0))
    occupied.listen(1)
    port = occupied.getsockname()[1]
    try:
        try:
            bind_api_listener("127.0.0.1", port)
        except ApiPortInUseError as exc:
            message = str(exc)
            assert "127.0.0.1" in message
            assert str(port) in message
            assert "OwningProcess" in message
        else:
            raise AssertionError("Expected ApiPortInUseError for an occupied listener")
        # The function must never close or otherwise affect the existing owner.
        assert occupied.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) == 1
    finally:
        occupied.close()


def test_bind_api_listener_rejects_invalid_port() -> None:
    for port in (0, -1, 65536):
        try:
            bind_api_listener("127.0.0.1", port)
        except ValueError as exc:
            assert "API_PORT" in str(exc)
        else:
            raise AssertionError(f"Port {port} should be rejected")
