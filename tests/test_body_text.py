"""Turn BODY1: ``body_text`` -- D14's view, on demand, with the line table and the stamps.

The typed labels are ``tests/support/body_text_labels.py``, hand-typed from each fixture's
construction **before** this accessor ran (the repo's label protocol; they sit under
``tests/support/`` so ``tools/update_label_ledger.py`` fingerprints them and an edit is
refused in place). This file compares against them and asserts the properties the brief
names:

* each fixture's text equals its typed label, over **D14's** view;
* the view is the digest's view (one rule: ``assemble.selected_body_text``);
* the segments cover the text with no gap and no overlap, and every locator resolves to its
  segment's own characters;
* ``truncated``/``max_chars`` boundaries, and a bad ``max_chars`` is a caller error;
* a message with no text body view returns a reason, not an exception, and one that cannot
  be read at all returns a typed refusal;
* the ``.msg`` and the ``.eml`` of one message agree on the text;
* a zero-width space survives and a tracking pixel adds no text;
* nothing the accessor returns reaches a record (no body text in a manifest field, no
  record shape moved);
* a decode-rule change moves the ledger's ``body_text`` fingerprint (so it cannot land
  without a ``BODY_TEXT_VERSION`` bump);
* the module imports no network and no new dependency.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import pytest  # noqa: E402
from docextract_core.codec import encode  # noqa: E402
from support import body_text_labels as labels  # noqa: E402

import behavior_ledger  # noqa: E402
from emailextract import (  # noqa: E402
    BODY_TEXT_VERSION,
    DECODE_CHAIN_VERSION,
    EMAIL_PARSER_VERSION,
    HTMLTEXT_VERSION,
    OUTPUT_SCHEMA_VERSION,
    BodyRefusal,
    BodyText,
    body_text,
)
from emailextract import text as text_stage  # noqa: E402
from emailextract.assemble import assemble, selected_body_text  # noqa: E402
from emailextract.container import EmlContainer, memory_bytes  # noqa: E402
from emailextract.ids import sha256_hex  # noqa: E402
from emailextract.msgcontainer import MsgContainer  # noqa: E402
from emailextract.model import BodyView, record_to_bytes  # noqa: E402
from emailextract.parse import Limits  # noqa: E402

FIXTURES = ROOT / "fixtures"
MODULE = ROOT / "emailextract" / "bodytext.py"
LIMITS = Limits.untrusted()

#: The labelled stems, in the label file's own order.
LABELLED = sorted(labels.BODY_TEXT_LABELS)


def _document(source: object):
    """The assembled document for one source, so a test can compare against D14's view."""
    if isinstance(source, (bytes, str, Path)):
        decision = EmlContainer(source).raw_bytes()
        container = MsgContainer(decision) if decision[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" else EmlContainer(decision)
    else:
        container = source
    return assemble(container, limits=LIMITS)


@pytest.mark.parametrize("stem", LABELLED)
def test_each_labelled_fixture_returns_its_typed_text(stem: str) -> None:
    """The typed body text, verbatim -- the label protocol's comparison."""
    label = labels.BODY_TEXT_LABELS[stem]
    record = body_text(FIXTURES / str(label["fixture"]))
    assert isinstance(record, BodyText), record
    assert record.view == label["view"]
    assert record.text == label["text"]
    assert record.reason_id == label["reason_id"]
    assert record.char_count == len(str(label["text"]))
    assert record.truncated is False


@pytest.mark.parametrize("stem", LABELLED)
def test_every_labelled_fixture_takes_the_view_d14_digests(stem: str) -> None:
    """The view is D14's view and the text is over the digest's own code points."""
    label = labels.BODY_TEXT_LABELS[stem]
    record = body_text(FIXTURES / str(label["fixture"]))
    assert isinstance(record, BodyText), record
    document = _document(FIXTURES / str(label["fixture"]))
    assert record.view == document.content_fingerprint.body_digest_view.value
    assert record.view == BodyView(record.view).value
    assert sha256_hex(record.text.encode("utf-8")) == document.content_fingerprint.body_digest


@pytest.mark.parametrize("stem", LABELLED)
def test_the_segments_partition_the_text_and_every_locator_resolves(stem: str) -> None:
    """No gap, no overlap, and each locator names exactly its segment's characters."""
    label = labels.BODY_TEXT_LABELS[stem]
    record = body_text(FIXTURES / str(label["fixture"]))
    assert isinstance(record, BodyText), record
    text = record.text
    if not text:
        assert record.segments == ()
        return
    assert record.segments, stem
    previous_end = 0
    for ordinal, (start, end, locator) in enumerate(record.segments):
        assert start == previous_end, (stem, ordinal, start, previous_end)
        assert end > start, (stem, ordinal)
        # The locator's own four members name the same characters.
        assert locator.span.start == start and locator.span.end == end
        assert locator.unit == ordinal
        assert locator.view == record.view
        assert locator.part == (record.segments[0][2].part)
        assert text[start:end] != "" or start == end
        previous_end = end
    assert previous_end == len(text)


def test_a_message_with_no_text_body_has_a_reason_not_an_exception() -> None:
    """``body.no_text_part`` when no text body view exists -- and ``None`` when one is empty.

    The two are different facts and the accessor keeps them apart: ``body_no_text_part`` has
    only an ``application/pdf`` child, so there is nothing to choose and the reason id says
    why; ``headers_only`` *does* declare a ``text/plain`` body, whose text is the empty
    string, so it needs no reason at all.
    """
    record = body_text(FIXTURES / "generated" / "body_no_text_part.eml")
    assert isinstance(record, BodyText), record
    assert record.text == "" and record.segments == () and record.char_count == 0
    assert record.reason_id == "body.no_text_part"
    empty_but_present = body_text(FIXTURES / "raw" / "headers_only.eml")
    assert isinstance(empty_but_present, BodyText), empty_but_present
    assert empty_but_present.text == ""
    assert empty_but_present.view == BodyView.PLAIN.value
    assert empty_but_present.reason_id is None


def test_a_source_that_is_not_a_message_is_a_typed_refusal() -> None:
    """A non-message is refused with the entry point's own reason, never an exception."""
    refused = body_text(b"this is not a message at all, just text\r\n")
    assert isinstance(refused, BodyRefusal), refused
    assert refused.reason_id == "not_a_message"


def test_a_body_that_cannot_be_decoded_is_a_typed_refusal(monkeypatch) -> None:
    """A stage that raises is a refusal with ``extractor_error``, not an exception."""
    def explodes(*arguments, **keywords):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "planted failure")

    monkeypatch.setattr(text_stage, "analyse_parts", explodes)
    refused = body_text(FIXTURES / "generated" / "plain_simple.eml")
    assert isinstance(refused, BodyRefusal), refused
    assert refused.reason_id == "extractor_error"


