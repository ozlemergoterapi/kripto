from math import sqrt


def ema(values, period):
    if len(values) < period:
        raise ValueError("EMA için veri yetersiz")
    result = sum(values[:period]) / period
    alpha = 2 / (period + 1)
    for value in values[period:]:
        result += alpha * (value - result)
    return result


def rsi(values, period=14):
    if len(values) <= period:
        raise ValueError("RSI için veri yetersiz")
    changes = [b - a for a, b in zip(values, values[1:])]
    gain = sum(max(0, c) for c in changes[:period]) / period
    loss = sum(max(0, -c) for c in changes[:period]) / period
    for c in changes[period:]:
        gain = (gain * (period - 1) + max(0, c)) / period
        loss = (loss * (period - 1) + max(0, -c)) / period
    if loss == 0:
        return 100.0 if gain else 50.0
    return 100 - 100 / (1 + gain / loss)


def atr(candles, period=14):
    if len(candles) <= period:
        raise ValueError("ATR için veri yetersiz")
    ranges = [max(c.high - c.low, abs(c.high - prev.close), abs(c.low - prev.close))
              for prev, c in zip(candles, candles[1:])]
    value = sum(ranges[:period]) / period
    for r in ranges[period:]:
        value = (value * (period - 1) + r) / period
    return value


def returns(candles):
    return {c.close_time: c.close / prev.close - 1 for prev, c in zip(candles, candles[1:])}


def correlation(a, b):
    common = sorted(set(a) & set(b))[-96:]
    if len(common) < 48:
        return None
    av, bv = [a[k] for k in common], [b[k] for k in common]
    am, bm = sum(av) / len(av), sum(bv) / len(bv)
    den = sqrt(sum((x - am)**2 for x in av) * sum((x - bm)**2 for x in bv))
    return sum((x - am) * (y - bm) for x, y in zip(av, bv)) / den if den else None
