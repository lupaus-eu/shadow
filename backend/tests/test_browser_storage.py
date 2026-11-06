"""The cookies the backend sets must be the ones the browser storage notice lists (ADR-0041)."""
import json
import re
from pathlib import Path

from app.auth import AuthSettings

BACKEND = Path(__file__).resolve().parents[1]
LISTED = json.loads((BACKEND / "legal" / "browser-storage.json").read_text(encoding="utf-8"))
FIX = "Update backend/legal/browser-storage.json and the browser storage notice (backend/legal/storage.*.md) in the same change."


def _cookie_names(call: str) -> set[str]:
    names = set()
    for source in sorted((BACKEND / "app").glob("*.py")):
        text = source.read_text(encoding="utf-8")
        for match in re.finditer(rf"\.{call}\(\s*([^,\)\n]+)", text):
            argument = match.group(1).strip()
            if argument.startswith(("settings.", "auth_settings.")):
                names.add(getattr(AuthSettings(), argument.split(".", 1)[1]))
            else:
                names.add(argument.strip("\"'"))
    return names


def test_the_cookies_the_code_sets_are_exactly_the_listed_ones() -> None:
    listed = {cookie["name"] for cookie in LISTED["cookies"]}
    setting = _cookie_names("set_cookie")
    assert setting, "the scan found no set_cookie call; has the code moved?"
    assert setting == listed, f"set_cookie names {sorted(setting)} differ from the list {sorted(listed)}. {FIX}"


def test_only_listed_cookies_are_deleted() -> None:
    listed = {cookie["name"] for cookie in LISTED["cookies"]}
    assert _cookie_names("delete_cookie") <= listed, FIX


def test_every_listed_cookie_has_a_purpose_and_a_lifetime() -> None:
    for cookie in LISTED["cookies"]:
        assert len(cookie["purpose"]) > 10 and len(cookie["lifetime"]) > 3, cookie["name"]