def test_max_chars_boundaries_truncate_and_flag() -> None:
    """``max_chars`` equal to the length keeps the text; one less truncates and says so."""
    label = labels.BODY_TEXT_LABELS["plain_simple"]
    text = str(label["text"])
    exact = body_text(FIXTURES / str(label["fixture"]), max_chars=len(text))
    assert isinstance(exact, BodyText), exact
    assert exact.truncated is False
    assert exact.text == text and exact.char_count == len(text)
    cut = body_text(FIXTURES / str(label["fixture"]), max_chars=len(text) - 1)
    assert isinstance(cut, BodyText), cut
    assert cut.truncated is True
    assert cut.text == text[: len(text) - 1]
    assert cut.char_count == len(text) - 1
    # The segments are over the returned text, so they still partition it exactly.
    assert cut.segments[-1][1] == len(cut.text)
    one = body_text(FIXTURES / str(label["fixture"]), max_chars=1)
    assert isinstance(one, BodyText), one
    assert one.text == text[:1] and one.truncated is True


def test_max_chars_outside_its_bounds_is_a_caller_error() -> None:
    """``0``, a negative and a value over the hard ceiling all raise; the ceiling works."""
    from emailextract import MAX_CHARS_CEILING

    for bad in (0, -1, MAX_CHARS_CEILING + 1):
        with pytest.raises(ValueError):
            body_text(FIXTURES / "generated" / "plain_simple.eml", max_chars=bad)
    generous = body_text(
        FIXTURES / "generated" / "plain_simple.eml", max_chars=MAX_CHARS_CEILING
    )
    assert isinstance(generous, BodyText)


