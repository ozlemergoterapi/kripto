from dataclasses import replace
import pytest

from conftest import NOW, candle_frames
from lsa.indicators import atr, correlation, ema, rsi
from lsa.market import BinancePublic, MarketError
from lsa.strategy import analyze


def test_indicators_and_aligned_correlation():
    assert ema([2]*30,20) == 2
    assert rsi([2]*30) == 50
    assert rsi(list(range(30))) == 100
    assert correlation({i:i for i in range(60)},{i:2*i for i in range(60)}) == pytest.approx(1)
    assert correlation({1:1},{2:2}) is None
    with pytest.raises(ValueError):
        ema([1],20)


def test_valid_candidate_and_no_future_data(config):
    frames = candle_frames()
    candidate = analyze("BTCUSDT",frames,NOW,config)
    assert candidate is not None
    assert candidate.side == "LONG"
    assert candidate.stop < candidate.entry < candidate.tp1 < candidate.tp2
    assert candidate.expires_at - candidate.created_at == 600
    assert analyze("BTCUSDT",frames,NOW,config).id == candidate.id
    frames["5m"][-1] = replace(frames["5m"][-1],close_time=int(NOW*1000))
    assert analyze("BTCUSDT",frames,NOW,config) is None


def test_missing_stale_and_gapped_candles_rejected(config):
    frames = candle_frames()
    frames["4h"] = frames["4h"][:100]
    assert analyze("BTCUSDT",frames,NOW,config) is None
    frames = candle_frames()
    frames["3m"].pop(100)
    assert analyze("BTCUSDT",frames,NOW,config) is None
    assert analyze("BTCUSDT",candle_frames(),NOW+90000,config) is None


def test_adapter_filters_open_candle_and_detects_gap(config, monkeypatch):
    m = BinancePublic(config)
    row = [0,"10","12","9","11","5",179999]
    monkeypatch.setattr(m,"get",lambda *args,**kw:[row,[180000,"11","12","9","10","5",359999]])
    assert len(m.candles("BTCUSDT","3m",now=200)) == 1
    monkeypatch.setattr(m,"get",lambda *args,**kw:[row,[360000,"11","12","9","10","5",539999]])
    with pytest.raises(MarketError,match="Eksik"):
        m.candles("BTCUSDT","3m",now=600)


def test_universe_excludes_non_usdt_and_illiquid(config, monkeypatch):
    from lsa.models import Quote
    m = BinancePublic(config)
    symbols = [{"symbol":s,"status":"TRADING","quoteAsset":q,"marginAsset":q,
                "contractType":"PERPETUAL","filters":[]} for s,q in (("BTCUSDT","USDT"),("ETHUSDC","USDC"),("LOWUSDT","USDT"))]
    tickers = [{"symbol":s,"quoteVolume":v} for s,v in (("BTCUSDT","100000000"),("LOWUSDT","100"),("ETHUSDC","200000000"))]
    monkeypatch.setattr(m,"get",lambda path: {"symbols":symbols} if "exchangeInfo" in path else tickers)
    quotes = {s:Quote(s,100,100.01,NOW) for s in ("BTCUSDT","ETHUSDC","LOWUSDT")}
    assert list(m.universe(quotes)) == ["BTCUSDT"]
