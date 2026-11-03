"""Explicitly requested historical downloads only; resumable Parquet partitions."""
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import time

from .models import Candle


class Archive:
    def __init__(self, root):
        self.root = Path(root)

    def write(self, symbol, interval, candles):
        import pyarrow as pa
        import pyarrow.parquet as pq
        grouped = {}
        for c in candles:
            if not c.valid():
                raise ValueError("Geçersiz mum arşivlenemez")
            month = datetime.fromtimestamp(c.open_time / 1000, timezone.utc).strftime("%Y-%m")
            grouped.setdefault(month, []).append(asdict(c))
        for month, rows in grouped.items():
            path = self.root / symbol / interval / f"{month}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            existing = pq.read_table(path).to_pylist() if path.exists() else []
            merged = {r["open_time"]: r for r in existing}
            for r in rows:
                if r["open_time"] in merged and merged[r["open_time"]] != r:
                    raise ValueError("Arşivde çelişen mum: sessizce üzerine yazılmaz")
                merged[r["open_time"]] = r
            temporary = path.with_suffix(".tmp")
            pq.write_table(pa.Table.from_pylist([merged[k] for k in sorted(merged)]), temporary, compression="zstd")
            temporary.replace(path)

    def read(self, symbol, interval):
        import pyarrow.parquet as pq
        result = []
        for path in sorted((self.root / symbol / interval).glob("*.parquet")):
            result.extend(Candle(**r) for r in pq.read_table(path).to_pylist())
        return result


def download(market, archive, symbol, interval, start_ms, end_ms):
    from .market import INTERVAL_MS
    step = INTERVAL_MS[interval]
    cursor = start_ms
    total = 0
    while cursor < end_ms:
        bars = market.candles(symbol, interval, now=end_ms / 1000, start_ms=cursor, limit=1000)
        if not bars:
            break
        archive.write(symbol, interval, bars)
        cursor = bars[-1].open_time + step
        total += len(bars)
        print(f"{symbol} {interval}: {total} mum", flush=True)
        time.sleep(.25)
    return total
