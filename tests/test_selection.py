"""Turn 1.5b: the referenced-cid set, the alternative grouping and the display rule.

The second half of Turn 1.5 (its first half is ``tests/test_htmltree.py`` and
``tests/test_htmltext.py``). ``selection.py`` owns four of the turn's facts
(``body.alternative_group``, ``body.selection``, ``body.cid_refs``,
``body.plain_effectively_empty``) and the Phase 1 gap channel for
``body.digest_default_not_applied``, ``body.no_text_part``,
``security.remote_content_present`` and ``body.inline_data_uri`` (plus the tree's own
``body.html_quote_rule_gap``).

The frozen labels are the judge: where a hand-typed row and the rule disagree the label wins
and the disagreement is a finding. Here they agree, and the declared tests assert the labelled
values directly. The extras (declared in ``phase1-turn-declarations.md``) are the gap catalogue
with its anti-vacuity triple, the stdlib HTML shape comparison with its closed exclusions, the
seeded fuzz and the interpreter-stability check, and the proof that the L1 gate still fails on
a wrong sidecar for each of the five new facts.

Every failure names the fixture, the fact and the gap id (the build spec's rule).
"""

from __future__ import annotations

import json
import os
import random
import socket
import subprocess
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import pytest

import docextract_core

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from support import html_projection_hash  # noqa: E402
from support import stdlib_scanner  # noqa: E402
from support.sidecar_copy import tamper  # noqa: E402

from emailextract import htmltext, htmltree  # noqa: E402
from emailextract import selection as selection_stage  # noqa: E402
from emailextract.container import EmlContainer, memory_bytes  # noqa: E402
from emailextract.evals.labels import DEFAULT_FIXTURES, load_sidecars  # noqa: E402
from emailextract.walk import walk  # noqa: E402

GENERATED = ROOT / "fixtures" / "generated"

#: The caller's caps for every projection this file builds: the approved untrusted defaults.
CAP_DEPTH = 16
CAP_ELEMENTS = 1000


def _raw(name: str) -> bytes:
    return (GENERATED / f"{name}.eml").read_bytes()


def _walk(raw: bytes) -> Any:
    return walk(EmlContainer(memory_bytes(raw)))


def _label(name: str, fact_id: str) -> Any:
    sidecar = json.loads((GENERATED / f"{name}.expected.json").read_text(encoding="utf-8"))
    return sidecar["facts"][fact_id]["value"]


def _later_gaps(name: str) -> list[list[Any]]:
    sidecar = json.loads((GENERATED / f"{name}.expected.json").read_text(encoding="utf-8"))
    return sidecar["facts"].get("gaps.later", {}).get("value", [])


def _message(body: bytes, content_type: bytes = b"text/html; charset=utf-8") -> bytes:
    """A minimal one-part message: a Content-Type, then ``body``."""
    head = b"From: Ada Sender <ada@example.test>\r\n"
    head += b"Content-Type: " + content_type + b"\r\n"
    return head + b"\r\n" + body


def _gaps(raw: bytes, result: Any) -> list[str]:
    return [
        gap_id
        for gap_id, _locator in selection_stage.body_gaps(
            raw, result, max_depth=CAP_DEPTH, max_elements=CAP_ELEMENTS
        )
    ]


def _content_ids(result: Any) -> list[str]:
    """Every part's ``Content-ID``, normalized as ``selection.py`` normalizes a cid."""
    found: list[str] = []
    for part in result.parts:
        for field in part.header_fields:
            if field.name.lower() == "content-id":
                found.append(field.raw_value.strip().strip("<>").strip())
    return found


def _referenced(raw: bytes, result: Any) -> list[str]:
    return [
        cid
        for _part, cids in selection_stage.cid_ref_rows(
            raw, result, max_depth=CAP_DEPTH, max_elements=CAP_ELEMENTS
        )
        for cid in cids
    ]


def _corpus_artifacts() -> list[tuple[str, bytes]]:
    """Every committed sidecar's stem and its fixture's bytes (``generated``, ``raw``, ``time``)."""
    return [
        (stem, sidecar.artifact.read_bytes())
        for stem, sidecar in sorted(load_sidecars(DEFAULT_FIXTURES).items())
    ]


# --------------------------------------------------------- the display rule (declared)


def test_the_display_rule_selects_the_plain_alternative() -> None:
    """Inside a group the closed preference order picks one part; the labels are the judge."""
    for name in ("alternative_text_html", "multipart_mixed_wraps_alternative"):
        raw = _raw(name)
        rows = selection_stage.selection_rows(raw, _walk(raw))
        assert rows == _label(name, "body.selection"), (name, rows)
        selected = [row[0] for row in rows if row[1] == selection_stage.SELECTED]
        assert len(selected) == 1, (name, rows)
        assert all(row[1] in selection_stage.SELECTION_STATES for row in rows), rows


