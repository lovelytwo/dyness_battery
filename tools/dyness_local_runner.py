#!/usr/bin/env python3
"""Run the local logger listener outside Home Assistant.

    python3 tools/dyness_local_runner.py --port 15005                      # endpoint
    python3 tools/dyness_local_runner.py --mode passthru --upstream 47.254.174.207
    python3 tools/dyness_local_runner.py --trace /tmp/dyness_trace.log    # JSON trace

Prints one line per completed upload cycle. Needs Python 3.9+, no packages.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
import types
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "dyness_battery"
stub = types.ModuleType("dyness_battery")
stub.__path__ = [str(PACKAGE_DIR)]  # type: ignore[attr-defined]
sys.modules.setdefault("dyness_battery", stub)

from dyness_battery.local.listener import MODE_ENDPOINT, MODE_PASSTHRU, LoggerListener  # noqa: E402
from dyness_battery.local.responder import PATH_POWER, local_response  # noqa: E402
from dyness_battery.local.store import LocalStore  # noqa: E402
from dyness_battery.local.trace import Trace  # noqa: E402


async def main(args) -> None:
    store = LocalStore()
    trace = None
    if args.trace:
        trace = Trace(Path(args.trace), "runner")
        trace.open()

    def on_update() -> None:
        power = local_response(
            store, PATH_POWER, {}, now=time.time(), device_model="", capacity_total=None, n_modules=1,
        ).get("data") or {}
        print(
            f"cycle {store.cycles_completed}: bank={store.bank_sn} boards={len(store.boards)} "
            f"soc={power.get('soc')} power={power.get('realTimePower')} W "
            f"createTime={power.get('createTime')}",
            flush=True,
        )

    def on_upstream(ok: bool, failures: int, error) -> None:
        print(f"upstream {'ok' if ok else f'failed x{failures}: {error}'}", flush=True)

    listener = LoggerListener(
        store, args.mode, bind_host=args.bind, port=args.port,
        upstream_host=args.upstream, upstream_port=args.upstream_port,
        fallback_to_endpoint=args.fallback, trace=trace,
        on_update=on_update, on_upstream=on_upstream,
    )
    await listener.start()
    try:
        await asyncio.Event().wait()
    finally:
        await listener.stop()
        if trace:
            trace.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=[MODE_ENDPOINT, MODE_PASSTHRU], default=MODE_ENDPOINT)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--upstream", help="upstream host for passthru (IPv4 or hostname)")
    parser.add_argument("--upstream-port", type=int, default=5005)
    parser.add_argument("--fallback", action="store_true", help="answer locally when upstream is down")
    parser.add_argument("--trace", help="write the JSON trace to this file")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        pass
