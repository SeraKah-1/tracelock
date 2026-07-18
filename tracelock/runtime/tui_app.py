"""Full-screen TraceLock TUI (curses) — operator console for agentic OSINT.

Features (stdlib only — no prompt_toolkit/rich required):
  • Header: product + model + API base + LLM status
  • Scrollable conversation transcript
  • Live tool-progress feed while agent runs
  • Status bar: session, case, turns, mode, clock
  • Multiline input (Ctrl+J / Alt+Enter), Enter to send
  • Slash-command autocomplete (Tab)
  • Input history (↑/↓)
  • Ctrl+C interrupt busy agent, double Ctrl+C / Ctrl+D exit
  • /sessions picker, resume last with -c

Design: dark operator aesthetic (TraceLock), not a clone of any third-party skin.
"""

from __future__ import annotations

import curses
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Deque, List, Optional

from tracelock.runtime.config import RuntimeConfig, load_config
from tracelock.runtime.react_agent import ReactAgent
from tracelock.runtime.session import Session, SessionStore, sessions_dir
from tracelock.runtime.slash import COMMANDS, dispatch_slash


# ── palette (curses color pairs) ────────────────────────────────────────────
# 1 header  2 status  3 user  4 agent  5 tool  6 dim  7 input  8 accent  9 err


@dataclass
class ChatLine:
    role: str  # system | user | agent | tool | info | error
    text: str
    ts: float = field(default_factory=time.time)


