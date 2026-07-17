"""Thin operator cockpit: logs + HITL gates + run trigger (stdlib HTTP only).

Does not reimplement websearch/command — host AI CLIs keep those tools.
TraceLock remains the investigation engine; this UI streams events and
lets operators complete zero-autonomy gates (captcha / Layer-B / portal).
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from osint_cli.hitl import complete_gate, list_gates
from osint_cli.state import load_state, save_state

from tracelock.agent import run_agent
from tracelock.events import EventLog, make_event_callback
from tracelock.qwen_client import QwenConfig

COCKPIT_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>TraceLock Cockpit</title>
<style>
  :root {
    --bg: #0b1220; --panel: #121a2b; --border: #243049;
    --text: #e8eefc; --muted: #8aa0c8; --accent: #5b8def;
    --ok: #3ecf8e; --warn: #e6d48a; --bad: #e05b7a;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif;
    background: var(--bg); color: var(--text); min-height: 100vh;
  }
  header {
    display: flex; align-items: center; gap: 14px; padding: 16px 20px;
    border-bottom: 1px solid var(--border); background: #0e1628;
  }
  header img { width: 40px; height: 40px; border-radius: 10px; }
  header h1 { font-size: 1.1rem; margin: 0; font-weight: 650; letter-spacing: -0.02em; }
  header p { margin: 2px 0 0; color: var(--muted); font-size: 0.85rem; }
  main { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; padding: 14px; }
  @media (max-width: 960px) { main { grid-template-columns: 1fr; } }
  .card {
    background: var(--panel); border: 1px solid var(--border); border-radius: 14px;
    padding: 14px; min-height: 200px; display: flex; flex-direction: column;
  }
  .card h2 { margin: 0 0 10px; font-size: 0.8rem; text-transform: uppercase;
    letter-spacing: 0.06em; color: var(--muted); font-weight: 600; }
  label { display: block; font-size: 0.8rem; color: var(--muted); margin-bottom: 4px; }
  textarea, input, select {
    width: 100%; background: #0b1220; color: var(--text); border: 1px solid var(--border);
    border-radius: 10px; padding: 10px; font: inherit; margin-bottom: 10px;
  }
  textarea { min-height: 90px; resize: vertical; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.85rem; }
  .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  button {
    background: var(--accent); color: #fff; border: 0; border-radius: 10px;
    padding: 10px 14px; font-weight: 600; cursor: pointer; font: inherit;
  }
  button.secondary { background: #243049; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  #log {
    flex: 1; overflow: auto; background: #070c16; border-radius: 10px;
    padding: 10px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.78rem; line-height: 1.45; max-height: 420px; border: 1px solid var(--border);
  }
  .ev { margin-bottom: 6px; white-space: pre-wrap; word-break: break-word; }
  .ev .k { color: var(--accent); font-weight: 600; }
  .ev.hitl_open { color: var(--warn); }
  .ev.run_end { color: var(--ok); }
  .ev.tool_end.fail { color: var(--bad); }
  .gate {
    border: 1px solid var(--warn); background: #1a1810; border-radius: 12px;
    padding: 12px; margin-bottom: 10px;
  }
  .gate h3 { margin: 0 0 6px; font-size: 0.95rem; color: var(--warn); }
  .gate a { color: var(--accent); }
  .gate .meta { color: var(--muted); font-size: 0.8rem; margin-bottom: 8px; }
  #report {
    flex: 1; overflow: auto; white-space: pre-wrap; font-family: ui-monospace, Menlo, monospace;
    font-size: 0.8rem; background: #070c16; border-radius: 10px; padding: 10px;
    border: 1px solid var(--border); max-height: 420px;
  }
  .status-pill {
    display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 0.75rem;
    background: #243049; color: var(--muted);
  }
  .status-pill.busy { background: #1a2a18; color: var(--ok); }
  footer { padding: 8px 20px 18px; color: var(--muted); font-size: 0.75rem; }
</style>
</head>
<body>
<header>
  <div>
    <h1>TraceLock Cockpit</h1>
    <p>Operator panel · live logs · HITL zero-autonomy gates · same CLI engine</p>
  </div>
  <span id="runState" class="status-pill">idle</span>
</header>
<main>
  <section class="card">
    <h2>Run</h2>
    <label>Clues (one per line, type:value)</label>
    <textarea id="clues">username:demo_subject_ig
phone:0811-6060-0613
other:FK demo university maba cohort fixture</textarea>
    <div class="row">
      <label style="display:flex;align-items:center;gap:6px;margin:0">
        <input type="checkbox" id="offline" checked/> Offline planner
      </label>
      <button id="btnRun">Start autopilot</button>
      <button class="secondary" id="btnRefresh">Refresh</button>
    </div>
    <h2 style="margin-top:14px">Open HITL gates</h2>
    <div id="gates"><p class="meta" style="color:var(--muted)">No open gates</p></div>
  </section>
  <section class="card">
    <h2>Event log</h2>
    <div id="log"></div>
  </section>
  <section class="card" style="grid-column: 1 / -1">
    <h2>Dossier report</h2>
    <div id="report">(run to generate)</div>
  </section>
</main>
<footer>
  Host AI agents (Claude / Qwen / Grok) keep websearch &amp; shell. This UI only drives TraceLock + HITL.
  Captchas are never auto-solved — open the portal URL, complete the challenge, then mark the gate done.
</footer>
<script>
let lastSeq = 0;
const logEl = document.getElementById('log');
const gatesEl = document.getElementById('gates');
const reportEl = document.getElementById('report');
const runState = document.getElementById('runState');

function appendEv(ev) {
  const div = document.createElement('div');
  div.className = 'ev ' + (ev.kind || '');
  if (ev.kind === 'tool_end' && ev.data && ev.data.ok === false) div.classList.add('fail');
  const data = ev.data && Object.keys(ev.data).length ? ' ' + JSON.stringify(ev.data).slice(0, 280) : '';
  div.innerHTML = '<span class="k">[' + ev.kind + ']</span> ' + (ev.message || '') +
    (data ? '<span style="color:var(--muted)">' + data + '</span>' : '');
  logEl.appendChild(div);
  logEl.scrollTop = logEl.scrollHeight;
  lastSeq = Math.max(lastSeq, ev.seq || 0);
}

async function poll() {
  try {
    const r = await fetch('/api/events?since=' + lastSeq);
    const j = await r.json();
    (j.events || []).forEach(appendEv);
    if (j.running) {
      runState.textContent = 'running';
      runState.classList.add('busy');
    } else {
      runState.textContent = 'idle';
      runState.classList.remove('busy');
    }
  } catch (e) {}
}

async function refreshStatus() {
  const r = await fetch('/api/status');
  const j = await r.json();
  // gates
  const open = j.open_gates || [];
  if (!open.length) {
    gatesEl.innerHTML = '<p style="color:var(--muted);margin:0;font-size:0.85rem">No open gates</p>';
  } else {
    gatesEl.innerHTML = open.map(g => {
      const url = g.url ? '<div><a href="' + g.url + '" target="_blank" rel="noopener">Open portal / challenge</a></div>' : '';
      const checklist = (g.operator_checklist || []).slice(0, 4).map(c => '<li>' + c + '</li>').join('');
      return '<div class="gate" data-id="' + g.id + '">' +
        '<h3>Gate ' + g.id + ' · ' + (g.kind || g.source || 'hitl') + '</h3>' +
        '<div class="meta">' + (g.why || '') + '</div>' + url +
        (checklist ? '<ul style="margin:8px 0;padding-left:18px;color:var(--muted);font-size:0.8rem">' + checklist + '</ul>' : '') +
        '<label>Operator notes / JSON value</label>' +
        '<textarea class="gate-val" rows="3">{"operator":"completed challenge","note":"demo"}</textarea>' +
        '<div class="row"><button onclick="completeGate(\'' + g.id + '\', this)">Mark completed &amp; resume evidence</button></div>' +
        '</div>';
    }).join('');
  }
  if (j.report_markdown) reportEl.textContent = j.report_markdown;
  if (j.running) {
    runState.textContent = 'running';
    runState.classList.add('busy');
  }
}

async function completeGate(id, btn) {
  const card = btn.closest('.gate');
  const val = card.querySelector('.gate-val').value;
  btn.disabled = true;
  try {
    const r = await fetch('/api/hitl/complete', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({gate_id: id, value: val, grade: 'operator_clue'})
    });
    const j = await r.json();
    if (!j.ok) alert(j.error || 'failed');
    await refreshStatus();
  } finally {
    btn.disabled = false;
  }
}

document.getElementById('btnRun').onclick = async () => {
  const clues = document.getElementById('clues').value.split('\n').map(s => s.trim()).filter(Boolean);
  const offline = document.getElementById('offline').checked;
  document.getElementById('btnRun').disabled = true;
  logEl.innerHTML = '';
  lastSeq = 0;
  try {
    const r = await fetch('/api/run', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({clues, offline})
    });
    const j = await r.json();
    if (!j.ok && j.error) alert(j.error);
  } finally {
    document.getElementById('btnRun').disabled = false;
    await refreshStatus();
  }
};
document.getElementById('btnRefresh').onclick = () => { refreshStatus(); poll(); };
setInterval(poll, 800);
setInterval(refreshStatus, 2000);
refreshStatus();
poll();
</script>
</body>
</html>
"""


