"""JSON-file replacement for eqore-demo's SQLite workspace store, with the same optimistic-version contract."""
import json
import threading
from pathlib import Path


class Conflict(Exception):
    pass


class JsonStore:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.lock = threading.RLock()
        self._initial = {}

    def _file(self, identity):
        return self.folder / f"{identity}.json"

    def ensure_workspace(self, identity, initial):
        with self.lock:
            self._initial[identity] = json.loads(json.dumps(initial))
            if not self._file(identity).exists():
                self._save(identity, {"version": 1, "state": initial})

    def read_workspace(self, identity):
        with self.lock:
            f = self._file(identity)
            if not f.exists() and identity in self._initial:  # the data folder was cleared while running: start fresh
                self._save(identity, {"version": 1, "state": json.loads(json.dumps(self._initial[identity]))})
            if not f.exists():
                raise ValueError("Unknown workspace.")
            return json.loads(f.read_text(encoding="utf-8"))

    def write_workspace(self, identity, state, expected):
        with self.lock:
            current = self.read_workspace(identity)
            if current["version"] != expected:
                raise Conflict("Paperwork changed. Refresh and review the current record before applying this action.")
            self._save(identity, {"version": expected + 1, "state": state})
            return expected + 1

    def _save(self, identity, doc):
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self._file(identity).with_suffix(".tmp")
        tmp.write_text(json.dumps(doc), encoding="utf-8")
        tmp.replace(self._file(identity))
