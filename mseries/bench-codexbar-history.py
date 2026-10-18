#!/usr/bin/env python3
"""Synthetic old-history benchmark against the public pre-audit revision.

Run from a Git checkout retaining 2235e9e. No real profiles/databases are used.
Timings include tracemalloc overhead and do not measure whole-panel performance.
"""
import importlib.util
import json
import pathlib
import sqlite3
import statistics
import subprocess
import tempfile
import time
import tracemalloc

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = "2235e9ed6a40f7066aaee639c1b19902c4d8d33e"
NOW = 1_800_000_000_000


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def benchmark():
    with tempfile.TemporaryDirectory() as temporary:
        directory = pathlib.Path(temporary)
        old_file = directory / "old.py"
        old_file.write_bytes(subprocess.check_output(
            ["git", "show", f"{BASELINE}:mseries/codexbar-opencode-local.py"], cwd=ROOT))
        readers = [("before", load_module(old_file, "old_reader")),
                   ("after", load_module(ROOT / "mseries/codexbar-opencode-local.py", "new_reader"))]
        database = directory / "usage.db"
        payload = json.dumps({"model": {"providerID": "opencode-go"}, "cost": .1,
                              "tokens": {"total": 100}, "syntheticPadding": "x" * 2048})
        with sqlite3.connect(database) as db:
            db.execute("CREATE TABLE session_message(type TEXT,time_created INTEGER,data TEXT)")
            db.executemany("INSERT INTO session_message VALUES ('assistant',?,?)",
                           [(NOW - 40 * 86400000, payload)] * 20000 + [(NOW - 1000, payload)] * 100)
        results, answers = {}, []
        for label, reader in readers:
            samples = []
            for _ in range(3):
                tracemalloc.start()
                start = time.perf_counter()
                answer = reader.read_usage(database, NOW)
                elapsed = time.perf_counter() - start
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                samples.append((elapsed * 1000, peak / 1048576))
            answers.append(answer["periods"])
            results[label] = {"medianMs": round(statistics.median(s[0] for s in samples), 2),
                              "peakPythonMiB": round(max(s[1] for s in samples), 2)}
        assert answers[0] == answers[1]
        return {"fixture": {"oldRows": 20000, "recentRows": 100, "paddingBytes": 2048, "indexed": False},
                "baseline": BASELINE, "repeats": 3, "tracemalloc": True,
                "periodsEqual": True, "results": results}


if __name__ == "__main__":
    print(json.dumps(benchmark(), indent=2))
