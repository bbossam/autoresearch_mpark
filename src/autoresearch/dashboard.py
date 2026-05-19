"""Minimal web dashboard for the autoresearch leaderboard.

No third-party dependencies — uses the stdlib ``http.server``. Serves a
sortable leaderboard table with per-row delete. Binds to localhost by default.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .leaderboard import Leaderboard

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>autoresearch leaderboard</title>
<style>
 body { font-family: system-ui, sans-serif; margin: 2rem; background:#0f1117; color:#e6e6e6; }
 h1 { font-size: 1.2rem; }
 .muted { color:#8a8f9a; font-size:.9rem; }
 table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
 th, td { padding: .5rem .75rem; border-bottom: 1px solid #2a2f3a; text-align: left; }
 th { cursor: pointer; user-select: none; }
 th:hover { color: #6ea8fe; }
 tr:hover td { background: #161a23; }
 button { background:#3a2330; color:#ff8a8a; border:1px solid #5a2a3a;
          border-radius:4px; cursor:pointer; padding:.2rem .55rem; }
 button:hover { background:#5a2a3a; }
</style>
</head>
<body>
<h1>autoresearch leaderboard</h1>
<p class="muted">click a column to sort &middot; delete removes the entry from leaderboard.json</p>
<table id="t">
 <thead><tr>
  <th data-k="key">project::metric</th>
  <th data-k="value">value</th>
  <th data-k="run_id">run</th>
  <th data-k="higher_is_better">higher is better</th>
  <th></th>
 </tr></thead>
 <tbody></tbody>
</table>
<p id="empty" class="muted" hidden>leaderboard is empty.</p>
<script>
let rows = [], sortKey = "key", sortAsc = true;
async function load() {
  rows = (await (await fetch("/api/leaderboard")).json()).rows;
  render();
}
function render() {
  rows.sort((a, b) => {
    const x = a[sortKey], y = b[sortKey];
    if (x < y) return sortAsc ? -1 : 1;
    if (x > y) return sortAsc ? 1 : -1;
    return 0;
  });
  const tb = document.querySelector("#t tbody");
  tb.innerHTML = "";
  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${row.key}</td><td>${row.value}</td>`
      + `<td>${row.run_id}</td><td>${row.higher_is_better}</td>`
      + `<td><button>delete</button></td>`;
    tr.querySelector("button").onclick = () => del(row.key);
    tb.appendChild(tr);
  }
  document.querySelector("#t").hidden = rows.length === 0;
  document.querySelector("#empty").hidden = rows.length !== 0;
}
async function del(key) {
  if (!confirm("Delete " + key + " ?")) return;
  await fetch("/api/leaderboard/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key }),
  });
  load();
}
document.querySelectorAll("#t th[data-k]").forEach((th) => {
  th.onclick = () => {
    const k = th.dataset.k;
    if (sortKey === k) sortAsc = !sortAsc;
    else { sortKey = k; sortAsc = true; }
    render();
  };
});
load();
</script>
</body>
</html>
"""


def _make_handler(leaderboard_path: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # keep the console quiet
            pass

        def _send(self, code: int, body: str, content_type: str) -> None:
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                self._send(200, _PAGE, "text/html; charset=utf-8")
            elif self.path == "/api/leaderboard":
                entries = Leaderboard(leaderboard_path).entries()
                rows = [{"key": key, **value} for key, value in sorted(entries.items())]
                self._send(200, json.dumps({"rows": rows}), "application/json")
            else:
                self._send(404, json.dumps({"error": "not found"}), "application/json")

        def do_POST(self) -> None:
            if self.path != "/api/leaderboard/delete":
                self._send(404, json.dumps({"error": "not found"}), "application/json")
                return
            length = int(self.headers.get("Content-Length", 0))
            try:
                payload = json.loads(self.rfile.read(length) or "{}")
            except json.JSONDecodeError:
                self._send(400, json.dumps({"error": "bad JSON"}), "application/json")
                return
            key = str(payload.get("key", ""))
            board = Leaderboard(leaderboard_path)
            removed = board.remove(key)
            if removed:
                board.save()
            self._send(200, json.dumps({"ok": removed, "key": key}), "application/json")

    return Handler


def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    leaderboard_path: str | Path = "experiments/leaderboard.json",
) -> None:
    """Run the dashboard server until interrupted."""
    server = ThreadingHTTPServer((host, port), _make_handler(Path(leaderboard_path)))
    print(f"autoresearch dashboard on http://{host}:{port}  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
