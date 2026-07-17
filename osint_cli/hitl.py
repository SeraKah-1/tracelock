"""Human-in-the-loop (HITL) gates for CAPTCHA / browser walls.

Design: agent emits a gate when automation stops honestly; operator unlocks
a real browser (or pastes fields/HTML); agent resumes via evidence import
or optional CDP attach. No captcha farms, no credential stuffing.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from .normalize import add_evidence
from .state import utc_now


def ensure_hitl(state: dict[str, Any]) -> list[dict[str, Any]]:
    if "hitl_gates" not in state or state["hitl_gates"] is None:
        state["hitl_gates"] = []
    return state["hitl_gates"]


def _next_gate_id(state: dict[str, Any]) -> str:
    gates = ensure_hitl(state)
    n = len(gates) + 1
    return f"g{n}"


# Portal templates operators commonly hit during ID person OSINT
PORTAL_TEMPLATES: dict[str, dict[str, Any]] = {
    "pddikti": {
        "url": "https://pddikti.kemdiktisaintek.go.id/",
        "kind": "browser_challenge",
        "expected_fields": [
            "nama",
            "nim",
            "nama_pt",
            "nama_prodi",
            "status",
            "jenjang",
            "tahun_masuk",
        ],
        "checklist": [
            "Open portal in a real browser (not headless automation)",
            "Complete Cloudflare / human verification if shown",
            "Search by full name, then NIM if available",
            "Open matching row(s); copy all public fields",
            "Return via: hitl complete --gate gN --value '{...}'  OR  hitl import-file",
        ],
    },
    "putusan_ma": {
        "url": "https://putusan3.mahkamahagung.go.id/",
        "kind": "portal_search",
        "expected_fields": ["nomor_putusan", "nama_pihak", "tahun", "pengadilan", "pdf_url"],
        "checklist": [
            "Search public putusan by full name (and known aliases)",
            "Record case numbers and PDF links only from public pages",
            "Do not bulk-download entire court databases",
            "Paste summary fields via hitl complete",
        ],
    },
    "ahu": {
        "url": "https://ahu.go.id/",
        "kind": "portal_search",
        "expected_fields": ["nama_badan_hukum", "jenis", "status", "alamat", "pengurus"],
        "checklist": [
            "Use public AHU search / profil PT surfaces only",
            "No admin panels, no credential reuse, no undocumented grey APIs",
            "Record directors/commissioners as published on public pages",
        ],
    },
    "lpse": {
        "url": "https://lpse.lkpp.go.id/",
        "kind": "portal_search",
        "expected_fields": ["nama_lelang", "kode", "instansi", "pemenang", "nilai", "dokumen_url"],
        "checklist": [
            "Search tender/winner pages with company or person name",
            "Prefer site:lpse.*.go.id dorks + single PDF downloads",
            "No aggressive multi-LPSE scanning from one IP",
        ],
    },
    "kpu": {
        "url": "https://infopemilu.kpu.go.id/",
        "kind": "portal_search",
        "expected_fields": ["nama_calon", "dapil", "partai", "dokumen_url"],
        "checklist": [
            "Search public caleg/DCT materials only when relevant",
            "Prefer Google filetype:pdf site:kpu.go.id passive discovery",
            "Do not scrape voter rolls or non-public systems",
        ],
    },
    "generic": {
        "url": "",
        "kind": "manual_fields",
        "expected_fields": [],
        "checklist": [
            "Open the provided URL in a real browser",
            "Complete any human challenge",
            "Copy public fields or save HTML/JSON for import",
        ],
    },
}


def open_gate(
    state: dict[str, Any],
    *,
    source: str = "generic",
    url: str | None = None,
    why: str = "",
    expected_fields: list[str] | None = None,
    seed_ids: list[str] | None = None,
    query_hints: list[str] | None = None,
    kind: str | None = None,
) -> dict[str, Any]:
    """Create an open HITL gate the agent waits on."""
    tpl = PORTAL_TEMPLATES.get(source, PORTAL_TEMPLATES["generic"])
    gate = {
        "id": _next_gate_id(state),
        "status": "open",
        "kind": kind or tpl["kind"],
        "source": source,
        "url": url or tpl.get("url") or "",
        "why": why or f"Human browser required for {source}",
        "expected_fields": expected_fields or list(tpl.get("expected_fields") or []),
        "operator_checklist": list(tpl.get("checklist") or []),
        "query_hints": list(query_hints or []),
        "seed_ids": list(seed_ids or []),
        "created_at": utc_now(),
        "completed_at": None,
        "result_evidence_ids": [],
        "notes": "",
        "cyborg": {
            "recommended": True,
            "cdp_hint": (
                "Start Chrome with --remote-debugging-port=9222 --user-data-dir=$HOME/chrome-osint-profile; "
                "solve challenge manually; then collect --modules browser_cdp "
                "or hitl complete / hitl import-file"
            ),
            "pause_play_hint": (
                "Optional local debug only: Playwright page.pause() with headed browser — "
                "not the default agent path"
            ),
        },
    }
    ensure_hitl(state).append(gate)
    return gate


def list_gates(state: dict[str, Any], status: str | None = None) -> list[dict[str, Any]]:
    gates = ensure_hitl(state)
    if status:
        return [g for g in gates if g.get("status") == status]
    return list(gates)


def get_gate(state: dict[str, Any], gate_id: str) -> dict[str, Any] | None:
    for g in ensure_hitl(state):
        if g.get("id") == gate_id:
            return g
    return None


def cancel_gate(state: dict[str, Any], gate_id: str, notes: str = "") -> dict[str, Any]:
    g = get_gate(state, gate_id)
    if not g:
        raise ValueError(f"gate not found: {gate_id}")
    g["status"] = "cancelled"
    g["completed_at"] = utc_now()
    if notes:
        g["notes"] = notes
    return g


def complete_gate(
    state: dict[str, Any],
    gate_id: str,
    *,
    value: Any,
    grade: str = "full_page",
    url: str | None = None,
    notes: str = "",
    confidence: float | None = None,
) -> dict[str, Any]:
    """Mark gate completed and record graded evidence from operator."""
    g = get_gate(state, gate_id)
    if not g:
        raise ValueError(f"gate not found: {gate_id}")
    if g.get("status") != "open":
        raise ValueError(f"gate {gate_id} is not open (status={g.get('status')})")

    conf_map = {
        "full_page": 0.88,
        "search_snippet": 0.55,
        "portal_metadata": 0.4,
        "operator_clue": 0.35,
    }
    conf = confidence if confidence is not None else conf_map.get(grade, 0.5)

    if isinstance(value, str):
        try:
            parsed: Any = json.loads(value)
        except json.JSONDecodeError:
            parsed = {"text": value}
    else:
        parsed = value

    if isinstance(parsed, dict):
        payload = dict(parsed)
    else:
        payload = {"data": parsed}

    payload["observation_grade"] = grade
    payload["observed_via"] = "hitl_complete"
    payload["hitl_gate_id"] = gate_id
    payload["hitl_source"] = g.get("source")

    item = {
        "type": "public_record",
        "value": payload,
        "source_name": f"hitl:{g.get('source') or 'manual'}",
        "source_url": url or g.get("url") or None,
        "confidence": float(conf),
        "tags": [
            "hitl",
            "human_in_loop",
            f"grade:{grade}",
            f"source:{g.get('source')}",
            "cyborg_path",
        ],
        "seed_ids": list(g.get("seed_ids") or []),
        "identifiers": _idents_from_payload(payload),
        "meta": {"observation_grade": grade, "hitl_gate_id": gate_id},
    }
    ev = add_evidence(state, item)
    g["status"] = "completed"
    g["completed_at"] = utc_now()
    g["notes"] = notes or g.get("notes") or ""
    if ev:
        g["result_evidence_ids"] = [ev["id"]]
    return {"gate": g, "evidence": ev}


def import_file(
    state: dict[str, Any],
    path: str | Path,
    *,
    gate_id: str | None = None,
    source: str = "generic",
    grade: str = "full_page",
    url: str | None = None,
) -> dict[str, Any]:
    """Import operator-saved HTML/JSON/text as evidence; optionally complete a gate."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"import file not found: {p}")
    raw = p.read_text(encoding="utf-8", errors="replace")
    suffix = p.suffix.lower()

    if suffix == ".json":
        try:
            data: Any = json.loads(raw)
        except json.JSONDecodeError:
            data = {"text": raw[:50_000]}
        value: Any = data if isinstance(data, dict) else {"data": data}
    elif suffix in (".html", ".htm"):
        title = None
        m = re.search(r"<title[^>]*>([^<]+)</title>", raw, re.I)
        if m:
            title = re.sub(r"\s+", " ", m.group(1)).strip()[:300]
        value = {
            "format": "html_export",
            "title": title,
            "html_excerpt": raw[:80_000],
            "char_count": len(raw),
            "filename": p.name,
        }
    else:
        value = {
            "format": "text_export",
            "text": raw[:50_000],
            "filename": p.name,
        }

    if gate_id:
        return complete_gate(
            state,
            gate_id,
            value=value,
            grade=grade,
            url=url,
            notes=f"imported from {p.name}",
        )

    # open+complete synthetic path
    gate = open_gate(state, source=source, url=url, why=f"import from {p.name}")
    return complete_gate(
        state,
        gate["id"],
        value=value,
        grade=grade,
        url=url,
        notes=f"imported from {p.name}",
    )


