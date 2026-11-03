from dataclasses import asdict

from .patterns import compare_shapes
from .market import INTERVAL_MS


def entry_snapshot(position, signal, frames, quote, now):
    bars = [c for c in frames.get(position.timeframe, []) if c.close_time < now*1000][-120:]
    if not bars or any(not c.valid() for c in bars):
        raise ValueError("Giriş grafiği için geçerli kapanmış mum yok")
    return {"schema_version":1, "id":position.id, "symbol":position.symbol,
            "side":position.side, "timeframe":position.timeframe, "captured_at":now,
            "last_closed_at":bars[-1].close_time/1000,
            "candles":[asdict(c) for c in bars], "entry_quote":asdict(quote),
            "levels":{"entry":position.entry,"stop":position.original_stop,
                      "tp1":position.tp1,"tp2":position.tp2},
            "capital":position.capital_summary(), "leverage":position.leverage,
            "signal_reason":signal.reason, "strategy_version":signal.version,
            "pattern":compare_shapes(bars),
            "note":"Giriş anında bilinen kapanmış mumlar. Gelecekteki mumlar eklenmez; seviyeler sonradan değiştirilmez."}


def live_snapshot(position, bars, forming, quote, now, event_at, stale_seconds):
    closed=[c for c in bars if c.valid() and c.close_time < now*1000][-120:]
    candles=[asdict(c)|{"forming":False} for c in closed]
    if forming and forming.valid() and forming.open_time<=now*1000 and (not closed or forming.open_time>closed[-1].open_time):
        candles.append(asdict(forming)|{"forming":True})
    gap=any(b["open_time"]-a["open_time"]!=INTERVAL_MS[position.timeframe] for a,b in zip(candles,candles[1:]))
    quote_age=now-quote.observed_at if quote and quote.valid() else None
    candle_age=now-event_at if event_at else None
    return {"schema_version":1,"mode":"live","id":position.id,"symbol":position.symbol,
            "side":position.side,"timeframe":position.timeframe,"captured_at":position.opened_at,
            "updated_at":now,"last_closed_at":closed[-1].close_time/1000 if closed else None,
            "candles":candles,"levels":{"entry":position.entry,"stop":position.stop,
                                          "tp1":position.tp1,"tp2":position.tp2},
            "price":quote.mid if quote and quote.valid() else None,
            "quote_age_seconds":quote_age,"candle_age_seconds":candle_age,
            "price_stale":quote_age is None or not -2<=quote_age<=stale_seconds,
            "candles_stale":candle_age is None or not -2<=candle_age<=stale_seconds,
            "history_gap":gap,"capital":position.capital_summary(),"leverage":position.leverage,
            "signal_reason":"Canlı takip: hareket eden mum yalnızca görüntülenir; analiz kapanmış mumlarla yapılır.",
            "pattern":compare_shapes(closed),
            "note":"Açık mum kapanana kadar şekil değiştirebilir. Bu görünüm güncellenir; giriş anı kaydı ayrı saklanır."}
