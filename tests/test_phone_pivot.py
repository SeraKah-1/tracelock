"""Phone clue: normalize, dedupe, plan route, offline footprint."""

from osint_cli.clue_analyze import analyze_clues
from osint_cli.collect import MODULE_MAP, run_collect
from osint_cli.normalize import add_seed, detect_type, normalize_value
from osint_cli.phone_pivot import (
    build_footprint_queries,
    hitl_phone_checklist,
    normalize_phone_record,
)
from osint_cli.state import new_investigation


def test_detect_phone_bare_and_typed():
    assert detect_type("081160600613") == "phone"
    assert detect_type("+62 811-60600-613") == "phone"
    assert detect_type("phone:0811-60600-613".split(":", 1)[1]) == "phone"


def test_normalize_id_to_e164():
    assert normalize_value("phone", "0811-60600-613") == "+6281160600613"
    assert normalize_value("phone", "6281160600613") == "+6281160600613"
    assert normalize_value("phone", "+62 811 60600 613") == "+6281160600613"
    rec = normalize_phone_record("0811-60600-613")
    assert rec["ok"] is True
    assert rec["e164"] == "+6281160600613"
    assert rec["national"] == "081160600613"
    assert rec["prefix"]["provider_hint"] == "Telkomsel"
    assert any(v.startswith("0") for v in rec["variants"])


def test_phone_seed_dedupe_across_forms():
    st = new_investigation("/tmp/phone-dedupe.json")
    a = add_seed(st, "phone:0811-60600-613")
    b = add_seed(st, "phone:+6281160600613")
    c = add_seed(st, "phone:6281160600613")
    assert a["id"] == b["id"] == c["id"]
    assert len(st["seeds"]) == 1
    assert a["normalized"] == "+6281160600613"
    assert a.get("meta", {}).get("phone_parse", {}).get("e164") == "+6281160600613"


def test_footprint_queries_and_checklist():
    rec = normalize_phone_record("081160600613")
    qs = build_footprint_queries(rec)
    assert any("0811" in q or "62811" in q for q in qs)
    assert any("wa.me" in q for q in qs)
    cl = hitl_phone_checklist(rec)
    assert cl["layer"] == "B"
    assert any(s["id"] == "B1_wallet_name_preview" for s in cl["steps"])
    assert "breach_bot_nik_address" in cl["forbidden"]


def test_plan_has_phone_route():
    st = new_investigation("/tmp/phone-plan.json")
    add_seed(st, "phone:0811-60600-613")
    a = analyze_clues(st)
    assert a["summary"]["has_phone_route"] is True
    blob = str(a).lower()
    assert "phone_footprint" in blob
    assert "phone_breach" in blob or "breach" in blob
    p0 = [q for q in a["questions"] if q["priority"] == 0]
    assert any("phone" in q["text"].lower() for q in p0)


def test_offline_phone_footprint_collect():
    st = new_investigation("/tmp/phone-collect.json")
    s = add_seed(st, "phone:0811-60600-613")
    assert "phone_footprint" in MODULE_MAP
    result = run_collect(
        st,
        modules=["phone_footprint"],
        offline=True,
        seed_ids=[s["id"]],
    )
    assert "phone_footprint" in result["modules_run"]
    types = {e.get("type") for e in st["evidence"]}
    assert "phone_meta" in types
    assert "phone_hitl_plan" in types
    assert any(e.get("type") == "web_hit" for e in st["evidence"])
