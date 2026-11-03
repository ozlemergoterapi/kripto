from dataclasses import replace
import math

import pytest

from conftest import NOW
from lsa.config import CONFIG
from lsa.engine import Engine
from lsa.models import Quote
from lsa.risk import PaperBook
from lsa.storage import Store


def test_clean_account_has_1000_balance_five_slots_and_approved_risk(tmp_path,signal,quote,filters):
    assert CONFIG.initial_balance==1000
    assert CONFIG.max_positions==5
    e=Engine(CONFIG,Store(tmp_path/"clean.sqlite"))
    e.ingest({quote.symbol:quote},NOW)
    state=e.view()
    assert state["equity"]==1000
    assert state["initial_balance"]==1000
    assert state["daily_loss_limit"]==60
    assert not state["positions"] and not state["closed"]
    assert state["metrics"]["trades"]==0
    assert not e.running
    signal=replace(signal,version=CONFIG.fingerprint)
    assert e.book.open(signal,quote,NOW,filters,{}) is None
    p=e.book.positions[signal.symbol]
    assert 19.9<p.initial_risk<=20
    assert e.book.open_risk()<=40
    e._save()
    restored=Engine(CONFIG,e.store)
    assert restored.book.balance==e.book.balance
    assert restored.book.positions
    assert restored.config.max_positions==5


def test_five_positions_fit_with_smaller_risk_and_sixth_is_blocked(signal,quote,filters):
    # The 2% figure is a ceiling, not a mandate to allocate 2% five times.
    c=replace(CONFIG,trade_risk=.005)
    book=PaperBook(c)
    book.roll_day(NOW,1000)
    for i in range(5):
        symbol=f"TEST{i}USDT"
        series={j:math.sin(j*(i+1)*.7) for j in range(96)}
        s=replace(signal,id=f"slot-{i}",symbol=symbol,version=c.fingerprint)
        assert book.open(s,replace(quote,symbol=symbol),NOW,filters,series) is None
    assert len(book.positions)==5
    assert book.open_risk()<=40
    sixth=replace(signal,id="sixth",symbol="SIXUSDT",version=c.fingerprint)
    assert book.open(sixth,replace(quote,symbol="SIXUSDT"),NOW,filters,{})=="Pozisyon sınırı"
    with pytest.raises(ValueError):
        replace(CONFIG,max_positions=6)


def test_changed_defaults_do_not_silently_reset_existing_journal(tmp_path):
    store=Store(tmp_path/"old.sqlite")
    old=PaperBook(replace(CONFIG,initial_balance=100,max_positions=3))
    old.balance=97
    store.save(old)
    restored=Engine(CONFIG,store)
    assert restored.book.balance==97
    assert restored.view()["initial_balance"]==100
