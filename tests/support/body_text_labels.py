"""Turn BODY1's hand-typed labels: the body text and the attachment list, typed first.

The repo's label protocol (Phase 1b): type the expected value **before** the accessor that
answers it runs, freeze it, compare after, and report every disagreement rather than
editing the label to fit. So nothing in this file was read off ``body_text`` or
``iter_attachment_payloads``; each entry's ``provenance`` names the construction it was
typed from:

* a generated fixture: the table entry in ``tools/make_fixtures.py`` (the exact payload
  bytes, the charset, the transfer encoding, the HTML);
* a raw fixture: the committed bytes, read as the fixture's own construction (it has no
  builder);
* a ``.msg``: ``tools/make_msg_fixtures.py``'s stream table plus
  ``tests/support/msg_construction.py``'s layout for ``fixtures/msg/<stem>.msg``.

The **sizes** are the length of the construction's own decoded payload (``len(tiny_pdf(
"tiny fixture"))`` and friends, computed from ``tools/make_fixtures.py``'s builders -- an
independent arithmetic on the construction, never a call to the accessor). The **texts**
are the construction's body bytes verbatim, because the flat projection is verbatim
(``htmltext``: no collapsing, no element inserts a character, character references decoded
once by the parser): an HTML label therefore keeps every ``\\r\\n`` between elements and
drops only the markup.

This file is under ``tests/support/``, so ``tools/update_label_ledger.py`` fingerprints it:
once recorded, an edit here is refused in place -- which is what "frozen" means.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "ATTACHMENT_LABELS",
    "BODY_TEXT_LABELS",
    "ZERO_WIDTH_TRACKING_PIXEL_EML",
    "ZERO_WIDTH_TRACKING_PIXEL_TEXT",
]

#: ``stem -> {fixture, view, text, reason_id, provenance}``. ``fixture`` is relative to
#: ``fixtures/``; ``view`` is the view **D14 digests** (``html`` whenever a displayable
#: ``text/html`` view exists, else ``plain``); ``reason_id`` is ``None`` unless the message
#: has no text body view at all.
BODY_TEXT_LABELS: Final[dict[str, dict[str, object]]] = {
    "plain_simple": {
        "fixture": "generated/plain_simple.eml",
        "view": "plain",
        "text": "Hello Ben.\r\n\r\nThis is the plain simple fixture.\r\n",
        "reason_id": None,
        "provenance": "make_fixtures._fixture_plain_simple: the payload bytes, us-ascii, identity CTE",
    },
    "html_only": {
        "fixture": "generated/html_only.eml",
        "view": "html",
        "text": "Hello Ben. No quoting here at all.\r\n",
        "reason_id": None,
        "provenance": (
            "make_fixtures._fixture_html_only: '<p>Hello Ben. No quoting here at all.</p>\\r\\n' "
            "-- the <p> inserts nothing, so the projection is the text node plus its CRLF"
        ),
    },
    "alternative_text_html": {
        "fixture": "generated/alternative_text_html.eml",
        "view": "html",
        "text": "Hello Ben.\r\nA plain view.\r\n",
        "reason_id": None,
        "provenance": (
            "make_fixtures._fixture_alternative_text_html: multipart/alternative, plain + html; "
            "D14 digests the html view '<p>Hello Ben.</p>\\r\\n<p>A plain view.</p>\\r\\n'"
        ),
    },
    "qp_raw_8bit": {
        "fixture": "raw/qp_raw_8bit.eml",
        "view": "plain",
        "text": "Caf\u00e9 = ok\r\n",
        "reason_id": None,
        "provenance": (
            "the committed bytes: 'Caf\\xe9 =3D ok\\r\\n' with quoted-printable and charset "
            "iso-8859-1; '=3D' is one '=' and the raw 8-bit 0xe9 is U+00E9 in that charset"
        ),
    },
    "windows_1252_declared_iso_8859_1": {
        "fixture": "raw/windows_1252_declared_iso_8859_1.eml",
        "view": "plain",
        "text": "\u0093Hi\u0094\r\n",
        "reason_id": None,
        "provenance": (
            "the committed bytes: 0x93 'Hi' 0x94 with chartype iso-8859-1 declared, so the C1 "
            "code points U+0093/U+0094 are the literal answer (no alias widens the charset)"
        ),
    },
    "body_no_text_part": {
        "fixture": "generated/body_no_text_part.eml",
        "view": "plain",
        "text": "",
        "reason_id": "body.no_text_part",
        "provenance": (
            "make_fixtures._fixture_body_no_text_part: multipart/mixed whose only child is an "
            "application/pdf attachment, so there is no text body view to choose"
        ),
    },
    "html_data_uri_and_tracking_pixel": {
        "fixture": "generated/html_data_uri_and_tracking_pixel.eml",
        "view": "html",
        "text": "\r\n\r\n",
        "reason_id": None,
        "provenance": (
            "make_fixtures._fixture_html_data_uri_and_tracking_pixel: two <img> elements and "
            "nothing else; each element inserts no character, so the projection is the two CRLF "
            "text nodes between/after them"
        ),
    },
    "attach_decoration_tracking_pixel": {
        "fixture": "generated/attach_decoration_tracking_pixel.eml",
        "view": "html",
        "text": "No image reference here.\r\n",
        "reason_id": None,
        "provenance": (
            "make_fixtures._fixture_attach_decoration_tracking_pixel: the multipart/related body "
            "is '<p>No image reference here.</p>\\r\\n'"
        ),
    },
    "attach_message_rfc822_no_filename": {
        "fixture": "generated/attach_message_rfc822_no_filename.eml",
        "view": "plain",
        "text": "Forwarded message attached.\r\n",
        "reason_id": None,
        "provenance": (
            "make_fixtures._fixture_attach_message_rfc822_no_filename: the plain leaf's payload; "
            "the message/rfc822 child is an attachment and is not part of the body view"
        ),
    },
    "forwarded_inline_marker": {
        "fixture": "generated/forwarded_inline_marker.eml",
        "view": "plain",
        "text": (
            "Hello Ben.\r\n"
            "\r\n"
            "Begin forwarded message:\r\n"
            "From: Ada Sender <ada@example.test>\r\n"
            "Date: Tue, 4 Mar 2025 09:00:00 +0000\r\n"
            "Subject: FYI\r\n"
            "\r\n"
            "The forwarded note.\r\n"
        ),
        "reason_id": None,
        "provenance": (
            "make_fixtures._fixture_forwarded_inline_marker: the single text/plain payload, "
            "verbatim -- a forwarded message is one body view, not a second part"
        ),
    },
    "attachments_mixed": {
        "fixture": "generated/attachments_mixed.eml",
        "view": "plain",
        "text": "Hello Ben.\r\n\r\nFour tiny attachments.\r\n",
        "reason_id": None,
        "provenance": (
            "make_fixtures._fixture_attachments_mixed: the plain leaf's payload; the four "
            "base64 attachments are occurrences, not body views"
        ),
    },
    "msg_plain_only": {
        "fixture": "msg/msg_plain_only.msg",
        "view": "plain",
        "text": "\r\n",
        "reason_id": None,
        "provenance": (
            "tools/make_msg_fixtures._fixture_plain_only: the 0x1000 stream is "
            "T15_PLAIN_TEXT = '\\r\\n' (UTF-16LE in the CFB, 8-bit in the projection)"
        ),
    },
    "msg_plain_and_html": {
        "fixture": "msg/msg_plain_and_html.msg",
        "view": "html",
        "text": "synthetic turn 1b.5 body\r\n",
        "reason_id": None,
        "provenance": (
            "tools/make_msg_fixtures: T15_HTML_BODY = '<html><body><p>synthetic turn 1b.5 "
            "body</p></body></html>\\r\\n'; D14 digests the html view, whose projection is the "
            "text node plus its CRLF"
        ),
    },
}

#: ``stem -> {payloads, skipped}`` over the **manifest's** occurrence order. A payload is
#: ``(occurrence_ref, filename, media_type, size)``; a skipped occurrence is
#: ``(occurrence_ref, reason_id)`` -- the decorative rule's skip, which is a refusal and not a
#: drop. ``occurrence_ref`` is ``<part path>@<ordinal among the message's attachments>``, the
#: ``occurrence_path`` an ``AttachmentOccurrence`` carries.
ATTACHMENT_LABELS: Final[dict[str, dict[str, object]]] = {
    "attachments_mixed": {
        "fixture": "generated/attachments_mixed.eml",
        "payloads": [
            # part 1.1 is the plain body; 1.2..1.5 are the four children of the multipart/mixed
            ("1.2@0", "tiny.pdf", "application/pdf", 583),
            (
                "1.3@1",
                "tiny.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                2268,
            ),
            (
                "1.4@2",
                "tiny.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                1284,
            ),
            ("1.5@3", "tiny.png", "image/png", 82),
        ],
        "skipped": [],
        "provenance": (
            "make_fixtures._fixture_attachments_mixed + _attachment_leaf: four base64 parts, "
            "sizes len(tiny_pdf('tiny fixture'))=583, len(tiny_xlsx())=2268, len(tiny_docx())"
            "=1284, len(tiny_png(b'\\x10\\x20\\x30'))=82"
        ),
    },
    "attach_message_rfc822_no_filename": {
        "fixture": "generated/attach_message_rfc822_no_filename.eml",
        # a nested message is a payload, returned unrecursed (no filename is declared on it)
        "payloads": [("1.2@0", None, "message/rfc822", 163)],
        "skipped": [],
        "provenance": (
            "make_fixtures._fixture_attach_message_rfc822_no_filename + _C_NESTED_MESSAGE: "
            "len(_C_NESTED_MESSAGE)=163 bytes, returned as the payload and never opened"
        ),
    },
    "attach_decoration_tracking_pixel": {
        "fixture": "generated/attach_decoration_tracking_pixel.eml",
        "payloads": [],
        "skipped": [("1.2@0", "attach.cid_unreferenced")],
        "provenance": (
            "make_fixtures._fixture_attach_decoration_tracking_pixel: the inline 1x1 png "
            "(len(tiny_png(b'\\x00\\x00\\x00',1,1))=72) whose cid '<pixel@example.test>' the "
            "html body never references, so the decorative rule fires and it is skipped"
        ),
    },
    "html_data_uri_and_tracking_pixel": {
        "fixture": "generated/html_data_uri_and_tracking_pixel.eml",
        "payloads": [],
        "skipped": [],
        "provenance": (
            "make_fixtures._fixture_html_data_uri_and_tracking_pixel: both images are <img> tags "
            "in the body, not MIME parts, so the message has no attachment occurrence at all"
        ),
    },
    "body_no_text_part": {
        "fixture": "generated/body_no_text_part.eml",
        "payloads": [("1.1@0", "doc.pdf", "application/pdf", 23)],
        "skipped": [],
        "provenance": (
            "make_fixtures._fixture_body_no_text_part: one base64 pdf child, "
            "len(b'%PDF-1.4\\nfixture\\n%%EOF\\n')=23 (typed 22 first; the construction's own "
            "length corrected it before the accessor ran)"
        ),
    },
}

#: The one message this turn types **without a committed fixture**: a body carrying a
#: zero-width space and a 1x1 ``data:`` tracking pixel. No committed fixture carries a
#: zero-width character, and adding one would move the corpus and every recorded fingerprint
#: line, so the message is hand-built here and driven through ``memory_bytes`` (the second
#: route every input test takes).
ZERO_WIDTH_TRACKING_PIXEL_EML: Final[bytes] = (
    b"From: Ada Sender <ada@example.test>\r\n"
    b"To: Ben Receiver <ben@example.test>\r\n"
    b"Subject: zero width and a tracking pixel\r\n"
    b"Date: Tue, 4 Mar 2025 08:30:00 +0000\r\n"
    b"Message-ID: <zero-width-pixel-body1@example.test>\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: text/html; charset=utf-8\r\n"
    b"\r\n"
    b"<p>Hi&#8203;Ben.</p>\r\n"
    b'<img src="data:image/gif;base64,R0lGODlhAQABAIAAAAUEBAAAACwAAAAAAQABAAACAkQBADs="'
    b' width="1" height="1">\r\n'
)

#: Its typed text: the parser decodes ``&#8203;`` once (``convert_charrefs=True``), so the
#: zero-width space is one code point, and the ``<p>``/``<img>`` insert nothing.
ZERO_WIDTH_TRACKING_PIXEL_TEXT: Final[str] = "Hi\u200bBen.\r\n\r\n"