class CockpitState:
    def __init__(self, case_path: Path, work_dir: Path) -> None:
        self.case_path = case_path
        self.work_dir = work_dir
        self.log = EventLog(jsonl_path=work_dir / "events.jsonl")
        self.running = False
        self.last_result: dict[str, Any] | None = None
        self._lock = threading.Lock()

    def status(self) -> dict[str, Any]:
        open_gates: list[dict[str, Any]] = []
        report_md = ""
        if self.case_path.is_file():
            try:
                st = load_state(self.case_path)
                open_gates = list_gates(st, status="open")
                report_md = st.get("report_markdown") or ""
            except Exception as e:
                report_md = f"(case load error: {e})"
        if self.last_result and self.last_result.get("report_markdown"):
            report_md = self.last_result["report_markdown"]
        return {
            "running": self.running,
            "case_path": str(self.case_path),
            "open_gates": open_gates,
            "report_markdown": report_md,
            "event_count": len(self.log.snapshot()),
            "last_ok": (self.last_result or {}).get("ok"),
        }


def _json_response(handler: BaseHTTPRequestHandler, code: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    raw = handler.rfile.read(length) if length else b"{}"
    try:
        data = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def make_handler(state: CockpitState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            # quieter server logs; still available via events
            pass

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            if path in ("/", "/index.html"):
                body = COCKPIT_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/api/status":
                _json_response(self, 200, state.status())
                return
            if path == "/api/events":
                qs = parse_qs(parsed.query)
                since = int((qs.get("since") or ["0"])[0] or 0)
                _json_response(
                    self,
                    200,
                    {
                        "events": state.log.since(since),
                        "running": state.running,
                    },
                )
                return
            if path == "/api/report":
                st = state.status()
                _json_response(
                    self,
                    200,
                    {"markdown": st.get("report_markdown") or "", "ok": True},
                )
                return
            _json_response(self, 404, {"ok": False, "error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            data = _read_json(self)

            if path == "/api/run":
                with state._lock:
                    if state.running:
                        _json_response(
                            self, 409, {"ok": False, "error": "run already in progress"}
                        )
                        return
                    state.running = True
                clues = data.get("clues") or []
                if isinstance(clues, str):
                    clues = [c.strip() for c in clues.splitlines() if c.strip()]
                offline = bool(data.get("offline", True))

                def worker() -> None:
                    try:
                        state.log.clear()
                        if offline:
                            os.environ["TRACELOCK_OFFLINE"] = "1"
                        cfg = QwenConfig.from_env()
                        if offline:
                            cfg = QwenConfig(
                                api_key="",
                                base_url=cfg.base_url,
                                model=cfg.model,
                                offline=True,
                            )
                        cb = make_event_callback(state.log)
                        result = run_agent(
                            list(clues),
                            state.case_path,
                            cfg=cfg,
                            on_event=cb,
                        )
                        state.last_result = result.to_dict()
                    except Exception as e:
                        state.log.emit("error", str(e))
                        state.last_result = {"ok": False, "error": str(e)}
                    finally:
                        with state._lock:
                            state.running = False

                threading.Thread(target=worker, daemon=True).start()
                _json_response(self, 200, {"ok": True, "started": True})
                return

            if path == "/api/hitl/complete":
                gate_id = str(data.get("gate_id") or "")
                if not gate_id:
                    _json_response(self, 400, {"ok": False, "error": "gate_id required"})
                    return
                if not state.case_path.is_file():
                    _json_response(self, 400, {"ok": False, "error": "no case yet"})
                    return
                try:
                    st = load_state(state.case_path)
                    value = data.get("value", {"operator": "completed"})
                    grade = str(data.get("grade") or "operator_clue")
                    out = complete_gate(
                        st,
                        gate_id,
                        value=value,
                        grade=grade,
                        notes=str(data.get("notes") or "cockpit"),
                    )
                    save_state(st, state.case_path)
                    state.log.emit(
                        "hitl_complete",
                        f"Gate {gate_id} completed by operator",
                        gate_id=gate_id,
                        grade=grade,
                    )
                    _json_response(self, 200, {"ok": True, "result": {
                        "gate_id": gate_id,
                        "status": (out.get("gate") or {}).get("status"),
                    }})
                except Exception as e:
                    _json_response(self, 400, {"ok": False, "error": str(e)})
                return

            _json_response(self, 404, {"ok": False, "error": "not found"})

    return Handler


def serve_cockpit(
    host: str = "127.0.0.1",
    port: int = 8765,
    case_path: Optional[Path] = None,
    open_browser: bool = False,
) -> None:
    work = Path(tempfile.mkdtemp(prefix="tracelock-cockpit-"))
    case = Path(case_path) if case_path else work / "case.json"
    case.parent.mkdir(parents=True, exist_ok=True)
    state = CockpitState(case_path=case, work_dir=work)
    handler = make_handler(state)
    httpd = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}/"
    print(f"TraceLock cockpit: {url}")
    print(f"Case file: {case}")
    print("Ctrl+C to stop. Host AI CLIs can still call: python3 -m tracelock run")
    if open_browser:
        try:
            import webbrowser

            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping cockpit.")
    finally:
        httpd.server_close()
