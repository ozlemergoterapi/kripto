from dataclasses import replace
import math
import pytest

from lsa.config import CONFIG
from lsa.market import INTERVAL_MS
from lsa.models import Candle, Quote, Signal
from lsa.risk import PaperBook

NOW = 1793721600.0


@pytest.fixture
def config():
    # Retain the original 100-USDT/3-slot regression scenarios. The approved
    # 1000-USDT/5-slot production defaults are exercised separately.
    return replace(CONFIG, initial_balance=100.0, max_positions=3)


@pytest.fixture
def quote():
    return Quote("BTCUSDT", 99.99, 100.01, NOW)


@pytest.fixture
def signal(config):
    return Signal("test-1", "BTCUSDT", "LONG", 85, "5m", NOW - 1, NOW + 599,
                  100, 98, 102, 104, "Test fixture", config.fingerprint, 2)


@pytest.fixture
def filters():
    return {"LOT_SIZE": {"stepSize": "0.001", "minQty": "0.001", "maxQty": "1000"},
            "MIN_NOTIONAL": {"notional": "5"}}


@pytest.fixture
def book(config):
    b = PaperBook(config)
    b.roll_day(NOW, 100)
    return b


def candle_frames(now=NOW):
    frames = {}
    for tf, step in INTERVAL_MS.items():
        # Align each series to its real exchange interval boundary.
        end = int(now * 1000) // step * step
        rows = []
        for i in range(260):
            close = 100 + i * .02 + math.sin(i) * .8
            start = end - (260 - i) * step
            rows.append(Candle(start, start + step - 1, close - .1, close + .4, close - .4, close, 100))
        last = rows[-1]
        rows[-1] = replace(last, close=106, high=106.4, low=104, open=105, volume=200)
        frames[tf] = rows
    return frames
