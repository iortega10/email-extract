"""Turn 1.12: ``emailextract.mediatype`` -- the one effective-media-type helper.

Before this turn every stage computed a part's media type as ``(part.content_type or
"").strip().lower()``, so a part that declared no ``Content-Type`` at all read as ``""``
and every ``== "text/plain"`` / ``startswith("text/")`` test failed. The helper adds the
two RFC defaults the walker does not supply: RFC 2045 section 5.2 (a part with no
``Content-Type`` is ``text/plain``) and RFC 2046 section 5.1.5 (a ``multipart/digest``
child with no ``Content-Type`` is ``message/rfc822``). The table here is the helper's
own contract; the end-to-end behaviour is in ``tests/test_headerless_part.py``.
"""

from __future__ import annotations

from emailextract.mediatype import (
    DIGEST_MEDIA_TYPE,
    RFC_2045_DEFAULT_MEDIA_TYPE,
    RFC_2046_DIGEST_CHILD_MEDIA_TYPE,
    declared_media_type,
    declares_content_type,
    effective_media_type,
    effective_media_type_in,
)
from emailextract.walk import PartShape, RawHeaderField, RawSpan


def _field(name: str, value: str = "", parse_status: str = "ok") -> RawHeaderField:
    """A header field with no spans: only the name and status matter to the helper."""
    return RawHeaderField(
        ordinal=0,
        name=name,
        raw_value=value,
        parse_status=parse_status,
        name_span=RawSpan(0, 0, ""),
        value_span=RawSpan(0, 0, ""),
        raw_span=RawSpan(0, 0, ""),
    )


def _part(
    content_type: str | None,
    *,
    path: str = "1",
    parent_path: str | None = None,
    fields: list[RawHeaderField] | None = None,
) -> PartShape:
    """A part carrying only what the helper reads: its parsed type and its header fields."""
    if fields is None:
        fields = [_field("Content-Type")] if content_type is not None else []
    return PartShape(
        path=path,
        part_id="p",
        parent_path=parent_path,
        content_type=content_type,
        raw_span=RawSpan(0, 0, path),
        headers_span=RawSpan(0, 0, path),
        body_span=RawSpan(0, 0, path),
        header_fields=fields,
    )


def test_the_declared_type_is_lowercased_and_parameter_stripped() -> None:
    """A part that declares a type gets it lowercased, with any parameter dropped."""
    assert declared_media_type(_part("Text/HTML")) == "text/html"
    assert declared_media_type(_part("application/octet-stream; name=x.pdf")) == (
        "application/octet-stream"
    )
    assert effective_media_type(_part("TEXT/Plain; charset=utf-8")) == "text/plain"
    assert declares_content_type(_part("text/plain")) is True


def test_an_absent_content_type_defaults_to_text_plain() -> None:
    """RFC 2045 section 5.2: a part with no ``Content-Type`` is ``text/plain``."""
    for parent_media in (None, "multipart/mixed", "multipart/alternative", "multipart/related"):
        assert effective_media_type(_part(None), parent_media) == "text/plain"
    assert RFC_2045_DEFAULT_MEDIA_TYPE == "text/plain"
    assert declares_content_type(_part(None)) is False
    assert declared_media_type(_part(None)) == ""


def test_an_absent_content_type_under_multipart_digest_defaults_to_message_rfc822() -> None:
    """RFC 2046 section 5.1.5: a ``multipart/digest`` child is ``message/rfc822``."""
    assert effective_media_type(_part(None), DIGEST_MEDIA_TYPE) == "message/rfc822"
    assert RFC_2046_DIGEST_CHILD_MEDIA_TYPE == "message/rfc822"
    # The digest default is for a *header-less* child: one that declares text/plain stays text.
    assert effective_media_type(_part("text/plain"), DIGEST_MEDIA_TYPE) == "text/plain"


def test_a_present_but_empty_content_type_keeps_the_walkers_reading() -> None:
    """A declaration the walker parsed but whose media token is empty is ``""``, not the default.

    The walker saw a ``Content-Type`` field, so the part is not header-less: its parsed type
    stays ``""`` and downstream tests on ``""`` keep the behaviour they had. Recorded so the
    default is never silently applied over a malformed declaration.
    """
    part = _part(None, fields=[_field("Content-Type", "")])
    assert declares_content_type(part) is True
    assert effective_media_type(part) == ""
    # ... and even under a digest parent: the declaration wins, the default does not apply.
    assert effective_media_type(part, DIGEST_MEDIA_TYPE) == ""
    # A malformed header *line* is not a field the walker parsed, so the part is header-less.
    malformed = _part(None, fields=[_field("", "text/plain no colon", parse_status="unknown")])
    assert declares_content_type(malformed) is False
    assert effective_media_type(malformed) == "text/plain"


def test_effective_media_type_in_resolves_the_parent_from_the_parts_map() -> None:
    """The mapping convenience resolves a digest child's parent without a second copy of the rule."""
    digest = _part("multipart/digest", path="1")
    digest_child = _part(None, path="1.1", parent_path="1")
    mixed = _part("multipart/mixed", path="2")
    mixed_child = _part(None, path="2.1", parent_path="2")
    top = _part(None, path="3", parent_path=None)
    parts = {part.path: part for part in (digest, digest_child, mixed, mixed_child, top)}
    assert effective_media_type_in(digest_child, parts) == "message/rfc822"
    assert effective_media_type_in(mixed_child, parts) == "text/plain"
    assert effective_media_type_in(top, parts) == "text/plain"
    assert effective_media_type_in(digest, parts) == "multipart/digest"


def test_the_helper_is_a_pure_function_of_the_part_and_the_parent_media() -> None:
    """Two calls with the same inputs agree, and the helper mutates neither."""
    part = _part(None)
    assert effective_media_type(part) == effective_media_type(part) == "text/plain"
    before = part
    effective_media_type(part, DIGEST_MEDIA_TYPE)
    assert part == before
    assert part.content_type is None and part.header_fields == []
