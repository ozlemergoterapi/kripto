from dataclasses import replace

from conftest import NOW, candle_frames
from lsa.engine import Engine
from lsa.models import Quote
from lsa.storage import Store
from lsa.stream import closed_event


def ready_engine(tmp_path, config, filters):
    e = Engine(config, Store(tmp_path/"journal.sqlite"))
    e.universe = {"BTCUSDT": {"filters": filters}}
    e.cache_snapshot("BTCUSDT", candle_frames())
    e._analyze_cached("BTCUSDT", NOW)
    assert len(e.pending_signals) == 1
    e.funding_checked_at = NOW
    return e


def test_paused_candidate_can_enter_on_price_tick_without_new_scan(tmp_path, config, filters):
    e = ready_engine(tmp_path,config,filters)
    q = Quote("BTCUSDT",105.99,106.01,NOW)
    e.ingest({q.symbol:q},NOW)
    assert not e.book.positions
    e.running = True
    e.ingest({q.symbol:replace(q,observed_at=NOW+2)},NOW+2)
    assert len(e.book.positions) == 1
    assert not e.pending_signals
    # Re-registering the same bar after a close must not re-enter that signal.
    e.book.manage({q.symbol:replace(q,observed_at=NOW+3)},NOW+3,"EMERGENCY")
    e._analyze_cached("BTCUSDT",NOW+4)
    e.ingest({q.symbol:replace(q,observed_at=NOW+4)},NOW+4)
    assert not e.book.positions
    assert len([f for f in e.book.fills if f["reason"]=="ENTRY"]) == 1


def test_price_rejection_retries_when_price_returns(tmp_path,config,filters):
    e = ready_engine(tmp_path,config,filters)
    e.running = True
    e.ingest({"BTCUSDT":Quote("BTCUSDT",106.99,107.01,NOW)},NOW)
    assert not e.book.positions and e.pending_signals
    e.ingest({"BTCUSDT":Quote("BTCUSDT",105.99,106.01,NOW+2)},NOW+2)
    assert e.book.positions


def test_expired_pending_and_stale_funding_cannot_enter(tmp_path,config,filters):
    e = ready_engine(tmp_path,config,filters)
    e.running = True
    e.funding_checked_at = NOW-100
    e.ingest({"BTCUSDT":Quote("BTCUSDT",105.99,106.01,NOW)},NOW)
    assert not e.book.positions
    e.funding_checked_at = NOW+601
    e.ingest({"BTCUSDT":Quote("BTCUSDT",105.99,106.01,NOW+601)},NOW+601)
    assert not e.pending_signals and not e.book.positions


def test_new_closed_bar_blocks_old_plan_until_reanalysis(tmp_path,config,filters):
    e = ready_engine(tmp_path,config,filters)
    last = e.frames["BTCUSDT"]["3m"][-1]
    new = replace(last,open_time=last.open_time+180000,close_time=last.close_time+180000)
    e.on_closed_candle("BTCUSDT","3m",new)
    e.running = True
    e.funding_checked_at = NOW+180
    e.ingest({"BTCUSDT":Quote("BTCUSDT",105.99,106.01,NOW+180)},NOW+180)
    assert not e.book.positions
    assert "BTCUSDT" in e.dirty_symbols


def test_snapshot_keeps_newer_stream_bars(tmp_path,config,filters):
    e = ready_engine(tmp_path,config,filters)
    bars = e.frames["BTCUSDT"]["3m"]
    last = bars[-1]
    new = replace(last,open_time=last.open_time+180000,close_time=last.close_time+180000)
    e.on_closed_candle("BTCUSDT","3m",new)
    e.cache_snapshot("BTCUSDT",candle_frames())
    assert e.frames["BTCUSDT"]["3m"][-1] == new
    assert len(e.frames["BTCUSDT"]["3m"]) == 260


def test_conflicting_closed_candle_invalidates_cached_plan(tmp_path,config,filters):
    e = ready_engine(tmp_path,config,filters)
    last = e.frames["BTCUSDT"]["3m"][-1]
    e.on_closed_candle("BTCUSDT","3m",replace(last,volume=999))
    e.running = True
    e.ingest({"BTCUSDT":Quote("BTCUSDT",105.99,106.01,NOW)},NOW)
    assert not e.book.positions
    e._analyze_cached("BTCUSDT",NOW)
    assert not e.pending_signals