def test_a_selected_html_alternative_marks_the_plain_unselected() -> None:
    """An effectively-empty plain alternative loses to the html view in the same group."""
    raw = _raw("plain_effectively_empty")
    rows = selection_stage.selection_rows(raw, _walk(raw))
    assert rows == [["1.1", "alternative_not_selected"], ["1.2", "selected"]], rows
    assert rows == _label("plain_effectively_empty", "body.selection")
    # the display rule really is the closed preference order the design fixes (D3)
    assert selection_stage.DISPLAY_PREFERENCE == ("text/plain", "text/html", "text/calendar")


def test_an_alternative_group_id_is_message_local() -> None:
    """The group id is the alternative's own locator, so it restarts at ``1`` per message."""
    for name, expected in (
        ("alternative_text_html", [["1.1", "1"], ["1.2", "1"]]),
        ("text_calendar_alternative", [["1.1", "1"], ["1.2", "1"], ["1.3", "1"]]),
        (
            "nested_alternative_in_related_in_mixed",
            [["1.1.1.1", "1.1.1"], ["1.1.1.2", "1.1.1"]],
        ),
    ):
        raw = _raw(name)
        result = _walk(raw)
        rows = selection_stage.alternative_group_rows(raw, result)
        assert rows == expected, (name, rows)
        # where a sidecar types the fact, the label is the judge (the first two do not)
        sidecar = json.loads((GENERATED / f"{name}.expected.json").read_text(encoding="utf-8"))
        if "body.alternative_group" in sidecar["facts"]:
            assert rows == sidecar["facts"]["body.alternative_group"]["value"]
        # message-local by construction: the id is one of the message's own part locators
        locators = {part.path for part in result.parts}
        assert all(group_id in locators for _part, group_id in rows), (name, rows)
    # ... so two messages' first groups both say "1", which is not a collision
    first = selection_stage.alternative_group_rows(
        _raw("alternative_text_html"), _walk(_raw("alternative_text_html"))
    )
    other = selection_stage.alternative_group_rows(
        _raw("text_calendar_alternative"), _walk(_raw("text_calendar_alternative"))
    )
    assert {group for _part, group in first} == {group for _part, group in other} == {"1"}


def test_a_plain_effectively_empty_alternative_is_the_fact() -> None:
    """A present-but-whitespace-only ``text/plain`` is a FACT (D16), not a gap."""
    for name, expected in (
        ("plain_effectively_empty", [["1.1", "whitespace_only"]]),
        ("attach_remote_image_only", [["1.1", "whitespace_only"]]),
    ):
        raw = _raw(name)
        result = _walk(raw)
        rows = selection_stage.plain_effectively_empty_rows(raw, result)
        assert rows == expected, (name, rows)
        assert rows == _label(name, "body.plain_effectively_empty")
        assert "body.plain_effectively_empty" not in _gaps(raw, result), name
        members = [part for part, _group in selection_stage.alternative_group_rows(raw, result)]
        assert "1.1" in members, (name, members)
    # the emptiness set is the stated Unicode White_Space code points, NBSP included
    assert 0x00A0 in selection_stage.WHITESPACE_ONLY_CODE_POINTS
    assert 0x0020 in selection_stage.WHITESPACE_ONLY_CODE_POINTS
    assert 0x3000 in selection_stage.WHITESPACE_ONLY_CODE_POINTS
    assert ord("A") not in selection_stage.WHITESPACE_ONLY_CODE_POINTS
    # ``stub_only`` is declared by the vocabulary but never emitted: no label types it
    assert selection_stage.EMPTINESS_STUB_ONLY in selection_stage.EMPTINESS_RULES
    emitted = {
        rule
        for _stem, raw in _corpus_artifacts()
        for _part, rule in selection_stage.plain_effectively_empty_rows(raw, _walk(raw))
    }
    assert emitted == {selection_stage.EMPTINESS_WHITESPACE_ONLY}, emitted


def test_a_digest_child_without_content_type_is_the_gap() -> None:
    """A ``multipart/digest`` child with no Content-Type is the gap, never a silent default."""
    raw = _raw("multipart_digest_content_type_less_child")
    result = _walk(raw)
    assert _gaps(raw, result) == ["body.digest_default_not_applied"], _gaps(raw, result)
    assert ("body.digest_default_not_applied", "1.1") in selection_stage.body_gaps(
        raw, result, max_depth=CAP_DEPTH, max_elements=CAP_ELEMENTS
    )
    assert [row[0] for row in _later_gaps("multipart_digest_content_type_less_child")] == [
        "body.digest_default_not_applied"
    ]
    # RFC 2046 5.1.5's message/rfc822 default is NOT applied to the child
    child = {part.path: part for part in result.parts}["1.1"]
    assert child.content_type is None, child.content_type


def test_a_text_calendar_alternative_is_a_view_not_an_attachment() -> None:
    """A ``text/calendar`` alternative is a ranked view candidate, never an attachment."""
    name = "text_calendar_alternative"
    raw = _raw(name)
    result = _walk(raw)
    rows = selection_stage.selection_rows(raw, result)
    assert rows == _label(name, "body.selection"), rows
    assert rows[-1] == ["1.3", "alternative_not_selected"], rows
    assert ["1.3", "1"] in selection_stage.alternative_group_rows(raw, result)
    assert selection_stage.DISPLAY_PREFERENCE.index("text/calendar") == 2
    # no attachment logic runs this turn: no attach.* gap, and no part is dropped
    assert not [gap for gap in _gaps(raw, result) if gap.startswith("attach.")], _gaps(raw, result)
    assert {part.path for part in result.parts} >= {"1.1", "1.2", "1.3"}


