"""Indonesian (and light global) *public* government source pack for OSINT.

Source-of-truth orient: courts, corporate registry, procurement, academic index,
election transparency — **passive public paths only**.

HARD BOUNDARIES (enforced by design):
- No IDOR / sequential ID brute-force of .go.id profil URLs
- No admin panel / grey-area undocumented API probing (e.g. admin.ahu abuse)
- No mass NIK harvesting playbooks; NIK may appear in *public* court/PDF
  materials — treat under purpose limitation + local law
- No captcha bypass services; use HITL / real browser when challenged
- Prefer Google dorks + single document review over aggressive scanners
"""

from __future__ import annotations

from typing import Any


# Catalog: routing metadata for clue_analyze + gov_id collector
GOV_CATALOG: dict[str, dict[str, Any]] = {
    "pddikti": {
        "jurisdiction": "ID",
        "label": "PDDIKTI (higher education index)",
        "dimension": "education",
        "portals": [
            "https://pddikti.kemdiktisaintek.go.id/",
            "https://pddikti.kemdikbud.go.id/",
        ],
        "why": "Official student/lecturer/PT registration — good for CV/academic claims",
        "passive_only": True,
        "hitl_source": "pddikti",
        "optional_api": "parse_bot_pddikti",
    },
    "putusan_ma": {
        "jurisdiction": "ID",
        "label": "Mahkamah Agung putusan directory",
        "dimension": "risk",
        "portals": ["https://putusan3.mahkamahagung.go.id/"],
        "why": "Public court decisions; names/parties as published by the court",
        "passive_only": True,
        "hitl_source": "putusan_ma",
    },
    "ahu": {
        "jurisdiction": "ID",
        "label": "AHU / badan hukum (Kemenkumham)",
        "dimension": "work",
        "portals": ["https://ahu.go.id/"],
        "why": "Public company/yayasan officers and corporate shells as published",
        "passive_only": True,
        "hitl_source": "ahu",
        "forbid": [
            "admin.ahu undocumented API abuse",
            "credential reuse",
            "IDOR enumeration of private records",
        ],
    },
    "lpse": {
        "jurisdiction": "ID",
        "label": "LPSE procurement / tender",
        "dimension": "work",
        "portals": ["https://lpse.lkpp.go.id/"],
        "why": "Public tender winners and attachments often list company contacts",
        "passive_only": True,
        "hitl_source": "lpse",
        "forbid": ["mass multi-LPSE port scanning", "nmap/nikto against gov hosts"],
    },
    "kpu": {
        "jurisdiction": "ID",
        "label": "KPU / election transparency materials",
        "dimension": "notable",
        "portals": ["https://infopemilu.kpu.go.id/"],
        "why": "Public caleg/DCT PDFs during election cycles — only when relevant",
        "passive_only": True,
        "hitl_source": "kpu",
        "forbid": ["voter roll scraping", "non-public KPU systems"],
    },
    "companies_house_uk": {
        "jurisdiction": "UK",
        "label": "UK Companies House",
        "dimension": "work",
        "portals": ["https://find-and-update.company-information.service.gov.uk/"],
        "why": "PSC, officers, filings — strong public corporate truth",
        "passive_only": True,
        "hitl_source": "generic",
    },
    "sec_edgar": {
        "jurisdiction": "US",
        "label": "SEC EDGAR",
        "dimension": "work",
        "portals": ["https://www.sec.gov/edgar/search/"],
        "why": "Public company filings / insider reports",
        "passive_only": True,
        "hitl_source": "generic",
    },
    "courtlistener": {
        "jurisdiction": "US",
        "label": "CourtListener (public PACER-derived)",
        "dimension": "risk",
        "portals": ["https://www.courtlistener.com/"],
        "why": "US federal court opinions/dockets that are public",
        "passive_only": True,
        "hitl_source": "generic",
    },
}


# Policy text agents must keep in reports
GOV_POLICY = {
    "mode": "passive_public",
    "forbid": [
        "IDOR sequential ID brute-force on .go.id profile URLs",
        "Aggressive port/vuln scanning of government hosts",
        "Captcha solving services / headless captcha farms",
        "Undocumented admin APIs or credential stuffing",
        "Mass NIK database assembly as a product goal",
    ],
    "prefer": [
        "Official public search UIs + HITL when challenged",
        "site: / filetype: PDF dorks for single-document review",
        "Wayback for removed-but-once-public pages",
        "Local PDF metadata/text extraction after single download",
        "Optional maintained third-party wrappers only with explicit API key + ToS awareness",
    ],
}


def directed_queries(name: str, sources: list[str] | None = None) -> list[dict[str, str]]:
    """Build passive directed search queries for a person/org name."""
    n = (name or "").strip()
    if not n or len(n) < 3:
        return []
    qn = n.replace('"', "")
    all_src = sources or ["pddikti", "putusan_ma", "ahu", "lpse", "kpu"]
    out: list[dict[str, str]] = []
    templates: dict[str, list[tuple[str, str]]] = {
        "pddikti": [
            ("web", f'"{qn}" PDDIKTI'),
            ("web", f'"{qn}" site:pddikti.kemdikbud.go.id'),
            ("web", f'"{qn}" site:pddikti.kemdiktisaintek.go.id'),
        ],
        "putusan_ma": [
            ("web", f'"{qn}" site:putusan3.mahkamahagung.go.id'),
            ("web", f'"{qn}" putusan (pidana OR perdata OR cerai)'),
            ("web", f'"{qn}" filetype:pdf site:mahkamahagung.go.id'),
        ],
        "ahu": [
            ("web", f'"{qn}" site:ahu.go.id'),
            ("web", f'"{qn}" (PT OR CV OR Yayasan) (direksi OR komisaris)'),
        ],
        "lpse": [
            ("web", f'"{qn}" site:lpse.go.id'),
            ("web", f'site:lpse.*.go.id "{qn}"'),
            ("web", f'"{qn}" (pemenang tender OR LPSE OR pengadaan)'),
        ],
        "kpu": [
            ("web", f'"{qn}" filetype:pdf site:kpu.go.id'),
            ("web", f'"{qn}" (DCT OR caleg OR bacaleg) site:kpu.go.id'),
        ],
        "companies_house_uk": [
            ("web", f'"{qn}" site:company-information.service.gov.uk'),
        ],
        "sec_edgar": [
            ("web", f'"{qn}" site:sec.gov/Archives'),
        ],
        "courtlistener": [
            ("web", f'"{qn}" site:courtlistener.com'),
        ],
    }
    for src in all_src:
        for kind, query in templates.get(src, []):
            out.append({"source": src, "kind": kind, "query": query})
    return out


def catalog_for_plan(include_global: bool = False) -> list[dict[str, Any]]:
    rows = []
    for key, meta in GOV_CATALOG.items():
        if not include_global and meta.get("jurisdiction") not in ("ID",):
            continue
        rows.append(
            {
                "source": key,
                "label": meta["label"],
                "dimension": meta["dimension"],
                "why": meta["why"],
                "portals": meta["portals"],
                "passive_only": True,
            }
        )
    return rows
