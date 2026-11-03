from dataclasses import replace
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import pytest

from conftest import NOW
from lsa.engine import Engine
from lsa.storage import Store
from lsa.web import make_server


def test_restart_manual_start_and_data_loss_exit(tmp_path,config,signal,quote,filters):
    store = Store(tmp_path/"journal.sqlite")
    e = Engine(config,store)
    e.ingest({quote.symbol:quote},NOW)
    assert e.book.open(signal,quote,NOW,filters,{}) is None
    e.store.save(e.book)
    restored = Engine(config,store)
    assert not restored.running
    assert not restored.pending_exit
    restored.ingest({quote.symbol:replace(quote,observed_at=NOW+1)},NOW+1)
    assert restored.book.positions
    assert not restored.running
    assert not restored.book.closed


def test_stale_check_no_invented_fill_then_recovery(tmp_path,config,signal,quote,filters):
    e = Engine(config,Store(tmp_path/"journal.sqlite"))
    e.ingest({quote.symbol:quote},NOW)
    assert e.book.open(signal,quote,NOW,filters,{}) is None
    e.running = True
    e.check_stale(NOW+16)
    assert e.pending_exit and not e.running
    assert e.book.positions
    e.ingest({quote.symbol:replace(quote,observed_at=NOW+17)},NOW+17)
    assert not e.book.positions
    assert e.book.closed[-1].closed_at == NOW+17


def test_http_state_security_and_controls(tmp_path,config):
    e = Engine(config,Store(tmp_path/"journal.sqlite"))
    server = make_server(e,port=0)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base+"/") as r:
            assert "LSA" in r.read().decode()
            assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
        with urlopen(base+"/api/state") as r:
            state = json.load(r)
            assert state["mode"] == "SİMÜLASYON"
            assert not state["live_trading_available"]
        req = Request(base+"/api/control",data=b'{"action":"start"}',headers={"Content-Type":"application/json"})
        with pytest.raises(HTTPError) as error:
            urlopen(req)
        assert error.value.code == 403
        token = json.load(urlopen(base+"/api/session"))["token"]
        req = Request(base+"/api/control",data=b'{"action":"emergency"}',headers={"X-LSA-Token":token})
        assert json.load(urlopen(req))["ok"]
        with pytest.raises(HTTPError):
            urlopen(base+"/../config.py")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