# ------------------------------------------------------------- the fact's neighbours


def test_a_message_with_no_text_part_selects_none_and_records_the_gap() -> None:
    """No part reads as text: the selection is empty and the gap is recorded."""
    raw = _raw("body_no_text_part")
    result = _walk(raw)
    assert selection_stage.selection_rows(raw, result) == []
    assert _gaps(raw, result) == ["body.no_text_part"]
    assert [row[0] for row in _later_gaps("body_no_text_part")] == ["body.no_text_part"]


# --------------------------------------------------------------- the referenced cid set


def test_the_cid_reference_set_comes_from_the_tree_and_is_deduplicated_in_order() -> None:
    """cid refs come from the element tree (never a regex) and collapse in document order."""
    body = (
        b'<img src="cid:one@example.test">\r\n'
        b'<img src="cid:two@example.test">\r\n'
        b'<img src="cid:one@example.test">\r\n'
        b'<a href="CID:two@example.test">x</a>\r\n'
        b'<a href="mailto:ben@example.test">Ben</a>\r\n'
    )
    raw = _message(body)
    rows = selection_stage.cid_ref_rows(
        raw, _walk(raw), max_depth=CAP_DEPTH, max_elements=CAP_ELEMENTS
    )
    assert rows == [["1", ["one@example.test", "two@example.test"]]], rows
    # a cid inside a dropped subtree or a comment is never seen: the tree, not a regex
    hidden = _message(
        b'<!-- <img src="cid:comment@example.test"> -->\r\n'
        b"<style>p{background:url(cid:style@example.test)}</style>\r\n"
        b'<script>var u = "cid:script@example.test";</script>\r\n'
    )
    assert (
        selection_stage.cid_ref_rows(
            hidden, _walk(hidden), max_depth=CAP_DEPTH, max_elements=CAP_ELEMENTS
        )
        == []
    )
    # the committed cid fixtures carry exactly what the bytes name
    for name, expected in (
        ("attach_cid_dangling", [["1", ["missing@example.test"]]]),
        ("attach_inline_referenced", [["1.1", ["logo@example.test"]]]),
        ("html_href_img_remote_and_cid", [["1", ["logo@example.test"]]]),
    ):
        raw = _raw(name)
        assert (
            selection_stage.cid_ref_rows(
                raw, _walk(raw), max_depth=CAP_DEPTH, max_elements=CAP_ELEMENTS
            )
            == expected
        ), name
        assert _label(name, "body.cid_refs") == expected


def test_a_cid_a_remote_url_and_a_data_uri_are_three_distinct_kinds() -> None:
    """The one classification point: a cid is not remote, a remote url is not a cid, and a
    ``data:`` URI is recorded but never decoded; a ``Content-Location`` is never fetched."""
    kind = selection_stage._url_kind
    assert kind("cid:x@example.test") == "cid"
    assert kind("CID:x@example.test") == "cid"  # RFC 3986: the scheme is case-insensitive
    assert kind("http://example.test/a") == "remote"
    assert kind("HTTPS://example.test/a") == "remote"
    assert kind("//example.test/a") == "remote"  # protocol-relative
    assert kind("data:image/gif;base64,AA") == "data"
    assert kind("mailto:ben@example.test") == "other"

    raw = _raw("html_href_img_remote_and_cid")
    refs = selection_stage.external_references(
        raw, _walk(raw), max_depth=CAP_DEPTH, max_elements=CAP_ELEMENTS
    )
    entry = next(item for item in refs.parts if item.cids)
    assert entry.cids == ("logo@example.test",) and entry.remote == ("http://example.test/pic.png",)
    assert not set(entry.cids) & set(entry.remote)

    # a data: URI: recorded, never expanded, and the gap says so
    data_raw = _raw("html_data_uri_and_tracking_pixel")
    data_refs = selection_stage.external_references(
        data_raw, _walk(data_raw), max_depth=CAP_DEPTH, max_elements=CAP_ELEMENTS
    )
    assert data_refs.decoded == (), data_refs.decoded
    assert [part.part for part in data_refs.parts if part.data_uris] == ["1"]
    assert _gaps(data_raw, _walk(data_raw)) == [
        "security.remote_content_present",
        "body.inline_data_uri",
    ]

    # a Content-Location: recorded as a claim, and the fetch observation stays empty
    location_raw = _raw("content_location_in_related")
    location_refs = selection_stage.external_references(
        location_raw, _walk(location_raw), max_depth=CAP_DEPTH, max_elements=CAP_ELEMENTS
    )
    assert location_refs.content_locations == ("http://example.test/photo.png",)
    assert location_refs.followed == (), location_refs.followed
    assert _gaps(location_raw, _walk(location_raw)) == ["security.remote_content_present"]


