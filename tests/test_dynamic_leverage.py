from dataclasses import replace

import pytest

from conftest import NOW
from lsa.config import CONFIG
from lsa.risk import PaperBook


def test_dynamic_leverage_allows_over_ten_without_increasing_risk(signal,quote,filters):
    assert CONFIG.max_leverage is None
    c=CONFIG
    s=replace(signal,version=c.fingerprint,stop=99.5,tp1=100.5,tp2=101,atr=.5)
    capped=replace(c,max_leverage=10)
    old=PaperBook(capped)
    old.roll_day(NOW,1000)
    assert old.open(replace(s,version=capped.fingerprint),quote,NOW,filters,{})=="10× kaldıraç tavanı yetersiz"
    book=PaperBook(c)
    book.roll_day(NOW,1000)
    assert book.open(s,quote,NOW,filters,{}) is None
    p=book.positions[s.symbol]
    assert p.leverage>10
    assert p.initial_risk<=1000*c.trade_risk
    assert book.open_risk()<=1000*c.portfolio_risk
    assert p.margin<=1000/c.max_positions


def test_no_cap_does_not_disable_collateral_checks(signal,quote,filters):
    c=CONFIG
    s=replace(signal,version=c.fingerprint,stop=99.5,tp1=100.5,tp2=101,atr=.5)
    book=PaperBook(c)
    book.roll_day(NOW,1000)
    # Lack of available collateral still prevents an otherwise valid entry.
    book.last_equity=1000
    assert book.open(s,quote,NOW,filters,{}) is None
    p=book.positions[s.symbol]
    p.margin=1000
    short=replace(s,id="short",symbol="ETHUSDT",side="SHORT",stop=100.5,tp1=99.5,tp2=99)
    assert "teminat yetersiz" in book.open(short,replace(quote,symbol="ETHUSDT"),NOW,filters,{})
    assert len(book.positions)==1
    with pytest.raises(ValueError):
        replace(c,max_leverage=-1)
    with pytest.raises(ValueError):
        replace(c,max_leverage=1.5)
    assert replace(c,max_leverage=20).max_leverage==20


def test_liquidation_proximity_still_rejects_extreme_model_leverage(signal,quote,filters):
    # Isolated stress fixture, not a change to the active risk configuration.
    c=replace(CONFIG,trade_risk=.06,portfolio_risk=.06,daily_loss=.06)
    s=replace(signal,version=c.fingerprint,stop=99.999,tp1=100.5,tp2=101,atr=.5)
    book=PaperBook(c)
    book.roll_day(NOW,1000)
    assert book.open(s,quote,NOW,filters,{})=="Stop, tahmini likidasyon bölgesine yakın"
    assert not book.positions
