"""Read-only public HTTP adapter. No order/account API exists in this project."""
import json
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import Candle, Quote

INTERVAL_MS = {"1m": 60000, "3m": 180000, "5m": 300000, "15m": 900000, "30m": 1800000,
               "1h": 3600000, "4h": 14400000, "1d": 86400000}


class MarketError(RuntimeError):
    pass


class BinancePublic:
    def __init__(self, config):
        self.config = config
        self.clock_offset = None
        self.blocked_until = 0.0

    def get(self, path, params=None, spot=False):
        if time.time() < self.blocked_until:
            raise MarketError("Binance hız sınırı: bekleme etkin")
        host = "https://api.binance.com" if spot else "https://fapi.binance.com"
        url = host + path + ("?" + urlencode(params) if params else "")
        try:
            req = Request(url, headers={"User-Agent": "LSA-Paper/0.1"})
            with urlopen(req, timeout=6, context=ssl.create_default_context()) as response:
                return json.load(response)
        except HTTPError as e:
            if e.code in (418, 429):
                try:
                    wait = max(60, int(e.headers.get("Retry-After", "60")))
                except ValueError:
                    wait = 120
                self.blocked_until = time.time() + wait
            raise MarketError(f"Public veri HTTP {e.code}: {path}") from e
        except (URLError, TimeoutError, OSError, ValueError) as e:
            raise MarketError(f"Public veri alınamadı: {path} ({type(e).__name__})") from e

    def sync_clock(self):
        before = time.time()
        server = self.get("/fapi/v1/time")["serverTime"] / 1000
        after = time.time()
        offset = server - (before + after) / 2
        if after - before > 5 or abs(offset) > 5:
            raise MarketError("Saat farkı veya ağ gecikmesi güvenli sınırı aşıyor")
        self.clock_offset = offset

    def quotes(self):
        rows = self.get("/fapi/v1/ticker/bookTicker")
        now = time.time()
        result = {}
        for row in rows:
            # Binance event time, not the HTTP response arrival, establishes freshness.
            stamp = float(row.get("time", 0)) / 1000 - (self.clock_offset or 0)
            q = Quote(row["symbol"], float(row["bidPrice"]), float(row["askPrice"]), stamp)
            if q.valid() and -2 <= now - stamp <= self.config.stale_seconds:
                result[q.symbol] = q
        if not result:
            raise MarketError("Güncel ve geçerli alış/satış verisi yok")
        return result

    def universe(self, quotes):
        info = self.get("/fapi/v1/exchangeInfo")
        eligible = {r["symbol"]: r for r in info["symbols"]
                    if r["status"] == "TRADING" and r["quoteAsset"] == "USDT"
                    and r["marginAsset"] == "USDT" and r["contractType"] == "PERPETUAL"}
        tickers = self.get("/fapi/v1/ticker/24hr")
        ranked = sorted(tickers, key=lambda r: float(r["quoteVolume"]), reverse=True)
        result = {}
        for r in ranked:
            s = r["symbol"]
            if (s in eligible and s in quotes and quotes[s].spread <= self.config.max_spread
                    and float(r["quoteVolume"]) >= self.config.min_quote_volume):
                filters = {f["filterType"]: f for f in eligible[s]["filters"]}
                result[s] = {"quote_volume": float(r["quoteVolume"]), "filters": filters}
                if len(result) >= self.config.max_symbols:
                    break
        return result

    def candles(self, symbol, interval, now=None, start_ms=None, limit=260):
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_ms is not None:
            params["startTime"] = start_ms
        rows = self.get("/fapi/v1/klines", params)
        local_now = time.time()
        # Conservative clock boundary: do not admit the current exchange candle
        # when the local clock is slightly ahead of Binance.
        cutoff = int((now if now is not None else min(local_now, local_now + (self.clock_offset or 0) - 1)) * 1000)
        candles = [Candle(int(r[0]), int(r[6]), *map(float, r[1:6])) for r in rows if int(r[6]) < cutoff]
        if any(not c.valid() for c in candles):
            raise MarketError(f"Geçersiz OHLCV: {symbol}/{interval}")
        step = INTERVAL_MS[interval]
        if any(b.open_time - a.open_time != step for a, b in zip(candles, candles[1:])):
            raise MarketError(f"Eksik/tekrarlı mum: {symbol}/{interval}")
        return candles

    def funding(self):
        rows = self.get("/fapi/v1/premiumIndex")
        return {r["symbol"]: {"rate": float(r["lastFundingRate"]),
                              "next_time": int(r["nextFundingTime"]) / 1000,
                              "mark": float(r["markPrice"])} for r in rows}

    def funding_history(self, symbol, start_ms, end_ms):
        rows = self.get("/fapi/v1/fundingRate", {"symbol": symbol, "startTime": start_ms,
                                               "endTime": end_ms, "limit": 1000})
        return rows

    def try_rate(self):
        row = self.get("/api/v3/ticker/price", {"symbol": "USDTTRY"}, spot=True)
        price = float(row["price"])
        if price <= 0:
            raise MarketError("Geçersiz USDT/TRY kuru")
        return {"value": price, "at": time.time(), "source": "Binance spot USDT/TRY"}