def test_the_cid_helper_is_set_arithmetic_and_case_sensitive() -> None:
    """``dangling_and_unreferenced``: pure set arithmetic, case-sensitive (RFC 2392)."""
    helper = selection_stage.dangling_and_unreferenced
    assert helper([], []) == ([], [])
    assert helper(["a"], []) == (["a"], [])
    assert helper([], ["a"]) == ([], ["a"])
    # duplicates collapse; the order is first occurrence in each input
    assert helper(["a", "b", "a"], ["b"]) == (["a"], [])
    # case-sensitive: a fold would merge two genuinely different ids (the addr-spec local part)
    assert helper(["Logo@example.test"], ["logo@example.test"]) == (
        ["Logo@example.test"],
        ["logo@example.test"],
    )
    # the Family C sidecars are the judges: the helper reproduces each one's typed outcome
    for name, expected in (
        ("attach_cid_dangling", (["missing@example.test"], [])),
        ("attach_inline_unreferenced", ([], ["spare@example.test"])),
        ("attach_inline_referenced", ([], [])),
    ):
        raw = _raw(name)
        result = _walk(raw)
        assert helper(_referenced(raw, result), _content_ids(result)) == expected, name
    # attach.cid_dangling / attach.cid_unreferenced stay in gaps.later: Turn 1.8 emits them
    assert "attach.cid_dangling" not in set(selection_stage.GAP_IDS)
    assert "attach.cid_unreferenced" not in set(selection_stage.GAP_IDS)


def test_the_selection_path_touches_no_socket_and_no_open(monkeypatch) -> None:
    """The whole selection/HTML path does no I/O: no socket, no file open, ever (D10)."""

    def _refuse(*args, **kwargs):  # pragma: no cover - reached only on a defect
        raise AssertionError("the selection path touched the outside world")

    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr("builtins.open", _refuse)
    for name in (
        "html_href_img_remote_and_cid",
        "html_data_uri_and_tracking_pixel",
        "content_location_in_related",
        "attach_cid_dangling",
    ):
        raw = _raw(name)
        result = _walk(raw)
        assert selection_stage.body_gaps(
            raw, result, max_depth=CAP_DEPTH, max_elements=CAP_ELEMENTS
        ) is not None
        assert selection_stage.external_references(
            raw, result, max_depth=CAP_DEPTH, max_elements=CAP_ELEMENTS
        ) is not None
        assert selection_stage.selection_rows(raw, result) is not None


# ------------------------------------------------------------------- gap catalogue


#: gap id -> its hand-typed case: the bytes, and the **one** symbol to patch. ``patch`` is
#: ``(module, symbol, replacement(original) -> callable)``; the baseline is that the measurement
#: contains the gap, the mutant replaces the symbol and the observation flips (the anti-vacuity
#: triple adds the reached flag). The replacement takes the original so it can delegate to it.
GAP_CASES: dict[str, dict[str, Any]] = {
    selection_stage.GAP_BODY_DIGEST_DEFAULT_NOT_APPLIED: {
        "raw": _raw("multipart_digest_content_type_less_child"),
        "patch": (
            selection_stage,
            "_is_digest_child_without_content_type",
            lambda original: (lambda *a, **k: False),
        ),
    },
    selection_stage.GAP_BODY_NO_TEXT_PART: {
        "raw": _raw("body_no_text_part"),
        "patch": (selection_stage, "_reads_as_text", lambda original: (lambda *a, **k: True)),
    },
    selection_stage.GAP_SECURITY_REMOTE_CONTENT_PRESENT: {
        "raw": _raw("html_href_img_remote_and_cid"),
        "patch": (
            selection_stage,
            "_url_kind",
            lambda original: (
                lambda url: "cid"
                if url.strip().lower().startswith(("http:", "https:"))
                else original(url)
            ),
        ),
    },
    selection_stage.GAP_BODY_INLINE_DATA_URI: {
        "raw": _raw("html_data_uri_and_tracking_pixel"),
        "patch": (
            selection_stage,
            "_url_kind",
            lambda original: (
                lambda url: "other" if url.strip().lower().startswith("data:") else original(url)
            ),
        ),
    },
    htmltree.GAP_BODY_HTML_QUOTE_RULE_GAP: {
        "raw": _message(b"<blockquote>an unclosed container<b>never closed"),
        "patch": (htmltree, "is_quote_container", lambda original: (lambda *a, **k: False)),
    },
}


@pytest.mark.parametrize("gap_id", sorted(GAP_CASES))
def test_every_emitted_gap_id_has_an_anti_vacuity_case(gap_id: str, monkeypatch) -> None:
    """A catalogue test: an emitted gap id with no case fails, and the case is anti-vacuous."""
    assert set(GAP_CASES) == set(selection_stage.GAP_IDS) | {htmltree.GAP_BODY_HTML_QUOTE_RULE_GAP}
    case = GAP_CASES[gap_id]
    raw = case["raw"]
    assert gap_id in _gaps(raw, _walk(raw)), f"{gap_id} is not emitted by its own case"

    module, symbol, factory = case["patch"]
    assert hasattr(module, symbol), f"the patched symbol {symbol} must exist"
    reached: list[bool] = []
    replacement = factory(getattr(module, symbol))

    def mutant(*args, **kwargs):
        reached.append(True)
        return replacement(*args, **kwargs)

    monkeypatch.setattr(module, symbol, mutant)
    assert reached == []
    flipped = _gaps(raw, _walk(raw))
    assert reached, "the patch was never reached -- the case is vacuous"
    assert gap_id not in flipped, (gap_id, flipped)


