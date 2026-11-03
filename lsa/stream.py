"""Public closed-kline stream. No account endpoints or API keys."""
import json
import logging
import threading
import time
from math import isfinite

from .market import INTERVAL_MS
from .models import Candle

log = logging.getLogger(__name__)


def kline_event(message, now):
    data = message.get("data", message)
    if data.get("e") != "kline":
        return None
    k = data.get("k", {})
    if type(k.get("x")) is not bool or k.get("i") not in INTERVAL_MS:
        return None
    candle = Candle(int(k["t"]), int(k["T"]), float(k["o"]), float(k["h"]),
                    float(k["l"]), float(k["c"]), float(k["v"]))
    closed = k["x"]
    if not candle.valid() or candle.open_time > now*1000+5000 or (closed and candle.close_time >= now * 1000):
        raise ValueError("Geçersiz veya henüz kapanmamış stream mumu")
    if candle.close_time - candle.open_time + 1 != INTERVAL_MS[k["i"]]:
        raise ValueError("Stream mum süresi geçersiz")
    event_at=float(data.get("E",0))/1000
    if not isfinite(event_at) or event_at<0 or event_at>now+5:
        raise ValueError("Stream olay zamanı geçersiz")
    return data["s"], k["i"], candle, closed, event_at


def closed_event(message, now):
    event = kline_event(message, now)
    return event[:3] if event and event[3] else None


class ClosedCandleStreams:
    """Three bounded connections, each <=420 subscriptions; automatic resubscribe."""
    def __init__(self, engine):
        self.engine = engine
        self.states = {}
        self.threads = []

    def start(self):
        for index in range(3):
            t = threading.Thread(target=self._run, args=(index,), daemon=True)
            t.start()
            self.threads.append(t)

    def _symbols(self, index):
        with self.engine.lock:
            symbols = set(self.engine.universe) | set(self.engine.book.positions)
            return tuple(sorted(symbols)[index * 60:(index + 1) * 60])

    def _run(self, index):
        from websockets.sync.client import connect
        while not self.engine.stop_event.is_set():
            symbols = self._symbols(index)
            if not symbols:
                self.engine.stop_event.wait(1)
                continue
            try:
                with connect("wss://fstream.binance.com/ws", open_timeout=8,
                             close_timeout=2, max_size=2_000_000) as ws:
                    channels = [f"{s.lower()}@kline_{tf}" for s in symbols for tf in self.engine.config.timeframes]
                    ws.send(json.dumps({"method": "SUBSCRIBE", "params": channels, "id": index + 1}))
                    self.states[index] = "connected"
                    self.engine.event("INFO", f"Mum akışı bağlandı: {len(symbols)} coin")
                    while not self.engine.stop_event.is_set() and self._symbols(index) == symbols:
                        try:
                            raw = ws.recv(timeout=1)
                        except TimeoutError:
                            continue
                        message = json.loads(raw)
                        if "code" in message:
                            raise ValueError("Binance stream aboneliği reddedildi")
                        event = kline_event(message, time.time())
                        if event:
                            self.engine.on_kline(*event)
            except Exception as e:
                self.states[index] = "disconnected"
                log.warning("Closed-candle stream: %s", type(e).__name__)
                self.engine.event("WARN", f"Mum akışı kesildi ({type(e).__name__}); yeni mum adayları veri tamamlanana kadar bekler.")
                self.engine.stop_event.wait(5)
            finally:
                self.states[index] = "disconnected"

    def status(self):
        active = sum(bool(self._symbols(i)) for i in range(3))
        return {"connected": sum(v == "connected" for v in list(self.states.values())), "required": active}
