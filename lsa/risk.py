"""Paper fills only. This module cannot send an exchange order."""
from dataclasses import asdict, dataclass
from datetime import datetime
from math import ceil, floor, isfinite
from zoneinfo import ZoneInfo

from .indicators import correlation


def day_key(now):
    return datetime.fromtimestamp(now, ZoneInfo("Europe/Istanbul")).date().isoformat()


@dataclass
class Position:
    id: str
    symbol: str
    side: str
    timeframe: str
    entry: float
    stop: float
    original_stop: float
    tp1: float
    tp2: float
    quantity: float
    remaining: float
    opened_at: float
    initial_risk: float
    leverage: int
    margin: float
    net: float
    tp1_hit: bool = False
    closed_at: float | None = None
    exit_reason: str = ""
    tp2_hit: bool = False
    sl_hit: bool = False

    @property
    def direction(self):
        return 1 if self.side == "LONG" else -1


class PaperBook:
    def __init__(self, config, saved=None):
        self.config = config
        saved = saved or {}
        self.balance = saved.get("balance", config.initial_balance)
        self.positions = {k: Position(**v) for k, v in saved.get("positions", {}).items()}
        self.closed = [Position(**v) for v in saved.get("closed", [])]
        self.fills = saved.get("fills", [])
        self.funding_keys = set(saved.get("funding_keys", []))
        self.days = saved.get("days", {})
        self.day = saved.get("day", "")
        self.daily_base = saved.get("daily_base", config.initial_balance)
        self.daily_locked = saved.get("daily_locked", False)
        self.last_equity = saved.get("last_equity", self.balance)
        self.equity_peak = saved.get("equity_peak", self.balance)
        self.max_drawdown = saved.get("max_drawdown", 0.0)
        self.market_returns = saved.get("market_returns", {})
        # JSON object keys are strings after restart; normalize correlation timestamps.
        self.market_returns = {s: {int(k): v for k, v in r.items()} for s, r in self.market_returns.items()}

    def snapshot(self):
        return {"balance": self.balance, "positions": {k: asdict(p) for k, p in self.positions.items()},
                "closed": [asdict(p) for p in self.closed], "fills": self.fills,
                "funding_keys": sorted(self.funding_keys), "days": self.days, "day": self.day,
                "daily_base": self.daily_base, "daily_locked": self.daily_locked,
                "last_equity": self.last_equity, "equity_peak": self.equity_peak,
                "max_drawdown": self.max_drawdown, "market_returns": self.market_returns}

    def exit_price(self, p, quote):
        return quote.bid * (1 - self.config.slippage) if p.direction == 1 else quote.ask * (1 + self.config.slippage)

    def equity(self, quotes):
        value = self.balance
        for p in self.positions.values():
            q = quotes.get(p.symbol)
            if q is None or not q.valid():
                raise ValueError(f"Değerleme için fiyat eksik: {p.symbol}")
            price = self.exit_price(p, q)
            value += p.direction * (price - p.entry) * p.remaining - price * p.remaining * self.config.fee
        return value

    def roll_day(self, now, equity):
        day = day_key(now)
        if day != self.day:
            if self.day:
                self.days[self.day]["end_equity"] = equity
            self.day = day
            self.daily_base = equity
            self.daily_locked = False
            self.days[day] = {"start_equity": equity, "end_equity": equity, "fills": 0, "costs": 0.0}
        self.last_equity = equity
        self.equity_peak = max(self.equity_peak, equity)
        if self.equity_peak:
            self.max_drawdown = max(self.max_drawdown, 1 - equity / self.equity_peak)
        self.days[day]["end_equity"] = equity

    def open_risk(self):
        return sum(max(0, p.direction * (p.entry - p.stop) * p.remaining) +
                   (self.config.fee + self.config.slippage) * p.entry * p.remaining
                   for p in self.positions.values())

    def open(self, signal, quote, now, filters, return_series):
        c = self.config
        if signal.version != c.fingerprint:
            return "Strateji sürümü uyuşmuyor"
        if self.daily_locked:
            return "Günlük zarar kilidi"
        if now > signal.expires_at or now < signal.created_at:
            return "Sinyalin süresi geçersiz"
        if signal.symbol != quote.symbol or not quote.valid() or not -2 <= now - quote.observed_at <= c.stale_seconds:
            return "Güncel fiyat yok"
        if quote.spread > c.max_spread:
            return "Spread yüksek"
        if signal.symbol in self.positions or len(self.positions) >= c.max_positions:
            return "Pozisyon sınırı"
        if signal.side not in ("LONG", "SHORT") or not all(isfinite(x) and x > 0 for x in
                (signal.entry, signal.stop, signal.tp1, signal.tp2, signal.atr)):
            return "Geçersiz sinyal"
        direction = 1 if signal.side == "LONG" else -1
        entry = quote.ask * (1 + c.slippage) if direction == 1 else quote.bid * (1 - c.slippage)
        if abs(entry - signal.entry) > .25 * signal.atr:
            return "Giriş fiyatı kaçtı"
        if not (direction * (entry - signal.stop) > 0 and direction * (signal.tp1 - entry) > 0
                and direction * (signal.tp2 - signal.tp1) > 0):
            return "Stop/hedef sıralaması geçersiz"
        for p in self.positions.values():
            if p.side == signal.side:
                corr = correlation(return_series, self.market_returns.get(p.symbol, {}))
                if corr is None or corr >= c.correlation_limit:
                    return "Korelasyon yüksek veya veri yetersiz"
        stop_fill = signal.stop * (1 - direction * c.slippage)
        risk_per_unit = direction * (entry - stop_fill) + c.fee * (entry + stop_fill)
        budget = min(self.last_equity * c.trade_risk,
                     self.last_equity * c.portfolio_risk - self.open_risk(),
                     self.last_equity - self.daily_base * (1 - c.daily_loss))
        if budget <= 0:
            return "Risk bütçesi tükendi"
        if self.last_equity <= 0:
            return "Bakiye yetersiz"
        raw_qty = budget / risk_per_unit
        lot = filters.get("LOT_SIZE", {})
        step = float(lot.get("stepSize", 0))
        if step <= 0:
            return "Miktar filtresi eksik"
        # TP1 must be executable at the same quantity granularity.
        qty = floor(raw_qty / (2 * step)) * 2 * step
        qty = min(qty, floor(float(lot.get("maxQty", qty)) / (2 * step)) * 2 * step)
        notional = entry * qty
        minimum = float(filters.get("MIN_NOTIONAL", {}).get("notional", 5))
        if qty / 2 < float(lot.get("minQty", step)) or notional / 2 < minimum:
            return "Kısmi çıkış için minimum tutar/miktar sağlanmıyor"
        leverage = max(1, ceil(notional / (self.last_equity / c.max_positions)))
        if leverage > c.max_leverage:
            return "10× kaldıraç tavanı yetersiz"
        margin = notional / leverage
        used = sum(p.margin * p.remaining / p.quantity for p in self.positions.values())
        fee = notional * c.fee
        if margin + fee + used > self.last_equity:
            return "Kullanılabilir izole teminat yetersiz"
        # Conservative liquidation-distance guard; not an exchange liquidation model.
        if abs(entry - signal.stop) / entry + .01 >= 1 / leverage:
            return "Stop, tahmini likidasyon bölgesine yakın"
        p = Position(signal.id, signal.symbol, signal.side, signal.timeframe, entry, signal.stop,
                     signal.stop, signal.tp1, signal.tp2, qty, qty, now, qty * risk_per_unit,
                     leverage, margin, -fee)
        self.positions[p.symbol] = p
        self.market_returns[p.symbol] = return_series
        self.balance -= fee
        self._fill(p, now, "ENTRY", qty, entry, fee, 0)
        return None

    def _fill(self, p, now, reason, qty, price, fee, pnl):
        self.fills.append({"signal_id": p.id, "symbol": p.symbol, "at": now, "reason": reason,
                           "quantity": qty, "price": price, "fee": fee, "pnl": pnl})
        day = self.days.get(day_key(now))
        if day:
            day["fills"] += 1
            day["costs"] += fee

    def close(self, p, quote, now, reason, quantity=None):
        qty = min(p.remaining, quantity if quantity is not None else p.remaining)
        if qty <= 0:
            return
        price = self.exit_price(p, quote)
        fee = price * qty * self.config.fee
        pnl = p.direction * (price - p.entry) * qty - fee
        p.net += pnl
        self.balance += pnl
        p.remaining = max(0, p.remaining - qty)
        self._fill(p, now, reason, qty, price, fee, pnl)
        if p.remaining <= p.quantity * 1e-9:
            p.remaining = 0
            p.closed_at, p.exit_reason = now, reason
            p.tp2_hit = reason == "TP2"
            p.sl_hit = reason == "SL"
            self.closed.append(p)
            del self.positions[p.symbol]

    def apply_funding(self, symbol, timestamp, rate, mark, now):
        key = f"{symbol}:{timestamp}"
        p = self.positions.get(symbol)
        if p is None:
            p = next((t for t in reversed(self.closed) if t.symbol == symbol and
                      t.opened_at < timestamp <= (t.closed_at or now)), None)
        if key in self.funding_keys or p is None or not p.opened_at < timestamp <= now:
            return
        # Late funding publication can arrive after a partial or complete exit.
        # Reconstruct held quantity at the event time from the durable fill ledger.
        exited = sum(f["quantity"] for f in self.fills if f["signal_id"] == p.id
                     and f["reason"] not in ("ENTRY", "FUNDING") and f["at"] < timestamp)
        held = max(0, p.quantity - exited)
        cost = p.direction * held * mark * rate
        self.balance -= cost
        p.net -= cost
        self.funding_keys.add(key)
        self._fill(p, timestamp, "FUNDING", 0, mark, cost, -cost)

    def manage(self, quotes, now, force_reason=None):
        c = self.config
        for p in list(self.positions.values()):
            q = quotes.get(p.symbol)
            if not q or not q.valid() or not -2 <= now - q.observed_at <= c.stale_seconds:
                continue  # Never invent a stale-price emergency execution.
            trigger = q.bid if p.direction == 1 else q.ask
            if force_reason:
                self.close(p, q, now, force_reason)
            elif p.direction * (trigger - p.stop) <= 0:
                self.close(p, q, now, "SL")
            else:
                if not p.tp1_hit and p.direction * (trigger - p.tp1) >= 0:
                    self.close(p, q, now, "TP1", p.quantity / 2)
                    p.tp1_hit = True
                    # Include entry/exit fees and assumed exit slippage for remaining quantity.
                    if p.direction == 1:
                        p.stop = p.entry * (1 + c.fee) / ((1 - c.slippage) * (1 - c.fee))
                    else:
                        p.stop = p.entry * (1 - c.fee) / ((1 + c.slippage) * (1 + c.fee))
                if p.direction * (trigger - p.tp2) >= 0:
                    self.close(p, q, now, "TP2")
                elif now - p.opened_at >= c.max_hold_seconds:
                    self.close(p, q, now, "TIME")

    def enforce_daily(self, quotes, now):
        equity = self.equity(quotes)
        self.roll_day(now, equity)
        if equity <= self.daily_base * (1 - self.config.daily_loss):
            self.daily_locked = True
            self.manage(quotes, now, "DAILY_LIMIT")
        self.roll_day(now, self.equity(quotes))
        return self.daily_locked
