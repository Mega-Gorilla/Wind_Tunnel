import json
import sqlite3
from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    """All calls are serialized by Controller.lock; DELETE journal, bounded timeout."""
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=0.2)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          PRAGMA journal_mode=DELETE;
          PRAGMA foreign_keys=ON;
          CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY, owner TEXT, idem_key TEXT, request_hash TEXT,
            document TEXT, UNIQUE(owner, idem_key));
          CREATE TABLE IF NOT EXISTS samples (
            run_id TEXT REFERENCES runs(id), document TEXT);
          CREATE INDEX IF NOT EXISTS sample_run ON samples(run_id);
          CREATE TABLE IF NOT EXISTS clients (id TEXT PRIMARY KEY, document TEXT);
          CREATE TABLE IF NOT EXISTS events (at TEXT, kind TEXT, actor TEXT, detail TEXT);
        """)
        for row in self.db.execute("SELECT id,document FROM runs").fetchall():
            run = json.loads(row["document"])
            if run["state"] in ("RUNNING","ARMING","STOPPING"):
                run.update(state="INTERRUPTED", reason="service_restart", finished_at=utc_now())
                self.update_run(run)

    def event(self, kind, actor, detail):
        with self.db:
            self.db.execute("INSERT INTO events VALUES (?,?,?,?)", (utc_now(), kind, actor, detail))

    def create_run(self, run, key, digest):
        with self.db:
            self.db.execute("INSERT INTO runs VALUES (?,?,?,?,?)",
                            (run["id"], run["owner"], key, digest, json.dumps(run)))

    def replay(self, owner, key):
        row = self.db.execute("SELECT request_hash,document FROM runs WHERE owner=? AND idem_key=?",
                              (owner, key)).fetchone()
        return (row[0], json.loads(row[1])) if row else None

    def update_run(self, run):
        with self.db:
            self.db.execute("UPDATE runs SET document=? WHERE id=?", (json.dumps(run), run["id"]))

    def run(self, run_id):
        row = self.db.execute("SELECT document FROM runs WHERE id=?", (run_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def runs(self, limit, offset):
        return [json.loads(r[0]) for r in self.db.execute(
            "SELECT document FROM runs ORDER BY rowid DESC LIMIT ? OFFSET ?", (limit, offset))]

    def sample(self, run_id, sample):
        with self.db:
            self.db.execute("INSERT INTO samples VALUES (?,?)", (run_id, json.dumps(sample)))

    def samples(self, run_id):
        return [json.loads(r[0]) for r in self.db.execute(
            "SELECT document FROM samples WHERE run_id=? ORDER BY rowid", (run_id,))]

    def clients(self):
        return [json.loads(r[0]) for r in self.db.execute("SELECT document FROM clients")]

    def save_client(self, client):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO clients VALUES (?,?)", (client["id"], json.dumps(client)))

    def close(self):
        self.db.close()
