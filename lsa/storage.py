import json
import sqlite3
from pathlib import Path


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS signals (id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, at REAL, level TEXT, message TEXT);
                CREATE TABLE IF NOT EXISTS versions (hash TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS entry_charts (id TEXT PRIMARY KEY, body TEXT NOT NULL);
            """)

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def load(self):
        with self.connect() as db:
            row = db.execute("SELECT body FROM state WHERE id=1").fetchone()
            return json.loads(row[0]) if row else None

    def save(self, book, signals=(), entry_charts=()):
        # Ledger and signals are committed atomically; retries cannot duplicate fills.
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO state VALUES (1, ?)", (json.dumps(book.snapshot(), allow_nan=False),))
            db.executemany("INSERT OR IGNORE INTO signals VALUES (?, ?)",
                           [(s.id, json.dumps(s.record(), allow_nan=False)) for s in signals])
            db.executemany("INSERT OR IGNORE INTO entry_charts VALUES (?, ?)",
                           [(c["id"], json.dumps(c, allow_nan=False)) for c in entry_charts])

    def entry_chart(self, id):
        with self.connect() as db:
            row = db.execute("SELECT body FROM entry_charts WHERE id=?", (id,)).fetchone()
            return json.loads(row[0]) if row else None

    def entry_chart_ids(self, ids):
        if not ids:
            return set()
        with self.connect() as db:
            placeholders = ",".join("?" for _ in ids)
            return {row[0] for row in db.execute(f"SELECT id FROM entry_charts WHERE id IN ({placeholders})", ids)}

    def signal_exists(self, id):
        with self.connect() as db:
            return db.execute("SELECT 1 FROM signals WHERE id=?", (id,)).fetchone() is not None

    def signals(self, limit=100):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT body FROM signals ORDER BY rowid DESC LIMIT ?", (limit,))]

    def event(self, at, level, message):
        with self.connect() as db:
            db.execute("INSERT INTO events(at,level,message) VALUES(?,?,?)", (at, level, message))

    def events(self):
        with self.connect() as db:
            return [dict(zip(("at", "level", "message"), r)) for r in
                    db.execute("SELECT at,level,message FROM events ORDER BY id DESC LIMIT 80")]

    def version(self, config):
        from dataclasses import asdict
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO versions VALUES(?,?)", (config.fingerprint, json.dumps(asdict(config))))
