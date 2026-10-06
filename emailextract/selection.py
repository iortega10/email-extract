"""Turn 1.5b: the referenced-cid set, the alternative grouping and the display rule.

This is the second half of Turn 1.5 (its first half, the own element tree and the HTML
projection, is :mod:`emailextract.htmltree` and :mod:`emailextract.htmltext`). It owns
four of the turn's facts and the Phase 1 body gaps beside them:

* ``body.cid_refs`` -- the set of ``cid:`` references an HTML part makes, taken **from the
  tree** (:mod:`emailextract.htmltree`), never a regex over raw HTML text, so a ``cid:``
  inside a dropped ``style``/``script`` subtree or inside a comment is never seen;
* ``body.alternative_group`` -- one row per part inside a ``multipart/alternative``;
* ``body.selection`` -- the recorded display rule (D3/D16);
* ``body.plain_effectively_empty`` -- the D16 fact (a fact, not a gap);
* the Phase 1 gap channel for ``body.digest_default_not_applied``, ``body.no_text_part``,
  ``body.html_quote_rule_gap`` (read off the tree's own ``gaps``),
  ``security.remote_content_present`` and ``body.inline_data_uri``.

Nothing here fetches, decodes or opens anything: a remote URL and a ``data:`` URI are
**recorded** and never dereferenced (D9/D10), and
:func:`external_references` builds the recorded observation the mutation catalogue and the
no-network guard test read.

The cid comparison rule
------------------------

A ``cid:`` URL and a ``Content-ID`` header are both an RFC 2392 ``addr-spec``. Before a
comparison, an **attribute** URL is normalized **once**: surrounding whitespace and angle
brackets are stripped and it is percent-decoded once (``%40`` -> ``@``); a ``?`` or ``#``
suffix is kept verbatim (RFC 2392 has no query or fragment, so a producer that writes one
gets it recorded rather than repaired, and the cid is not silently truncated). A
``Content-ID`` header is normalized the same way from the header side (whitespace and
``<>`` stripped). The **comparison is case-sensitive** (:func:`dangling_and_unreferenced`):
RFC 2392 defines the cid as an addr-spec, whose local part is case-sensitive, and the two
judging sidecars (``attach_cid_dangling``, ``attach_inline_unreferenced``) both type a cid
that differs from every ``Content-ID``, so no case fold is needed to reach the labelled
answer -- and a fold would merge two genuinely different ids. The scheme token ``cid`` is
matched **case-insensitively** (RFC 3986 schemes are case-insensitive), which is a
different thing from the cid *value* under it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Iterable, Mapping, Sequence

from . import htmltext, htmltree, text as text_stage
from .walk import PartShape, WalkResult, WorkCounter

__all__ = [
    "ALTERNATIVE_NOT_SELECTED",
    "CID_ATTRIBUTES",
    "EMPTINESS_RULES",
    "EMPTINESS_STUB_ONLY",
    "EMPTINESS_WHITESPACE_ONLY",
    "ExternalReferences",
    "GAP_BODY_DIGEST_DEFAULT_NOT_APPLIED",
    "GAP_BODY_INLINE_DATA_URI",
    "GAP_BODY_NO_TEXT_PART",
    "GAP_IDS",
    "GAP_SECURITY_REMOTE_CONTENT_PRESENT",
    "NOT_APPLICABLE",
    "PartReferences",
    "SELECTED",
    "SELECTION_STATES",
    "URL_ATTRIBUTES",
    "WHITESPACE_ONLY_CODE_POINTS",
    "WORK",
    "alternative_group_rows",
    "body_gaps",
    "cid_ref_rows",
    "dangling_and_unreferenced",
    "display_text",
    "external_references",
    "html_projections",
    "is_body_view",
    "plain_effectively_empty_rows",
    "selection_rows",
]

# --------------------------------------------------------------- the work counter

#: The stage's deterministic work counter -- the :class:`~emailextract.walk.WorkCounter`
#: pattern the other stages use (a seam a test resets and reads, **never** a clock): one
#: step per projected element examined and one per :data:`URL_ATTRIBUTES` row compared, so
#: the count is a pure function of the bytes and a linearity claim is reproducible.
WORK: Final[WorkCounter] = WorkCounter()

# --------------------------------------------------------------------- vocabularies

#: The ``body.selection`` states (the closed ``Selection`` vocabulary, D3).
SELECTED: Final[str] = "selected"
ALTERNATIVE_NOT_SELECTED: Final[str] = "alternative_not_selected"
NOT_APPLICABLE: Final[str] = "n/a"
SELECTION_STATES: Final[tuple[str, str, str]] = (
    SELECTED,
    ALTERNATIVE_NOT_SELECTED,
    NOT_APPLICABLE,
)

#: The closed ``body.plain_effectively_empty`` rules (D16). ``stub_only`` is declared
#: because the fact's vocabulary names it, but **no frozen sidecar types it** (both
#: committed rows are ``whitespace_only``), so :func:`plain_effectively_empty_rows` never
#: yields it: the stub rule is the empty closed set this turn, and the design text that
#: would define a stub is not written yet.
EMPTINESS_WHITESPACE_ONLY: Final[str] = "whitespace_only"
EMPTINESS_STUB_ONLY: Final[str] = "stub_only"
EMPTINESS_RULES: Final[tuple[str, ...]] = (EMPTINESS_WHITESPACE_ONLY, EMPTINESS_STUB_ONLY)

#: The **exact** whitespace set an effectively-empty ``text/plain`` alternative is tested
#: against: the Unicode ``White_Space`` property (U+0009..U+000D, U+0020, U+0085, U+00A0,
#: U+1680, U+2000..U+200A, U+2028, U+2029, U+202F, U+205F, U+3000), which already contains
#: every ASCII whitespace character and NBSP. Stated as code points so the set is readable
#: without ``str.isspace``'s own definition.
WHITESPACE_ONLY_CODE_POINTS: Final[frozenset[int]] = frozenset(
    {
        0x0009, 0x000A, 0x000B, 0x000C, 0x000D,
        0x0020,
        0x0085,
        0x00A0,
        0x1680,
        *range(0x2000, 0x200B),
        0x2028, 0x2029,
        0x202F,
        0x205F,
        0x3000,
    }
)

# ---------------------------------------------------------------- the gap ids this owns

#: A ``multipart/digest`` child with no ``Content-Type`` is ``message/rfc822`` by RFC 2046
#: 5.1.5; the walker records ``content_type = None`` and this gap says the default is a
#: projection over the raw field, never a rewrite of it (``docs/design/phase0-gaps.md``).
GAP_BODY_DIGEST_DEFAULT_NOT_APPLIED: Final[str] = "body.digest_default_not_applied"
#: No part reads as text: there is no body text view and the selection is none (D3/D16).
GAP_BODY_NO_TEXT_PART: Final[str] = "body.no_text_part"
#: A body references remote content: recorded, never fetched (D10).
GAP_SECURITY_REMOTE_CONTENT_PRESENT: Final[str] = "security.remote_content_present"
#: A ``data:`` URI in a body: recorded, never expanded into bytes or a part (D4).
GAP_BODY_INLINE_DATA_URI: Final[str] = "body.inline_data_uri"

#: Every gap id this module emits. ``body.html_quote_rule_gap`` is emitted by
#: :mod:`emailextract.htmltree` (read off the tree's ``gaps``) and is not repeated here.
GAP_IDS: Final[tuple[str, ...]] = (
    GAP_BODY_DIGEST_DEFAULT_NOT_APPLIED,
    GAP_BODY_NO_TEXT_PART,
    GAP_SECURITY_REMOTE_CONTENT_PRESENT,
    GAP_BODY_INLINE_DATA_URI,
)

# ------------------------------------------------------------------------- the URLs

KIND_CID: Final[str] = "cid"
KIND_DATA: Final[str] = "data"
KIND_REMOTE: Final[str] = "remote"
KIND_OTHER: Final[str] = "other"

_CID_SCHEME: Final[str] = "cid:"
_DATA_SCHEME: Final[str] = "data:"
_REMOTE_SCHEMES: Final[frozenset[str]] = frozenset({"http", "https"})

#: ``(tag, attribute, required_attributes, cid_capable, source)`` for every attribute this
#: turn reads a URL out of. ``cid_capable`` marks the closed set the referenced-cid set is
#: taken from (the prompt's list); the rest are remote-content sources only (a ``cid:`` in
#: a ``script``/``iframe``/media ``src`` is classified but never counted as an embedded
#: part reference -- RFC 2392's use is image/link/style references).
URL_ATTRIBUTES: Final[tuple[tuple[str, str, tuple[tuple[str, str], ...], bool, str], ...]] = (
    ("img", "src", (), True, "HTML5 img@src (the image resource)"),
    ("image", "src", (), True, "HTML5 image@src (SVG's img alias)"),
    ("input", "src", (("type", "image"),), True, "HTML5 input[type=image]@src"),
    ("body", "background", (), True, "HTML 4.01 body@background (deprecated)"),
    ("td", "background", (), True, "HTML 4.01 td@background (deprecated)"),
    ("a", "href", (), True, "HTML5 a@href"),
    ("area", "href", (), True, "HTML5 area@href"),
    ("link", "href", (), True, "HTML5 link@href (a stylesheet carried as a part)"),
    ("script", "src", (), False, "HTML5 script@src"),
    ("iframe", "src", (), False, "HTML5 iframe@src"),
    ("video", "src", (), False, "HTML5 video@src"),
    ("audio", "src", (), False, "HTML5 audio@src"),
    ("source", "src", (), False, "HTML5 source@src"),
)

#: The referenced-cid sources: the ``cid_capable`` slice of :data:`URL_ATTRIBUTES`.
CID_ATTRIBUTES: Final[tuple[tuple[str, str], ...]] = tuple(
    (tag, attribute) for tag, attribute, _req, capable, _why in URL_ATTRIBUTES if capable
)

#: ``url()`` inside a ``style`` attribute (a CSS reference, remote-content source only).
_STYLE_URL = re.compile(
    r"""url\(\s*(?:'([^']*)'|"([^"]*)"|([^)'"\s]*))\s*\)""",
    re.IGNORECASE,
)

