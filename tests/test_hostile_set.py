"""Turn 1.10b A: the hostile set, the network guard, the filename rule and the work budget.

Twelve hostile inputs the package must **refuse, cap or bound** -- never raise on -- are
built **inline** (the frozen corpus is not touched) and driven **end to end** through
``assemble`` and ``ingest_path`` at caller-chosen caps:

* the bytes are typed in the test (``_hostile_set``), never committed as fixtures;
* every cap a run hits is a :class:`~emailextract.model.CapRecord` on
  ``run_record.caps`` with a **closed** reason id (``walk.CAP_REASONS``), and no input
  raises an ``Exception`` out of ``assemble`` -- a stage refuses *by name*;
* ``gates.holes`` over the capped walk is empty, so every byte is still accounted for
  (D9, no silent drop) even when a cap stopped the read;
* nothing is fetched: a **socket guard** patches every socket/http/urllib/ssl entry point
  to raise, a full ingest runs under it, and the guard is shown able to fail (the
  anti-vacuity triple: the symbol exists, the patch is reached by a planted fetch, and the
  guarded observation is identical to the unguarded one);
* no attachment is ever written under its raw filename: the hostile filenames
  (``../../x``, absolute paths, drive letters, ``NUL``, reserved Windows names, trailing
  dots, 300 characters, RTL override, zero-width, percent-encoded and RFC 2231 forms)
  land only in the record's recorded fields, never on a path.

The last test is the **work budget**: doubling a hostile input must grow each stage's
deterministic **step count** by less than a stated factor (never seconds, never
``perf_counter``; single-threaded, which is the assumption the module-level counters need).

The declared stop point is the caps and the accounting; the correctness of the parts is
other turns' business, so nothing here compares a part to a label.
"""

from __future__ import annotations

import base64
import http.client
import socket
import ssl
import urllib.request
from pathlib import Path

import pytest

from emailextract import attach as attach_stage
from emailextract import htmltree
from emailextract import selection as selection_stage
from emailextract import store
from emailextract.assemble import assemble
from emailextract.container import EmlContainer, memory_bytes
from emailextract.evals import gates
from emailextract.ingest import OUTCOMES, SKIP_REASONS, ingest_path
from emailextract.model import CapRecord, Status, StatusOutcome
from emailextract.parse import Limits
from emailextract.quote import dom_rules, text_rules
from emailextract.quote import resolve as quote_resolve
from emailextract.rfc2047 import decode_encoded_words
from emailextract.walk import CAP_REASONS, WORK, walk

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "fixtures" / "generated"

#: The generous base every hostile input starts from; each input overrides the *one* cap it
#: is aimed at (stated in :data:`EXPECTED`). ``max_field_work_units_per_byte`` is 8 (the
#: approved default is 64) so a header bomb's RFC 2047 budget is small.
_HIGH = dict(
    max_input_bytes=64 * 1024 * 1024,
    max_depth=16,
    max_parts=1000,
    max_header_bytes=256 * 1024,
    max_decoded_part_bytes=32 * 1024 * 1024,
    max_decoded_total_bytes=128 * 1024 * 1024,
    max_field_work_units_per_byte=8,
)


def limits(**over: int) -> Limits:
    """A caller's ``Limits``: the base caps, with the named ones overridden."""
    return Limits(**{**_HIGH, **over})


# --------------------------------------------------------------- inline hostile builders


def deep_mime_nesting(levels: int) -> bytes:
    """``levels`` nested ``multipart/mixed`` declarations around one leaf."""
    out = bytearray()
    for index in range(levels):
        out += b"Content-Type: multipart/mixed; boundary=B%d\r\n\r\n--B%d\r\n" % (index, index)
    out += b"Content-Type: text/plain\r\n\r\nleaf\r\n"
    for index in reversed(range(levels)):
        out += b"\r\n--B%d--\r\n" % index
    return bytes(out)


def part_count_bomb(parts: int) -> bytes:
    """One multipart with ``parts`` sibling leaves -- a part-count bomb."""
    out = bytearray(b"Content-Type: multipart/mixed; boundary=B\r\n\r\n")
    for index in range(parts):
        out += b"--B\r\nContent-Type: text/plain\r\n\r\npart %d\r\n" % index
    out += b"--B--\r\n"
    return bytes(out)


def enormous_header_block(size: int) -> bytes:
    """A header region of at least ``size`` bytes, then a small body."""
    out = bytearray()
    index = 0
    while len(out) < size:
        out += b"X-Filler-%d: %s\r\n" % (index, b"a" * 60)
        index += 1
    return bytes(out) + b"\r\nbody\r\n"


