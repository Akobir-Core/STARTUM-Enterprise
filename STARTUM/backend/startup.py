"""Safe listener binding helpers for the single STARTUM API process."""
from __future__ import annotations

import errno
import os
import socket
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class ApiPortInUseError(RuntimeError):
    host: str
    port: int
    owner: str = ""

    def __str__(self) -> str:
        message = (
            f"STARTUM API {self.host}:{self.port} manzilida ishga tusha olmadi: "
            "port allaqachon boshqa jarayon tomonidan band."
        )
        if self.owner:
            message += f" Ehtimoliy egasi: {self.owner}."
        message += (
            " Jarayonni to‘xtatishdan oldin PID va nomini tekshiring: "
            f"Get-NetTCPConnection -LocalPort {self.port} -State Listen | "
            "Select-Object LocalAddress,LocalPort,OwningProcess; "
            "Get-Process -Id <PID>"
        )
        return message


def _windows_port_owner(port: int) -> str:
    """Return a read-only process hint; never terminate or modify any process."""
    if os.name != "nt":
        return ""
    script = (
        f"$c=Get-NetTCPConnection -LocalPort {int(port)} -State Listen "
        "-ErrorAction SilentlyContinue | Select-Object -First 1; "
        "if($c){$p=Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue; "
        "if($p){\"$($p.ProcessName) (PID $($p.Id))\"}}"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
        return result.stdout.strip()[:160]
    except (OSError, subprocess.SubprocessError):
        return ""


def bind_api_listener(host: str, port: int) -> socket.socket:
    """Bind exactly one listening socket before any bot/background task starts."""
    if not 1 <= int(port) <= 65535:
        raise ValueError("API_PORT 1 dan 65535 gacha bo‘lishi kerak.")

    try:
        addresses = socket.getaddrinfo(host, int(port), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise RuntimeError(f"API_HOST manzili aniqlanmadi: {host}") from exc

    last_error: OSError | None = None
    for family, socktype, proto, _canonname, sockaddr in addresses:
        listener = socket.socket(family, socktype, proto)
        try:
            # Do not set SO_REUSEADDR here: a second STARTUM instance must not
            # silently share the production listener on Windows.
            listener.bind(sockaddr)
            listener.listen(socket.SOMAXCONN)
            listener.setblocking(False)
            return listener
        except OSError as exc:
            last_error = exc
            listener.close()
            if exc.errno in {errno.EADDRINUSE, 10048} or getattr(exc, "winerror", None) == 10048:
                raise ApiPortInUseError(host, int(port), _windows_port_owner(int(port))) from exc

    if last_error:
        raise RuntimeError(f"API {host}:{port} socketini ochib bo‘lmadi: {last_error}") from last_error
    raise RuntimeError(f"API {host}:{port} uchun mos tarmoq manzili topilmadi.")