_PERCENT = re.compile(r"%([0-9A-Fa-f]{2})")


# ------------------------------------------------------------------ URL classification


def _scheme(url: str) -> str:
    """The lowercased scheme of ``url`` (RFC 3986 schemes are case-insensitive), or ``""``.

    The **one** place a scheme is lowercased: a mutant that stops doing it makes a
    ``CID:``/``HTTP:`` reference invisible, which is exactly the "scheme compared
    case-sensitively" defect the catalogue guards.
    """
    text = url.strip()
    head, separator, _rest = text.partition(":")
    if not separator or not head:
        return ""
    if any(character in head for character in "/?# "):
        return ""
    return head.lower()


def _url_kind(url: str) -> str:
    """The closed classification of one URL: ``cid``, ``data``, ``remote`` or ``other``.

    The single decision point for both the referenced-cid set and the remote/``data:``
    gaps, so a mutant that mislabels a ``cid:`` as remote (or a remote URL as a cid) is one
    patch and one flipped observation. ``remote`` is ``http``/``https`` or protocol-relative
    (``//``); everything else (``mailto:``, a fragment, a relative path) is ``other``.
    """
    text = url.strip().strip("<>").strip()
    if not text:
        return KIND_OTHER
    scheme = _scheme(text)
    if not scheme:
        return KIND_REMOTE if text.startswith("//") else KIND_OTHER
    if f"{scheme}:" == _CID_SCHEME:
        return KIND_CID
    if f"{scheme}:" == _DATA_SCHEME:
        return KIND_DATA
    if scheme in _REMOTE_SCHEMES:
        return KIND_REMOTE
    return KIND_OTHER