def test_every_gap_emitted_over_the_corpus_is_catalogued() -> None:
    """No gap id leaves the selection stage without a catalogue row."""
    known = set(GAP_CASES)
    seen: set[str] = set()
    for stem, raw in _corpus_artifacts():
        for gap_id in _gaps(raw, _walk(raw)):
            assert gap_id in known, f"{stem}: emitted {gap_id!r} with no case"
            seen.add(gap_id)
    assert seen, "no gap id was emitted over the corpus: the catalogue is untested"


# ------------------------------------------------- the stdlib HTML shape comparison


#: The closed exclusions: a case where the own tree and the stdlib's flat start-tag events
#: legitimately differ, each because the tree **records its own repair** (decision 1). The
#: reasons live in ``stdlib_scanner.SHARED_HTML_MISREADING``.
def _ours_shape(projection: htmltext.HtmlProjection) -> tuple[tuple[tuple[str, int], ...], tuple[str, ...]]:
    """Our tree's own start-tag multiset and ``id`` set, the two things the comparison reads."""
    counts = Counter(element.tag for element in projection.tree.elements)
    ids = sorted(
        {
            value
            for element in projection.tree.elements
            for name, value in element.attributes
            if name.lower() == "id"
        }
    )
    return tuple(sorted(counts.items())), tuple(ids)


def _html_exclusions(projection: htmltext.HtmlProjection) -> set[str]:
    """The closed reasons this projection's shape comparison is not a gate."""
    tree = projection.tree
    reasons: set[str] = set()
    if tree.truncation is not None:
        reasons.add("element_count_cap")
    if any(name == "id" for _ordinal, name in tree.duplicate_attributes):
        reasons.add("duplicate_id_attribute")
    if tree.misnested_closures:
        reasons.add("misnested_input")
    if tree.unclosed_ordinals:
        reasons.add("unclosed_container")
    return reasons


@pytest.fixture(scope="module")
def corpus_html_parts():
    """Every committed HTML part: ``(stem, locator, html text, projection)``, walked once."""
    items = []
    for stem, sidecar in sorted(load_sidecars(DEFAULT_FIXTURES).items()):
        raw = sidecar.artifact.read_bytes()
        result = walk(EmlContainer(raw))
        texts = selection_stage.display_text(raw, result)
        for locator, projection in selection_stage.html_projections(
            raw, result, max_depth=CAP_DEPTH, max_elements=CAP_ELEMENTS
        ):
            items.append((stem, locator, texts[locator], projection))
    assert len(items) >= 15, f"the HTML sweep found only {len(items)} parts"
    return items


def test_the_stdlib_scanner_agrees_on_html_shape(corpus_html_parts) -> None:
    """Over the corpus, our element counts and ids equal the stdlib's own start-tag events."""
    compared = 0
    excluded: set[str] = set()
    for stem, locator, text, projection in corpus_html_parts:
        reasons = _html_exclusions(projection)
        if reasons:
            excluded |= reasons
            continue
        compared += 1
        shape = stdlib_scanner.html_shape(text)
        ours = _ours_shape(projection)
        assert ours[0] == shape.tag_counts, (stem, locator, ours[0], shape.tag_counts)
        assert ours[1] == shape.ids, (stem, locator, ours[1], shape.ids)
    assert compared >= 15, f"only {compared} HTML parts were comparable"
    assert not excluded, f"the corpus excluded {sorted(excluded)}: the comparison is weaker than it should be"


def test_the_stdlib_html_exclusions_are_closed_and_reachable() -> None:
    """Every exclusion is a closed reason with a reachable case; the catalogue is not decorative."""
    cases = {
        "element_count_cap": ("<div>" * 30, dict(max_depth=4, max_elements=1000)),
        "duplicate_id_attribute": ('<div id="first" id="second">x</div>', dict()),
        "misnested_input": ("<p><b>bold <i>and italic</b> still italic</i> tail</p>", dict()),
        "unclosed_container": ("<blockquote>open<p>never closed", dict()),
    }
    observed: set[str] = set()
    for reason, (text, caps) in cases.items():
        projection = htmltext.project(
            text,
            max_depth=caps.get("max_depth", CAP_DEPTH),
            max_elements=caps.get("max_elements", CAP_ELEMENTS),
        )
        reasons = _html_exclusions(projection)
        assert reason in reasons, (reason, reasons)
        observed |= reasons
    assert observed == set(stdlib_scanner.SHARED_HTML_MISREADING), observed
    for reason, why in stdlib_scanner.SHARED_HTML_MISREADING.items():
        assert why and len(why) > 20, reason


