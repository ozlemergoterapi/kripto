from dataclasses import asdict, dataclass
import hashlib
import json


@dataclass(frozen=True)
class Config:
    version: str = "0.3.1-paper"
    initial_balance: float = 1000.0
    trade_risk: float = 0.02
    portfolio_risk: float = 0.04
    daily_loss: float = 0.06
    max_positions: int = 5
    max_leverage: int | None = None  # None: no application-level cap in PAPER mode.
    max_symbols: int = 150
    stale_seconds: int = 15
    scan_seconds: int = 300
    max_hold_seconds: int = 14400
    signal_ttl: int = 600
    fee: float = 0.0005
    slippage: float = 0.0002
    tp1_r: float = 1.0
    tp2_r: float = 2.0
    # Engineering defaults, documented as provisional, not an optimized strategy.
    min_quote_volume: float = 50_000_000
    max_spread: float = 0.001
    min_score: int = 75
    correlation_limit: float = 0.80
    atr_period: int = 14
    min_stop_atr: float = 1.5
    max_stop_atr: float = 3.0
    timeframes: tuple = ("3m", "5m", "15m", "30m", "1h", "4h", "1d")

    def __post_init__(self):
        if not (0 < self.trade_risk <= self.portfolio_risk <= self.daily_loss < 1):
            raise ValueError("Invalid risk limits")
        if self.max_leverage is not None and (type(self.max_leverage) is not int or self.max_leverage < 1):
            raise ValueError("Leverage cap must be a positive integer or None")
        if not 1 <= self.max_positions <= 5:
            raise ValueError("Approved ceilings exceeded")

    @property
    def fingerprint(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:16]


CONFIG = Config()