def _percent_decode_once(text: str) -> str:
    """Percent-decode ``text`` exactly once (``%40`` -> ``@``); a bare ``%`` is kept."""
    return _PERCENT.sub(lambda match: chr(int(match.group(1), 16)), text)


def _cid_value(url: str) -> str:
    """The cid a ``cid:`` URL names: brackets and whitespace stripped, percent-decoded once,
    a ``?``/``#`` suffix kept verbatim (RFC 2392 has no query or fragment; it is recorded,
    never silently truncated)."""
    text = url.strip().strip("<>").strip()
    scheme = _scheme(text)
    if f"{scheme}:" != _CID_SCHEME:
        return text
    return _percent_decode_once(text[len(scheme) + 1 :].strip())


def _ordered_unique(items: Iterable[str]) -> tuple[str, ...]:
    """Deduplicate preserving first-occurrence order -- the ``body.cid_refs`` ordering rule.

    The **one** dedup/order point: a mutant that returns ``list(items)`` (no dedup) or
    ``tuple(sorted(items))`` (sorted) is one patch and one flipped observation.
    """
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return tuple(seen)


def _follow(url: str) -> bytes | None:
    """Nothing is ever fetched (D10): a recorded reference is never dereferenced.

    Returns ``None`` for **every** URL -- including a related part's ``Content-Location``.
    The function exists so the scan has exactly one place that would dereference, which the
    no-network guard test forbids and the mutation catalogue flips.
    """
    return None


