from dataclasses import replace
import json
import threading
from urllib.request import urlopen
from urllib.error import HTTPError

import pytest

from conftest import NOW
from lsa.models import Candle, Quote
from lsa.stream import kline_event, closed_event
from lsa.web import make_server
from test_entry_charts import opened_engine


def forming_for(e):
    p=e.book.positions["BTCUSDT"]
    last=e.frames[p.symbol][p.timeframe][-1]
    step=last.close_time-last.open_time+1
    return Candle(last.open_time+step,last.close_time+step,106,107,105.5,106.5,55)


def test_open_mum_updates_chart_without_touching_analysis_or_entry(tmp_path,config,filters):
    e=opened_engine(tmp_path,config,filters)
    p=e.book.positions["BTCUSDT"]
    entry=e.store.entry_chart(p.id)
    revision=e.frame_versions[p.symbol]
    bars=list(e.frames[p.symbol][p.timeframe])
    e.dirty_symbols.clear()
    forming=forming_for(e)
    e.on_kline(p.symbol,p.timeframe,forming,False,NOW+1)
    status,live=e.live_chart(p.id,NOW+1)
    assert status==200 and live["mode"]=="live"
    assert live["candles"][-1]["forming"]
    assert live["candles"][-1]["close"]==106.5
    assert not live["candles_stale"] and not live["price_stale"]
    assert e.frames[p.symbol][p.timeframe]==bars
    assert e.frame_versions[p.symbol]==revision
    assert not e.dirty_symbols
    assert e.store.entry_chart(p.id)==entry
    # A changed body for this same open candle is visible on the next poll.
    e.on_kline(p.symbol,p.timeframe,replace(forming,close=106.8),False,NOW+2)
    assert e.live_chart(p.id,NOW+2)[1]["candles"][-1]["close"]==106.8
    # An older event cannot move the live chart backward.
    e.on_kline(p.symbol,p.timeframe,forming,False,NOW+1)
    assert e.live_chart(p.id,NOW+2)[1]["candles"][-1]["close"]==106.8


def test_closed_candle_moves_to_analysis_once_and_removes_forming(tmp_path,config,filters):
    e=opened_engine(tmp_path,config,filters)
    p=e.book.positions["BTCUSDT"]
    forming=forming_for(e)
    e.on_kline(p.symbol,p.timeframe,forming,False,NOW+1)
    e.on_kline(p.symbol,p.timeframe,forming,True,forming.close_time/1000+.01)
    assert (p.symbol,p.timeframe) not in e.forming_candles
    assert e.frames[p.symbol][p.timeframe][-1]==forming
    assert p.symbol in e.dirty_symbols
    before=len(e.frames[p.symbol][p.timeframe])
    e.on_kline(p.symbol,p.timeframe,forming,True,forming.close_time/1000+.01)
    assert len(e.frames[p.symbol][p.timeframe])==before


def test_delayed_close_is_not_lost_after_newer_open_event(tmp_path,config,filters):
    e=opened_engine(tmp_path,config,filters)
    p=e.book.positions["BTCUSDT"]
    previous=forming_for(e)
    step=previous.close_time-previous.open_time+1
    current=replace(previous,open_time=previous.open_time+step,close_time=previous.close_time+step)
    t=current.open_time/1000
    e.on_kline(p.symbol,p.timeframe,current,False,t+1)
    e.on_kline(p.symbol,p.timeframe,previous,True,t)
    assert e.frames[p.symbol][p.timeframe][-1]==previous
    assert e.forming_candles[(p.symbol,p.timeframe)]==current
    assert e.chart_event_times[(p.symbol,p.timeframe)]==t+1


def test_live_current_stop_differs_from_immutable_entry_and_stale_is_marked(tmp_path,config,filters):
    e=opened_engine(tmp_path,config,filters)
    p=e.book.positions["BTCUSDT"]
    original=e.store.entry_chart(p.id)
    e.ingest({p.symbol:Quote(p.symbol,p.tp1,p.tp1+.02,NOW+1)},NOW+1)
    assert p.tp1_hit
    live=e.live_chart(p.id,NOW+1)[1]
    assert live["levels"]["stop"]==p.stop!=original["levels"]["stop"]
    assert e.store.entry_chart(p.id)==original
    stale=e.live_chart(p.id,NOW+20)[1]
    assert stale["price_stale"] and stale["candles_stale"]
    e.book.manage({p.symbol:Quote(p.symbol,p.tp2,p.tp2+.02,NOW+21)},NOW+21)
    assert e.live_chart(p.id,NOW+21)[0]==410
    assert e.store.entry_chart(p.id)==original


def test_missing_history_does_not_fabricate_candles(tmp_path,config,filters):
    e=opened_engine(tmp_path,config,filters)
    p=e.book.positions["BTCUSDT"]
    e.frames.clear()
    status,body=e.live_chart(p.id,NOW)
    assert status==503 and body["retry"]
    assert e.live_chart("unknown",NOW)[0]==404


def test_positions_outside_universe_keep_stream_coverage(tmp_path,config,filters):
    e=opened_engine(tmp_path,config,filters)
    e.universe={f"C{i:03}USDT":{} for i in range(150)}
    symbols=set()
    for i in range(3):
        group=e.streams._symbols(i)
        assert len(group)*len(config.timeframes)<=1024
        symbols.update(group)
    assert symbols==set(e.universe)|{"BTCUSDT"}
    e.on_kline("BTCUSDT","5m",forming_for(e),False,NOW+1)
    assert ("BTCUSDT","5m") in e.forming_candles


def test_stream_parser_accepts_forming_for_display_but_not_closed_analysis():
    start=int(NOW*1000)//300000*300000
    message={"e":"kline","s":"BTCUSDT","E":int((NOW+1)*1000),"k":{
        "t":start,"T":start+299999,"i":"5m","x":False,
        "o":"100","h":"102","l":"99","c":"101","v":"10"}}
    event=kline_event(message,NOW+1)
    assert event[3] is False and event[4]==NOW+1
    assert closed_event(message,NOW+1) is None
    message["E"]=float("nan")
    with pytest.raises(ValueError):
        kline_event(message,NOW+1)


def test_live_chart_http_never_mutates_stored_entry(tmp_path,config,filters):
    e=opened_engine(tmp_path,config,filters)
    p=e.book.positions["BTCUSDT"]
    snapshot=e.store.entry_chart(p.id)
    server=make_server(e,port=0)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    base=f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base+"/api/live-chart/"+p.id) as r:
            assert json.load(r)["mode"]=="live"
        assert e.store.entry_chart(p.id)==snapshot
        with pytest.raises(HTTPError) as error:
            urlopen(base+"/api/live-chart/../secret")
        assert error.value.code==400
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
