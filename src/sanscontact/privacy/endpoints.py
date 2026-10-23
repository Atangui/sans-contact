"""Read-only view of the TCP/UDP endpoints owned by a process.

Python-level blocking cannot see what native libraries do, so the operating
system's own connection tables are inspected. Nothing is sent anywhere: the
tables are read with GetExtendedTcpTable / GetExtendedUdpTable.
"""

from __future__ import annotations

import ctypes
import ipaddress
import os
import struct
from collections.abc import Iterable
from ctypes import wintypes
from dataclasses import dataclass

from sanscontact import _win32 as w

AF_INET = 2
AF_INET6 = 23
TCP_TABLE_OWNER_PID_ALL = 5
UDP_TABLE_OWNER_PID = 1
TCP_STATE_LISTEN = 2

_TCP4_ROW = struct.Struct("<6I")  # state, laddr, lport, raddr, rport, pid
_TCP6_ROW = struct.Struct("<16sII16sIIII")  # laddr, lscope, lport, raddr, rscope, rport, state, pid
_UDP4_ROW = struct.Struct("<3I")  # laddr, lport, pid
_UDP6_ROW = struct.Struct("<16sIII")  # laddr, lscope, lport, pid


@dataclass(frozen=True)
class Endpoint:
    protocol: str
    local: str
    remote: str | None
    state: int | None
    pid: int

    @property
    def listening(self) -> bool:
        return self.protocol.startswith("tcp") and self.state == TCP_STATE_LISTEN

    @property
    def outbound(self) -> bool:
        return self.protocol.startswith("tcp") and self.remote is not None and self.state != TCP_STATE_LISTEN


def _port(raw: int) -> int:
    return ((raw & 0xFF) << 8) | ((raw >> 8) & 0xFF)


def _v4(raw: int) -> str:
    return str(ipaddress.IPv4Address(struct.pack("<I", raw)))


def _read_table(func, family: int, table_class: int) -> bytes:
    size = wintypes.DWORD(0)
    for _ in range(5):
        buffer = ctypes.create_string_buffer(max(size.value, 4))
        status = func(buffer, ctypes.byref(size), False, family, table_class, 0)
        if status == w.NO_ERROR:
            return buffer.raw[: size.value]
        if status != w.ERROR_INSUFFICIENT_BUFFER:
            raise OSError(status, f"connection table query failed ({status})")
    raise OSError(w.ERROR_INSUFFICIENT_BUFFER, "connection table kept growing")


def _rows(raw: bytes, row: struct.Struct) -> Iterable[tuple]:
    (count,) = struct.unpack_from("<I", raw, 0)
    for i in range(count):
        yield row.unpack_from(raw, 4 + i * row.size)


def endpoints(pids: Iterable[int] | None = None) -> list[Endpoint]:
    wanted = set(pids) if pids is not None else {os.getpid()}
    found: list[Endpoint] = []

    for state, laddr, lport, raddr, rport, pid in _rows(
        _read_table(w.GetExtendedTcpTable, AF_INET, TCP_TABLE_OWNER_PID_ALL), _TCP4_ROW
    ):
        if pid in wanted:
            remote = None if state == TCP_STATE_LISTEN else f"{_v4(raddr)}:{_port(rport)}"
            found.append(Endpoint("tcp", f"{_v4(laddr)}:{_port(lport)}", remote, state, pid))

    for laddr, _ls, lport, raddr, _rs, rport, state, pid in _rows(
        _read_table(w.GetExtendedTcpTable, AF_INET6, TCP_TABLE_OWNER_PID_ALL), _TCP6_ROW
    ):
        if pid in wanted:
            remote = None if state == TCP_STATE_LISTEN else f"[{ipaddress.IPv6Address(raddr)}]:{_port(rport)}"
            found.append(Endpoint("tcp6", f"[{ipaddress.IPv6Address(laddr)}]:{_port(lport)}", remote, state, pid))

    for laddr, lport, pid in _rows(_read_table(w.GetExtendedUdpTable, AF_INET, UDP_TABLE_OWNER_PID), _UDP4_ROW):
        if pid in wanted:
            found.append(Endpoint("udp", f"{_v4(laddr)}:{_port(lport)}", None, None, pid))

    for laddr, _ls, lport, pid in _rows(
        _read_table(w.GetExtendedUdpTable, AF_INET6, UDP_TABLE_OWNER_PID), _UDP6_ROW
    ):
        if pid in wanted:
            found.append(Endpoint("udp6", f"[{ipaddress.IPv6Address(laddr)}]:{_port(lport)}", None, None, pid))
    return found


class EndpointWatch:
    """Counts distinct endpoints ever seen for the watched processes."""

    def __init__(self, pids: Iterable[int] | None = None) -> None:
        self.pids = set(pids) if pids is not None else {os.getpid()}
        self._seen: set[tuple[str, str, str | None]] = set()
        self.errors = 0

    def poll(self) -> int:
        try:
            current = endpoints(self.pids)
        except OSError:
            self.errors += 1
            return len(self._seen)
        for ep in current:
            self._seen.add((ep.protocol, ep.local, ep.remote))
        return len(self._seen)

    @property
    def count(self) -> int:
        return len(self._seen)