def _decode_data_uri(url: str) -> bytes | None:
    """A ``data:`` URI is recorded, never expanded into bytes (D4). Returns ``None`` always."""
    return None


def _content_location(part: PartShape) -> str | None:
    """The recorded ``Content-Location`` of a part, or ``None``.

    Recorded as a claim; never resolved, never fetched (D10). Read straight off the walker's
    raw header fields so no header stage is re-run.
    """
    for field in part.header_fields:
        if field.name.lower() == "content-location":
            return field.raw_value.strip()
    return None


# -------------------------------------------------------------- external references


@dataclass(frozen=True)
class PartReferences:
    """One part's recorded external references, in first-occurrence order."""

    part: str
    cids: tuple[str, ...]
    remote: tuple[str, ...]
    data_uris: tuple[str, ...]


@dataclass(frozen=True)
class ExternalReferences:
    """Everything the reference scan recorded for one message.

    ``followed`` and ``decoded`` are the recorded observation that **nothing** was
    dereferenced or expanded: both are empty for every input (D4/D10), and a mutant that
    makes either non-empty is caught by the catalogue and the no-network guard.
    """

    parts: tuple[PartReferences, ...]
    content_locations: tuple[str, ...]
    followed: tuple[str, ...]
    decoded: tuple[str, ...]


def html_projections(
    raw: bytes, result: WalkResult, *, max_depth: int, max_elements: int
) -> tuple[tuple[str, htmltext.HtmlProjection], ...]:
    """``(locator, projection)`` for every part the walker read as ``text/html``.

    The walker's own text decision is reused (``text.analyse_parts``): a part with no
    decoded text has nothing to project. ``max_depth``/``max_elements`` are the caller's
    caps, passed straight to :func:`emailextract.htmltext.project` (no defaults here).
    """
    bodies = {record.path: record.text for record in text_stage.analyse_parts(raw, result)}
    projections: list[tuple[str, htmltext.HtmlProjection]] = []
    for part in result.parts:
        if (part.content_type or "").lower() != "text/html":
            continue
        body = bodies.get(part.path)
        if body is None:
            continue
        projections.append(
            (part.path, htmltext.project(body, max_depth=max_depth, max_elements=max_elements))
        )
    return tuple(projections)


def _attribute_pairs(element: htmltree.Element) -> dict[str, str]:
    """The element's attributes as a dict (first-wins, which the tree already recorded)."""
    return {name: value for name, value in element.attributes}