def test_the_html_shape_comparison_can_fail(monkeypatch) -> None:
    """Planted defects flip the comparison, on our side and on the stdlib side."""
    text = '<p>a</p><img src="http://example.test/p.png">'
    projection = htmltext.project(text, max_depth=CAP_DEPTH, max_elements=CAP_ELEMENTS)
    assert _ours_shape(projection) == (
        stdlib_scanner.html_shape(text).tag_counts,
        stdlib_scanner.html_shape(text).ids,
    )

    original_build = htmltree.build_tree

    def drop_last(*args, **kwargs):
        tree = original_build(*args, **kwargs)
        return replace(tree, elements=tree.elements[:-1])

    monkeypatch.setattr(htmltree, "build_tree", drop_last)
    planted = htmltext.project(text, max_depth=CAP_DEPTH, max_elements=CAP_ELEMENTS)
    monkeypatch.undo()
    assert _ours_shape(planted)[0] != stdlib_scanner.html_shape(text).tag_counts, "ours did not flip"

    def blind_shape(html_text: str):
        return stdlib_scanner.HtmlShape(tag_counts=(), ids=())

    monkeypatch.setattr(stdlib_scanner, "html_shape", blind_shape)
    assert stdlib_scanner.html_shape(text).tag_counts != _ours_shape(projection)[0], "theirs did not flip"


# ----------------------------------------------------------------------------- fuzz


#: The strings injected into a fixture's HTML: unclosed tags, quotes, NULs and an
#: Arabic-Indic digit (a numeric position a bare ``str.isdigit`` would misread).
HTML_INJECTIONS = (
    "<div>",
    "<blockquote>",
    "<p>",
    "<b>",
    "</p>",
    "</div>",
    "<script>",
    "<style>",
    "<!--",
    '"',
    "'",
    "<",
    ">",
    "&amp;",
    "&#0;",
    "\x00",
    '<img width="\u0661\u0662\u0663">',
    '<img src="',
)

#: The special inputs, in addition to the corpus's own HTML text: empty, an element-count
#: bomb, and two huge-attribute values. The 100k character inputs are checked once, below,
#: rather than fed through the whole word-for-word selection leg (which would re-decode a
#: half-megabyte body per seed for no extra coverage).
HTML_SPECIAL_BASES = (
    "",
    "<div>" * 1_000,
    '<img src="' + "a" * 2_000 + '">',
    "<p title='" + "x" * 2_000 + "'>y</p>",
)

#: The 100k-scale inputs the prompt names: a depth bomb and a huge attribute value, both of
#: which the caps must turn into a recorded state rather than a failure.
HTML_HUGE_INPUTS = (
    "<div>" * 100_000,
    '<img src="' + "a" * 100_000 + '">',
)


def _mutate(rng: random.Random, text: str) -> str:
    """One seeded mutation: a byte flip, a truncation, a repeat or swap, or an injection."""
    kind = rng.randrange(6)
    if kind == 0 and text:
        position = rng.randrange(len(text))
        return text[:position] + rng.choice(HTML_INJECTIONS) + text[position + 1 :]
    if kind == 1 and text:
        return text[: rng.randrange(1, len(text) + 1)]
    if kind == 2 and text:
        position = rng.randrange(len(text))
        return text + text[position : position + rng.randrange(1, 40)]
    if kind == 3 and len(text) > 4:
        low, high = sorted((rng.randrange(len(text)), rng.randrange(len(text))))
        middle = len(text) // 2
        return text[:middle] + text[low:high] + text[middle:]
    if kind == 4:
        return text + rng.choice(HTML_INJECTIONS) * rng.randrange(1, 4)
    return rng.choice(HTML_INJECTIONS) + text


def _html_error(text: str) -> str | None:
    """Project, walk and select one fuzzed HTML text; describe any violated invariant, or None."""
    try:
        projection = htmltext.project(text, max_depth=CAP_DEPTH, max_elements=CAP_ELEMENTS)
        by_ordinal = {element.ordinal: element for element in projection.tree.elements}
        for element in projection.tree.elements:
            assert 0 <= element.projected_offset, (text, element)
            assert element.projected_end <= len(projection.text), (text, element)
            if element.parent_ordinal is not None:
                parent = by_ordinal[element.parent_ordinal]
                assert parent.projected_offset <= element.projected_offset, (text, element)
                assert element.projected_end <= parent.projected_end, (text, element)
        again = htmltext.project(text, max_depth=CAP_DEPTH, max_elements=CAP_ELEMENTS)
        assert again == projection, "projecting twice must give an identical projection"

        raw = _message(text.encode("utf-8", "surrogatepass"))
        result = _walk(raw)
        selection_stage.selection_rows(raw, result)
        selection_stage.alternative_group_rows(raw, result)
        selection_stage.plain_effectively_empty_rows(raw, result)
        selection_stage.external_references(
            raw, result, max_depth=CAP_DEPTH, max_elements=CAP_ELEMENTS
        )
        known = set(selection_stage.GAP_IDS) | {htmltree.GAP_BODY_HTML_QUOTE_RULE_GAP}
        for gap_id, _locator in selection_stage.body_gaps(
            raw, result, max_depth=CAP_DEPTH, max_elements=CAP_ELEMENTS
        ):
            assert gap_id in known, f"an unregistered gap id {gap_id!r}"
    except AssertionError as error:  # the anti-vacuity of the invariants themselves
        return f"{error}"
    except Exception as error:  # noqa: BLE001 -- a raise is the defect under test
        return f"{type(error).__name__}: {error}"
    return None