def encoded_word_bomb(words: int) -> bytes:
    """A ``Subject`` that is ``words`` adjacent RFC 2047 words -- a decoder bomb."""
    value = b" ".join([b"=?utf-8?B?aGVsbG8gd29ybGQ=?="] * words)
    return b"Subject: " + value + b"\r\nContent-Type: text/plain\r\n\r\nbody\r\n"


def long_base64_run(chars: int) -> bytes:
    """One base64 run of ~``chars`` encoded bytes with **no newline** (10 MB at 10 MB)."""
    payload = base64.b64encode(b"x" * (chars * 3 // 4))
    return (
        b"Content-Type: application/octet-stream\r\nContent-Transfer-Encoding: base64\r\n\r\n"
        + payload
        + b"\r\n"
    )


def single_long_line(size: int) -> bytes:
    """One body line of ``size`` bytes with no newline inside it."""
    return b"Content-Type: text/plain\r\n\r\n" + b"a" * size + b"\r\n"


def gt_lines(count: int) -> bytes:
    """``count`` quoted (``>``) lines -- a boundary storm for the quote stage."""
    return b"Content-Type: text/plain; charset=utf-8\r\n\r\n" + b"> quoted line\r\n" * count


def on_wrote_near_misses(count: int) -> bytes:
    """``count`` lines one character away from ``On ... wrote:`` -- a rule-search storm."""
    return b"Content-Type: text/plain; charset=utf-8\r\n\r\n" + b"On a b c d e f g h wrote\r\n" * count


def sibling_blockquotes(count: int) -> bytes:
    """``count`` sibling ``<blockquote>`` elements -- an element-count bomb for the tree."""
    body = b"<html><body>" + b"<blockquote>q</blockquote>" * count + b"</body></html>"
    return b"Content-Type: text/html; charset=utf-8\r\n\r\n" + body


def data_uri_html() -> bytes:
    """An HTML body whose ``<img>`` is a ``data:`` URI: recorded, never expanded."""
    pixel = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode("ascii")
    body = b'<html><body><img src="data:image/png;base64,' + pixel.encode() + b'"></body></html>'
    return b"Content-Type: text/html; charset=utf-8\r\n\r\n" + body


def remote_image_html() -> bytes:
    """An HTML body with a remote ``<img>``: recorded, never fetched."""
    body = b'<html><body><img src="http://127.0.0.1:1/track.png"></body></html>'
    return b"Content-Type: text/html; charset=utf-8\r\n\r\n" + body


def nested_rfc822(depth: int) -> bytes:
    """A chain of ``depth`` ``message/rfc822`` parts around one leaf.

    The walker records the top-level part and **never descends**, so the cost is one linear
    pass over the bytes, not ``depth`` levels of recursion.
    """
    body = b"Content-Type: text/plain\r\n\r\nleaf\r\n"
    for _ in range(depth):
        body = b"Content-Type: message/rfc822\r\n\r\n" + body
    return body


#: The hostile set, in the order the turn lists it. Each carries the bytes and the caps the
#: run is made at (``None`` means :func:`limits` with no overrides).
HOSTILE: dict[str, tuple[bytes, dict[str, int]]] = {
    "deep_mime_nesting": (deep_mime_nesting(200), {"max_depth": 4}),
    "part_count_bomb": (part_count_bomb(200), {"max_parts": 8}),
    "enormous_header_block": (enormous_header_block(200_000), {"max_header_bytes": 4096}),
    "encoded_word_bomb": (encoded_word_bomb(50_000), {"max_header_bytes": 8 * 1024 * 1024}),
    "long_base64_run": (long_base64_run(10 * 1024 * 1024), {"max_decoded_part_bytes": 4096}),
    "data_uri_image": (data_uri_html(), {}),
    "remote_image": (remote_image_html(), {}),
    "nested_rfc822": (nested_rfc822(2_000), {"max_decoded_part_bytes": 4096}),
    "single_long_line": (single_long_line(10 * 1024 * 1024), {"max_decoded_part_bytes": 4096}),
    "gt_lines": (gt_lines(100_000), {}),
    "on_wrote_near_misses": (on_wrote_near_misses(100_000), {}),
    "sibling_blockquotes": (sibling_blockquotes(100_000), {"max_parts": 8}),
}

#: What each input is expected to do: the caps that must fire, the gaps that must be
#: recorded, and the one non-cap property its dimension asserts.
EXPECTED: dict[str, dict[str, object]] = {
    "deep_mime_nesting": {"caps": {"depth_cap"}},
    "part_count_bomb": {"caps": {"part_count_cap"}},
    "enormous_header_block": {"caps": {"header_bytes_cap"}},
    "encoded_word_bomb": {"caps": set()},
    "long_base64_run": {"caps": {"size_cap"}},
    "data_uri_image": {"caps": set(), "gaps": {"body.inline_data_uri"}},
    "remote_image": {"caps": set(), "gaps": {"security.remote_content_present"}},
    "nested_rfc822": {"caps": {"size_cap"}, "parts": 1},
    "single_long_line": {"caps": {"size_cap"}},
    "gt_lines": {"caps": set()},
    "on_wrote_near_misses": {"caps": set()},
    "sibling_blockquotes": {"caps": set(), "truncation": htmltree.REASON_ELEMENT_COUNT_CAP},
}


def _capped_walk(raw: bytes, caps: Limits):
    return walk(EmlContainer(memory_bytes(raw)), limits=caps)


# ------------------------------------------------------------------------ the network guard

#: Every entry point a fetch could reach for, as ``(module, attribute)``. The guard patches
#: each to raise, naming the call.
_FETCH_SYMBOLS = (
    (socket, "socket"),
    (socket, "create_connection"),
    (socket, "getaddrinfo"),
    (socket, "gethostbyname"),
    (http.client, "HTTPConnection"),
    (http.client, "HTTPSConnection"),
    (urllib.request, "urlopen"),
    (ssl, "create_default_context"),
    (ssl, "SSLContext"),
)


def _refuser(module: object, name: str):
    def refuse(*args: object, **kwargs: object) -> object:
        raise AssertionError(f"the library reached for the network: {module.__name__}.{name}")

    return refuse


def _install_fetch_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every fetch entry point raise, and assert each was there to patch (the triple's
    first leg: the symbol exists)."""
    for module, name in _FETCH_SYMBOLS:
        assert hasattr(module, name), f"the guard's symbol is gone: {module.__name__}.{name}"
        monkeypatch.setattr(module, name, _refuser(module, name))


def _guard_inputs() -> dict[str, bytes]:
    """The hostile set **plus** the committed remote-image / data:-URI / cid fixtures."""
    inputs = {name: raw for name, (raw, _caps) in HOSTILE.items()}
    for stem in (
        "html_href_img_remote_and_cid",
        "html_data_uri_and_tracking_pixel",
        "attach_remote_image_only",
        "inline_cid_referenced_and_not",
    ):
        inputs[stem] = (GENERATED / f"{stem}.eml").read_bytes()
    return inputs


def _write_inputs(root: Path, inputs: dict[str, bytes]) -> Path:
    directory = root / "in"
    directory.mkdir(parents=True, exist_ok=True)
    for name, raw in inputs.items():
        (directory / f"{name}.eml").write_bytes(raw)
    return directory


def test_a_socket_guard_fails_loudly_on_any_fetch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A full ingest over the hostile corpus reaches for no socket, http client or ssl."""
    inputs = _guard_inputs()
    assert len(inputs) >= len(HOSTILE) >= 12, f"only {len(inputs)} hostile input(s)"
    assert "remote_image" in inputs and "data_uri_image" in inputs
    directory = _write_inputs(tmp_path, inputs)

    # The unguarded run, read before the guard is installed so the test itself cannot trip it.
    baseline = ingest_path(directory, store.document_store(tmp_path / "base"), limits=limits())
    assert len(baseline.rows) == len(inputs)
    assert all(row.outcome in OUTCOMES for row in baseline.rows)

    with monkeypatch.context() as guard:
        _install_fetch_guard(guard)
        guarded = ingest_path(directory, store.document_store(tmp_path / "guarded"), limits=limits())
    # The triple's third leg: the observation is identical, so the guard changed nothing.
    assert guarded == baseline, "the guarded ingest differed from the unguarded one"

    # The triple's second leg: the guard can fail. Plant a fetch inside a stage's own seam
    # (``selection._follow``, the one place a reference would be dereferenced) and watch the
    # guard name the attempted call. ``assemble`` swallows every content exception by design,
    # so the proof drives the same stage directly rather than through the ingest.
    raw = remote_image_html()
    result = walk(EmlContainer(memory_bytes(raw)))

    def planted_fetch(url: str) -> bytes | None:
        urllib.request.urlopen(url)  # a real call, refused by the guard
        return None

    with monkeypatch.context() as guard:
        _install_fetch_guard(guard)
        guard.setattr(selection_stage, "_follow", planted_fetch)
        with pytest.raises(AssertionError) as raised:
            selection_stage.external_references(raw, result, max_depth=16, max_elements=1000)
    assert "urlopen" in str(raised.value), raised.value


# ------------------------------------------------------------- the hostile set end to end


@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_the_hostile_set_is_recorded_and_never_raised(name: str, tmp_path: Path) -> None:
    """Each hostile input assembles and ingests with a recorded cap state, never an exception."""
    raw, overrides = HOSTILE[name]
    caps = limits(**overrides)
    expected = EXPECTED[name]

    document = assemble(EmlContainer(memory_bytes(raw)), limits=caps)
    assert isinstance(document.status, StatusOutcome), name

    cap_ids = {cap.cap_id for cap in document.run_record.caps}
    assert cap_ids <= set(CAP_REASONS), f"{name}: a cap id is not closed: {cap_ids}"
    for cap in document.run_record.caps:
        assert isinstance(cap, CapRecord), name
    assert set(expected["caps"]) <= cap_ids, f"{name}: caps {cap_ids} miss {expected['caps']}"
    if not expected["caps"]:
        assert cap_ids == set(), f"{name}: unexpected cap {cap_ids}"

    if document.status.status is Status.SKIPPED:
        assert document.status.reason in CAP_REASONS, (name, document.status)

    # No silent drop: every input byte is still in exactly one accounted region.
    result = _capped_walk(raw, caps)
    holes = gates.holes(result.regions, len(raw))
    assert holes == [], f"{name}: unaccounted bytes: {holes[:3]}"

    # End to end through ingest_path: one row, a closed outcome, never a raise.
    directory = _write_inputs(tmp_path, {name: raw})
    manifest = ingest_path(directory, store.document_store(tmp_path / "store"), limits=caps)
    assert len(manifest.rows) == 1, name
    row = manifest.rows[0]
    assert row.outcome in OUTCOMES, (name, row)
    if row.outcome == "skipped":
        assert row.reason_id in SKIP_REASONS, (name, row)

    if "parts" in expected:
        assert len(result.parts) == expected["parts"], (
            f"{name}: the walker must not descend (parts {len(result.parts)})"
        )
    if "gaps" in expected:
        recorded = {
            gap_id
            for gap_id, _locator in selection_stage.body_gaps(
                raw, result, max_depth=caps.max_depth, max_elements=caps.max_parts
            )
        }
        assert set(expected["gaps"]) <= recorded, f"{name}: gaps {recorded} miss {expected['gaps']}"
    if "truncation" in expected:
        projections = selection_stage.html_projections(
            raw, result, max_depth=caps.max_depth, max_elements=caps.max_parts
        )
        assert projections, f"{name}: no html projection"
        reasons = {
            projection.tree.truncation.reason_id
            for _locator, projection in projections
            if projection.tree.truncation is not None
        }
        assert expected["truncation"] in reasons, f"{name}: truncation {reasons}"


# ------------------------------------------------------- the work budget (never a clock)

#: The factor a doubled input may grow a linear stage's step count by: 2.0 for the doubling
#: plus half again for the fixed per-message overhead the smaller input spreads over.
DOUBLING_FACTOR = 2.5


def _boundary_storm(lines: int) -> bytes:
    return b"Content-Type: multipart/mixed; boundary=B\r\n\r\n" + b"--B\r\n" * lines


def _b64_part(chars: int) -> bytes:
    return long_base64_run(chars)


def _near_misses(lines: int) -> bytes:
    return on_wrote_near_misses(lines)


def _blockquotes(count: int) -> bytes:
    return sibling_blockquotes(count)


def _rfc822_chain(depth: int) -> bytes:
    return nested_rfc822(depth)


def _encoded_words(words: int) -> bytes:
    return encoded_word_bomb(words)


#: The doubling families: ``name -> (builder, small argument, large argument, caps)``. The
#: large argument is twice the small one. A family whose hostile dimension **is** a cap
#: (depth, parts, decoded size) is measured **at that cap**, so its claim is "the cap bounds
#: the work, the input does not"; a family whose dimension is a linear scan (quoted lines,
#: near-miss lines, encoded words) is measured with the caps out of the way.
FAMILIES = (
    ("boundary_storm", _boundary_storm, 1_000, 2_000, {"max_parts": 20}),
    ("long_base64", _b64_part, 4_000, 8_000, {"max_decoded_part_bytes": 4096}),
    ("gt_lines", gt_lines, 500, 1_000, {}),
    ("on_wrote_near_misses", _near_misses, 500, 1_000, {}),
    ("sibling_blockquotes", _blockquotes, 200, 400, {"max_parts": 8}),
    ("nested_rfc822", _rfc822_chain, 50, 100, {"max_decoded_part_bytes": 4096}),
    ("deep_mime_nesting", deep_mime_nesting, 50, 100, {"max_depth": 4}),
    ("encoded_word_bomb", _encoded_words, 500, 1_000, {"max_header_bytes": 8 * 1024 * 1024}),
)


def _steps(raw: bytes, caps: Limits) -> dict[str, int]:
    """Every counter-bearing stage's deterministic step count for one input.

    ``walk``, ``text_rules``, ``dom_rules`` and ``selection`` have a module-level
    ``WorkCounter``; ``htmltree`` and ``attach`` have none, so their counts are the
    deterministic **size of what they produce** (elements, occurrences) -- the same claim,
    read off the output rather than a counter. ``rfc2047``'s work is bounded by its
    per-input-byte budget, so its count is the decoded code points.
    """
    container = EmlContainer(memory_bytes(raw))
    WORK.reset()
    result = walk(container, limits=caps)
    walk_steps = WORK.count()

    text_rules.WORK.reset()
    dom_rules.WORK.reset()
    quote_resolve.all_views(raw, result, max_depth=caps.max_depth, max_elements=caps.max_parts)
    text_steps = text_rules.WORK.count()
    dom_steps = dom_rules.WORK.count()

    selection_stage.WORK.reset()
    selection_stage.external_references(
        raw, result, max_depth=caps.max_depth, max_elements=caps.max_parts
    )
    selection_steps = selection_stage.WORK.count()

    projections = selection_stage.html_projections(
        raw, result, max_depth=caps.max_depth, max_elements=caps.max_parts
    )
    elements = sum(len(projection.tree.elements) for _locator, projection in projections)

    occurrences = len(
        attach_stage.attachments(
            raw, result, max_depth=caps.max_depth, max_elements=caps.max_parts, limits=caps
        ).occurrences
    )

    subject = next(
        (
            field.raw_value
            for field in result.parts[0].header_fields
            if field.name.lower() == "subject"
        ),
        "",
    )
    rfc2047_steps = len(decode_encoded_words(subject.encode("latin-1"), max_work_units=8).text)

    return {
        "walk": walk_steps,
        "text_rules": text_steps,
        "dom_rules": dom_steps,
        "selection": selection_steps,
        "htmltree": elements,
        "attach": occurrences,
        "rfc2047": rfc2047_steps,
    }


def test_work_per_input_byte_is_not_superlinear() -> None:
    """Doubling a hostile input grows every stage's step count by < ``DOUBLING_FACTOR``.

    The counters are deterministic functions of the bytes (no clock), so each count is
    exact and reproduces: the assertion is on operation counts, never seconds. The counters
    are process-global, so the test assumes it runs single-threaded.
    """
    stages = ("walk", "text_rules", "dom_rules", "selection", "htmltree", "attach", "rfc2047")
    assert len(FAMILIES) >= 8, f"only {len(FAMILIES)} doubling famil(ies)"
    failures: list[str] = []
    moved = 0
    for name, builder, small_arg, large_arg, overrides in FAMILIES:
        caps = limits(**overrides)
        small = builder(small_arg)
        large = builder(large_arg)
        assert len(large) > len(small), f"{name}: the large input is not larger"
        first = _steps(small, caps)
        assert set(first) == set(stages), f"{name}: stages {sorted(first)}"
        assert first == _steps(small, caps), f"{name}: the counters do not reproduce: {first}"
        second = _steps(large, caps)
        for stage in stages:
            cheap, dear = first[stage], second[stage]
            assert cheap >= 0 and dear >= 0, f"{name}/{stage}: a negative count"
            if cheap > 0:
                moved += 1
                if dear > cheap * DOUBLING_FACTOR:
                    failures.append(
                        f"{name}/{stage}: doubling grew {cheap} -> {dear} "
                        f"(factor {dear / cheap:.2f} > {DOUBLING_FACTOR})"
                    )
    assert not failures, failures
    assert moved >= len(FAMILIES), f"only {moved} stage counts moved across {len(FAMILIES)} families"


# ------------------------------------------------------- never a raw attachment filename

#: The hostile attachment filenames, as the **raw bytes** a producer would write in the
#: ``filename``/``name`` parameter. Each is also carried in the record's recorded fields
#: (that is where a raw filename is allowed to live).
HOSTILE_FILENAMES: tuple[bytes, ...] = (
    b"../../x",
    b"..\\..\\x",
    b"/etc/passwd",
    b"C:\\Windows\\evil.exe",
    b"a\x00b.bin",
    b"CON",
    b"NUL",
    b"AUX",
    b"report.txt...",
    b"trailing space ",
    b"x" * 300,
    "gnp\u202eexe.txt".encode("utf-8"),
    "zero\u200bwidth.txt".encode("utf-8"),
    b"%2e%2e/x",
    b"=?utf-8?B?Li4vLi4veA==?=",
)

#: Content-addressed artifact names the store writes: ``<64 hex>.json``, plus its own index.
_INDEX_NAMES = {"index.json"}


def _attachment_message(filename: bytes, *, rfc2231: bool = False) -> bytes:
    """A real MIME message with one base64 attachment under ``filename``."""
    payload = base64.b64encode(b"an attachment body")
    if rfc2231:
        parameter = b"filename*=utf-8''" + filename
    else:
        parameter = b'filename="' + filename + b'"'
    return (
        b"From: Ada <ada@example.test>\r\n"
        b"Content-Type: multipart/mixed; boundary=B\r\n\r\n"
        b"--B\r\nContent-Type: text/plain\r\n\r\nbody\r\n"
        b"--B\r\nContent-Type: application/octet-stream\r\n"
        b"Content-Transfer-Encoding: base64\r\n"
        b"Content-Disposition: attachment; " + parameter + b"\r\n\r\n"
        + payload + b"\r\n--B--\r\n"
    )


def _snapshot(root: Path) -> set[str]:
    return {str(path.relative_to(root)) for path in root.rglob("*")}


def test_no_attachment_is_written_under_its_raw_filename(tmp_path: Path) -> None:
    """Hostile filenames are recorded, never turned into a path in the store."""
    directory = tmp_path / "in"
    directory.mkdir()
    messages: list[tuple[bytes, str]] = []
    for index, filename in enumerate(HOSTILE_FILENAMES):
        for rfc2231 in (False, True):
            raw = _attachment_message(filename, rfc2231=rfc2231)
            name = f"m{index}_{int(rfc2231)}.eml"
            (directory / name).write_bytes(raw)
            messages.append((filename, name))

    store_root = tmp_path / "store"
    before = _snapshot(tmp_path)
    manifest = ingest_path(directory, store.document_store(store_root), limits=limits())
    assert len(manifest.rows) == len(messages)
    after = _snapshot(tmp_path)
    created = after - before
    assert created, "the ingest wrote nothing; the test compared nothing"

    # (1) every path the library created is under the store root (nothing beside it).
    outside = sorted(path for path in created if Path(path).parts[0] != "store")
    assert not outside, f"a file appeared outside the store root: {outside}"

    # (2) every created artifact name is a content-derived id (or the store's own index).
    for relative in sorted(created):
        if (tmp_path / relative).is_dir():
            continue
        name = Path(relative).name
        if name in _INDEX_NAMES:
            continue
        stem = name.split(".", 1)[0]
        assert len(stem) == 64 and all(char in "0123456789abcdef" for char in stem), (
            f"a created artifact is not content-addressed: {relative}"
        )

    # (3) no created path carries any hostile filename byte sequence.
    for filename, _name in messages:
        needle = filename.decode("latin-1")
        offenders = [relative for relative in created if needle in relative]
        assert not offenders, f"the raw filename {filename!r} reached a path: {offenders}"

    # (4) the raw filename lives in the record's recorded field and nowhere else: the
    #     walker keeps the parameter verbatim (latin-1), so the hostile text is a substring
    #     of ``filename_raw`` and appears on no path (checked in (3) above).
    for filename, name in messages:
        raw = (directory / name).read_bytes()
        document = assemble(EmlContainer(memory_bytes(raw)), limits=limits())
        assert document.attachments, f"{name}: no attachment occurrence"
        recorded = {occurrence.filename_raw for occurrence in document.attachments}
        needle = filename.decode("latin-1")
        probe = needle.strip() or needle
        assert any(probe in value for value in recorded), (filename, recorded)
