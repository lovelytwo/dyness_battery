"""asyncio TCP listener for the Dyness logger (port 5005).

Modes:
- endpoint: answer the logger locally, never send `00 77`.
- passthru: relay bytes unchanged to upstream_host:upstream_port and parse a copy.

No Home Assistant imports; the integration passes callbacks.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
import time
from typing import Callable, Iterable, List, Optional, Set

from .protocol import (
    OP_CONFIG,
    OP_LOGIN,
    OP_UPLOAD,
    FieldError,
    Frame,
    FrameBuffer,
    FrameError,
    endpoint_replies,
    parse_upload,
)
from .store import LocalStore
from .trace import Trace

_LOGGER = logging.getLogger(__name__)

MODE_ENDPOINT = "endpoint"
MODE_PASSTHRU = "passthru"

DEFAULT_PORT = 5005
CONNECT_TIMEOUT_S = 10
CYCLE_QUIET_S = 30
READ_SIZE = 65536
REPAIR_AFTER_FAILURES = 5

UpdateCallback = Callable[[], None]
UpstreamCallback = Callable[[bool, int, Optional[str]], None]


class UpstreamRefused(OSError):
    """upstream_host resolves to this host (loopback or own address)."""


class LoggerListener:
    def __init__(
        self,
        store: LocalStore,
        mode: str,
        *,
        bind_host: str = "0.0.0.0",
        port: int = DEFAULT_PORT,
        upstream_host: Optional[str] = None,
        upstream_port: int = DEFAULT_PORT,
        fallback_to_endpoint: bool = False,
        trace: Optional[Trace] = None,
        on_update: Optional[UpdateCallback] = None,
        on_upstream: Optional[UpstreamCallback] = None,
        own_addresses: Iterable[str] = (),
    ) -> None:
        if mode == MODE_PASSTHRU and not upstream_host:
            raise ValueError("passthru needs upstream_host")
        self.store = store
        self.mode = mode
        self.bind_host = bind_host
        self.port = port
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port
        self.fallback_to_endpoint = fallback_to_endpoint
        self.trace = trace
        self.on_update = on_update
        self.on_upstream = on_upstream
        self.own_addresses: Set[str] = set(own_addresses)
        self.upstream_failures = 0
        self.connected_peers: List[str] = []
        self._server: Optional[asyncio.AbstractServer] = None
        self._tasks: Set[asyncio.Task] = set()
        self._quiet_timer: Optional[asyncio.TimerHandle] = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._accept, self.bind_host, self.port, reuse_address=True
        )
        _LOGGER.info("Dyness local listener (%s) on %s:%s", self.mode, self.bind_host, self.port)

    async def stop(self) -> None:
        if self._quiet_timer is not None:
            self._quiet_timer.cancel()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    # ── session setup ───────────────────────────────────────────────────

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._tasks.add(task)
        peername = writer.get_extra_info("peername")
        peer = f"{peername[0]}:{peername[1]}" if peername else "?"
        sockname = writer.get_extra_info("sockname")
        self.connected_peers.append(peer)
        _LOGGER.info("Dyness logger connected from %s", peer)
        try:
            if self.mode == MODE_PASSTHRU:
                await self._passthru(reader, writer, peer, sockname[0] if sockname else None)
            else:
                await self._endpoint(reader, writer, peer)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - one bad session must not stop the listener
            _LOGGER.exception("Dyness logger session %s failed", peer)
        finally:
            self.connected_peers.remove(peer)
            await _close(writer)
            _LOGGER.info("Dyness logger %s disconnected", peer)
            if task is not None:
                self._tasks.discard(task)

    async def _resolve_upstream(self, local_addr: Optional[str]) -> List[str]:
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(
            self.upstream_host, self.upstream_port, family=socket.AF_INET, type=socket.SOCK_STREAM
        )
        addresses = sorted({info[4][0] for info in infos})
        own = set(self.own_addresses)
        if local_addr:
            own.add(local_addr)
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if ip.is_loopback or ip.is_unspecified or address in own:
                raise UpstreamRefused(
                    f"{self.upstream_host} resolves to {address}, which is this host"
                )
        return addresses

    async def _connect_upstream(self, local_addr: Optional[str]):
        addresses = await self._resolve_upstream(local_addr)
        last_error: Optional[BaseException] = None
        for address in addresses:
            try:
                return await asyncio.wait_for(
                    asyncio.open_connection(address, self.upstream_port), CONNECT_TIMEOUT_S
                ), address
            except (OSError, asyncio.TimeoutError) as exc:
                last_error = exc
        raise OSError(f"no upstream address reachable: {last_error}")

    def _upstream_result(self, ok: bool, error: Optional[str]) -> None:
        self.upstream_failures = 0 if ok else self.upstream_failures + 1
        if self.on_upstream is not None:
            self.on_upstream(ok, self.upstream_failures, error)

    # ── endpoint ────────────────────────────────────────────────────────

    async def _endpoint(self, reader, writer, peer: str) -> None:
        buffer = FrameBuffer()
        while True:
            try:
                data = await asyncio.wait_for(reader.read(READ_SIZE), self.store.timeout_s)
            except asyncio.TimeoutError:
                _LOGGER.info("Dyness logger %s idle for %ss, closing", peer, self.store.timeout_s)
                return
            if not data:
                return
            try:
                frames = buffer.feed(data)
            except FrameError as exc:
                _LOGGER.warning("Dyness logger %s sent an invalid frame (%s), closing", peer, exc)
                if self.trace:
                    self.trace.unframed("logger_to_upstream", peer, data, str(exc))
                return
            for frame in frames:
                now = time.time()
                self._observe("logger_to_upstream", peer, frame, now)
                replies = endpoint_replies(frame, int(now * 1000))
                if not replies:
                    _LOGGER.debug("Dyness logger %s: no reply for opcode %s", peer, frame.opcode_hex)
                for reply in replies:
                    writer.write(reply)
                    if self.trace:
                        self.trace.frame("upstream_to_logger", peer, FrameBuffer().feed(reply)[0], now)
                await writer.drain()

    # ── passthru ────────────────────────────────────────────────────────

    async def _passthru(self, reader, writer, peer: str, local_addr: Optional[str]) -> None:
        try:
            (up_reader, up_writer), address = await self._connect_upstream(local_addr)
        except (OSError, asyncio.TimeoutError) as exc:
            error = str(exc) or type(exc).__name__
            self._upstream_result(False, error)
            _LOGGER.warning(
                "Dyness upstream %s:%s failed (%s), attempt %d",
                self.upstream_host, self.upstream_port, error, self.upstream_failures,
            )
            if self.fallback_to_endpoint:
                _LOGGER.info("Dyness: answering %s locally (fallback_to_endpoint)", peer)
                await self._endpoint(reader, writer, peer)
            return
        self._upstream_result(True, None)
        _LOGGER.info("Dyness passthru %s <-> %s:%s", peer, address, self.upstream_port)
        try:
            to_up = asyncio.ensure_future(
                self._pump(reader, up_writer, peer, "logger_to_upstream", self.store.timeout_s)
            )
            to_logger = asyncio.ensure_future(
                self._pump(up_reader, writer, peer, "upstream_to_logger", None)
            )
            done, pending = await asyncio.wait({to_up, to_logger}, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                if task.exception() is not None and not isinstance(task.exception(), (OSError, asyncio.TimeoutError)):
                    raise task.exception()
        finally:
            await _close(up_writer)

    async def _pump(self, reader, writer, peer: str, direction: str, idle: Optional[float]) -> None:
        buffer: Optional[FrameBuffer] = FrameBuffer()
        while True:
            if idle is not None:
                data = await asyncio.wait_for(reader.read(READ_SIZE), idle)
            else:
                data = await reader.read(READ_SIZE)
            if not data:
                return
            writer.write(data)
            await writer.drain()
            if buffer is None:
                continue
            try:
                frames = buffer.feed(data)
            except FrameError as exc:
                _LOGGER.warning("Dyness %s: unparseable stream (%s); relaying without parsing", direction, exc)
                if self.trace:
                    self.trace.unframed(direction, peer, data, str(exc))
                buffer = None
                continue
            now = time.time()
            for frame in frames:
                self._observe(direction, peer, frame, now)

    # ── parsing copy ────────────────────────────────────────────────────

    def _observe(self, direction: str, peer: str, frame: Frame, now: float) -> None:
        if self.trace:
            self.trace.frame(direction, peer, frame, now)
        if direction != "logger_to_upstream":
            return
        if frame.opcode == OP_LOGIN:
            _LOGGER.debug("Dyness logger %s login (serial %s)", peer, frame.serial)
            return
        if frame.opcode not in (OP_UPLOAD, OP_CONFIG):
            _LOGGER.debug("Dyness logger %s opcode %s", peer, frame.opcode_hex)
            return
        try:
            upload = parse_upload(frame)
        except FieldError as exc:
            _LOGGER.warning(
                "Dyness logger %s: %s frame did not parse (%s); acknowledged anyway",
                peer, frame.opcode_hex, exc,
            )
            return
        _LOGGER.debug(
            "Dyness %s %s %s: %d fields", frame.serial, frame.opcode_hex, upload.name, len(upload.fields)
        )
        events = self.store.ingest(frame.serial, upload, now)
        for event in events:
            if self.trace:
                self.trace.event(event)
            if event.get("event") == "cycle_complete":
                self._cycle_done(event)
        if frame.opcode == OP_UPLOAD and not upload.is_bank:
            self._arm_quiet_timer()

    def _arm_quiet_timer(self) -> None:
        if self._quiet_timer is not None:
            self._quiet_timer.cancel()
        self._quiet_timer = asyncio.get_running_loop().call_later(CYCLE_QUIET_S, self._quiet)

    def _quiet(self) -> None:
        self._quiet_timer = None
        for event in self.store.finish_cycle():
            if self.trace:
                self.trace.event(event)
            self._cycle_done(event)

    def _cycle_done(self, event) -> None:
        if event.get("shortfall"):
            _LOGGER.info(
                "Dyness upload cycle: %d of %s boards", len(event["boards"]), event["expected_boards"]
            )
        if self.on_update is not None:
            self.on_update()


async def _close(writer: asyncio.StreamWriter) -> None:
    try:
        writer.close()
        await writer.wait_closed()
    except (OSError, asyncio.CancelledError, RuntimeError):
        pass