def _urls_of(projection: htmltext.HtmlProjection) -> list[str]:
    """Every URL an element tree carries, in document order, from the closed attribute list.

    Read from the **tree** (never a regex over the HTML text), so a URL inside a dropped
    ``style``/``script`` subtree contributes nothing.
    """
    found: list[str] = []
    for element in projection.tree.elements:
        WORK.add()
        attributes = _attribute_pairs(element)
        for tag, attribute, required, _capable, _why in URL_ATTRIBUTES:
            WORK.add()
            if element.tag != tag:
                continue
            if any(attributes.get(name) != value for name, value in required):
                continue
            url = attributes.get(attribute)
            if url:
                found.append(url)
        style = attributes.get("style")
        if style:
            for match in _STYLE_URL.finditer(style):
                url = next((group for group in match.groups() if group is not None), "")
                if url:
                    found.append(url)
    return found


def external_references(
    raw: bytes, result: WalkResult, *, max_depth: int, max_elements: int
) -> ExternalReferences:
    """Scan every HTML part's tree for cid/remote/``data:`` references, and record nothing else.

    A ``cid:`` reference is taken only from :data:`CID_ATTRIBUTES`; a remote reference from
    the whole :data:`URL_ATTRIBUTES` list plus a ``style`` attribute's ``url()``; a
    ``data:`` URI from the same URL list. Every remote and ``data:`` URL is passed to
    :func:`_follow`/:func:`_decode_data_uri`, whose recorded result is never anything but
    ``None`` -- that empty tuple is the proof nothing was touched.
    """
    parts: list[PartReferences] = []
    content_locations: list[str] = []
    followed: list[str] = []
    decoded: list[str] = []
    for locator, projection in html_projections(
        raw, result, max_depth=max_depth, max_elements=max_elements
    ):
        cids: list[str] = []
        remote: list[str] = []
        data_uris: list[str] = []
        for element in projection.tree.elements:
            WORK.add()
            attributes = _attribute_pairs(element)
            for tag, attribute, required, capable, _why in URL_ATTRIBUTES:
                WORK.add()
                if element.tag != tag:
                    continue
                if any(attributes.get(name) != value for name, value in required):
                    continue
                url = attributes.get(attribute)
                if not url:
                    continue
                kind = _url_kind(url)
                if kind == KIND_CID:
                    if capable:
                        cids.append(_cid_value(url))
                elif kind == KIND_DATA:
                    data_uris.append(url)
                    if _decode_data_uri(url) is not None:
                        decoded.append(url)
                elif kind == KIND_REMOTE:
                    remote.append(url)
                    if _follow(url) is not None:
                        followed.append(url)
            style = attributes.get("style")
            if style:
                for match in _STYLE_URL.finditer(style):
                    url = next((group for group in match.groups() if group is not None), "")
                    if not url:
                        continue
                    if _url_kind(url) == KIND_REMOTE:
                        remote.append(url)
                        if _follow(url) is not None:
                            followed.append(url)
        parts.append(
            PartReferences(
                part=locator,
                cids=_ordered_unique(cids),
                remote=_ordered_unique(remote),
                data_uris=_ordered_unique(data_uris),
            )
        )
    for part in result.parts:
        location = _content_location(part)
        if location is None:
            continue
        content_locations.append(location)
        if _follow(location) is not None:
            followed.append(location)
    return ExternalReferences(
        parts=tuple(parts),
        content_locations=tuple(content_locations),
        followed=tuple(followed),
        decoded=tuple(decoded),
    )


def cid_ref_rows(
    raw: bytes, result: WalkResult, *, max_depth: int, max_elements: int
) -> list[list[object]]:
    """``body.cid_refs`` rows: ``[[part, [cid, ...]], ...]`` for parts that reference any cid."""
    references = external_references(raw, result, max_depth=max_depth, max_elements=max_elements)
    return [[entry.part, list(entry.cids)] for entry in references.parts if entry.cids]


