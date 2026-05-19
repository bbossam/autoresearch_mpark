from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from autoresearch.dashboard import _make_handler
from autoresearch.leaderboard import Leaderboard


def _server(tmp_path: Path):
    lb = tmp_path / "leaderboard.json"
    board = Leaderboard(lb)
    board.record("p1", "score", 0.9, "r1", higher_is_better=True)
    board.save()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(lb))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, lb


def test_api_lists_leaderboard(tmp_path: Path):
    server, _ = _server(tmp_path)
    try:
        port = server.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/leaderboard") as r:
            data = json.loads(r.read())
        assert len(data["rows"]) == 1
        assert data["rows"][0]["run_id"] == "r1"
    finally:
        server.shutdown()


def test_api_deletes_entry(tmp_path: Path):
    server, lb = _server(tmp_path)
    try:
        port = server.server_address[1]
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/leaderboard/delete",
            data=json.dumps({"key": "p1::score"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as r:
            assert json.loads(r.read())["ok"] is True
        assert Leaderboard(lb).entries() == {}
    finally:
        server.shutdown()


def test_index_page_is_served(tmp_path: Path):
    server, _ = _server(tmp_path)
    try:
        port = server.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as r:
            html = r.read().decode("utf-8")
        assert "autoresearch leaderboard" in html
    finally:
        server.shutdown()