def _fuzz_seeds(corpus_html_parts, count: int = 60):
    """The bases and the seeded mutants over them: ``(description, text)`` pairs, in order."""
    bases = [text for _stem, _loc, text, _proj in corpus_html_parts]
    bases.extend(HTML_SPECIAL_BASES)
    rng = random.Random(20250315)
    for base in bases:
        for _ in range(count):
            yield _mutate(rng, base)


def test_the_html_and_selection_stages_never_raise_over_a_seeded_fuzz(corpus_html_parts) -> None:
    """No exception, spans nest and stay in range, projecting twice is identical, and every
    gap the fuzzed input emits is registered. A depth bomb hits the cap as a recorded state."""
    print(f"selection fuzz -- {stdlib_scanner.interpreter_label()}")
    failures: list[str] = []
    seeds = 0
    for text in _fuzz_seeds(corpus_html_parts):
        seeds += 1
        problem = _html_error(text)
        if problem is not None:
            failures.append(f"{text[:60]!r}: {problem}")
    assert not failures, f"{len(failures)} failure(s):\n" + "\n".join(failures[:10])
    assert seeds >= 1000, seeds

    # A depth bomb is a recorded cap, never an exception or unbounded recursion; a huge
    # attribute value is one element with a long value and projects fine.
    bomb = htmltext.project(HTML_HUGE_INPUTS[0], max_depth=CAP_DEPTH, max_elements=CAP_ELEMENTS)
    assert bomb.tree.truncation is not None, "a 100k-deep bomb must be a recorded cap"
    assert bomb.tree.truncation.reason_id in (
        htmltree.REASON_DEPTH_CAP,
        htmltree.REASON_ELEMENT_COUNT_CAP,
    )
    huge_attribute = htmltext.project(
        HTML_HUGE_INPUTS[1], max_depth=CAP_DEPTH, max_elements=CAP_ELEMENTS
    )
    assert isinstance(huge_attribute.text, str)
    assert [element.tag for element in huge_attribute.tree.elements] == ["img"]


def test_a_planted_raiser_makes_the_html_fuzz_fail() -> None:
    """The fuzz is not vacuous: a planted raise is caught, and the seed stream is deterministic."""
    assert _html_error("<p>x</p>") == _html_error("<p>x</p>") == None  # noqa: E711
    original = htmltree._TreeBuilder._apply_implied_end

    def raiser(self, tag: str) -> None:
        raise RuntimeError("planted")

    htmltree._TreeBuilder._apply_implied_end = raiser
    try:
        problem = _html_error("<p>x</p>")
    finally:
        htmltree._TreeBuilder._apply_implied_end = original
    assert problem is not None and "planted" in problem, problem

    first = list(_mutate(random.Random(7), "<p>a</p>") for _ in range(5))
    second = list(_mutate(random.Random(7), "<p>a</p>") for _ in range(5))
    assert first == second, "the fuzz seed stream is not deterministic"