def test_stream_ignores_open_candles_and_validates_close():
    import pytest
    bar = candle_frames()["3m"][-1]
    k = {"x":False,"i":"3m","t":bar.open_time,"T":bar.close_time,
         "o":str(bar.open),"h":str(bar.high),"l":str(bar.low),"c":str(bar.close),"v":str(bar.volume)}
    event = {"e":"kline","s":"BTCUSDT","k":k}
    assert closed_event(event,NOW) is None
    k["x"] = True
    assert closed_event({"data":event},NOW) == ("BTCUSDT","3m",bar)
    with pytest.raises(ValueError):
        closed_event(event,bar.close_time/1000)
    k["h"] = "0"
    with pytest.raises(ValueError):
        closed_event(event,NOW)


def test_stream_reconnects_and_resubscribes_without_exceeding_limits(tmp_path,config,monkeypatch):
    import json
    import websockets.sync.client
    e = Engine(config,Store(tmp_path/"journal.sqlite"))
    e.universe = {s:{} for s in ["BTCUSDT"]+[f"C{i:03}USDT" for i in range(149)]}
    calls, subscriptions = [], []
    bar = candle_frames()["3m"][-1]

    class Socket:
        def __enter__(self):
            return self

        def __exit__(self,*args):
            return False

        def send(self,raw):
            subscriptions.append(json.loads(raw))

        def recv(self,timeout):
            e.stop_event.set()
            return json.dumps({"e":"kline","s":"BTCUSDT","k":{
                "x":True,"i":"3m","t":bar.open_time,"T":bar.close_time,
                "o":str(bar.open),"h":str(bar.high),"l":str(bar.low),
                "c":str(bar.close),"v":str(bar.volume)}})

    def connect(url,**kwargs):
        calls.append((url,kwargs))
        if len(calls)==1:
            raise ConnectionError("simulated disconnect")
        return Socket()

    monkeypatch.setattr(websockets.sync.client,"connect",connect)
    monkeypatch.setattr(e.stop_event,"wait",lambda timeout:False)
    e.streams._run(0)
    assert len(calls)==2
    assert calls[0][0].startswith("wss://")
    assert len(subscriptions[0]["params"]) == 420
    assert subscriptions[0]["method"] == "SUBSCRIBE"
    assert e.frames["BTCUSDT"]["3m"][-1] == bar


def test_analysis_race_cannot_register_old_decision(tmp_path,config,filters,monkeypatch):
    import lsa.engine as module
    e = ready_engine(tmp_path,config,filters)
    e.pending_signals.clear()
    actual = module.analyze

    def racing_analysis(symbol,frames,now,config):
        result = actual(symbol,frames,now,config)
        e.frame_versions[symbol] += 1
        return result

    monkeypatch.setattr(module,"analyze",racing_analysis)
    e._analyze_cached("BTCUSDT",NOW)
    assert not e.pending_signals
    assert "BTCUSDT" in e.dirty_symbols


def test_background_workers_open_paper_after_manual_start(tmp_path,config,filters,monkeypatch):
    import time

    class Market:
        clock_offset = 0

        def sync_clock(self):
            self.clock_offset = 0

        def quotes(self):
            return {"BTCUSDT":Quote("BTCUSDT",105.99,106.01,time.time())}

        def universe(self,quotes):
            return {"BTCUSDT":{"filters":filters}}

        def candles(self,symbol,tf):
            return candle_frames(time.time())[tf]

        def try_rate(self):
            return {"value":40,"at":time.time(),"source":"synthetic fixture"}

        def funding_history(self,*args):
            return []

    e = Engine(config,Store(tmp_path/"journal.sqlite"),Market())
    monkeypatch.setattr(e.streams,"start",lambda:None)
    e.start_workers()
    try:
        deadline = time.monotonic()+7
        started = False
        while time.monotonic()<deadline:
            if not started and e.last_data and not e.safe_reason:
                started = e.control("start")[0]
            with e.lock:
                if e.book.positions:
                    break
            time.sleep(.05)
        assert started and e.book.positions
        assert len([f for f in e.book.fills if f["reason"]=="ENTRY"]) == 1
    finally:
        e.shutdown()
