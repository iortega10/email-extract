"""An independent byte-level MIME delimiter splitter (Turn 1.10b, the "third check").

Lineage, stated honestly: this was written from **RFC 2046 section 5.1** -- the multipart
grammar, the delimiter line, the preamble and epilogue, and the closing delimiter -- plus
the build-spec paragraph that asks for this third check. It **imports nothing from
``emailextract``** and shares no code with ``walk.py``'s splitter: it is a second opinion
about the *spans*, not a different author. The build spec names that limit; the owner's
structure-only probe is the strongest common-mode breaker.

It produces, in the whole message's byte coordinate space, the four quantities the spec
asks for:

* the ordered **part byte spans**;
* the **part count**;
* the **preamble** and **epilogue** span per multipart (the lengths are their sizes);
* the **boundary-delimiter line spans**.

The RFC 2046 5.1 conventions this implements, so a disagreement can be attributed rather
than guessed at:

* the CRLF that precedes a delimiter line belongs to the **delimiter**, never the part
  ("The CRLF preceding the boundary delimiter line is conceptually attached to the
  boundary");
* a delimiter line is ``--boundary`` at the start of a line, followed by the end of the
  line, LWSP, or ``--`` (the closing delimiter, whose trailing text is LWSP only);
* a delimiter's span takes its own terminating CRLF **only when that CRLF lies inside the
  multipart's body region** -- the same rule that makes a body-start delimiter carry no
  leading CRLF;
* a part's span runs from the end of the delimiter before it to the start of the CRLF
  before the delimiter after it.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Leaf", "Split", "split_message"]

_DASH = b"--"
_LWSP = b" \t"


@dataclass(frozen=True)
class Leaf:
    """A non-multipart part: its span and the media type its header declares."""

    start: int
    end: int
    media: str


@dataclass(frozen=True)
class Split:
    """One multipart's four quantities, in absolute byte offsets."""

    start: int
    end: int
    media: str
    boundary: bytes
    preamble: tuple[int, int]
    epilogue: tuple[int, int]
    delimiters: tuple[tuple[int, int], ...]
    closed: bool
    parts: tuple["Split | Leaf", ...]


def _lines(raw: bytes, start: int, end: int):
    """``(line_start, content_end, line_end)`` for every line of ``raw[start:end]``."""
    position = start
    while position < end:
        found = raw.find(b"\r\n", position, end)
        if found == -1:
            yield position, end, end
            return
        yield position, found, found + 2
        position = found + 2


def _header_body(raw: bytes, start: int, end: int) -> tuple[int, int, bytes]:
    """``(body_start, body_end, header_bytes)``: the header region ends at the first blank line."""
    marker = raw.find(b"\r\n\r\n", start, end)
    if marker == -1:
        return end, end, raw[start:end]
    return marker + 4, end, raw[start:marker]


def _content_type(header: bytes) -> tuple[str, dict[str, str]]:
    """``(media_type, params)`` from the header block, first `Content-Type` wins (RFC 5322 3.6)."""
    media = ""
    params: dict[str, str] = {}
    lines = header.replace(b"\r\n", b"\n").split(b"\n")
    index = 0
    while index < len(lines):
        line = lines[index]
        if line[:1] in (b" ", b"\t"):  # an obs-fold continuation of the previous field
            index += 1
            continue
        name, _, value = line.partition(b":")
        if name.strip().lower() != b"content-type":
            index += 1
            continue
        media = value.strip().split(b";", 1)[0].decode("latin-1").strip().lower()
        for section in value.strip().split(b";")[1:]:
            key, _, entry = section.partition(b"=")
            key = key.strip().lower().decode("latin-1")
            entry = entry.strip().decode("latin-1")
            if len(entry) >= 2 and entry[0] == '"' and entry[-1] == '"':
                entry = entry[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            if key and key not in params:
                params[key] = entry
        break
    return media, params


def _is_delimiter(content: bytes, boundary: bytes) -> bool | None:
    """``None`` if not a delimiter line; else whether it is the **closing** one."""
    prefix = _DASH + boundary
    if not content.startswith(prefix):
        return None
    rest = content[len(prefix) :]
    if rest.startswith(_DASH):
        return True if rest[len(_DASH) :].strip(_LWSP) == b"" else None
    return False if rest.strip(_LWSP) == b"" else None


def _split_body(
    raw: bytes, part: tuple[int, int], body: tuple[int, int], media: str, boundary: bytes
) -> Split:
    """Split one multipart: ``part`` is the whole part span, ``body`` its body region."""
    start, end = body
    delimiters: list[tuple[int, int]] = []
    closing_at: int | None = None
    for line_start, content_end, line_end in _lines(raw, start, end):
        verdict = _is_delimiter(raw[line_start:content_end], boundary)
        if verdict is None:
            continue
        opening = (
            line_start - 2
            if line_start > start and raw[line_start - 2 : line_start] == b"\r\n"
            else line_start
        )
        span_end = line_end if line_end <= end else content_end
        delimiters.append((opening, span_end))
        if verdict:
            closing_at = len(delimiters) - 1
            break

    if not delimiters:
        return Split(*part, media, boundary, (start, start), (end, end), (), False, ())

    last = delimiters[closing_at] if closing_at is not None else None
    body_end = last[1] if last is not None else end
    preamble = (start, delimiters[0][0])
    epilogue = (body_end, end)

    stops = delimiters
    parts: list[Split | Leaf] = []
    for index, delimiter in enumerate(stops):
        if closing_at is not None and index >= closing_at:
            break
        part_start = delimiter[1]
        part_end = stops[index + 1][0] if index + 1 < len(stops) else end
        parts.append(_split_part(raw, part_start, part_end))
    return Split(
        part[0], part[1], media, boundary, preamble, epilogue, tuple(delimiters),
        closing_at is not None, tuple(parts),
    )


def _split_part(raw: bytes, start: int, end: int) -> Split | Leaf:
    body_start, body_end, header = _header_body(raw, start, end)
    media, params = _content_type(header)
    if media.startswith("multipart/") and "boundary" in params and body_start < body_end:
        boundary = params["boundary"].encode("latin-1", errors="replace")
        return _split_body(raw, (start, end), (body_start, body_end), media, boundary)
    return Leaf(start, end, media)


def split_message(raw: bytes, start: int = 0, end: int | None = None) -> Split | Leaf:
    """Split ``raw`` (or ``raw[start:end]``, one part) into parts, recursively."""
    stop = len(raw) if end is None else end
    body_start, body_end, header = _header_body(raw, start, stop)
    media, params = _content_type(header)
    if media.startswith("multipart/") and "boundary" in params and body_start < body_end:
        boundary = params["boundary"].encode("latin-1", errors="replace")
        return _split_body(raw, (start, stop), (body_start, body_end), media, boundary)
    return Leaf(start, stop, media)
