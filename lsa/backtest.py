"""Conservative fixed-universe research replay; never certifies a trading strategy."""
from bisect import bisect_left
from dataclasses import replace
import hashlib
import json

from .indicators import returns
from .market import INTERVAL_MS
from .models import Quote
from .reporting import metrics
from .risk import PaperBook
from .strategy import analyze


def partitions(start, end, warmup_days=365):
    """Three chronological evaluation folds and an untouched final six-month holdout."""
    day = 86400
    if end - start < 730 * day:
        raise ValueError("24 aylık kapsam sağlanmıyor")
    train_end = start + warmup_days * day
    holdout_start = end - 183 * day
    if holdout_start <= train_end:
        raise ValueError("Walk-forward için süre yetersiz")
    width = (holdout_start - train_end) / 3
    folds = [{"name": f"walk-forward-{i+1}", "train_start": start,
              "train_end": train_end + i * width,
              "test_start": train_end + i * width,
              "test_end": train_end + (i + 1) * width} for i in range(3)]
    return folds + [{"name": "holdout", "train_start": start, "train_end": holdout_start,
                     "test_start": holdout_start, "test_end": end}]


def acceptance(result, coverage_days, funding_complete=False, historical_universe=False):
    m = result
    criteria = {"coverage_24_months": coverage_days >= 730, "at_least_300_trades": m["trades"] >= 300,
                "positive_expectancy": m["expectancy_r"] is not None and m["expectancy_r"] > 0,
                "profit_factor_1_2": m["profit_factor"] is not None and m["profit_factor"] >= 1.2,
                "drawdown_under_15pct": m["max_drawdown"] is not None and m["max_drawdown"] <= .15,
                "actual_funding_included": funding_complete,
                "point_in_time_universe": historical_universe}
    return {"checks": criteria, "passed": all(criteria.values()),
            "strategy_validated": False, "note": "Tek replay yeterli değildir; bağımsız holdout, maliyet stresi ve veri denetimi gerekir."}


def replay(archive, symbols, config, start, end, spread=.0004):
    """OHLC simulation with adverse-first intrabar ordering, fixed selected symbols.

    Historical spread is an assumption, not measured order-book data. Missing funding
    and point-in-time universe explicitly prevent a validation claim.
    """
    frames = {s: {tf: archive.read(s, tf) for tf in ("1m", *config.timeframes)} for s in symbols}
    for symbol, data in frames.items():
        for tf, bars in data.items():
            if len(bars) < 220 or any(not b.valid() for b in bars):
                raise ValueError(f"Yetersiz/geçersiz veri: {symbol}/{tf}")
            if any(b.open_time - a.open_time != INTERVAL_MS[tf] for a, b in zip(bars, bars[1:])):
                raise ValueError(f"Veri boşluğu: {symbol}/{tf}")
    times = {s: {tf: [b.close_time for b in bars] for tf, bars in data.items()} for s, data in frames.items()}
    timeline = {}
    for symbol in symbols:
        for bar in frames[symbol]["1m"]:
            if start <= bar.open_time / 1000 < end:
                timeline.setdefault(bar.open_time / 1000, {})[symbol] = bar
    book = PaperBook(config)
    seen = set()
    rejected = {}
    last_quotes = {}
    for now, current in sorted(timeline.items()):
        def quote(symbol, price, stamp):
            return Quote(symbol, price * (1 - spread / 2), price * (1 + spread / 2), stamp)
        opens = {s: quote(s, b.open, now) for s, b in current.items()}
        if set(book.positions) - set(opens):
            raise ValueError("Açık pozisyon için tarihsel fiyat eksik")
        book.roll_day(now, book.equity(opens))
        book.enforce_daily(opens, now)
        for symbol in sorted(current) if int(now) % config.scan_seconds == 0 else ():
            visible = {}
            for tf, bars in frames[symbol].items():
                i = bisect_left(times[symbol][tf], int(now * 1000))
                visible[tf] = bars[max(0, i - 260):i]
            signal = analyze(symbol, visible, now, config)
            if signal and signal.id not in seen:
                seen.add(signal.id)
                filters = {"LOT_SIZE": {"stepSize": "0.000001", "minQty": "0.000001"}, "MIN_NOTIONAL": {"notional": "5"}}
                reason = book.open(signal, opens[symbol], now, filters, returns(visible["15m"]))
                if reason:
                    rejected[reason] = rejected.get(reason, 0) + 1
        stamp = now + 59.999
        # Conservative: adverse excursion first, then favorable, then adverse again
        # to avoid assuming TP1 can move a stop without a possible retracement.
        adverse = {s: quote(s, b.low if s not in book.positions or book.positions[s].side == "LONG" else b.high, stamp)
                   for s, b in current.items()}
        favorable = {s: quote(s, b.high if s not in book.positions or book.positions[s].side == "LONG" else b.low, stamp)
                     for s, b in current.items()}
        for quotes in (adverse, favorable, adverse):
            book.enforce_daily(quotes, stamp)
            book.manage(quotes, stamp)
        last_quotes = {s: quote(s, b.close, stamp) for s, b in current.items()}
        book.enforce_daily(last_quotes, stamp)
    if last_quotes:
        book.manage(last_quotes, max(timeline) + 59.999, "DATA_END")
    result = metrics(book.closed, book.max_drawdown)
    identity = hashlib.sha256(json.dumps({"symbols": symbols, "start": start, "end": end,
                                         "config": config.fingerprint, "spread": spread}, sort_keys=True).encode()).hexdigest()[:16]
    return {"run_id": identity, "config_hash": config.fingerprint, "start": start, "end": end,
            "symbols": symbols, "spread_assumption": spread, "metrics": result, "rejected": rejected,
            "limitations": ["Funding henüz replay'e bağlanmadı; doğrulama engeli.",
                            "Sabit coin listesi: geçmişe dönük likidite evreni yok.",
                            "Geçmiş spread varsayımı ve yaklaşık miktar filtresi kullanılır.",
                            "1dk OHLC: mum içi sıra bilinmez; kötümser sıra uygulanır.",
                            "Likidasyon, tam emir defteri ve gerçek emir gerçekleşmeleri modellenmez."],
            "acceptance": acceptance(result, (end - start) / 86400)}


def walk_forward(archive, symbols, config, start, end):
    runs = []
    for fold in partitions(start, end):
        baseline = replay(archive, symbols, config, fold["test_start"], fold["test_end"])
        stressed = replay(archive, symbols, replace(config, slippage=config.slippage * 2),
                          fold["test_start"], fold["test_end"], spread=.0008)
        runs.append({"fold": fold, "baseline": baseline, "cost_stress": stressed})
    return {"runs": runs, "strategy_validated": False,
            "note": "Sabit kurallar; fold sınırları optimizasyonda kullanılmaz. Holdout sonrası parametre değişirse yeni holdout gerekir."}
