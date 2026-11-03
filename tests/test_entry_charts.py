from dataclasses import replace
import json
import threading
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from conftest import NOW, candle_frames
from lsa.engine import Engine
from lsa.models import Candle, Quote
from lsa.patterns import TEMPLATES, compare_shapes, resample
from lsa.storage import Store
from lsa.web import make_server


def bars_for(values):
    # All data here are synthetic fixtures, not a historical performance dataset.
    closes=resample(values,120)
    return [Candle(i*180000,(i+1)*180000-1,100+v,100+v+.01,100+v-.01,100+v,10)
            for i,v in enumerate(closes)]


@pytest.mark.parametrize("name",list(TEMPLATES))
def test_shape_names_on_exact_reference_fixtures(name):
    result=compare_shapes(bars_for(TEMPLATES[name]))
    assert result["best"]["name"]==name
    assert result["best"]["score"]>95
    assert result["is_trade_signal"] is False


def test_shape_is_price_scale_invariant_and_flat_is_not_forced():
    bars=bars_for(TEMPLATES["İkili dip"])
    transformed=[replace(c,open=c.open*10+500,high=c.high*10+500,low=c.low*10+500,close=c.close*10+500) for c in bars]
    a,b=compare_shapes(bars),compare_shapes(transformed)
    assert a["best"]["name"]==b["best"]["name"]
    assert a["best"]["score"]==b["best"]["score"]
    assert compare_shapes(bars_for([1,1,1]))["best"] is None
    assert compare_shapes(bars[:10])["status"]=="insufficient"


def opened_engine(tmp_path,config,filters):
    e=Engine(config,Store(tmp_path/"journal.sqlite"))
    e.universe={"BTCUSDT":{"filters":filters}}
    e.cache_snapshot("BTCUSDT",candle_frames())
    e._analyze_cached("BTCUSDT",NOW)
    e.funding_checked_at=NOW
    e.running=True
    e.ingest({"BTCUSDT":Quote("BTCUSDT",105.99,106.01,NOW)},NOW)
    assert e.book.positions
    return e


def test_entry_chart_is_saved_with_trade_and_immutable_after_tp1(tmp_path,config,filters):
    e=opened_engine(tmp_path,config,filters)
    p=e.book.positions["BTCUSDT"]
    snapshot=e.store.entry_chart(p.id)
    assert snapshot is not None
    assert len(snapshot["candles"])==120
    assert all(c["close_time"]<NOW*1000 for c in snapshot["candles"])
    assert snapshot["levels"]["entry"]==p.entry
    assert snapshot["levels"]["stop"]==p.original_stop
    assert e.view()["positions"][0]["chart_available"]
    # Neither future candles nor the managed break-even stop rewrite the entry view.
    last=e.frames["BTCUSDT"][p.timeframe][-1]
    e.frames["BTCUSDT"][p.timeframe].append(replace(last,open_time=last.open_time+300000,close_time=last.close_time+300000))
    e.ingest({"BTCUSDT":Quote("BTCUSDT",p.tp1,p.tp1+.02,NOW+1)},NOW+1)
    assert p.tp1_hit and p.stop!=p.original_stop
    assert e.store.entry_chart(p.id)==snapshot
    restored=Engine(config,e.store)
    assert restored.store.entry_chart(p.id)==snapshot
    restored.ingest({"BTCUSDT":Quote("BTCUSDT",p.tp2,p.tp2+.02,NOW+2)},NOW+2)
    assert restored.view()["closed"][0]["chart_available"]
    assert restored.store.entry_chart(p.id)==snapshot
    # Attempted overwrite is ignored even when the rest of the ledger is saved.
    e.store.save(e.book,entry_charts=[snapshot|{"levels":{"entry":0}}])
    assert e.store.entry_chart(p.id)==snapshot


def test_chart_save_and_ledger_are_one_transaction(tmp_path,book):
    store=Store(tmp_path/"journal.sqlite")
    store.save(book)
    book.balance=50
    with pytest.raises(ValueError):
        store.save(book,entry_charts=[{"id":"bad","value":float("nan")}])
    assert store.load()["balance"]==100
    assert store.entry_chart("bad") is None


def test_chart_http_endpoint_and_missing_legacy_entry(tmp_path,config,filters):
    e=opened_engine(tmp_path,config,filters)
    id=e.book.positions["BTCUSDT"].id
    server=make_server(e,port=0)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    base=f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base+"/api/entry-chart/"+id) as r:
            data=json.load(r)
            assert data["id"]==id
            assert data["pattern"]["is_trade_signal"] is False
        with urlopen(base+"/charts.js") as r:
            assert r.status==200
        with pytest.raises(HTTPError) as missing:
            urlopen(base+"/api/entry-chart/legacy")
        assert missing.value.code==404
        with pytest.raises(HTTPError) as invalid:
            urlopen(base+"/api/entry-chart/../secret")
        assert invalid.value.code==400
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
