import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path

from .config import CONFIG


def timestamp(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()


def main():
    parser = argparse.ArgumentParser(description="LSA Trader — yalnızca simülasyon")
    parser.add_argument("--data-dir", default="data")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8765)
    for name in ("download", "backtest"):
        p = sub.add_parser(name)
        p.add_argument("--symbols", required=True, help="BTCUSDT,ETHUSDT")
        p.add_argument("--start", required=True, help="UTC YYYY-MM-DD")
        p.add_argument("--end", required=True, help="UTC YYYY-MM-DD (exclusive)")
        if name == "backtest":
            p.add_argument("--output", default="data/backtest.json")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.command == "serve":
        from .engine import Engine
        from .storage import Store
        from .web import make_server
        engine = Engine(CONFIG, Store(Path(args.data_dir) / "journal.sqlite"))
        server = make_server(engine, port=args.port)
        engine.start_workers()
        logging.info("LSA paneli loopback port %s üzerinde; gerçek emir özelliği yok", args.port)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
            engine.shutdown()
    else:
        from .history import Archive, download
        from .market import BinancePublic
        start, end = timestamp(args.start), timestamp(args.end)
        if end <= start:
            parser.error("end, start'tan sonra olmalı")
        symbols = args.symbols.split(",")
        if any(not s.isalnum() or not s.endswith("USDT") for s in symbols):
            parser.error("USDT sembolleri gerekli")
        archive = Archive(Path(args.data_dir) / "history")
        if args.command == "download":
            market = BinancePublic(CONFIG)
            market.sync_clock()
            for symbol in symbols:
                for tf in ("1m", *CONFIG.timeframes):
                    download(market, archive, symbol, tf, int(start * 1000), int(end * 1000))
        else:
            from .backtest import walk_forward
            result = walk_forward(archive, symbols, CONFIG, start, end)
            target = Path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
            print(f"Araştırma raporu: {target}. Strateji doğrulanmış değildir.")


if __name__ == "__main__":
    main()
