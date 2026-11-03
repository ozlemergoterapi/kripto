import pytest
from conftest import NOW, candle_frames
from lsa.history import Archive
from lsa.reporting import metrics, reports
from lsa.storage import Store
from lsa.backtest import acceptance, partitions


def test_store_atomic_roundtrip(tmp_path,book,signal,quote,filters):
    store = Store(tmp_path/"test.sqlite")
    assert book.open(signal,quote,NOW,filters,{}) is None
    store.save(book,[signal])
    store.save(book,[signal])
    assert store.load()["positions"]["BTCUSDT"]["id"] == signal.id
    assert len(store.signals()) == 1
    store.event(NOW,"WARN","test")
    assert store.events()[0]["message"] == "test"


def test_parquet_roundtrip_is_idempotent(tmp_path):
    archive = Archive(tmp_path)
    bars = candle_frames()["3m"]
    archive.write("BTCUSDT","3m",bars)
    archive.write("BTCUSDT","3m",bars)
    assert archive.read("BTCUSDT","3m") == bars


def test_metrics_no_trades_not_claimed_success(book):
    m = metrics([])
    assert m["win_rate"] is None
    assert m["expectancy_r"] is None
    assert not acceptance(m,730)["passed"]
    r = reports(book)
    assert len(r["daily"]) == 1
    assert r["weekly"][0]["net_pnl"] == 0


def test_forward_partitions_do_not_overlap():
    folds = partitions(0,730*86400)
    assert folds[-1]["name"] == "holdout"
    assert all(f["train_end"] <= f["test_start"] < f["test_end"] for f in folds)
    assert all(a["test_end"] <= b["test_start"] for a,b in zip(folds,folds[1:]))
    with pytest.raises(ValueError):
        partitions(0,86400)


def test_replay_runs_without_claiming_validation(config):
    from lsa.backtest import replay
    from conftest import NOW
    from lsa.models import Candle
    frames = candle_frames()
    # Add execution bars after the known closed-candle signal; future bars are
    # only used for fills, never injected into the analysis window.
    for i in range(4):
        start_ms = int((NOW+i*60)*1000)
        frames["1m"].append(Candle(start_ms,start_ms+59999,106,108,105.9,107,100))

    class MemoryArchive:
        def read(self,symbol,interval):
            return frames[interval]

    result = replay(MemoryArchive(),["BTCUSDT"],config,NOW-3600,NOW+240)
    assert result["run_id"]
    assert result["metrics"]["trades"] >= 1
    assert not result["acceptance"]["passed"]
    assert not result["acceptance"]["strategy_validated"]


def test_conflicting_archive_data_rejected(tmp_path):
    from dataclasses import replace
    archive = Archive(tmp_path)
    candle = candle_frames()["3m"][0]
    archive.write("BTCUSDT","3m",[candle])
    with pytest.raises(ValueError,match="çelişen"):
        archive.write("BTCUSDT","3m",[replace(candle,volume=123)])
