from dataclasses import asdict

from .patterns import compare_shapes


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
