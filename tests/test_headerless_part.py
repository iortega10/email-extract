"""Turn 1.12: a part with no ``Content-Type`` is ``text/plain`` (RFC 2045 section 5.2).

The bug: a body part that declared no ``Content-Type`` got no quote analysis and a content
fingerprint over the empty string, because every stage computed the media type as
``(part.content_type or "").strip().lower()`` and saw ``""``. RFC 2045 section 5.2 makes such a
part ``text/plain; charset=us-ascii``; RFC 2046 section 5.1.5 makes a ``multipart/digest`` child
``message/rfc822``. The fix routes every stage through ``emailextract.mediatype``.

These tests run the reproduction and each new header-less fixture end to end through
``assemble`` and compare it, **as data**, with an explicit ``text/plain; charset=us-ascii`` twin
built by inserting the one header the fixture omits -- so the fix is shown to make a header-less
message behave exactly like the message that spells the default out. The mutation cases carry the
anti-vacuity triple (the patched symbol exists, the patch was reached, the observation differs).
"""

from __future__ import annotations

import hashlib
import importlib
import re
from pathlib import Path

import pytest

# ``emailextract/__init__`` re-exports ``assemble`` (the function) under the name
# ``emailextract.assemble``, shadowing the submodule, so the modules are fetched by importlib.
assemble_module = importlib.import_module("emailextract.assemble")
mediatype = importlib.import_module("emailextract.mediatype")
resolve_module = importlib.import_module("emailextract.quote.resolve")
from emailextract.assemble import assemble  # noqa: E402
from emailextract.container import EmlContainer  # noqa: E402
from emailextract.parse import Limits  # noqa: E402
from emailextract.selection import selection_rows  # noqa: E402
from emailextract.walk import walk  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "emailextract"
FIXTURES = ROOT / "fixtures" / "generated"

#: The default RFC 2045 section 5.2 spells out; the twins insert it.
DEFAULT_HEADER = b"Content-Type: text/plain; charset=us-ascii\r\n"

#: The single-part header-less fixtures and the multipart ones whose text child is header-less.
SINGLE_PART = (
    "headerless_plain_on_wrote",
    "headerless_plain_gt_only",
    "headerless_plain_mime_version_only",
    "headerless_plain_8bit",
)
EMPTY_DIGEST = hashlib.sha256(b"").hexdigest()


def _raw(stem: str) -> bytes:
    return (FIXTURES / f"{stem}.eml").read_bytes()


def _twin_single(raw: bytes) -> bytes:
    """The same message with the one omitted header spelled out on its single part."""
    return raw.replace(b"\r\n\r\n", b"\r\n" + DEFAULT_HEADER + b"\r\n", 1)


def _twin_child(raw: bytes, boundary: str) -> bytes:
    """The same message with the explicit header inserted into its first (header-less) child."""
    marker = b"--" + boundary.encode("ascii") + b"\r\n\r\n"
    return raw.replace(marker, marker[:-2] + DEFAULT_HEADER + b"\r\n", 1)


def _facts(raw: bytes) -> dict[str, object]:
    """The assembled document's body facts, as plain data for comparison.

    Selection and classification are compared by their **values**, not by ``part_id``: a part id
    is content-addressed (it includes the part's own bytes), so a header-less part and its twin
    have different ids for the same state -- the state is the fact under test.
    """
    document = assemble(EmlContainer(raw), limits=Limits.untrusted())
    return {
        "quote_boundaries": [
            (row.rule_id, row.kind.value, row.ordinal, tuple(row.prefix_depth), row.span.start, row.span.end)
            for row in document.quote_boundaries
        ],
        "view_levels": [
            (row.view_id, row.quote_level, row.resolution_rule_id) for row in document.view_levels
        ],
        "selection": tuple(row.selection.value for row in document.parts),
        "classification": tuple(row.classification.value for row in document.parts),
        "fingerprint": document.content_fingerprint.body_digest,
    }


def test_the_reproduction_gets_the_quote_boundary_its_explicit_twin_gets() -> None:
    """The reviewer's reproduction: header-less and explicit text/plain must agree exactly."""
    raw = _raw("headerless_plain_on_wrote")
    facts = _facts(raw)
    twin = _facts(_twin_single(raw))
    assert facts["quote_boundaries"] == twin["quote_boundaries"] != []
    assert facts["view_levels"] == twin["view_levels"] != []
    assert facts["selection"] == twin["selection"]
    # The boundary really is the on_wrote_en attribution, ordinal 1.
    assert facts["quote_boundaries"][0][0] == "on_wrote_en"

@pytest.mark.parametrize("stem", SINGLE_PART)
def test_every_single_part_headerless_fixture_agrees_with_its_explicit_twin(stem: str) -> None:
    """A header-less part and its explicit text/plain twin give the same body facts."""
    raw = _raw(stem)
    assert _facts(raw) == _facts(_twin_single(raw)), stem


def test_the_headerless_alternative_child_agrees_with_its_explicit_twin() -> None:
    """A header-less multipart/alternative child is a text/plain view and is selected."""
    raw = _raw("headerless_alternative_text_part")
    facts = _facts(raw)
    twin = _facts(_twin_child(raw, "b0-headerless-alt-20250304"))
    assert facts["quote_boundaries"] == twin["quote_boundaries"] != []
    assert facts["view_levels"] == twin["view_levels"] != []
    assert facts["selection"] == twin["selection"]
    # The one selected part is the header-less first child (the plain alternative), as D3 says.
    states = set(facts["selection"])
    assert "selected" in states and "alternative_not_selected" in states


