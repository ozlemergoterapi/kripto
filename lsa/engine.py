import logging
import threading
import time
from dataclasses import asdict

from .indicators import returns
from .market import BinancePublic, MarketError
from .market import INTERVAL_MS
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
        self.frames = {}
        self.frame_versions = {}
        self.dirty_symbols = set()
        self.pending_signals = {}
        self.entered_ids = {f["signal_id"] for f in self.book.fills if f["reason"] == "ENTRY"}
        from .stream import ClosedCandleStreams
        self.streams = ClosedCandleStreams(self)
        self.event("INFO", "SİMÜLASYON açıldı; gerçek emir özelliği bulunmuyor. Başlat onayı bekleniyor.")

    def event(self, level, message):
        log.info("%s: %s", level, message)
        self.store.event(time.time(), level, message)

    def start_workers(self):
        self.streams.start()
        for target in (self._quotes_loop, self._scan_loop, self._watchdog_loop, self._analysis_loop, self._maintenance_loop):
            t = threading.Thread(target=target, daemon=True)
            t.start()
            self.threads.append(t)

    def shutdown(self):
        self.stop_event.set()
        with self.lock:
            self.running = False
            self.store.save(self.book)
        for thread in self.threads + self.streams.threads:
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
            # Global feed health follows the newest verified exchange event.
            # An unrelated illiquid symbol must not age the entire feed.
            # Position prices are still checked independently below / by watchdog.
            self.last_data = max(q.observed_at for q in good.values())
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
                self._evaluate_pending(now)
            self.store.save(self.book)

    def cache_snapshot(self, symbol, frames):
        """Merge REST warmup with any newer stream candles received during download."""
        with self.lock:
            cached = self.frames.setdefault(symbol, {})
            for tf, bars in frames.items():
                merged = {b.open_time: b for b in bars}
                merged.update({b.open_time: b for b in cached.get(tf, [])})
                cached[tf] = [merged[k] for k in sorted(merged)][-260:]
            self.frame_versions[symbol] = self.frame_versions.get(symbol, 0) + 1
            self.dirty_symbols.add(symbol)

    def on_closed_candle(self, symbol, tf, candle):
        with self.lock:
            if symbol not in self.universe or tf not in self.config.timeframes:
                return
            bars = self.frames.setdefault(symbol, {}).setdefault(tf, [])
            duplicate = next((b for b in bars if b.open_time == candle.open_time), None)
            if duplicate is not None:
                if duplicate != candle:
                    self.frames[symbol] = {}
                    self.frame_versions[symbol] = self.frame_versions.get(symbol, 0) + 1
                    self.dirty_symbols.add(symbol)
                    self.event("ERROR", f"{symbol}: çelişen kapanmış mum; REST mutabakatı bekleniyor.")
                return
            bars.append(candle)
            bars.sort(key=lambda b: b.open_time)
            del bars[:-260]
            self.frame_versions[symbol] = self.frame_versions.get(symbol, 0) + 1
            self.dirty_symbols.add(symbol)

    def _analyze_cached(self, symbol, now):
        with self.lock:
            frames = {tf: list(bars) for tf, bars in self.frames.get(symbol, {}).items()}
            revision = self.frame_versions.get(symbol, 0)
        signal = analyze(symbol, frames, now, self.config)
        with self.lock:
            if revision != self.frame_versions.get(symbol, 0):
                self.dirty_symbols.add(symbol)
                return
            # A new closed-bar decision supersedes the previous pending plan.
            for id in [k for k, v in self.pending_signals.items() if v["signal"].symbol == symbol
                       and (signal is None or k != signal.id)]:
                del self.pending_signals[id]
            if signal is None or signal.id in self.entered_ids:
                return
            if signal.id not in self.pending_signals:
                self.pending_signals[signal.id] = {"signal": signal, "returns": returns(frames["15m"]),
                                                   "attempted_at": None, "last_reason": None,
                                                   "revision": revision}
                self.latest_candidates = [c for c in self.latest_candidates if c["symbol"] != symbol]
                self.latest_candidates.append(signal.record())
                self.store.save(self.book, [signal])
                self.event("INFO", f"{symbol} {signal.side}: giriş adayı canlı fiyat takibine alındı.")
            else:
                self.pending_signals[signal.id]["revision"] = revision
                self.pending_signals[signal.id]["returns"] = returns(frames["15m"])

    def _analysis_loop(self):
        while not self.stop_event.wait(.25):
            with self.lock:
                dirty = sorted(self.dirty_symbols)
                self.dirty_symbols.clear()
            for symbol in dirty:
                try:
                    self._analyze_cached(symbol, time.time())
                except Exception:
                    log.exception("Cached analysis failed: %s", symbol)
                    with self.lock:
                        for id in [k for k, v in self.pending_signals.items() if v["signal"].symbol == symbol]:
                            del self.pending_signals[id]
                    self.event("ERROR", f"{symbol}: canlı mum analizi başarısız; aday iptal edildi.")

    def _evaluate_pending(self, now):
        # Called under the account lock after exits and equity/daily checks.
        for id, item in list(self.pending_signals.items()):
            signal = item["signal"]
            if now > signal.expires_at or id in self.entered_ids or signal.symbol not in self.universe:
                del self.pending_signals[id]
                continue
            if not self.running or self.safe_reason or self.pending_exit or self.book.daily_locked:
                continue
            if now - self.funding_checked_at >= 60:
                continue
            frames = self.frames.get(signal.symbol, {})
            if item["revision"] != self.frame_versions.get(signal.symbol, 0):
                continue
            if any(not frames.get(tf) or now * 1000 - frames[tf][-1].close_time > INTERVAL_MS[tf] + 15000
                   or any(b.open_time - a.open_time != INTERVAL_MS[tf] for a, b in zip(frames[tf], frames[tf][1:]))
                   for tf in self.config.timeframes):
                continue
            q = self.quotes.get(signal.symbol)
            if not q or item["attempted_at"] == q.observed_at:
                continue
            item["attempted_at"] = q.observed_at
            reason = self.book.open(signal, q, now, self.universe[signal.symbol]["filters"], item["returns"])
            if reason is None:
                self.entered_ids.add(id)
                del self.pending_signals[id]
                self.book.enforce_daily(self.quotes, now)
                self.event("INFO", f"{signal.symbol} {signal.side}: canlı fiyat koşullarıyla SİMÜLASYON açıldı.")
            elif reason != item["last_reason"]:
                self.event("INFO", f"{signal.symbol}: giriş bekliyor — {reason}")
                item["last_reason"] = reason

    def check_stale(self, now):
        with self.lock:
            if not self.last_data and now - self.started_at < self.config.stale_seconds:
                return
            stale_positions = [s for s in self.book.positions if s not in self.quotes or
                               now - self.quotes[s].observed_at >= self.config.stale_seconds]
            if now - self.last_data >= self.config.stale_seconds or stale_positions:
                reason = ("pozisyon fiyatı güncel değil: " + ", ".join(stale_positions)
                          if stale_positions else "15 saniyedir güncel veri yok")
                self._trip("SAFE_MODE: " + reason + "; " +
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
        retry_delay = 2
        while not self.stop_event.is_set():
            try:
                now = time.time()
                if self.market.clock_offset is None:
                    self.market.sync_clock()
                self.ingest(self.market.quotes(), time.time())
                self.error = None
                retry_delay = 2
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

    def _maintenance_loop(self):
        # Funding / FX network calls must not block the price-management loop.
        clock_at = rate_at = 0.0
        while not self.stop_event.wait(1):
            now = time.time()
            try:
                if now - self.funding_checked_at > 30:
                    try:
                        self._funding()
                    except Exception:
                        with self.lock:
                            self._trip("SAFE_MODE: funding maliyeti doğrulanamadı; çıkış bekleniyor")
                        raise
                if now - clock_at > 300 and self.market.clock_offset is not None:
                    self.market.sync_clock()
                    clock_at = now
                if now - rate_at > 60:
                    rate_at = now
                    try:
                        rate = self.market.try_rate()
                        with self.lock:
                            self.rate, self.rate_error = rate, None
                    except MarketError as e:
                        self.rate_error = str(e)
            except Exception as e:
                log.exception("Maintenance failed")
                with self.lock:
                    self._trip(f"SAFE_MODE: bakım verisi doğrulanamadı ({type(e).__name__})")
                self.stop_event.wait(5)

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
                        self.cache_snapshot(symbol, frames)
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
                    "universe_size": len(self.universe),
                    "candidates": [v["signal"].record() for v in self.pending_signals.values()
                                   if v["signal"].expires_at >= now][-30:],
                    "entry_monitor": {"pending": len(self.pending_signals), "price_poll_seconds": 2,
                                      "candles": self.streams.status()},
                    "events": self.store.events(), "config": asdict(self.config),
                    "config_hash": self.config.fingerprint, "server_time": now}