def test_the_html_stages_are_linear_on_a_megabyte_body() -> None:
    """A doubling test on **operation counts**: scanning the projected tree stays linear.

    The stage is the selection pass that reads every projected element
    (``selection_stage.external_references``), whose own deterministic counter
    (``selection_stage.WORK`` -- the ``WorkCounter`` seam ``walk``, ``text_rules`` and
    ``dom_rules`` already use) replaces the wall-clock check the operating rules forbid.
    The count is a pure function of the bytes, so the assertion is exact and reproducible,
    never a clock. The counter is one step per element examined plus one per
    ``URL_ATTRIBUTES`` row compared, hence the ``1 + len(URL_ATTRIBUTES)`` per element.
    """
    steps: dict[int, int] = {}
    elements: dict[int, int] = {}
    for megabytes in (1, 2):
        body = ("<p>x</p>" * ((megabytes * 1024 * 1024) // 8)).encode("ascii")
        raw = _message(body)
        result = _walk(raw)
        assert len(result.parts) == 1, megabytes
        selection_stage.WORK.reset()
        selection_stage.external_references(
            raw, result, max_depth=8, max_elements=1_000_000
        )
        steps[megabytes] = selection_stage.WORK.count()
        elements[megabytes] = (megabytes * 1024 * 1024) // 8
    per_element = 1 + len(selection_stage.URL_ATTRIBUTES)
    assert steps[1] == elements[1] * per_element, (steps[1], elements[1], per_element)
    assert steps[2] == elements[2] * per_element, (steps[2], elements[2], per_element)
    # A linear stage doubles; the bound is loose so a fault elsewhere cannot fail the gate,
    # but it still catches a quadratic pass (which would be ~4x or worse).
    assert steps[2] <= steps[1] * 2.5, (steps[1], steps[2])


def test_the_corpus_projection_hash_is_interpreter_stable() -> None:
    """The corpus projection hash is recorded and equal on CPython 3.14 and CPython 3.11."""
    label = html_projection_hash.interpreter_label()
    print(f"selection projection hash input -- {label}")
    assert label.startswith("CPython ")
    mine = html_projection_hash.corpus_projection_hash()
    assert len(mine) == 64, mine

    sys.path.insert(0, str(ROOT / "tools"))
    import runboth

    second = runboth.find_python311()
    if second is None:
        print("selection: no CPython 3.11 found -- cross-interpreter projection hash not checked")
        return
    prefix, source, version = second
    core = Path(docextract_core.__file__).resolve().parent.parent
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT), str(core)])}
    completed = subprocess.run(
        [*prefix, str(ROOT / "tests" / "support" / "html_projection_hash.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    theirs = next(
        line.split(":", 1)[1].strip()
        for line in completed.stdout.splitlines()
        if line.startswith("corpus projection hash:")
    )
    assert theirs == mine, (
        f"the corpus projection hash differs between {label} and CPython {version} ({source}): "
        f"{mine} vs {theirs}"
    )


# ------------------------------------------------------- the L1 gate can still fail

HTML_SPANS_SIDECAR = GENERATED / "html_style_and_script.expected.json"
CID_SIDECAR = GENERATED / "html_href_img_remote_and_cid.expected.json"
GROUP_SIDECAR = GENERATED / "text_calendar_alternative.expected.json"
SELECTION_SIDECAR = GENERATED / "alternative_text_html.expected.json"
EMPTY_SIDECAR = GENERATED / "plain_effectively_empty.expected.json"


def _gate(tmp_path: Path, name: str, source: Path, mutate):
    tamper(tmp_path, source, mutate, name=name)
    from emailextract.evals import l1_gate

    return l1_gate(tmp_path / name)


def test_an_untampered_html_copy_is_green(tmp_path: Path) -> None:
    """The control: the wrong copies below fail because they are wrong, not because they are copies."""
    from emailextract.evals import l1_gate

    tamper(tmp_path, HTML_SPANS_SIDECAR, lambda payload: None, name="clean")
    gate = l1_gate(tmp_path / "clean")
    assert gate.passed is True, gate.lines()


#: name -> (sidecar, the one-row tamper, the fact whose mismatch line the gate must print).
GATE_TAMPERS: dict[str, tuple[Path, Callable[[dict], None], str]] = {
    "shifted_html_span": (
        HTML_SPANS_SIDECAR,
        lambda payload: payload["facts"]["body.html_spans"]["value"][0].__setitem__(3, 99),
        "body.html_spans",
    ),
    "missing_cid": (
        CID_SIDECAR,
        lambda payload: payload["facts"]["body.cid_refs"]["value"][0].__setitem__(
            1, ["wrong@example.test"]
        ),
        "body.cid_refs",
    ),
    "wrong_group_id": (
        GROUP_SIDECAR,
        lambda payload: [
            row.__setitem__(1, "9") for row in payload["facts"]["body.alternative_group"]["value"]
        ],
        "body.alternative_group",
    ),
    "wrong_selection": (
        SELECTION_SIDECAR,
        lambda payload: payload["facts"]["body.selection"]["value"].reverse(),
        "body.selection",
    ),
    "missing_emptiness_row": (
        EMPTY_SIDECAR,
        lambda payload: payload["facts"]["body.plain_effectively_empty"]["value"][0].__setitem__(
            1, "stub_only"
        ),
        "body.plain_effectively_empty",
    ),
}


@pytest.mark.parametrize("name", sorted(GATE_TAMPERS))
def test_a_wrong_sidecar_for_each_new_body_fact_fails_the_gate(name: str, tmp_path: Path) -> None:
    """A wrong sidecar for each of the five new facts flips the L1 gate to fail, naming the fact."""
    source, mutate, fact_id = GATE_TAMPERS[name]
    gate = _gate(tmp_path, name, source, mutate)
    assert gate.passed is False, gate.lines()
    assert any(f"{fact_id} mismatch" in line for line in gate.evidence), (name, gate.evidence)


def test_the_cid_helper_is_deterministic_for_sets() -> None:
    """A set input has no order and str hashing is randomised per process: the result is sorted (review fix)."""
    from emailextract.selection import dangling_and_unreferenced

    referenced = {"z@x.test", "m@x.test", "B@x.test", "a@x.test"}
    content_ids = {"a@x.test", "q@x.test", "c@x.test", "y@x.test", "b@x.test"}
    dangling, unreferenced = dangling_and_unreferenced(referenced, content_ids)
    assert dangling == ["B@x.test", "m@x.test", "z@x.test"]
    assert unreferenced == ["b@x.test", "c@x.test", "q@x.test", "y@x.test"]
    # a list keeps its first-occurrence order
    assert dangling_and_unreferenced(["z@x.test", "a@x.test"], ["q@x.test"]) == (
        ["z@x.test", "a@x.test"],
        ["q@x.test"],
    )
