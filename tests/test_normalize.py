"""Tests for shipped normalize helpers."""

from osint_cli.normalize import add_seed, detect_type, normalize_value
from osint_cli.state import new_investigation


def test_detect_and_normalize_email_username():
    assert detect_type("Alice@Example.COM") == "email"
    assert normalize_value("email", "Alice@Example.COM") == "alice@example.com"
    assert detect_type("@Bob_99") == "username"
    assert normalize_value("username", "@Bob_99") == "bob_99"
    assert detect_type("https://github.com/x") == "url"


def test_add_seed_dedupes():
    st = new_investigation("/tmp/case-test.json")
    a = add_seed(st, "email:Foo@Bar.com")
    b = add_seed(st, "email:foo@bar.com")
    assert a["id"] == b["id"]
    assert len(st["seeds"]) == 1
    add_seed(st, "username:foo")
    assert len(st["seeds"]) == 2
