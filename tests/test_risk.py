from dataclasses import replace
import pytest

from conftest import NOW
from lsa.models import Quote
from lsa.risk import PaperBook, day_key


def open_trade(book, signal, quote, filters):
    assert book.open(signal, quote, NOW, filters, {}) is None
    return book.positions[signal.symbol]


def test_stop_includes_fees_slippage_and_respects_risk(book, signal, quote, filters):
    p = open_trade(book, signal, quote, filters)
    assert p.initial_risk <= 2
    assert p.leverage <= 10
    book.manage({p.symbol: replace(quote, bid=98, ask=98.02, observed_at=NOW+1)}, NOW+1)
    assert not book.positions
    assert book.balance == pytest.approx(100 - p.initial_risk)
    assert p.net == pytest.approx(-p.initial_risk)
    assert len(book.fills) == 2


def test_short_stop_direction(book, signal, quote, filters):
    s = replace(signal, side="SHORT", stop=102, tp1=98, tp2=96)
    p = open_trade(book, s, quote, filters)
    book.manage({p.symbol: replace(quote, bid=101.98, ask=102, observed_at=NOW+1)}, NOW+1)
    assert p.net == pytest.approx(-p.initial_risk)


def test_tp1_partial_then_break_even_costs(book, signal, quote, filters):
    p = open_trade(book, signal, quote, filters)
    book.manage({p.symbol: Quote(p.symbol,102,102.02,NOW+1)}, NOW+1)
    assert p.tp1_hit
    assert p.remaining == pytest.approx(p.quantity / 2)
    assert p.stop > p.entry
    book.manage({p.symbol: Quote(p.symbol,p.stop,p.stop+.02,NOW+2)}, NOW+2)
    assert p.closed_at
    # Remaining half breaks even after its allocated entry fee.
    assert book.fills[-1]["pnl"] == pytest.approx(p.entry * p.quantity / 2 * book.config.fee)


def test_tp2_closes_once_and_matches_balance(book, signal, quote, filters):
    p = open_trade(book, signal, quote, filters)
    q = Quote(p.symbol,104,104.02,NOW+1)
    book.manage({p.symbol:q},NOW+1)
    book.manage({p.symbol:q},NOW+1)
    assert len(book.closed) == 1
    assert len(book.fills) == 3
    assert book.balance == pytest.approx(100 + p.net)
    assert p.tp1_hit and p.tp2_hit


def test_reject_expired_spread_and_missing_filter(book, signal, quote, filters):
    assert "süresi" in book.open(replace(signal, expires_at=NOW-2),quote,NOW,filters,{})
    assert "Spread" in book.open(signal,replace(quote,ask=102),NOW,filters,{})
    assert "filtresi" in book.open(signal,quote,NOW,{}, {})
    assert not book.positions


def test_stale_force_exit_remains_pending(book, signal, quote, filters):
    p = open_trade(book,signal,quote,filters)
    book.manage({p.symbol:quote},NOW+16,"EMERGENCY")
    assert p.symbol in book.positions
    book.manage({p.symbol:replace(quote,observed_at=NOW+17)},NOW+17,"EMERGENCY")
    assert not book.positions


def test_daily_limit_includes_open_loss_and_new_day_resets(book, signal, quote, filters):
    p = open_trade(book, signal, quote, filters)
    q = Quote(p.symbol,90,90.01,NOW+1)
    assert book.enforce_daily({p.symbol:q}, NOW+1)
    assert not book.positions
    assert book.daily_locked
    assert book.closed[-1].exit_reason == "DAILY_LIMIT"
    tomorrow = NOW + 86400
    assert not book.enforce_daily({},tomorrow)
    assert len(book.days) == 2
    assert book.daily_base == book.balance


def test_total_risk_cap_and_correlation(book, signal, quote, filters):
    series = {i: (i % 7) / 100 for i in range(96)}
    assert book.open(signal,quote,NOW,filters,series) is None
    second = replace(signal,id="two",symbol="ETHUSDT")
    assert "Korelasyon" in book.open(second,replace(quote,symbol="ETHUSDT"),NOW,filters,series)
    inverse = {k:-v for k,v in series.items()}
    assert book.open(second,replace(quote,symbol="ETHUSDT"),NOW,filters,inverse) is None
    assert book.open_risk() <= 4 + 1e-8


def test_funding_idempotent_and_survives_restart(book, signal, quote, filters, config):
    p = open_trade(book,signal,quote,filters)
    book.apply_funding(p.symbol,NOW+1,.001,100,NOW+2)
    balance = book.balance
    restored = PaperBook(config,book.snapshot())
    restored.apply_funding(p.symbol,NOW+1,.001,100,NOW+2)
    assert restored.balance == balance
    assert book.balance < 100


def test_late_funding_applies_held_quantity_before_partial_exit(book, signal, quote, filters):
    p = open_trade(book,signal,quote,filters)
    book.manage({p.symbol:Quote(p.symbol,104,104.02,NOW+10)},NOW+10)
    balance = book.balance
    book.apply_funding(p.symbol,NOW+5,.001,100,NOW+20)
    assert book.balance == pytest.approx(balance-p.quantity*100*.001)
    assert p.net == pytest.approx(book.balance-100)


def test_time_exit_and_istanbul_midnight(book, signal, quote, filters):
    p = open_trade(book,signal,quote,filters)
    now = NOW + book.config.max_hold_seconds
    book.manage({p.symbol:replace(quote,observed_at=now)},now)
    assert p.exit_reason == "TIME"
    from datetime import datetime, timezone
    before = datetime(2026,11,3,20,59,59,tzinfo=timezone.utc).timestamp()
    assert day_key(before) == "2026-11-03"
    assert day_key(before+1) == "2026-11-04"


def test_approved_ceiling_config_validation(config):
    with pytest.raises(ValueError):
        replace(config,max_leverage=0)
