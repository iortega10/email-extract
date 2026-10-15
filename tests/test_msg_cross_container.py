"""Turn 1b.9: the cross-container pair -- D14 both ways.

One synthetic message built twice, as ``.eml`` (a ``multipart/alternative`` with plain + HTML)
and as ``.msg`` (an ``IPM.Note`` with the original headers and the same HTML, no plain stream).
By D14 they share a ``content_fingerprint.body_digest`` (over the selected HTML view's code
points as UTF-8) and differ in ``container_hash`` (the file bytes), and the pair is **never**
deduped on the raw hash.

The three declared tests are:

* ``test_the_pair_has_different_container_hash_and_equal_body_digest``;
* ``test_the_pair_is_one_document_shape_modulo_d14``;
* ``test_the_pair_with_a_plain_only_view_is_no_candidate``;

plus the extras: D5 (never dedupe, through ``ingest``) and the determinism of both halves.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

from cfb_writer import build_cfb, storage, stream  # noqa: E402

from emailextract import store  # noqa: E402
from emailextract.assemble import assemble  # noqa: E402
from emailextract.container import EmlContainer, memory_bytes  # noqa: E402
from emailextract.ids import sha256_hex  # noqa: E402
from emailextract.model import BodyView, ContainerKind  # noqa: E402
from emailextract.msgcontainer import MsgContainer  # noqa: E402
from emailextract.parse import Limits  # noqa: E402
from support import mapi_table, msg_construction  # noqa: E402

MSG = ROOT / "fixtures" / "msg"
LIMITS = Limits.untrusted()

#: The HTML view's text for the pair, typed by hand; its sha256 is the expected ``body_digest``
#: (D2: computed independently, never by calling ``_content_fingerprint``).
PAIR_HTML_TEXT = "synthetic turn 1b.9 pair body\r\n"
#: The scaffolding the projection owns and the ``.msg`` document never carries (D2/C6).
SCAFFOLDING = {"MIME-Version", "Content-Type", "Content-Transfer-Encoding"}

#: The hand-typed allowed differences between the two documents (D3), each with its reason.
ALLOWED_DOCUMENT_FIELDS = {
    "container_kind": "rfc822 against cfb_msg (D14)",
    "container_hash": "the file bytes differ (D14)",
    "container_facts": "the container reports its own kind's facts (D14)",
    "headers": "the .msg excludes the projection's scaffolding headers; each keeps its value",
    "parts": "the .eml adds a multipart/alternative and a plain leaf (D2)",
    "run_record": "run_id is content-addressed over the container hash",
}
ALLOWED_PART_FIELDS = {
    "part_id": "content-addressed over the container hash, so it differs",
    "parent_part_id": "the .eml's HTML is a member of the alternative; the .msg's is standalone",
    "selection": "the .eml's HTML is alternative_not_selected; the .msg's is n/a",
    "size_bytes": "the .eml leaf's decoded size; the .msg leaf is a pass-through stream",
    "sha256": "the .eml leaf's decoded bytes; the .msg leaf is a pass-through stream",
    "encoding_source": "the .msg leaf is a pass-through with the 0x007D code page's charset",
    "decode_chain": "declared_cte 8bit/utf-8 against binary/windows-1252; the HTML is ASCII",
    "stream_ref": "only the .msg publishes a container stream reference",
}

_CLASS_BYTES = "IPM.Note".encode("utf-16-le")


def _bytes(name: str) -> bytes:
    return (MSG / f"{name}.msg").read_bytes()


def _pair():
    eml = assemble(EmlContainer(memory_bytes(msg_construction.pair_eml_bytes())), limits=LIMITS)
    msg = assemble(MsgContainer(_bytes("pair_gmail_reply")), limits=LIMITS)
    return eml, msg


def _shape(value: object, prefix: str = "") -> set[str]:
    """The nested field-name set of a record tree (one ``EmailDocument``'s shape)."""
    out: set[str] = set()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        for field in dataclasses.fields(value):
            out.add(prefix + "." + field.name)
            out |= _shape(getattr(value, field.name), prefix + "." + field.name)
    elif isinstance(value, (list, tuple)):
        for item in value:
            out |= _shape(item, prefix + "[]")
    return out


def _html_only_msg(*, transport: str, html: bytes) -> bytes:
    """An ``IPM.Note`` with a ``001F`` transport stream and one HTML body (a test-built half)."""
    table = mapi_table.message_table(
        [mapi_table.variable_entry(mapi_table.PROP_MESSAGE_CLASS, mapi_table.PT_UNICODE, len(_CLASS_BYTES))]
    )
    return build_cfb(
        storage(
            "Root Entry",
            stream("__properties_version1.0", table),
            stream("__substg1.0_001A001F", _CLASS_BYTES),
            stream("__substg1.0_007D001F", transport.encode("utf-16-le")),
            stream("__substg1.0_10130102", html),
        )
    )


def _plain_only_eml(text: str) -> bytes:
    return (
        "Subject: plain only\r\n"
        "MIME-Version: 1.0\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "Content-Transfer-Encoding: 8bit\r\n"
        "\r\n"
        + text
    ).encode("utf-8")


# ------------------------------------------------------- the declared tests


def test_the_pair_has_different_container_hash_and_equal_body_digest() -> None:
    """D2/D14: different ``container_hash``, equal ``body_digest`` over the HTML view's text."""
    eml, msg = _pair()
    expected = hashlib.sha256(PAIR_HTML_TEXT.encode("utf-8")).hexdigest()
    assert eml.content_fingerprint.body_digest == expected
    assert msg.content_fingerprint.body_digest == expected
    assert eml.content_fingerprint == msg.content_fingerprint
    assert eml.content_fingerprint.body_digest_view is BodyView.HTML
    assert msg.content_fingerprint.body_digest_view is BodyView.HTML
    # The hashes address the file bytes, and differ.
    assert eml.container_hash == sha256_hex(msg_construction.pair_eml_bytes())
    assert msg.container_hash == sha256_hex(_bytes("pair_gmail_reply"))
    assert eml.container_hash != msg.container_hash
    assert eml.container_kind is ContainerKind.RFC822
    assert msg.container_kind is ContainerKind.CFB_MSG
    # The .eml has a plain view; the .msg has none (the measured 10-of-11 real shape).
    assert any(part.content_type == "text/plain" for part in eml.parts)
    assert not any(part.content_type == "text/plain" for part in msg.parts)


def test_the_pair_is_one_document_shape_modulo_d14() -> None:
    """D3: every field that differs between the two documents is in a hand-typed allow-list."""
    eml, msg = _pair()
    # One shape: the same nested field names, ignoring the optional ``stream_ref`` subtree.
    assert {path for path in _shape(eml) if "stream_ref" not in path} == {
        path for path in _shape(msg) if "stream_ref" not in path
    }
    # Document level: every difference is allowed, with its reason; everything else is equal.
    for field in dataclasses.fields(eml):
        if getattr(eml, field.name) != getattr(msg, field.name):
            assert field.name in ALLOWED_DOCUMENT_FIELDS, field.name
    for name in ("content_fingerprint", "status", "attachments", "quote_boundaries", "view_levels"):
        assert getattr(eml, name) == getattr(msg, name), name
    # The run record differs only in run_id (content-addressed over the container hash).
    for field in dataclasses.fields(eml.run_record):
        if field.name == "run_id":
            assert eml.run_record.run_id != msg.run_record.run_id
            continue
        assert getattr(eml.run_record, field.name) == getattr(msg.run_record, field.name), field.name
    # The headers: the .msg excludes the projection's scaffolding; shared fields keep the value.
    assert [field.name for field in msg.headers] == [
        field.name for field in eml.headers if field.name not in SCAFFOLDING
    ]
    twin = {field.name: field for field in eml.headers}
    for field in msg.headers:
        assert field.raw_value == twin[field.name].raw_value
        assert field.stream_ref is not None
        assert twin[field.name].stream_ref is None
    # The parts: the .msg is HTML-only; the .eml adds the alternative and the plain leaf.
    assert [part.content_type for part in msg.parts] == ["text/html"]
    assert [part.content_type for part in eml.parts] == ["multipart/alternative", "text/plain", "text/html"]
    eml_html = next(part for part in eml.parts if part.content_type == "text/html")
    msg_html = next(part for part in msg.parts if part.content_type == "text/html")
    assert eml_html.sha256 != msg_html.sha256  # the .eml's decoded bytes vs the stream's
    for field in dataclasses.fields(eml_html):
        if getattr(eml_html, field.name) != getattr(msg_html, field.name):
            assert field.name in ALLOWED_PART_FIELDS, field.name
    # The plain part exists only on the .eml side: a named difference, not a length.
    assert not any(part.content_type == "text/plain" for part in msg.parts)


def test_the_pair_with_a_plain_only_view_is_no_candidate() -> None:
    """D4: a plain-only against an HTML-only view differs in ``body_digest_view``: no candidate."""
    words = "the same words\r\n"
    plain = assemble(EmlContainer(memory_bytes(_plain_only_eml(words))), limits=LIMITS)
    html = assemble(
        MsgContainer(_html_only_msg(transport="Subject: x\r\n\r\n", html=b"<html><body><p>the same words</p></body></html>\r\n")),
        limits=LIMITS,
    )
    assert plain.content_fingerprint.body_digest_view is BodyView.PLAIN
    assert html.content_fingerprint.body_digest_view is BodyView.HTML
    # The text is the same, so the digests are equal; the records still differ (the view).
    assert plain.content_fingerprint.body_digest == html.content_fingerprint.body_digest
    assert plain.content_fingerprint != html.content_fingerprint
    # No candidates are built in Phase 1b; the view difference is what makes it "no candidate".
    assert plain.same_message_candidates == []
    assert html.same_message_candidates == []


# ------------------------------------------------------- the extras


def test_the_pair_is_never_deduped_by_raw_hash(tmp_path: Path) -> None:
    """D5: both halves are retained, no merge and no cross-reference; re-ingest is a no-op."""
    collection = store.document_store(tmp_path / "store")
    eml_artifact, eml_created = store.store_document(
        EmlContainer(memory_bytes(msg_construction.pair_eml_bytes())), collection, limits=LIMITS
    )
    msg_artifact, msg_created = store.store_document(
        MsgContainer(_bytes("pair_gmail_reply")), collection, limits=LIMITS
    )
    assert eml_created is True and msg_created is True
    assert eml_artifact.container_hash != msg_artifact.container_hash
    assert eml_artifact.key != msg_artifact.key
    # The equal digest was not a reason to drop one: two documents, both retained.
    stored = [
        name
        for name in store.store_snapshot(tmp_path / "store")
        if name.startswith("documents/") and not name.endswith("index.json")
    ]
    assert len(stored) == 2, stored
    assert (
        eml_artifact.document.content_fingerprint.body_digest
        == msg_artifact.document.content_fingerprint.body_digest
    )
    # No merge and no cross-reference is written.
    assert eml_artifact.document.same_message_candidates == []
    assert msg_artifact.document.same_message_candidates == []
    # Re-ingesting either is a no-op, and the store is byte-identical afterwards.
    before = store.store_snapshot(tmp_path / "store")
    assert store.reingest_document_is_noop(
        EmlContainer(memory_bytes(msg_construction.pair_eml_bytes())), collection, limits=LIMITS
    )
    assert store.reingest_document_is_noop(
        MsgContainer(_bytes("pair_gmail_reply")), collection, limits=LIMITS
    )
    assert store.store_snapshot(tmp_path / "store") == before


def test_the_pair_is_deterministic_across_hash_seeds() -> None:
    """The pair's two container hashes and digests are identical under any hash seed."""
    script = (
        "import hashlib, json, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "sys.path.insert(0, sys.argv[1] + '/tests')\n"
        "from pathlib import Path\n"
        "from emailextract.container import EmlContainer, memory_bytes\n"
        "from emailextract.msgcontainer import MsgContainer\n"
        "from emailextract.assemble import assemble\n"
        "from emailextract.parse import Limits\n"
        "from support import msg_construction\n"
        "L = Limits.untrusted()\n"
        "root = Path(sys.argv[1])\n"
        "eml = assemble(EmlContainer(memory_bytes(msg_construction.pair_eml_bytes())), limits=L)\n"
        "msg = assemble(MsgContainer((root / 'fixtures' / 'msg' / 'pair_gmail_reply.msg').read_bytes()), limits=L)\n"
        "print(json.dumps({\n"
        "  'eml_hash': eml.container_hash, 'msg_hash': msg.container_hash,\n"
        "  'eml_digest': eml.content_fingerprint.body_digest,\n"
        "  'msg_digest': msg.content_fingerprint.body_digest,\n"
        "}, sort_keys=True))\n"
    )
    baseline = None
    for seed in ("0", "1234567"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        result = subprocess.run(
            [sys.executable, "-c", script, str(ROOT)],
            capture_output=True,
            text=True,
            cwd=ROOT,
            env=env,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        payload = result.stdout.strip()
        if baseline is None:
            baseline = payload
        else:
            assert payload == baseline, (seed, payload, baseline)
