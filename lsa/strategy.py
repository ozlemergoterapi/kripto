import hashlib

from .indicators import atr, ema, rsi
from .market import INTERVAL_MS
from .models import Signal


def analyze(symbol, frames, now, config):
    """Deterministic close-only v0.1 candidate selection, never a probability."""
    for interval in config.timeframes:
        bars = frames.get(interval, [])
        if len(bars) < 220 or any(not c.valid() or c.close_time >= now * 1000 for c in bars):
            return None
        step = INTERVAL_MS[interval]
        if now * 1000 - bars[-1].close_time > step + 15000:
            return None
        if any(b.open_time - a.open_time != step for a, b in zip(bars, bars[1:])):
            return None
    directions = []
    for interval in ("1h", "4h"):
        bars = frames[interval]
        closes = [c.close for c in bars]
        fast, slow = ema(closes, 50), ema(closes, 200)
        structure_up = bars[-1].close > max(c.high for c in bars[-6:-1]) or bars[-1].low > min(c.low for c in bars[-11:-6])
        structure_down = bars[-1].close < min(c.low for c in bars[-6:-1]) or bars[-1].high < max(c.high for c in bars[-11:-6])
        directions.append(1 if closes[-1] > fast > slow and structure_up else
                          -1 if closes[-1] < fast < slow and structure_down else 0)
    if not directions[0] or directions[0] != directions[1]:
        return None
    direction = directions[0]
    daily = frames["1d"]
    daily_bias = (daily[-1].close - ema([c.close for c in daily], 50)) * direction > 0
    candidates = []
    for tf in ("3m", "5m", "15m", "30m"):
        bars = frames[tf]
        last = bars[-1]
        # A slow scan cannot revive a historical trigger after its ten-minute lifetime.
        if now - last.close_time / 1000 > config.signal_ttl:
            continue
        closes = [c.close for c in bars]
        trend = ema(closes, 20)
        momentum = rsi(closes)
        volatility = atr(bars, config.atr_period)
        prior = bars[-21:-1]
        volume_ratio = last.volume / max(sum(c.volume for c in prior) / len(prior), 1e-12)
        breakout = (last.close > max(c.high for c in prior) if direction == 1 else
                    last.close < min(c.low for c in prior))
        pullback = (last.low <= trend < last.close and last.close > bars[-2].close if direction == 1 else
                    last.high >= trend > last.close and last.close < bars[-2].close)
        momentum_ok = 50 <= momentum <= 70 if direction == 1 else 30 <= momentum <= 50
        if not (breakout or pullback) or not momentum_ok or volume_ratio < 1.2 or volatility <= 0:
            continue
        score = 50 + (15 if breakout else 10) + (15 if volume_ratio >= 1.5 else 10) + (10 if daily_bias else 0) + 10
        if score < config.min_score:
            continue
        swing = min(c.low for c in bars[-6:]) if direction == 1 else max(c.high for c in bars[-6:])
        distance = max(config.min_stop_atr * volatility, abs(last.close - swing) + .1 * volatility)
        if distance > config.max_stop_atr * volatility:
            continue
        entry = last.close
        identity = f"{config.fingerprint}:{symbol}:{tf}:{last.close_time}:{direction}"
        signal = Signal(hashlib.sha256(identity.encode()).hexdigest()[:20], symbol,
                        "LONG" if direction == 1 else "SHORT", min(score, 100), tf,
                        last.close_time / 1000, last.close_time / 1000 + config.signal_ttl,
                        entry, entry - direction * distance, entry + direction * config.tp1_r * distance,
                        entry + direction * config.tp2_r * distance,
                        f"1sa/4sa EMA50/200 ve yapı uyumu; {tf} " +
                        ("kırılım" if breakout else "geri çekilme") +
                        f"; RSI {momentum:.1f}, hacim {volume_ratio:.2f}×; günlük yön " +
                        ("uyumlu" if daily_bias else "uyumsuz"), config.fingerprint, volatility)
        candidates.append(signal)
    return max(candidates, key=lambda s: (s.score, s.created_at)) if candidates else None