def test_the_msg_and_eml_of_one_message_agree_on_text() -> None:
    """The same message as ``.msg`` and as ``.eml``: one body view, one text (D14)."""
    from support import msg_construction

    eml = body_text(
        memory_bytes(msg_construction.pair_eml_bytes())
    )
    msg = body_text((FIXTURES / "msg" / "pair_gmail_reply.msg").read_bytes())
    assert isinstance(eml, BodyText) and isinstance(msg, BodyText)
    assert eml.view == msg.view == BodyView.HTML.value
    assert eml.text == msg.text


def test_a_zero_width_space_survives_and_a_tracking_pixel_adds_no_text() -> None:
    """``&#8203;`` is one code point; the two images insert no character."""
    record = body_text(memory_bytes(labels.ZERO_WIDTH_TRACKING_PIXEL_EML))
    assert isinstance(record, BodyText), record
    assert record.view == BodyView.HTML.value
    assert record.text == labels.ZERO_WIDTH_TRACKING_PIXEL_TEXT
    assert "\u200b" in record.text
    assert record.char_count == 11


def test_the_record_stamps_every_version() -> None:
    """The record carries the four stamps D1 names, and they are the live constants."""
    record = body_text(FIXTURES / "generated" / "html_only.eml")
    assert isinstance(record, BodyText), record
    assert record.email_parser_version == EMAIL_PARSER_VERSION
    assert record.decode_chain_version == DECODE_CHAIN_VERSION
    assert record.htmltext_version == HTMLTEXT_VERSION
    assert record.body_text_version == BODY_TEXT_VERSION
    # Nothing else in the record is a stamp: the record is the answer, not a citation.
    assert BODY_TEXT_VERSION not in (record.text,)


def test_the_body_accessor_is_exported_from_the_package() -> None:
    """``body_text``, its records and its constants are public (the hub's whole surface)."""
    import emailextract

    for name in (
        "body_text",
        "BodyText",
        "BodyRefusal",
        "BODY_TEXT_VERSION",
        "DEFAULT_MAX_CHARS",
        "MAX_CHARS_CEILING",
    ):
        assert name in emailextract.__all__, name
        assert hasattr(emailextract, name), name


@pytest.mark.parametrize("stem", LABELLED)
def test_no_manifest_byte_changes(stem: str) -> None:
    """No body text reaches a record: the digest is a digest, and the text is nowhere in it.

    ``assemble`` is the only thing that writes a record and the accessor calls it with nothing,
    so a document assembled after two accessor calls is byte-identical to the one assembled
    before them (the committed golden is the suite's own re-run, in
    ``tests/test_eml_golden.py``). On that serialized record three things are asserted: the
    fingerprint field holds a **digest** and not the text, the body text appears nowhere in the
    record's bytes, and no record field was added (the ``contracts`` fingerprint is the one the
    ledger holds under ``OUTPUT_SCHEMA_VERSION``).
    """
    label = labels.BODY_TEXT_LABELS[stem]
    path = FIXTURES / str(label["fixture"])
    body = body_text(path)
    assert isinstance(body, BodyText), body
    before = _document(path)
    body_text(path)
    after = _document(path)
    assert record_to_bytes(before) == record_to_bytes(after)
    assert after.content_fingerprint.body_digest == sha256_hex(body.text.encode("utf-8"))
    assert after.content_fingerprint.body_digest != body.text
    serialized = record_to_bytes(after)
    if len(body.text) >= 8 and body.text.strip():
        assert body.text.encode("utf-8") not in serialized, stem
    ledger = behavior_ledger.load_ledger()["contracts"]
    assert behavior_ledger.contracts_fingerprint() == ledger[OUTPUT_SCHEMA_VERSION]