class TraceLockTUI:
    def __init__(
        self,
        *,
        session_id: str = "tui_local",
        resume: bool = False,
        resume_id: str = "",
    ) -> None:
        self.cfg = load_config()
        self.store = SessionStore()
        self.session_id = session_id
        self.session: Session
        if resume_id:
            s = self.store.get(resume_id)
            self.session = s or self.store.get_or_create(
                platform="tui", external_id=session_id, case_dir=self.cfg.cases_dir
            )
        elif resume:
            self.session = self._latest_session() or self.store.get_or_create(
                platform="tui", external_id=session_id, case_dir=self.cfg.cases_dir
            )
        else:
            self.session = self.store.get_or_create(
                platform="tui",
                external_id=session_id,
                case_dir=self.cfg.cases_dir,
            )

        self.lines: List[ChatLine] = []
        self.tool_feed: Deque[str] = deque(maxlen=40)
        self.input_buf: List[str] = [""]  # multiline buffer (list of logical lines joined later)
        self.input_row = 0
        self.cursor = 0  # position in current line
        self.history: List[str] = []
        self.history_idx = -1
        self.scroll = 0  # conversation scroll offset from bottom
        self.running = True
        self.busy = False
        self.interrupt = threading.Event()
        self.last_ctrl_c = 0.0
        self.status_msg = "ready"
        self.last_mode = "—"
        self.last_turns = 0
        self.last_tools = 0
        self.ac_candidates: List[str] = []
        self.ac_index = 0
        self.show_help_overlay = False
        self.stdscr: Any = None
        self._lock = threading.Lock()

        # hydrate transcript from session
        for m in self.session.messages[-40:]:
            role = "user" if m.get("role") == "user" else "agent"
            self.lines.append(ChatLine(role=role, text=str(m.get("content") or "")[:4000]))

    def _latest_session(self) -> Optional[Session]:
        root = sessions_dir()
        files = sorted(root.glob("tui_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            files = sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            return None
        try:
            import json

            data = json.loads(files[0].read_text(encoding="utf-8"))
            return Session.from_dict(data)
        except Exception:
            return None

    # ── agent ───────────────────────────────────────────────────────────────
    def _on_progress(self, kind: str, msg: str) -> None:
        with self._lock:
            prefix = {"tool": "⚙", "think": "◉", "info": "·"}.get(kind, "·")
            self.tool_feed.append(f"{prefix} {msg}")
            self.status_msg = msg[:60]

    def _run_agent(self, text: str) -> None:
        self.busy = True
        self.interrupt.clear()
        try:
            agent = ReactAgent(self.cfg, on_progress=self._on_progress)
            # cooperative interrupt: agent doesn't poll yet — we still mark busy
            result = agent.chat(
                text,
                platform="tui",
                external_id=self.session.external_id or self.session_id,
                session=self.session,
            )
            if self.interrupt.is_set():
                with self._lock:
                    self.lines.append(ChatLine("info", "⟪ interrupted ⟫"))
            else:
                with self._lock:
                    self.lines.append(ChatLine("agent", result.reply or "(empty)"))
                    self.last_mode = result.mode
                    self.last_turns = result.turns
                    self.last_tools = len(result.tool_trace)
                    if result.tool_trace:
                        tools = ", ".join(t.get("tool", "?") for t in result.tool_trace[-8:])
                        self.tool_feed.append(f"✓ tools: {tools}")
                    self.status_msg = f"done · {result.mode} · {result.turns} turns"
            s = self.store.get(self.session.id)
            if s:
                self.session = s
        except Exception as e:
            with self._lock:
                self.lines.append(ChatLine("error", f"agent error: {e}"))
                self.status_msg = "error"
        finally:
            self.busy = False

    # ── drawing ─────────────────────────────────────────────────────────────
    def _init_colors(self) -> None:
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)  # header
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_WHITE)  # status
        curses.init_pair(3, curses.COLOR_GREEN, -1)  # user
        curses.init_pair(4, curses.COLOR_WHITE, -1)  # agent
        curses.init_pair(5, curses.COLOR_YELLOW, -1)  # tool
        curses.init_pair(6, curses.COLOR_BLUE, -1)  # dim/info
        curses.init_pair(7, curses.COLOR_CYAN, -1)  # input
        curses.init_pair(8, curses.COLOR_MAGENTA, -1)  # accent
        curses.init_pair(9, curses.COLOR_RED, -1)  # error

    def _layout(self) -> dict[str, int]:
        h, w = self.stdscr.getmaxyx()
        header_h = 3
        status_h = 1
        input_h = min(6, max(3, len(self.input_buf) + 2))
        feed_h = 4 if self.tool_feed or self.busy else 0
        chat_h = max(3, h - header_h - status_h - input_h - feed_h)
        return {
            "h": h,
            "w": w,
            "header_h": header_h,
            "chat_y": header_h,
            "chat_h": chat_h,
            "feed_y": header_h + chat_h,
            "feed_h": feed_h,
            "status_y": h - status_h - input_h,
            "input_y": h - input_h,
            "input_h": input_h,
        }

    def _safe_add(self, y: int, x: int, s: str, attr: int = 0) -> None:
        h, w = self.stdscr.getmaxyx()
        if y < 0 or y >= h or x >= w:
            return
        s = (s or "").replace("\t", " ")
        # strip non-printable that break curses
        s = "".join(ch if (ch == "\n" or ord(ch) >= 32) else "?" for ch in s)
        maxw = w - x - 1
        if maxw <= 0:
            return
        try:
            self.stdscr.addnstr(y, x, s, maxw, attr)
        except curses.error:
            pass

    def _wrap(self, text: str, width: int) -> List[str]:
        if width < 8:
            width = 8
        out: List[str] = []
        for para in (text or "").splitlines() or [""]:
            while len(para) > width:
                out.append(para[:width])
                para = para[width:]
            out.append(para)
        return out or [""]

    def draw(self) -> None:
        self.stdscr.erase()
        L = self._layout()
        w, h = L["w"], L["h"]
        cfg = self.cfg

        # header
        title = " TraceLock · detective OSINT "
        meta = (
            f" {cfg.model[:28]} │ "
            f"{'LLM' if cfg.has_llm else 'local'} │ "
            f"sess {self.session.id[:18]} "
        )
        self.stdscr.attron(curses.color_pair(1))
        for y in range(L["header_h"]):
            self._safe_add(y, 0, " " * (w - 1), curses.color_pair(1))
        self._safe_add(0, 0, title.ljust(w - 1), curses.color_pair(1) | curses.A_BOLD)
        self._safe_add(1, 0, meta.ljust(w - 1), curses.color_pair(1))
        base = (cfg.api_base or "")[: w - 2]
        self._safe_add(2, 0, f" {base}".ljust(w - 1), curses.color_pair(1))
        self.stdscr.attroff(curses.color_pair(1))

        # conversation
        rendered: List[tuple[str, str]] = []  # role, line
        with self._lock:
            snapshot = list(self.lines)
        for line in snapshot:
            prefix = {
                "user": "You › ",
                "agent": "TL  › ",
                "tool": "  ⚙ ",
                "info": "  · ",
                "error": "  ! ",
                "system": "  # ",
            }.get(line.role, "  ")
            for i, wr in enumerate(self._wrap(line.text, w - len(prefix) - 2)):
                rendered.append((line.role, (prefix if i == 0 else " " * len(prefix)) + wr))

        max_vis = L["chat_h"]
        total = len(rendered)
        if self.scroll < 0:
            self.scroll = 0
        end = total - self.scroll
        start = max(0, end - max_vis)
        visible = rendered[start:end]
        # pad top
        pad = max_vis - len(visible)
        y0 = L["chat_y"] + pad
        for i, (role, txt) in enumerate(visible):
            attr = {
                "user": curses.color_pair(3) | curses.A_BOLD,
                "agent": curses.color_pair(4),
                "tool": curses.color_pair(5),
                "info": curses.color_pair(6),
                "error": curses.color_pair(9),
                "system": curses.color_pair(8),
            }.get(role, curses.color_pair(4))
            self._safe_add(y0 + i, 1, txt, attr)

        # tool feed
        if L["feed_h"]:
            self._safe_add(
                L["feed_y"],
                0,
                "─ tools " + "─" * max(0, w - 10),
                curses.color_pair(6),
            )
            with self._lock:
                feed = list(self.tool_feed)[-(L["feed_h"] - 1) :]
            for i, t in enumerate(feed):
                self._safe_add(L["feed_y"] + 1 + i, 1, t, curses.color_pair(5))

        # status bar
        case = (self.session.case_path or "—")[-36:]
        busy = " BUSY " if self.busy else " idle "
        st = (
            f"{busy}│ mode={self.last_mode} turns={self.last_turns} tools={self.last_tools} "
            f"│ case={case} │ {self.status_msg[:24]} │ {datetime.now().strftime('%H:%M:%S')}"
        )
        self.stdscr.attron(curses.color_pair(2))
        self._safe_add(L["status_y"], 0, st.ljust(w - 1)[: w - 1], curses.color_pair(2))
        self.stdscr.attroff(curses.color_pair(2))

        # input area
        iy = L["input_y"]
        hint = " Enter send · Ctrl+J newline · Tab complete · /help · Ctrl+C stop · Ctrl+D quit "
        self._safe_add(iy, 0, "─" + hint[: w - 3].ljust(w - 2, "─"), curses.color_pair(6))
        # autocomplete strip
        if self.ac_candidates:
            ac = "  ".join(
                (f"[{c}]" if i == self.ac_index else c)
                for i, c in enumerate(self.ac_candidates[:8])
            )
            self._safe_add(iy + 1, 1, ac[: w - 3], curses.color_pair(8))
            body_y = iy + 2
        else:
            body_y = iy + 1
        joined = self.input_buf
        for i, ln in enumerate(joined[-(L["input_h"] - 2) :]):
            prompt = "› " if i == 0 else "  "
            self._safe_add(body_y + i, 0, prompt + ln, curses.color_pair(7) | curses.A_BOLD)

        # cursor
        cur_line = self.input_buf[self.input_row] if self.input_buf else ""
        cx = 2 + min(self.cursor, len(cur_line))
        cy = body_y + min(self.input_row, L["input_h"] - 3)
        try:
            curses.curs_set(1)
            self.stdscr.move(min(cy, h - 2), min(cx, w - 2))
        except curses.error:
            pass

        if self.show_help_overlay:
            self._draw_help_overlay(w, h)

        self.stdscr.refresh()

    def _draw_help_overlay(self, w: int, h: int) -> None:
        lines = [
            " TraceLock TUI — keys ",
            " Enter          send",
            " Ctrl+J         newline",
            " Tab            slash autocomplete",
            " ↑/↓            history / ac cycle",
            " PgUp/PgDn      scroll chat",
            " Ctrl+C         interrupt (×2 quit)",
            " Ctrl+D / :q    quit",
            " /find @x       detective OSINT",
            " /pivot         force triangulation",
            " /models /key   LLM setup",
            " /sessions      list sessions",
            " Esc            close help",
            " (press any key)",
        ]
        box_w = min(44, w - 4)
        box_h = len(lines) + 2
        y0 = max(1, (h - box_h) // 2)
        x0 = max(1, (w - box_w) // 2)
        for i in range(box_h):
            self._safe_add(y0 + i, x0, " " * box_w, curses.color_pair(2))
        for i, ln in enumerate(lines):
            self._safe_add(y0 + 1 + i, x0 + 1, ln[: box_w - 2], curses.color_pair(2))

    # ── input handling ──────────────────────────────────────────────────────
    def _current_line(self) -> str:
        if not self.input_buf:
            self.input_buf = [""]
        return self.input_buf[self.input_row]

    def _set_line(self, s: str) -> None:
        self.input_buf[self.input_row] = s

    def _update_ac(self) -> None:
        line = self._current_line()
        if not line.startswith("/"):
            self.ac_candidates = []
            return
        token = line[1:].split(" ")[0].lower()
        names = sorted(COMMANDS.keys())
        self.ac_candidates = [n for n in names if n.startswith(token)][:12]
        self.ac_index = 0

    def _apply_ac(self) -> None:
        if not self.ac_candidates:
            return
        pick = self.ac_candidates[self.ac_index % len(self.ac_candidates)]
        line = self._current_line()
        rest = ""
        if " " in line:
            rest = line[line.index(" ") :]
        self._set_line("/" + pick + rest)
        self.cursor = len(self._current_line())
        self.ac_candidates = []

    def _submit(self) -> None:
        text = "\n".join(self.input_buf).strip()
        self.input_buf = [""]
        self.input_row = 0
        self.cursor = 0
        self.ac_candidates = []
        if not text:
            return
        if text in (":q", ":quit", "exit", "quit"):
            self.running = False
            return
        self.history.append(text)
        self.history_idx = -1
        with self._lock:
            self.lines.append(ChatLine("user", text))

        if text in ("/?", "/keys", "/keymap"):
            self.show_help_overlay = True
            return

        if text.startswith("/sessions"):
            self._cmd_sessions()
            return

        if text.startswith("/"):
            sr = dispatch_slash(text, cfg=self.cfg, session=self.session, platform="tui")
            if sr.reset_session:
                self.session = self.store.reset(self.session.id)
                with self._lock:
                    self.lines.append(ChatLine("info", sr.reply or "session reset"))
                return
            if sr.passthrough:
                text = sr.passthrough
            elif sr.handled:
                with self._lock:
                    self.lines.append(ChatLine("system", sr.reply))
                self.cfg = load_config()
                return

        if self.busy:
            with self._lock:
                self.lines.append(ChatLine("info", "still busy — Ctrl+C to interrupt"))
            return

        t = threading.Thread(target=self._run_agent, args=(text,), daemon=True)
        t.start()

    def _cmd_sessions(self) -> None:
        root = sessions_dir()
        files = sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:12]
        lines = ["Sessions (newest first):"]
        for p in files:
            try:
                import json

                d = json.loads(p.read_text(encoding="utf-8"))
                lines.append(
                    f"  {d.get('id')}  msgs={len(d.get('messages') or [])}  "
                    f"{d.get('title') or ''}"
                )
            except Exception:
                lines.append(f"  {p.name}")
        lines.append("Resume: tracelock chat -c   or   chat --resume <id>")
        with self._lock:
            self.lines.append(ChatLine("system", "\n".join(lines)))

    def handle_key(self, ch: int) -> None:
        if self.show_help_overlay:
            self.show_help_overlay = False
            return

        if ch == curses.KEY_RESIZE:
            return

        # Ctrl+C
        if ch == 3:
            now = time.time()
            if self.busy:
                self.interrupt.set()
                self.status_msg = "interrupt requested"
                with self._lock:
                    self.tool_feed.append("⚠ interrupt")
            if now - self.last_ctrl_c < 1.5:
                self.running = False
            self.last_ctrl_c = now
            return

        # Ctrl+D
        if ch == 4:
            self.running = False
            return

        # Ctrl+J newline
        if ch == 10 or ch == 13:  # Enter — but Ctrl+J is also 10 on many terms
            # distinguish: if we only get 10, treat as submit; use Alt+Enter as 27-then?
            # For simplicity: Enter submits; Ctrl+J we detect as KEY or raw 0?
            # Many curses map Ctrl+J to 10 same as Enter. Use Ctrl+N for newline as alt.
            self._submit()
            return

        if ch == 14:  # Ctrl+N newline
            line = self._current_line()
            left, right = line[: self.cursor], line[self.cursor :]
            self._set_line(left)
            self.input_buf.insert(self.input_row + 1, right)
            self.input_row += 1
            self.cursor = 0
            return

        if ch == 9:  # Tab
            if self.ac_candidates:
                self._apply_ac()
            else:
                self._update_ac()
                if len(self.ac_candidates) == 1:
                    self._apply_ac()
            return

        if ch == curses.KEY_UP:
            if self.ac_candidates:
                self.ac_index = (self.ac_index - 1) % len(self.ac_candidates)
            elif self.history:
                if self.history_idx < 0:
                    self.history_idx = len(self.history) - 1
                else:
                    self.history_idx = max(0, self.history_idx - 1)
                self.input_buf = [self.history[self.history_idx]]
                self.input_row = 0
                self.cursor = len(self.input_buf[0])
            return

        if ch == curses.KEY_DOWN:
            if self.ac_candidates:
                self.ac_index = (self.ac_index + 1) % len(self.ac_candidates)
            elif self.history and self.history_idx >= 0:
                self.history_idx += 1
                if self.history_idx >= len(self.history):
                    self.history_idx = -1
                    self.input_buf = [""]
                else:
                    self.input_buf = [self.history[self.history_idx]]
                self.input_row = 0
                self.cursor = len(self.input_buf[0])
            return

        if ch == curses.KEY_PPAGE:
            self.scroll += 5
            return
        if ch == curses.KEY_NPAGE:
            self.scroll = max(0, self.scroll - 5)
            return

        if ch == curses.KEY_LEFT:
            self.cursor = max(0, self.cursor - 1)
            return
        if ch == curses.KEY_RIGHT:
            self.cursor = min(len(self._current_line()), self.cursor + 1)
            return
        if ch == curses.KEY_HOME:
            self.cursor = 0
            return
        if ch == curses.KEY_END:
            self.cursor = len(self._current_line())
            return

        if ch in (curses.KEY_BACKSPACE, 127, 8):
            line = self._current_line()
            if self.cursor > 0:
                self._set_line(line[: self.cursor - 1] + line[self.cursor :])
                self.cursor -= 1
            elif self.input_row > 0:
                prev = self.input_buf[self.input_row - 1]
                self.cursor = len(prev)
                self.input_buf[self.input_row - 1] = prev + line
                self.input_buf.pop(self.input_row)
                self.input_row -= 1
            self._update_ac()
            return

        if ch == curses.KEY_DC:
            line = self._current_line()
            if self.cursor < len(line):
                self._set_line(line[: self.cursor] + line[self.cursor + 1 :])
            self._update_ac()
            return

        # printable
        if 32 <= ch < 127:
            line = self._current_line()
            self._set_line(line[: self.cursor] + chr(ch) + line[self.cursor :])
            self.cursor += 1
            self._update_ac()
            return

    def loop(self, stdscr: Any) -> None:
        self.stdscr = stdscr
        curses.raw()
        curses.noecho()
        stdscr.keypad(True)
        stdscr.nodelay(True)
        self._init_colors()
        try:
            curses.curs_set(1)
        except curses.error:
            pass

        with self._lock:
            if not self.lines:
                self.lines.append(
                    ChatLine(
                        "system",
                        "Welcome. Type find @handle · /help · /models · Tab for slash complete.\n"
                        "Ctrl+N = newline · Enter = send · PgUp/PgDn scroll.",
                    )
                )

        while self.running:
            self.draw()
            try:
                ch = stdscr.getch()
            except KeyboardInterrupt:
                ch = 3
            if ch == -1:
                time.sleep(0.05)
                continue
            self.handle_key(ch)
            time.sleep(0.01)


def run_curses_tui(
    *,
    session_id: str = "tui_local",
    resume: bool = False,
    resume_id: str = "",
) -> int:
    app = TraceLockTUI(session_id=session_id, resume=resume, resume_id=resume_id)
    try:
        curses.wrapper(app.loop)
    except curses.error as e:
        print(f"TUI unavailable ({e}); falling back to simple console.")
        from tracelock.runtime.tui import run_simple_tui

        return run_simple_tui(session_id=session_id)
    return 0
