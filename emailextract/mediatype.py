"""Turn 1.12: the one effective-media-type helper (``(part.content_type or "")`` in one place).

Several stages branch on a part's media type. Before this module each of them re-derived it
as ``(part.content_type or "").strip().lower()``, so a part that declares **no**
``Content-Type`` at all read as media type ``""`` and every ``== "text/plain"`` or
``startswith("text/")`` test failed -- even though the walker already treats such a part as
text (RFC 2045 5.2) and its decode chain reports the default charset. :func:`effective_media_type`
is that computation once, with the two RFC defaults the walker does not supply:

* **RFC 2045 section 5.2** -- a part with no ``Content-Type`` header has the default
  ``text/plain; charset=us-ascii``. So a non-multipart leaf that declares nothing is
  ``text/plain``.
* **RFC 2046 section 5.1.5** -- the body parts of a ``multipart/digest`` are themselves
  ``message/rfc822`` unless they say otherwise, so a ``multipart/digest`` child that declares
  nothing is ``message/rfc822``, not ``text/plain``.

Nothing here changes what the walker records: ``walk.py`` still stores ``PartShape.content_type``
as the header writes it (absent stays ``None``) and the behavior ledger's ``walk`` and
``decode_chain`` lines do not move. This module is a **projection over the raw field**, exactly
the shape the frozen ``body.digest_default_not_applied`` gap describes (design D3). It reads the
part's own header fields to tell "declares nothing" from "declares something unparsable", and it
is a pure function of the part and the parent's effective media type -- no clock, no
environment, no cap.
"""

from __future__ import annotations

from typing import Mapping

from .walk import PartShape

#: RFC 2045 section 5.2: the default media type of a part with no ``Content-Type`` is text/plain.
RFC_2045_DEFAULT_MEDIA_TYPE: str = "text/plain"

#: RFC 2046 section 5.1.5: a ``multipart/digest`` child with no ``Content-Type`` is a message.
RFC_2046_DIGEST_CHILD_MEDIA_TYPE: str = "message/rfc822"

#: The container whose header-less children default to :data:`RFC_2046_DIGEST_CHILD_MEDIA_TYPE`.
DIGEST_MEDIA_TYPE: str = "multipart/digest"

__all__ = [
    "DIGEST_MEDIA_TYPE",
    "RFC_2045_DEFAULT_MEDIA_TYPE",
    "RFC_2046_DIGEST_CHILD_MEDIA_TYPE",
    "declared_media_type",
    "declares_content_type",
    "effective_media_type",
    "effective_media_type_in",
]


def declares_content_type(part: PartShape) -> bool:
    """Whether the part's own headers carry a ``Content-Type`` field the walker parsed.

    Exactly the walker's own notion of "declared" (``walk._header_value`` looks for the first
    field with ``parse_status == "ok"`` and that name), so a malformed header **line** -- the
    walker records it as a nameless ``parse_status == "unknown"`` paragraph -- is not a
    declaration at all and the part is header-less for MIME purposes, as the walker already
    treats it (its charset ladder runs over it).
    """
    for field in part.header_fields:
        if field.parse_status == "ok" and field.name.lower() == "content-type":
            return True
    return False


def declared_media_type(part: PartShape) -> str:
    """The media type **as the walker parsed it**: lowercased, parameters dropped, or ``""``.

    ``PartShape.content_type`` is already lowercased and parameter-stripped by
    ``walk._split_params`` (the walker's one Content-Type split); the parameter strip here is a
    no-op for a real part and makes the rule literal -- "the declared media type lowercased and
    parameter-stripped". It returns ``""`` both when the part declares nothing and when it
    declares something whose media token is empty or unparsable -- the two are told apart by
    :func:`declares_content_type`, never here.
    """
    return (part.content_type or "").strip().lower().split(";", 1)[0].strip()


def effective_media_type(part: PartShape, parent_media: str | None = None) -> str:
    """The media type that governs behaviour, applying the two RFC defaults.

    * the declared media type, lowercased and parameter-stripped, when the part declares one
      (:func:`declares_content_type`). A declaration whose media token is **empty** or
      unparsable keeps the walker's reading -- ``""`` -- and is **never** reinterpreted as the
      default, because the walker saw a declaration; downstream tests on ``""`` keep the
      behaviour they had;
    * otherwise ``text/plain`` for a part that is not a ``multipart/digest`` child
      (**RFC 2045 section 5.2**);
    * otherwise ``message/rfc822`` for a child of a ``multipart/digest``
      (**RFC 2046 section 5.1.5**). ``parent_media`` is the parent's own **effective** media
      type; pass ``None`` for the top-level part.

    A multipart with no boundary is the walker's business (``body.no_boundary_found``), not this
    helper's: this only answers what the part's media type is.
    """
    if declares_content_type(part):
        return declared_media_type(part)
    if parent_media is not None and parent_media.strip().lower() == DIGEST_MEDIA_TYPE:
        return RFC_2046_DIGEST_CHILD_MEDIA_TYPE
    return RFC_2045_DEFAULT_MEDIA_TYPE


def effective_media_type_in(part: PartShape, parts: Mapping[str, PartShape]) -> str:
    """ :func:`effective_media_type` with the parent resolved from a ``{locator: PartShape}`` map.

    A convenience so every stage resolves the parent's effective media type the same way. A
    part's parent is never itself a header-less ``multipart/digest`` child (such a child is
    ``message/rfc822`` and the walker never descends into it), so the parent's own
    ``parent_media`` is always ``None``.
    """
    parent = parts.get(part.parent_path or "") if part.parent_path else None
    return effective_media_type(part, None if parent is None else effective_media_type(parent))