def test_the_accessor_stores_nothing_and_a_second_call_re_reads() -> None:
    """Two calls answer the same and neither writes: the accessor has no cache to disagree."""
    path = FIXTURES / "generated" / "attachments_mixed.eml"
    first = body_text(path)
    second = body_text(path)
    assert first == second
    assert list(EmlContainer(path).raw_bytes()) == list(path.read_bytes())


def test_a_decode_change_moves_the_body_text_fingerprint(monkeypatch) -> None:
    """A decode rule that reaches the text moves the recorded fingerprint, so it needs a bump."""
    before = behavior_ledger.fingerprints()["body_text"]
    monkeypatch.setattr(
        text_stage,
        "_decode_cte",
        lambda payload, declared, *, limit=None: ("7bit", payload, False, None),
    )
    after = behavior_ledger.fingerprints()["body_text"]
    assert after != before
    # ... and the ledger's own check names the constant to bump.
    problems = behavior_ledger.check()
    assert any(problem.startswith("body_text:") and "BODY_TEXT_VERSION" in problem for problem in problems)


def test_the_two_accessor_components_are_keyed_by_their_own_constants() -> None:
    """``body_text`` is keyed by ``BODY_TEXT_VERSION`` alone, and it is a corpus component."""
    from emailextract import ATTACHMENT_ACCESSOR_VERSION
    from emailextract import versions

    strings = behavior_ledger.version_strings()
    assert strings["body_text"] == versions.BODY_TEXT_VERSION == BODY_TEXT_VERSION
    assert strings["attachment_payloads"] == versions.ATTACHMENT_ACCESSOR_VERSION
    assert ATTACHMENT_ACCESSOR_VERSION == "1"
    assert behavior_ledger.VERSION_CONSTANTS["body_text"] == "BODY_TEXT_VERSION"
    assert behavior_ledger.VERSION_CONSTANTS["attachment_payloads"] == "ATTACHMENT_ACCESSOR_VERSION"
    assert "body_text" in behavior_ledger.CORPUS_DEPENDENT
    assert "attachment_payloads" in behavior_ledger.CORPUS_DEPENDENT
    ledger = behavior_ledger.load_ledger()
    latest = behavior_ledger.latest_corpus(behavior_ledger.load_corpora())
    for component, constant in (("body_text", BODY_TEXT_VERSION), ("attachment_payloads", ATTACHMENT_ACCESSOR_VERSION)):
        assert f"{constant}|corpus:{latest}" in ledger[component], component


def test_the_accessor_imports_no_network_and_no_new_dependency() -> None:
    """The module's imports are the package's own modules, the stdlib and nothing else."""
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    third_party = {
        root
        for root in roots
        if root not in sys.stdlib_module_names and root not in {"emailextract", "__future__"}
    }
    assert not third_party, sorted(third_party)
    assert not roots & {"socket", "http", "urllib", "requests", "httpx", "threading", "concurrent"}
    # The container is read through the library's own entry point, never a URL or a subprocess.
    source = MODULE.read_text(encoding="utf-8")
    for forbidden in ("subprocess", "urlopen", "requests.", "print("):
        assert forbidden not in source, forbidden


def test_an_unknown_source_kind_is_refused_by_type() -> None:
    """A non-FileMaterial input is a ``TypeError`` from the container, not a silent answer."""
    with pytest.raises(TypeError):
        body_text(object())
