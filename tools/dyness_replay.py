#!/usr/bin/env python3
"""Replay the logger side of a classic PCAP against a running endpoint listener.

    python3 tools/dyness_local_runner.py --port 15005 &
    python3 tools/dyness_replay.py reverse-engineering/captures/dyness.pcap --port 15005

For every logger frame it sends, it waits for the replies endpoint mode must
give (stop-and-wait, like the logger) and checks their opcodes. Frame bodies
are never printed; captures hold the logger's login credentials.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys
import types
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
stub = types.ModuleType("dyness_battery")
stub.__path__ = [str(ROOT / "custom_components" / "dyness_battery")]  # type: ignore[attr-defined]
sys.modules.setdefault("dyness_battery", stub)

from dyness_battery.local import protocol as p  # noqa: E402

EXPECTED = {
    p.OP_LOGIN: [p.OP_GREETING, p.OP_LOGIN],
    p.OP_TIME: [p.OP_TIME],
    p.OP_CONFIG: [p.OP_ACK_CONFIG],
    p.OP_UPLOAD: [p.OP_ACK_UPLOAD],
}


def load_decoder():
    spec = importlib.util.spec_from_file_location(
        "dyness_decode", ROOT / "reverse-engineering" / "dyness_decode.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def logger_sessions(pcap: Path):
    ref = load_decoder()
    for session in ref.session_groups(ref.parse_pcap(pcap)):
        for (_src, _sport, _dst, dport), packets in session["flows"].items():
            if dport == 5005:
                data, _, _ = ref.tcp_stream(packets)
                yield p.FrameBuffer().feed(data)


async def replay_session(frames, host: str, port: int, timeout: float, stats: Counter) -> None:
    reader, writer = await asyncio.open_connection(host, port)
    buffer = p.FrameBuffer()
    pending = []
    try:
        for frame in frames:
            expected = EXPECTED.get(frame.opcode, [])
            writer.write(frame.raw)
            await writer.drain()
            stats[f"sent {frame.opcode_hex}"] += 1
            got = []
            while len(got) < len(expected):
                if not pending:
                    try:
                        data = await asyncio.wait_for(reader.read(65536), timeout)
                    except asyncio.TimeoutError:
                        break
                    if not data:
                        break
                    pending.extend(buffer.feed(data))
                    continue
                got.append(pending.pop(0).opcode)
            if got == expected:
                stats["ok"] += 1
            else:
                stats["mismatch"] += 1
                print(f"frame {frame.opcode_hex}: expected {[o.hex() for o in expected]}, got {[o.hex() for o in got]}")
        try:
            extra = await asyncio.wait_for(reader.read(65536), 0.2)
        except asyncio.TimeoutError:
            extra = b""
        if pending or extra:
            stats["unexpected replies"] += len(pending) + len(buffer.feed(extra))
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except ConnectionError:
            pass


async def main(args) -> int:
    stats: Counter = Counter()
    sessions = list(logger_sessions(Path(args.pcap)))
    if args.sessions:
        sessions = sessions[: args.sessions]
    for frames in sessions:
        try:
            await replay_session(frames, args.host, args.port, args.timeout, stats)
        except ConnectionError as exc:
            stats["mismatch"] += 1
            print(f"listener closed the session: {exc}")
        stats["sessions"] += 1
    for key in sorted(stats):
        print(f"{key}: {stats[key]}")
    return 0 if stats["mismatch"] == 0 and stats["unexpected replies"] == 0 and stats["ok"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pcap")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--sessions", type=int, help="replay only the first N sessions")
    parser.add_argument("--timeout", type=float, default=3.0)
    sys.exit(asyncio.run(main(parser.parse_args())))