def _idents_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    idents: list[dict[str, Any]] = []
    mapping = {
        "nama": "name",
        "name": "name",
        "nim": "nim",
        "nidn": "nidn",
        "nik": "nik",
        "email": "email",
        "username": "username",
        "nama_pt": "organization",
        "nama_prodi": "other",
    }
    for k, t in mapping.items():
        if payload.get(k):
            idents.append({"type": t, "value": str(payload[k])})
    # nested common shapes
    for key in ("mahasiswa", "student", "data", "fields"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            idents.extend(_idents_from_payload(nested))
        elif isinstance(nested, list):
            for row in nested[:20]:
                if isinstance(row, dict):
                    idents.extend(_idents_from_payload(row))
    # dedupe
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for i in idents:
        key = (i.get("type") or "", str(i.get("value") or "").lower())
        if key in seen or not key[1]:
            continue
        seen.add(key)
        out.append(i)
    return out


def maybe_open_from_collect_block(
    state: dict[str, Any],
    *,
    source: str,
    url: str,
    body_or_note: str,
    seed_ids: list[str] | None = None,
    why: str | None = None,
) -> dict[str, Any] | None:
    """If response looks like Cloudflare/challenge wall, open a HITL gate once per source+url."""
    text = (body_or_note or "").lower()
    blocked = any(
        s in text
        for s in (
            "cf-browser-verification",
            "just a moment",
            "memverifikasi browser",
            "checking your browser",
            "attention required",
            "cloudflare",
            "captcha",
            "access denied",
            "403",
        )
    )
    if not blocked and "challenge" not in text:
        return None

    # avoid duplicate open gates for same source+url
    for g in ensure_hitl(state):
        if (
            g.get("status") == "open"
            and g.get("source") == source
            and (g.get("url") or "") == (url or "")
        ):
            return g

    return open_gate(
        state,
        source=source,
        url=url,
        why=why
        or f"Automated fetch hit browser/captcha wall on {source}; operator real-browser session required",
        seed_ids=seed_ids,
    )


def open_gates_summary(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Compact list for next/status planners."""
    out = []
    for g in list_gates(state, status="open"):
        out.append(
            {
                "id": g["id"],
                "source": g.get("source"),
                "url": g.get("url"),
                "why": g.get("why"),
                "command_hint": (
                    f'hitl complete --gate {g["id"]} --grade full_page '
                    f"--value '{{\"nama\":\"…\"}}'"
                ),
                "import_hint": f"hitl import-file --gate {g['id']} --path ./export.html",
                "cdp_hint": "collect --modules browser_cdp  # after Chrome --remote-debugging-port=9222",
            }
        )
    return out
