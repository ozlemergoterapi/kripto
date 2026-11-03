import logging
import threading
import time
from dataclasses import asdict

from .indicators import returns
from .market import BinancePublic, MarketError
from .reporting import metrics, reports
from .risk import PaperBook
from .strategy import analyze

log = logging.getLogger(__name__)


class Engine:
    def __init__(self, config, store, market=None):
        self.config, self.store = config, store
        self.market = market or BinancePublic(config)
        self.book = PaperBook(config, store.load())
        self.store.version(config)
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.running = False  # Intentionally not persisted: explicit Start after every restart.
        self.safe_reason = "İlk güncel veri bekleniyor"
        self.pending_exit = False
        self.started_at = time.time()
        self.quotes = {}
        self.last_data = 0.0
        self.scan = {"at": None, "done": 0, "total": 0, "errors": 0, "active": False}
        self.universe = {}
        self.rate = None
        self.rate_error = "Kur henüz alınmadı"
        self.error = None
        self.latest_candidates = []
        self.threads = []
        self.funding_checked_at = 0.0
        self.event("INFO", "SİMÜLASYON açıldı; gerçek emir özelliği bulunmuyor. Başlat onayı bekleniyor.")

    def event(self, level, message):
        log.info("%s: %s", level, message)
        self.store.event(time.time(), level, message)

    def start_workers(self):
        for target in (self._quotes_loop, self._scan_loop, self._watchdog_loop):
            t = threading.Thread(target=target, daemon=True)
            t.start()
            self.threads.append(t)

    def shutdown(self):
        self.stop_event.set()
        with self.lock:
            self.running = False
            self.store.save(self.book)
        for thread in self.threads:
            thread.join(timeout=8)

    def control(self, action):
        with self.lock:
            now = time.time()
            if action == "start":
                if (self.safe_reason or now - self.last_data > self.config.stale_seconds
                        or self.pending_exit or self.book.daily_locked):
                    return False, "Başlatılamadı: güncel veri, güvenlik ve günlük risk koşullarını kontrol et."
                self.running = True
                self.event("INFO", "Simülasyon işlemleri kullanıcı tarafından başlatıldı.")
            elif action == "pause":
                self.running = False
                self.event("INFO", "Yeni girişler durduruldu; mevcut pozisyon yönetimi sürüyor.")
            elif action == "emergency":
                self.running = False
                self.pending_exit = True
                self.safe_reason = "Acil durdurma — açık pozisyonların çıkışı bekleniyor"
                self.book.manage(self.quotes, now, "EMERGENCY")
                self.pending_exit = bool(self.book.positions)
                self.store.save(self.book)
                self.event("WARN", "Acil durdurma uygulandı; eski fiyattan çıkış yapılmadı.")
            else:
                return False, "Bilinmeyen komut"
            return True, "Komut uygulandı"

    def _trip(self, reason):
        self.running = False
        self.pending_exit = bool(self.book.positions)
        if self.safe_reason != reason:
            self.event("ERROR", reason)
        self.safe_reason = reason

    def ingest(self, quotes, now):
        """One atomic paper-account tick; exposed for deterministic integration tests."""
        with self.lock:
            good = {s: q for s, q in quotes.items() if q.valid() and
                    -2 <= now - q.observed_at <= self.config.stale_seconds}
            missing = set(self.book.positions) - set(good)
            self.quotes = good
            if not good or missing:
                self._trip("SAFE_MODE: güncel fiyat eksik; çıkış için geçerli veri bekleniyor")
                self.book.manage(good, now, "DATA_LOSS")
                self.pending_exit = bool(self.book.positions)
                self.store.save(self.book)
                return
            self.last_data = min(q.observed_at for q in good.values())
            if self.pending_exit:
                self.book.manage(good, now, "SAFETY_EXIT")
                self.pending_exit = bool(self.book.positions)
            # Daily limit checks precede ordinary TP handling and include open P&L/costs.
            self.book.enforce_daily(good, now)
            if self.book.daily_locked:
                self.running = False
                self.safe_reason = "Günlük %6 zarar sınırı — gün değişimi ve Başlat onayı bekleniyor"
            else:
                self.book.manage(good, now)
                self.book.enforce_daily(good, now)
                self.safe_reason = "" if not self.pending_exit else "Çıkış bekleniyor"
            self.store.save(self.book)

    def check_stale(self, now):
        with self.lock:
            if not self.last_data and now - self.started_at < self.config.stale_seconds:
                return
            if now - self.last_data >= self.config.stale_seconds:
                self._trip("SAFE_MODE: 15 saniyedir güncel veri yok; " +
                           ("pozisyon çıkışı bekleniyor" if self.book.positions else "yeni girişler durduruldu"))
                self.store.save(self.book)

    def _watchdog_loop(self):
        while not self.stop_event.wait(1):
            if time.time() - self.started_at >= self.config.stale_seconds:
                self.check_stale(time.time())

    def _funding(self):
        with self.lock:
            recent = list(self.book.positions.values()) + [p for p in self.book.closed if
                                                          time.time() - p.closed_at < 120]
            positions = list({(p.symbol, p.opened_at) for p in recent})
        now = time.time()
        for symbol, opened in positions:
            rows = self.market.funding_history(symbol, int(opened * 1000), int(now * 1000))
            with self.lock:
                for row in rows:
                    mark = float(row.get("markPrice", 0))
                    if mark <= 0:
                        raise MarketError("Funding mark fiyatı eksik")
                    self.book.apply_funding(symbol, int(row["fundingTime"]) / 1000,
                                            float(row["fundingRate"]), mark, now)
                self.store.save(self.book)
        self.funding_checked_at = now

    def _quotes_loop(self):
        clock_at = rate_at = 0.0
        retry_delay = 2
        while not self.stop_event.is_set():
            try:
                now = time.time()
                if now - clock_at >= 300:
                    self.market.sync_clock()
                    clock_at = time.time()
                self.ingest(self.market.quotes(), time.time())
                self.error = None
                retry_delay = 2
                if now - self.funding_checked_at > 30:
                    try:
                        self._funding()
                    except Exception:
                        with self.lock:
                            self._trip("SAFE_MODE: funding maliyeti doğrulanamadı; çıkış bekleniyor")
                        raise
                if now - rate_at > 60:
                    rate_at = now
                    try:
                        rate = self.market.try_rate()
                        with self.lock:
                            self.rate, self.rate_error = rate, None
                    except MarketError as e:
                        self.rate_error = str(e)
            except Exception as e:
                # Do not hide an unexpected programming error behind a healthy status.
                message = str(e) if isinstance(e, MarketError) else f"Beklenmeyen hata: {type(e).__name__}"
                with self.lock:
                    if self.error != message:
                        if isinstance(e, MarketError):
                            log.warning("%s", message)
                        else:
                            log.exception("Data loop failed")
                        self.event("ERROR", message)
                    self.error = message
                    if not isinstance(e, MarketError):
                        self._trip(message)
                self.check_stale(time.time())
                retry_delay = min(30, retry_delay * 2)
            self.stop_event.wait(retry_delay)

    def _scan_loop(self):
        next_scan = 0
        while not self.stop_event.is_set():
            if time.time() < next_scan:
                self.stop_event.wait(1)
                continue
            with self.lock:
                ready = self.last_data and time.time() - self.last_data < self.config.stale_seconds
                quotes = dict(self.quotes)
            if not ready:
                self.stop_event.wait(2)
                continue
            started = time.time()
            next_scan = (int(started) // self.config.scan_seconds + 1) * self.config.scan_seconds
            try:
                universe = self.market.universe(quotes)
                with self.lock:
                    self.universe = universe
                    self.scan = {"at": started, "done": 0, "total": len(universe), "errors": 0, "active": True}
                    self.latest_candidates = []
                for symbol, metadata in universe.items():
                    if self.stop_event.is_set():
                        break
                    try:
                        frames = {}
                        for tf in self.config.timeframes:
                            frames[tf] = self.market.candles(symbol, tf)
                            if self.stop_event.wait(.22):
                                break
                        if self.stop_event.is_set():
                            break
                        signal = analyze(symbol, frames, time.time(), self.config)
                        if signal:
                            with self.lock:
                                self.latest_candidates.append(signal.record())
                                if not self.store.signal_exists(signal.id):
                                    reason = "İşlemler kullanıcı tarafından başlatılmadı"
                                    q = self.quotes.get(symbol)
                                    if (self.running and not self.safe_reason and q and
                                            time.time() - self.funding_checked_at < 60):
                                        reason = self.book.open(signal, q, time.time(), metadata["filters"], returns(frames["15m"]))
                                    self.store.save(self.book, [signal])
                                    self.event("INFO", f"{symbol} {signal.side} {signal.score}/100: " +
                                               (reason or "SİMÜLASYON pozisyonu açıldı"))
                    except Exception as e:
                        with self.lock:
                            self.scan["errors"] += 1
                        log.exception("Scan error for %s", symbol)
                        self.event("WARN", f"{symbol}: analiz yapılmadı ({type(e).__name__})")
                    with self.lock:
                        self.scan["done"] += 1
                if time.time() > next_scan:
                    self.event("WARN", "Tarama 5 dakikalık bütçeyi aştı; gecikmiş tur tekrar oynatılmayacak.")
                    next_scan = (int(time.time()) // 300 + 1) * 300
            except Exception as e:
                log.exception("Universe scan failed")
                self.event("ERROR", f"Piyasa listesi alınamadı: {type(e).__name__}")
            finally:
                with self.lock:
                    self.scan["active"] = False

    def view(self):
        with self.lock:
            now = time.time()
            age = now - self.last_data if self.last_data else None
            status = "SAFE_MODE" if self.safe_reason or age is None or age > self.config.stale_seconds else ("RUNNING" if self.running else "PAUSED")
            equity = self.book.last_equity
            return {"mode": "SİMÜLASYON", "live_trading_available": False, "validated_strategy": False,
                    "status": status, "safe_reason": self.safe_reason, "error": self.error,
                    "pending_exit": self.pending_exit, "data_age_seconds": age,
                    "balance": self.book.balance, "equity": equity,
                    "daily_pnl": equity - self.book.daily_base,
                    "daily_loss_limit": self.book.daily_base * self.config.daily_loss,
                    "daily_locked": self.book.daily_locked, "open_risk": self.book.open_risk(),
                    "rate": self.rate, "rate_error": self.rate_error,
                    "rate_stale": not self.rate or now - self.rate["at"] > 180,
                    "positions": [asdict(p) | {"quote": asdict(q) if (q := self.quotes.get(p.symbol)) else None,
                                               "net_if_closed": (p.net + p.direction * (self.book.exit_price(p, q) - p.entry) * p.remaining
                                                                 - self.book.exit_price(p, q) * p.remaining * self.config.fee) if q else None}
                                  for p in self.book.positions.values()],
                    "closed": [asdict(p) for p in reversed(self.book.closed[-100:])],
                    "metrics": metrics(self.book.closed, self.book.max_drawdown),
                    "reports": reports(self.book), "scan": dict(self.scan),
                    "universe_size": len(self.universe), "candidates": self.latest_candidates[-30:],
                    "events": self.store.events(), "config": asdict(self.config),
                    "config_hash": self.config.fingerprint, "server_time": now}