def test_the_headerless_inline_text_body_agrees_with_its_explicit_twin() -> None:
    """The header-less inline body is a view, not an attachment; the disposition part stays one."""
    raw = _raw("headerless_mixed_text_and_attachment")
    facts = _facts(raw)
    twin = _facts(_twin_child(raw, "b0-headerless-mixed-20250304"))
    assert facts["selection"] == twin["selection"]
    assert facts["classification"] == twin["classification"]
    assert "n/a" in facts["selection"]


def test_the_content_fingerprint_of_a_headerless_message_is_not_the_empty_digest() -> None:
    """The fingerprint digests the selected view's text, never the empty string (D14)."""
    raw = _raw("headerless_plain_on_wrote")
    assert _facts(raw)["fingerprint"] != EMPTY_DIGEST
    assert _facts(raw)["fingerprint"] == _facts(_twin_single(raw))["fingerprint"]


def test_the_digest_child_default_is_message_rfc822_and_not_text_plain() -> None:
    """RFC 2046 section 5.1.5: a header-less multipart/digest child is a message, not text."""
    raw = _raw("headerless_digest_child")
    result = walk(EmlContainer(raw))
    child = next(part for part in result.parts if part.path == "1.1")
    parts = {part.path: part for part in result.parts}
    assert mediatype.effective_media_type_in(child, parts) == "message/rfc822"
    # So the child is no text/plain view: no quote boundary, no selection row from the stage.
    assert _facts(raw)["quote_boundaries"] == []
    assert selection_rows(raw, result) == []
    # The twin that *declares* text/plain on the same child is a text/plain view with a row.
    twin_raw = _twin_child(raw, "b0-headerless-digest-20250304")
    result_twin = walk(EmlContainer(twin_raw))
    twin_child = next(part for part in result_twin.parts if part.path == "1.1")
    twin_parts = {part.path: part for part in result_twin.parts}
    assert mediatype.effective_media_type_in(twin_child, twin_parts) == "text/plain"
    assert selection_rows(twin_raw, result_twin)


# ---------------------------------------------------------------- the static scan

#: The ad-hoc media computation this turn removes: ``(part.content_type or "")`` and friends.
_AD_HOC = re.compile(r"content_type\s+or\s+['\"]")

#: The only module allowed to spell the computation out: the helper itself.
SCAN_ALLOWED = {"mediatype.py"}


def test_no_module_outside_the_helper_computes_a_media_type_by_hand() -> None:
    """No module outside ``mediatype.py`` derives a media type from ``content_type`` by hand."""
    offenders: list[str] = []
    hits: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not _AD_HOC.search(line):
                continue
            where = path.relative_to(ROOT).as_posix()
            if path.name in SCAN_ALLOWED:
                hits.append(f"{where}:{lineno}")
            else:
                offenders.append(f"{where}:{lineno}: {line.strip()}")
    assert not offenders, f"a module computes a media type by hand: {offenders}"
    assert hits, "the scan is vacuous: the helper itself must carry the computation"


# ---------------------------------------------------------------- the mutation cases


def _patched(monkeypatch, module, name, wrapper):
    """The anti-vacuity triple: the symbol exists, the wrapper proves it was reached."""
    flags = {"reached": 0}
    real = getattr(module, name)

    def counted(*args, **kwargs):
        flags["reached"] += 1
        return wrapper(real, *args, **kwargs)

    monkeypatch.setattr(module, name, counted)
    return flags


def test_the_helper_returning_empty_for_an_absent_content_type_fails_the_reproduction(
    monkeypatch,
) -> None:
    """The mutation that reverts the fix: the helper returns ``""`` for a header-less part."""
    raw = _raw("headerless_plain_on_wrote")
    baseline = _facts(raw)

    def old_behaviour(real, part, parent_media=None):
        if not mediatype.declares_content_type(part):
            return ""
        return real(part, parent_media)

    flags = _patched(monkeypatch, mediatype, "effective_media_type", old_behaviour)
    mutated = _facts(raw)
    assert flags["reached"] > 0, "the patch never ran: the stages must reach the helper"
    assert mutated["quote_boundaries"] == [] and mutated["view_levels"] == []
    assert mutated != baseline


def test_a_stage_bypassing_the_helper_loses_the_headerless_boundary(monkeypatch) -> None:
    """A quote stage that keeps the old ad-hoc computation drops the header-less boundary."""
    raw = _raw("headerless_plain_on_wrote")
    baseline = _facts(raw)

    def ad_hoc(real, part, parts):
        del real, parts
        return (part.content_type or "").strip().lower()

    flags = _patched(monkeypatch, resolve_module, "_media", ad_hoc)
    mutated = _facts(raw)
    assert flags["reached"] > 0, "the patch never ran: the quote stage must call its _media"
    assert mutated["quote_boundaries"] == []
    assert mutated != baseline


def test_the_fingerprint_default_is_not_ignored(monkeypatch) -> None:
    """An assembly that keeps the old ad-hoc computation digests the empty string again."""
    raw = _raw("headerless_plain_on_wrote")
    assert _facts(raw)["fingerprint"] != EMPTY_DIGEST

    def ad_hoc(real, part, by_path):
        del real, by_path
        return (part.content_type or "").strip().lower()

    flags = _patched(monkeypatch, assemble_module, "_media", ad_hoc)
    mutated = _facts(raw)
    assert flags["reached"] > 0, "the patch never ran: assemble must call its _media"
    assert mutated["fingerprint"] == EMPTY_DIGEST