def dangling_and_unreferenced(
    referenced: Iterable[str], content_ids: Iterable[str]
) -> tuple[list[str], list[str]]:
    """``(dangling, unreferenced)`` from two already-normalized cid sets (Turn 1.8's helper).

    ``dangling``: a referenced cid no ``Content-ID`` carries (a reference with no part).
    ``unreferenced``: a ``Content-ID`` no view references (a part with no reference). Both
    are ordered by first occurrence in their input. Comparison is **case-sensitive** (RFC
    2392's addr-spec local part; see the module docstring), so a caller must not fold case
    on either side. No I/O and no message is touched: this is set arithmetic over two
    iterables, and it is tested on hand-typed sets including empty ones.
    """
    # A set has no order (and str hashing is randomised per process): sort it so the result is
    # deterministic. A list or tuple keeps its first-occurrence order.
    referenced_list = sorted(referenced) if isinstance(referenced, (set, frozenset)) else list(referenced)
    content_id_list = (
        sorted(content_ids) if isinstance(content_ids, (set, frozenset)) else list(content_ids)
    )
    referenced_set = set(referenced_list)
    content_id_set = set(content_id_list)
    dangling = [cid for cid in _ordered_unique(referenced_list) if cid not in content_id_set]
    unreferenced = [
        cid for cid in _ordered_unique(content_id_list) if cid not in referenced_set
    ]
    return dangling, unreferenced


# ---------------------------------------------------------- the alternative grouping

_ALTERNATIVE: Final[str] = "multipart/alternative"
_DIGEST: Final[str] = "multipart/digest"


def _by_path(result: WalkResult) -> Mapping[str, PartShape]:
    return {part.path: part for part in result.parts}


def _media(part: PartShape) -> str:
    """The part's media type, lowercased; ``""`` when it declares none."""
    return (part.content_type or "").lower()


def _is_digest_child_without_content_type(part: PartShape, parts: Mapping[str, PartShape]) -> bool:
    """A ``multipart/digest`` direct child that declares no ``Content-Type`` (RFC 2046 5.1.5)."""
    if part.content_type is not None:
        return False
    parent = parts.get(part.parent_path or "")
    return parent is not None and _media(parent) == _DIGEST


def _is_explicit_attachment(part: PartShape) -> bool:
    """A part whose own ``Content-Disposition`` is ``attachment`` (RFC 2183): an attached text file
    (``.txt``, ``.csv``, ``.ics``, ``.html``) is an attachment occurrence, never a displayable body
    view, whatever its ``text/*`` media type. ``inline`` and an absent disposition leave the part a view
    (a body part, or an inline text part, is displayed)."""
    for field in part.header_fields:
        if field.parse_status == "ok" and field.name.lower() == "content-disposition":
            token = field.raw_value.split(";", 1)[0].strip().lower()
            return token == "attachment"
    return False


def _is_body_view(part: PartShape, parts: Mapping[str, PartShape]) -> bool:
    """Whether a part is a **displayable text view**: a ``text/*`` part (an absent
    ``Content-Type`` defaults to ``text/plain``, RFC 2045 5.2), except a
    ``multipart/digest`` child with no ``Content-Type`` (that child is ``message/rfc822``,
    the recorded gap, never a text view)."""
    if _is_digest_child_without_content_type(part, parts):
        return False
    if _is_explicit_attachment(part):
        return False
    media = _media(part)
    return not media or media.startswith("text/")


def _reads_as_text(part: PartShape) -> bool:
    """The walker's own text decision (``text.py`` reuses it): a part the charset ladder ran
    over reads as text. Used by ``body.no_text_part`` only -- the digest child above runs the
    ladder (it declares no ``Content-Type``), so it *reads* as text even though it is not a
    displayable view."""
    return part.decode_chain.used_charset is not None


def is_body_view(part: PartShape, parts: Mapping[str, PartShape]) -> bool:
    """The **public** body-view predicate: Turn 1.8's attachment rule reuses this one rule.

    Exposed in Turn 1.8 (the attachment stage needs it and must not restate it): a leaf that is
    not a view and not a container is an attachment occurrence. It is exactly
    :func:`_is_body_view` -- a ``text/*`` leaf (an absent ``Content-Type`` defaults to
    ``text/plain``, RFC 2045 5.2) that is not a ``multipart/digest`` child without a
    ``Content-Type`` -- so a ``text/calendar`` alternative is a view, never an attachment, while
    a ``message/rfc822`` part is not one.
    """
    return _is_body_view(part, parts)


