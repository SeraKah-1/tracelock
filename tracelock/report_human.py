"""Human-readable OSINT report — clean executive format, not raw dossier dump."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _seed_lines(seeds: list[dict[str, Any]]) -> list[str]:
    out = []
    for s in seeds:
        t = s.get("type") or "other"
        v = s.get("normalized") or s.get("value") or ""
        if not v:
            continue
        label = {
            "name": "Nama",
            "username": "Handle / username",
            "phone": "Telepon",
            "url": "URL",
            "email": "Email",
            "nim": "NIM",
            "other": "Catatan",
        }.get(t, t)
        out.append(f"- **{label}:** {v}")
    return out or ["- (tidak ada seed)"]


def _status_id(s: str) -> str:
    s = (s or "open").lower()
    return {
        "open": "Belum terkunci",
        "partial": "Sebagian (perlu multi-sinyal)",
        "locked": "Terkunci",
        "high": "Tinggi",
        "clean_public_demo": "Bersih (jalur demo)",
    }.get(s, s)


def _clean_web_title(title: str) -> str:
    t = re.sub(r"\s+", " ", (title or "")).strip()
    # drop obvious garbage SERP noise
    bad = (
        "no_parseable",
        "api.flow.microsoft",
        "preview.api.flow",
        "gps coordinate",
        "latitude",
        "longitude",
        "google maps",
    )
    low = t.lower()
    if any(b in low for b in bad):
        return ""
    if len(t) < 4:
        return ""
    return t[:140]


def _web_hits(evidence: list[dict[str, Any]], limit: int = 12) -> list[str]:
    rows = []
    seen: set[str] = set()
    for e in evidence:
        if not isinstance(e, dict) or e.get("type") != "web_hit":
            continue
        val = e.get("value") if isinstance(e.get("value"), dict) else {}
        title = _clean_web_title(str(val.get("title") or val.get("snippet") or ""))
        url = e.get("source_url") or val.get("url") or ""
        if not title and not url:
            continue
        key = title or url
        if key in seen:
            continue
        seen.add(key)
        if title and url:
            rows.append(f"- {title}\n  - {url}")
        elif title:
            rows.append(f"- {title}")
        else:
            rows.append(f"- {url}")
        if len(rows) >= limit:
            break
    return rows


def _platform_hits(evidence: list[dict[str, Any]]) -> list[str]:
    rows = []
    seen: set[str] = set()
    for e in evidence:
        if not isinstance(e, dict):
            continue
        if e.get("type") not in ("username_platform_hit",):
            continue
        val = e.get("value") if isinstance(e.get("value"), dict) else {}
        plat = val.get("platform") or "?"
        handle = val.get("handle") or "?"
        url = val.get("url") or ""
        key = f"{plat}:{handle}"
        if key in seen:
            continue
        seen.add(key)
        status = val.get("http_status")
        note = f"HTTP {status}" if status else "probe"
        if url:
            rows.append(f"- **{plat}** `@{handle}` — {note} — {url}")
        else:
            rows.append(f"- **{plat}** `@{handle}` — {note}")
    return rows


def _phone_bits(evidence: list[dict[str, Any]], seeds: list[dict[str, Any]]) -> list[str]:
    lines = []
    for s in seeds:
        if s.get("type") == "phone":
            lines.append(f"- E.164 / normalized: `{s.get('normalized') or s.get('value')}`")
    for e in evidence:
        if not isinstance(e, dict):
            continue
        t = e.get("type") or ""
        val = e.get("value") if isinstance(e.get("value"), dict) else {}
        if t == "phone_normalize" or "e164" in val:
            e164 = val.get("e164") or (val.get("record") or {}).get("e164")
            if e164:
                lines.append(f"- Normalized: `{e164}`")
            pref = val.get("prefix") or (val.get("record") or {}).get("prefix") or {}
            if isinstance(pref, dict) and pref.get("provider_hint"):
                lines.append(
                    f"- Prefix soft (bukan domisili): {pref.get('provider_hint')} "
                    f"({pref.get('note') or 'portability possible'})"
                )
    # unique
    out, seen = [], set()
    for x in lines:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _hitl_section(gates: list[dict[str, Any]]) -> list[str]:
    open_g = [g for g in gates if isinstance(g, dict) and g.get("status") == "open"]
    done_g = [g for g in gates if isinstance(g, dict) and g.get("status") == "completed"]
    lines = []
    if not gates:
        lines.append("Tidak ada gate HITL yang dibuka pada run ini.")
        return lines
    if open_g:
        lines.append(f"**Menunggu operator ({len(open_g)}):**")
        for g in open_g:
            url = g.get("url") or ""
            why = g.get("why") or g.get("reason") or ""
            lines.append(
                f"- `{g.get('id')}` · **{g.get('kind') or g.get('source')}** — {why}"
            )
            if url:
                lines.append(f"  - Buka: {url}")
    if done_g:
        lines.append(f"**Selesai ({len(done_g)}):**")
        for g in done_g[:8]:
            lines.append(
                f"- `{g.get('id')}` · {g.get('kind') or g.get('source')} — completed"
            )
    lines.append("")
    lines.append(
        "_Captcha / portal / e-wallet Layer-B tidak pernah diselesaikan otomatis._"
    )
    return lines


def _plain_summary(
    seeds: list[dict[str, Any]],
    dims: dict[str, Any],
    web: list[str],
    platforms: list[str],
    hitl_open: int,
) -> str:
    """2–4 sentence plain language blurb."""
    names = [
        (s.get("normalized") or s.get("value") or "")
        for s in seeds
        if s.get("type") == "name"
    ]
    handles = [
        (s.get("normalized") or s.get("value") or "")
        for s in seeds
        if s.get("type") == "username"
    ]
    phones = [
        (s.get("normalized") or s.get("value") or "")
        for s in seeds
        if s.get("type") == "phone"
    ]
    subj = names[0] if names else (f"@{handles[0]}" if handles else (phones[0] if phones else "subjek"))
    dig = (dims.get("identity_digital") or {}).get("status") or "open"
    civ = (dims.get("identity_civil") or {}).get("status") or "open"
    parts = [
        f"Laporan investigasi publik untuk **{subj}**.",
        f"Jejak digital: **{_status_id(dig)}**"
        + (f" ({len(platforms)} indikasi platform)" if platforms else "")
        + ".",
        f"Identitas sipil (nama legal / institusi): **{_status_id(civ)}** — "
        "belum disamakan dengan akun digital kecuali multi-sinyal + HITL.",
    ]
    if web:
        parts.append(f"Ditemukan **{len(web)}** sebutan publik relevan di web (filter noise).")
    if hitl_open:
        parts.append(
            f"Ada **{hitl_open}** langkah yang menunggu manusia (portal/captcha/Layer-B)."
        )
    else:
        parts.append("Tidak ada gate HITL terbuka, atau belum diperlukan.")
    return " ".join(parts)


def build_human_report(state: dict[str, Any]) -> dict[str, str]:
    """Return human_md (main) + brief_txt (very short) + technical_md (appendix)."""
    seeds = [s for s in (state.get("seeds") or []) if isinstance(s, dict)]
    evidence = [e for e in (state.get("evidence") or []) if isinstance(e, dict)]
    gates = [g for g in (state.get("hitl_gates") or []) if isinstance(g, dict)]
    dossier = state.get("agent_dossier") or {}
    dims = dossier.get("dimensions") if isinstance(dossier, dict) else {}
    if not isinstance(dims, dict):
        dims = {}

    web = _web_hits(evidence)
    platforms = _platform_hits(evidence)
    phone_lines = _phone_bits(evidence, seeds)
    hitl_open = sum(1 for g in gates if g.get("status") == "open")
    inv = state.get("investigation_id") or "—"
    loop = state.get("investigation_loop") or {}

    # --- Human report ---
    h: list[str] = []
    h.append("# Laporan OSINT (Ringkas)")
    h.append("")
    h.append(f"**Dibuat:** {_utc_now()}  ")
    h.append(f"**Case ID:** `{inv}`  ")
    h.append("**Sumber:** publik saja · **Digital ≠ sipil** · tanpa breach/NIK")
    h.append("")
    h.append("---")
    h.append("")
    h.append("## Ringkasan eksekutif")
    h.append("")
    h.append(_plain_summary(seeds, dims, web, platforms, hitl_open))
    h.append("")
    h.append("## Apa yang dimasukkan (seed)")
    h.append("")
    h.extend(_seed_lines(seeds))
    h.append("")
    h.append("## Status identitas")
    h.append("")
    h.append("| Lapisan | Status | Arti singkat |")
    h.append("|---------|--------|--------------|")
    for key, label in (
        ("identity_digital", "Digital (akun / handle)"),
        ("identity_civil", "Sipil (nama legal / institusi)"),
        ("phone", "Telepon"),
        ("education", "Pendidikan"),
        ("risk_notes", "Catatan risiko publik"),
    ):
        body = dims.get(key) or {}
        st = body.get("status") if isinstance(body, dict) else "open"
        h.append(f"| {label} | `{st}` | {_status_id(str(st))} |")
    h.append("")
    h.append("## Jejak digital (platform)")
    h.append("")
    if platforms:
        h.extend(platforms)
    else:
        h.append("_Belum ada indikasi platform yang lolos probe (atau seed tanpa handle)._")
    h.append("")
    h.append("## Temuan web publik (disaring)")
    h.append("")
    if web:
        h.extend(web)
    else:
        h.append(
            "_Belum ada hit web yang lolos filter noise, atau collection belum dijalankan live._"
        )
    h.append("")
    if phone_lines:
        h.append("## Telepon")
        h.append("")
        h.extend(phone_lines)
        h.append("")
        h.append(
            "_Prefix operator = soft clue, bukan alamat domisili. Layer-B e-wallet = HITL saja._"
        )
        h.append("")
    # Detective triangulation / lead graph
    graph = state.get("lead_graph") or {}
    nodes = [n for n in (graph.get("nodes") or []) if isinstance(n, dict)]
    tri = state.get("triangulation") or {}
    if nodes or tri:
        h.append("## Jalur pivot (triangulasi)")
        h.append("")
        h.append(
            "Setiap temuan bisa membuka pintu baru (akun kedua, sekolah, domisili, "
            "dokumen publik) — bukan satu kali search lurus."
        )
        h.append("")
        pivots = [n for n in nodes if n.get("role") in ("pivot", "anchor_hint")]
        if pivots:
            for n in pivots[:18]:
                why = n.get("why") or ""
                h.append(
                    f"- **{n.get('kind')}** `{n.get('value')}` "
                    f"— {why} · role={n.get('role')}"
                )
        else:
            h.append(
                f"_Lead pool dipindai; promoted={tri.get('promoted_count', 0)} "
                f"nodes={tri.get('nodes', len(nodes))}._"
            )
        h.append("")
    h.append("## Yang perlu dilakukan manusia (HITL)")
    h.append("")
    h.extend(_hitl_section(gates))
    h.append("")
    h.append("## Kesimpulan & batasan")
    h.append("")
    h.append(
        "1. Laporan ini **bukan** vonis identitas sipil. "
        "Akun digital dan nama di seed harus dikunci terpisah."
    )
    h.append(
        "2. Hit web/platform bersifat **indikasi** (perlu koroborasi wajah/bio/multi-sumber)."
    )
    h.append(
        "3. Noise SERP (maps/GPS/API) sudah difilter; sisa temuan tetap perlu dicek manual."
    )
    if loop.get("wave"):
        h.append(
            f"4. Continuous loop: wave **{loop.get('wave')}** "
            f"(gaps: {', '.join(loop.get('gaps') or []) or '—'})."
        )
    if tri.get("promoted_count"):
        h.append(
            f"5. Triangulasi: **{tri.get('promoted_count')}** pivot dipromosikan "
            f"dari {tri.get('lead_pool', 0)} lead kandidat."
        )
    h.append("")
    h.append("---")
    h.append("")
    h.append("_TraceLock · laporan manusia · lampiran teknis di bawah jika diperlukan._")

    human_md = "\n".join(h)

    # --- Brief (chat-friendly) ---
    brief_lines = [
        f"OSINT ringkas — {inv}",
        _plain_summary(seeds, dims, web, platforms, hitl_open),
        "",
        "Seed:",
    ]
    for line in _seed_lines(seeds):
        brief_lines.append("  " + line.lstrip("- "))
    if platforms:
        brief_lines.append("Platform (indikasi):")
        for p in platforms[:6]:
            brief_lines.append("  " + p.lstrip("- "))
    if web:
        brief_lines.append("Web (top):")
        for w in web[:5]:
            brief_lines.append("  " + w.split("\n")[0].lstrip("- "))
    if hitl_open:
        brief_lines.append(f"HITL terbuka: {hitl_open} (selesaikan di cockpit/browser)")
    if tri.get("promoted_count"):
        brief_lines.append(
            f"Pivots: {tri.get('promoted_count')} lead baru (triangulasi multi-hop)"
        )
    brief_txt = "\n".join(brief_lines)

    # --- Technical appendix (compact, not full dump) ---
    tech = [
        "# Lampiran teknis (ringkas)",
        "",
        f"Evidence count: {len(evidence)}",
        f"Types: {dict(Counter(e.get('type') for e in evidence))}",
        "",
        "## Dimension signals (raw)",
    ]
    for name, body in dims.items():
        if not isinstance(body, dict):
            continue
        tech.append(f"### {name} [{body.get('status')}]")
        for sig in (body.get("signals") or [])[:8]:
            tech.append(f"- {sig}")
    tech.append("")
    tech.append("## Evidence IDs (last 15)")
    for e in evidence[-15:]:
        tech.append(
            f"- {e.get('id')} · {e.get('type')} · {e.get('source_name')}"
        )
    technical_md = "\n".join(tech)

    return {
        "human_md": human_md,
        "brief_txt": brief_txt,
        "technical_md": technical_md,
        "combined_md": human_md + "\n\n" + technical_md,
    }
