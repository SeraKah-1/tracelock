"""Campus list ingest: EPT / distribusi / class lists → structured rows + filters.

Agents paste or point at public text extracts (pdfcoffee, OCR, HITL HTML).
Does not scrape Scribd paywalls or bypass captchas.
"""

from __future__ import annotations

import re
from typing import Any


# UNRI-style NIM: 11 digits starting with 25 (year 2025) etc.
_NIM_RE = re.compile(r"\b(2[0-9]{10})\b")
# Row: NIM + NAME (greedy until trailing sex and/or known prodi tokens)
_ROW_RE = re.compile(
    r"(?P<nim>2[0-9]{10})\s+"
    r"(?P<nama>[A-Z][A-Z\s\.\']{2,80}?)"
    r"(?=\s+(?:[LP]\b|FISIP|FK\b|FEB|FMIPA|FT\b|FKIP|FH\b|ILMU\s+KOMUNIKASI|KEDOKTERAN)|$|\n)"
    r"(?:\s+(?P<sex>[LP]))?"
    r"(?:\s+(?P<prodi>FISIP|FK|FEB|FMIPA|FT|FKIP|FH|FAPERTA|FASILKOM|ILMU\s+KOMUNIKASI|KEDOKTERAN)[^\n]*)?",
    re.I | re.M,
)
_CEL_FAMILY = re.compile(r"\b(CEL|CEC|CELIA|CECIL|CELL|CELSA|ALICIA)\w*", re.I)


def parse_campus_list_text(text: str, source_label: str = "campus_list") -> list[dict[str, Any]]:
    """Extract student-like rows from free text."""
    if not text:
        return []
    # normalize whitespace for line-oriented parse
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for m in _ROW_RE.finditer(text):
        nim = m.group("nim")
        nama = re.sub(r"\s+", " ", m.group("nama")).strip(" .")
        # drop if nama too short or looks like header
        if len(nama) < 3 or nama.upper() in ("NAMA", "PROGRAM STUDI", "FAK"):
            continue
        key = f"{nim}|{nama.upper()}"
        if key in seen:
            continue
        seen.add(key)
        sex = (m.group("sex") or "").upper() or None
        prodi_raw = (m.group("prodi") or "").strip()
        rows.append(
            {
                "nim": nim,
                "nama": nama.upper(),
                "sex": sex,
                "prodi_hint": prodi_raw.upper() if prodi_raw else None,
                "source_label": source_label,
            }
        )

    # fallback: NIM + following capitals on same line
    if len(rows) < 3:
        for line in text.splitlines():
            nm = _NIM_RE.search(line)
            if not nm:
                continue
            nim = nm.group(1)
            rest = line[nm.end() :].strip()
            # take first name-like chunk
            m2 = re.match(r"([A-Z][A-Z\s\.\']{2,60})", rest)
            if not m2:
                continue
            nama = re.sub(r"\s+", " ", m2.group(1)).strip()
            key = f"{nim}|{nama}"
            if key in seen or len(nama) < 3:
                continue
            seen.add(key)
            rows.append(
                {
                    "nim": nim,
                    "nama": nama,
                    "sex": None,
                    "prodi_hint": None,
                    "source_label": source_label,
                }
            )

    return rows


def filter_ilkom(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        p = (r.get("prodi_hint") or "") + " " + (r.get("nama") or "")
        nim = r.get("nim") or ""
        # UNRI Ilkom often 25011x
        if "KOMUNIKASI" in p.upper() or "FISIP" in p.upper():
            out.append(r)
        elif re.match(r"25011\d{6}", nim):
            r = dict(r)
            r["prodi_hint"] = r.get("prodi_hint") or "FISIP_ILKOM_HEURISTIC_NIM"
            out.append(r)
    return out


def grep_name_family(
    rows: list[dict[str, Any]],
    pattern: str | None = None,
) -> list[dict[str, Any]]:
    """Default: Cel/Cec family; or custom regex."""
    rx = re.compile(pattern, re.I) if pattern else _CEL_FAMILY
    hits = []
    for r in rows:
        nama = r.get("nama") or ""
        if rx.search(nama):
            hits.append(dict(r, match=True))
    return hits


def decode_nim_unri(nim: str) -> dict[str, Any]:
    """Best-effort UNRI NIM decode (heuristic, not official)."""
    if not re.fullmatch(r"2[0-9]{10}", nim or ""):
        return {"nim": nim, "ok": False}
    year = "20" + nim[0:2]
    # faculty-ish codes seen in maba 2025 lists
    fac_map = {
        "01": "FISIP (heuristic)",
        "08": "FK (heuristic)",
        "02": "FEB (heuristic)",
        "03": "FMIPA (heuristic)",
        "04": "FT (heuristic)",
        "05": "FKIP (heuristic)",
    }
    fac = fac_map.get(nim[2:4], f"code_{nim[2:4]}")
    return {
        "nim": nim,
        "ok": True,
        "angkatan_year": year,
        "faculty_code": nim[2:4],
        "faculty_hint": fac,
        "note": "Heuristic decode only — verify against prodi lists",
    }


def ingest_summary(rows: list[dict[str, Any]], greps: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "kind": "campus_list_ingest",
        "row_count": len(rows),
        "ilkom_heuristic_count": len(filter_ilkom(rows)),
        "cel_family_hits": greps,
        "sample_rows": rows[:15],
        "nim_decodes_sample": [decode_nim_unri(r["nim"]) for r in rows[:5]],
        "policy": {
            "not_civil_identity_for_subject": True,
            "use_for_cohort_reverse": True,
        },
    }