def _alternative_children(
    alternative: PartShape, parts: Mapping[str, PartShape]
) -> tuple[PartShape, ...]:
    """The direct children of a ``multipart/alternative``, in part-tree order."""
    return tuple(part for part in parts.values() if part.parent_path == alternative.path)


def _group_members(
    alternative: PartShape, parts: Mapping[str, PartShape], texts: Mapping[str, str]
) -> tuple[PartShape, ...]:
    """The parts of one alternative group, in part-tree order.

    **Every** direct child is a member -- including a ``text/calendar`` view candidate and a
    whitespace-only ``text/plain`` one, both of which the frozen labels type inside the group
    (D16: a present-but-effectively-empty alternative is still present, and matching still
    considers it) -- so this is the **one** membership point the mutation catalogue patches.
    ``texts`` is taken so a membership policy *could* consult the content; it deliberately
    does not, because the labels say so.
    """
    del texts  # membership is structural, never content-driven (D16)
    return _alternative_children(alternative, parts)


def _group_id(alternative: PartShape) -> str:
    """The message-local stable group id: the alternative's ``part`` locator.

    The locator is message-local by construction (``1.2.3`` restarts at ``1`` per message)
    and is a pure function of the tree, so the same alternative gets the same id no matter
    what was parsed before it. The two frozen labels type exactly the locator (``"1"`` for
    the group at part 1, ``"1.1.1"`` for the group at part 1.1.1).
    """
    return alternative.path


def alternative_group_rows(raw: bytes, result: WalkResult) -> list[list[object]]:
    """``body.alternative_group`` rows: ``[[part, group_id], ...]`` in part-tree order."""
    parts = _by_path(result)
    texts = display_text(raw, result)
    rows: list[list[object]] = []
    for part in result.parts:
        if _media(part) != _ALTERNATIVE:
            continue
        group_id = _group_id(part)
        for child in _group_members(part, parts, texts):
            rows.append([child.path, group_id])
    return rows


# ---------------------------------------------------------------- the display rule

#: The closed display preference order (D3: "text/plain preferred"). ``text/calendar`` is a
#: **view candidate**, never an attachment (its only frozen label is
#: ``alternative_not_selected`` inside the group), and it ranks below a displayable text
#: body. A group with none of these has no selected part.
DISPLAY_PREFERENCE: Final[tuple[str, ...]] = ("text/plain", "text/html", "text/calendar")


def _effectively_empty(text: str) -> str | None:
    """The D16 emptiness rule for a ``text/plain`` body, or ``None``.

    Only ``whitespace_only`` (:data:`EMPTINESS_WHITESPACE_ONLY`) is implemented: **both**
    frozen ``body.plain_effectively_empty`` labels type it, and no sidecar types
    ``stub_only``, so the stub rule is the empty closed set this turn (see
    :data:`EMPTINESS_STUB_ONLY`). ``whitespace_only`` is "every code point of the body is
    :data:`WHITESPACE_ONLY_CODE_POINTS`", vacuously true for a zero-length body. A mutant
    that stops calling this (or always returns ``None``) makes a whitespace-only plain
    alternative selectable again.
    """
    if all(ord(character) in WHITESPACE_ONLY_CODE_POINTS for character in text):
        return EMPTINESS_WHITESPACE_ONLY
    return None


def display_text(
    raw: bytes, result: WalkResult
) -> Mapping[str, str]:
    """``locator -> decoded text`` for every text part (the walker's text decision, reused)."""
    return {record.path: record.text for record in text_stage.analyse_parts(raw, result)}


def _select_in_group(
    children: Sequence[PartShape], texts: Mapping[str, str]
) -> str | None:
    """The selected child of one group, or ``None`` (the closed preference order).

    The earliest child, in document order, whose media type is the best-ranked
    :data:`DISPLAY_PREFERENCE` type that has a qualifying child; a ``text/plain`` child is
    skipped when :func:`_effectively_empty` names it. Never a function of the content's
    *length*: a mutant that picks the longest body is caught by the catalogue.
    """
    for media in DISPLAY_PREFERENCE:
        for child in children:
            if _media(child) != media:
                continue
            if media == "text/plain" and _effectively_empty(texts.get(child.path, "")):
                continue
            return child.path
    return None


def selection_rows(
    raw: bytes, result: WalkResult
) -> list[list[object]]:
    """``body.selection`` rows: ``[[part, state], ...]`` in part-tree order.

    A part **inside** an alternative group is ``selected`` or ``alternative_not_selected``;
    a **displayable text view outside** any group is ``n/a`` (the design's own word for "no
    alternative selection applies"; the frozen labels type such a part in no fixture, so
    this is the conservative reading and it is recorded here). A non-text part, a container
    and a part the walker did not read as text get no row at all -- exactly the rows the
    frozen labels carry.
    """
    parts = _by_path(result)
    texts = display_text(raw, result)
    groups: dict[str, tuple[PartShape, ...]] = {}
    selected: dict[str, str] = {}
    for part in result.parts:
        if _media(part) != _ALTERNATIVE:
            continue
        children = _group_members(part, parts, texts)
        chosen = _select_in_group(children, texts)
        for child in children:
            groups[child.path] = children
        if chosen is not None:
            selected[chosen] = part.path
    rows: list[list[object]] = []
    for part in result.parts:
        if part.path in groups:
            state = SELECTED if part.path in selected else ALTERNATIVE_NOT_SELECTED
            rows.append([part.path, state])
        elif _is_body_view(part, parts) and _reads_as_text(part):
            rows.append([part.path, NOT_APPLICABLE])
    return rows


def plain_effectively_empty_rows(raw: bytes, result: WalkResult) -> list[list[object]]:
    """``body.plain_effectively_empty`` rows: ``[[part, rule], ...]``.

    One row per **present but effectively empty** ``text/plain`` part, in part-tree order.
    Matching and ``body_digest`` still consider the alternative (D16); the row only records
    the legal state.
    """
    texts = display_text(raw, result)
    rows: list[list[object]] = []
    for part in result.parts:
        if _media(part) != "text/plain":
            continue
        rule = _effectively_empty(texts.get(part.path, ""))
        if rule is not None:
            rows.append([part.path, rule])
    return rows


# ------------------------------------------------------------------ the gap channel


def body_gaps(
    raw: bytes, result: WalkResult, *, max_depth: int, max_elements: int
) -> list[tuple[str, str]]:
    """The ``(gap_id, locator)`` pairs this stage records, for ``gaps.later``.

    The Phase 1 gap channel, never the walker's Phase 0 ``part.gaps`` (decision 3). The
    ``body.html_quote_rule_gap`` the tree records for an unclosed quote container is carried
    here too, so it reaches the oracle's ``gaps.later`` channel.
    """
    pairs: list[tuple[str, str]] = []
    for locator, projection in html_projections(
        raw, result, max_depth=max_depth, max_elements=max_elements
    ):
        for gap_id in projection.tree.gaps:
            pairs.append((gap_id, locator))
    references = external_references(raw, result, max_depth=max_depth, max_elements=max_elements)
    for entry in references.parts:
        if entry.remote:
            pairs.append((GAP_SECURITY_REMOTE_CONTENT_PRESENT, entry.part))
        if entry.data_uris:
            pairs.append((GAP_BODY_INLINE_DATA_URI, entry.part))
    parts = _by_path(result)
    for part in result.parts:
        if _is_digest_child_without_content_type(part, parts):
            pairs.append((GAP_BODY_DIGEST_DEFAULT_NOT_APPLIED, part.path))
    if result.parts and not any(_reads_as_text(part) for part in result.parts):
        pairs.append((GAP_BODY_NO_TEXT_PART, result.parts[0].path))
    return pairs
