"""The closed quote-label tables (Turn 1.6; build-spec decisions 3 and 16).

One table per named language -- English, German, French -- and nowhere else: owner decision
16 says "more only when the owner's mail needs them", so a table that does not name a
language is the reason :data:`~emailextract.quote.text_rules.GAP_I18N_REPLY_MARKER` exists.

Each entry is the label **head** (the name before the colon) as an NFC string, with the
source it was typed from. The *separator before the colon* is any whitespace run, including
U+00A0 and U+202F, and is matched only after the **line** is NFC-normalised
(build-spec decision 3: "separators accepting any whitespace run before ``:`` including
U+00A0 and U+202F after NFC"): the stored text is never normalised, because a rule must not
move a label's own bytes.

The canonical order is the slot order below: a run of adjacent label lines is a block only
when, for **one** language, every line matches that language's set **and** the matched slots
are a non-decreasing subsequence of the canonical order (decision 3: "in canonical order as
a subsequence"). The date slot accepts both tokens per language (``Sent:``/``Date:``,
``Gesendet:``/``Datum:``, ``Envoyé:``/``Date:``); every other slot accepts exactly one.

NFKC is **not** used: the decision names NFC, and NFKC would fold ``À`` and ``A`` into one
label, which would make two different languages' labels indistinguishable.
"""

from __future__ import annotations

import re
import unicodedata
from types import MappingProxyType
from typing import Final, Mapping

__all__ = [
    "CANONICAL_ORDER",
    "LABEL_HEAD_SOURCES",
    "LABEL_TOKENS",
    "LANGUAGES",
    "label_head_at",
    "label_shaped",
    "language_of_run",
    "nfc",
    "slot_of_line",
]

#: The named languages, in the order a block is tested in (English first: the tables were
#: typed from the English design table and the owner's decision 16 names English first).
LANGUAGES: Final[tuple[str, ...]] = ("en", "de", "fr")

#: The canonical slot order (decision 3). ``None`` slots are not in v1.
CANONICAL_ORDER: Final[tuple[str, ...]] = ("from", "date", "to", "cc", "subject")

#: ``language -> slot -> the label heads that fill it``. Every head is NFC, exactly as the
#: design table writes it (``De :`` is stored as the head ``De``; the space is the
#: separator, not part of the head).
LABEL_TOKENS: Final[Mapping[str, Mapping[str, tuple[str, ...]]]] = MappingProxyType(
    {
        "en": MappingProxyType(
            {
                "from": ("From",),
                "date": ("Sent", "Date"),
                "to": ("To",),
                "cc": ("Cc",),
                "subject": ("Subject",),
            }
        ),
        "de": MappingProxyType(
            {
                "from": ("Von",),
                "date": ("Gesendet", "Datum"),
                "to": ("An",),
                "cc": ("Cc",),
                "subject": ("Betreff",),
            }
        ),
        "fr": MappingProxyType(
            {
                "from": ("De",),
                "date": ("Envoyé", "Date"),
                "to": ("À",),
                "cc": ("Cc",),
                "subject": ("Objet",),
            }
        ),
    }
)

#: Where each head was typed from: the design's rule-family table (decision 3) as restated
#: in ``docs/design/phase1-build-spec.md`` and ``docs/design/email-extraction-design.md`` D3.
LABEL_HEAD_SOURCES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "en": "build-spec decision 3 (EN: From: Sent:|Date: To: Cc: Subject:)",
        "de": "build-spec decision 3 (DE: Von: Gesendet:|Datum: An: Cc: Betreff:)",
        "fr": "build-spec decision 3 (FR: De : Envoyé :|Date : À : Cc : Objet :)",
    }
)

#: A label head is a run with no whitespace and no colon. ``[\w.-]`` keeps an accented head
#: (``Envoyé``, ``À``) and a dotted one (``Betreff``) inside the class; ``re.UNICODE`` is the
#: default for ``str`` patterns, so ``\\w`` is the Unicode word class.
_HEAD = r"[^\s:]{1,15}"

#: A label-shaped line: a short head, a whitespace run (possibly empty), then a colon at the
#: line's start. This is the shape the **i18n** gap is keyed on -- it is deliberately wider
#: than any one language's set, because its whole job is to recognise a header-like run whose
#: language is not named.
_LABEL_LINE: Final[re.Pattern[str]] = re.compile(rf"^(?P<head>{_HEAD})\s*:(?P<rest>.*)$")

#: ``^(head)\s*:`` per head, built once per language/slot/token. ``\s`` in a ``str`` pattern
#: is the Unicode whitespace class, so U+00A0 and U+202F are separators and so is a tab.
_HEAD_PATTERNS: Final[Mapping[str, Mapping[str, tuple[re.Pattern[str], ...]]]] = (
    MappingProxyType(
        {
            language: MappingProxyType(
                {
                    slot: tuple(
                        re.compile(rf"^{re.escape(head)}\s*:") for head in heads
                    )
                    for slot, heads in slots.items()
                }
            )
            for language, slots in LABEL_TOKENS.items()
        }
    )
)


def nfc(line: str) -> str:
    """The line, NFC-normalised **for matching only** (the stored text is never normalised)."""
    return unicodedata.normalize("NFC", line)


def label_head_at(line: str) -> tuple[str, str] | None:
    """``(head, rest)`` when ``line`` is label-shaped, else ``None``.

    The head is returned as written (post-NFC) and ``rest`` is the text after the colon, so a
    caller can record the run without re-splitting the line.
    """
    match = _LABEL_LINE.match(nfc(line))
    if match is None:
        return None
    return match.group("head"), match.group("rest")


def label_shaped(line: str) -> bool:
    """Whether a line is a short ``Label:`` line (the header-like run shape)."""
    return label_head_at(line) is not None


def slot_of_line(line: str, language: str) -> str | None:
    """The canonical slot ``line`` fills in ``language``'s table, or ``None``.

    Matching is case-sensitive on NFC text: the table is the closed set the design names, and
    widening it (a case fold) is exactly the kind of silent rule growth decision 13 warns
    about. The date slot answers ``date`` for both of its tokens.
    """
    target = nfc(line)
    for slot, patterns in _HEAD_PATTERNS[language].items():
        for pattern in patterns:
            if pattern.match(target):
                return slot
    return None


def language_of_run(lines: list[str]) -> str | None:
    """The one language a maximal run of adjacent label lines belongs to, or ``None``.

    A run is one language's block iff **every** line matches that language's set **and** the
    matched slots are a non-decreasing subsequence of :data:`CANONICAL_ORDER` (a repeated slot
    is allowed: ``From: ... From: ...`` is not a subsequence, but ``From: ... To: ...`` is).
    A run that mixes two languages matches none, because every line must come from the *same*
    language's set -- decision 3: "the language is per BLOCK (a run never mixes languages)".
    """
    for language in LANGUAGES:
        order = {
            slot: index for index, slot in enumerate(CANONICAL_ORDER)
        }
        previous = -1
        ok = True
        for line in lines:
            slot = slot_of_line(line, language)
            if slot is None or order[slot] < previous:
                ok = False
                break
            previous = order[slot]
        if ok:
            return language
    return None


def labels_from_one_known_set(lines: list[str]) -> bool:
    """Whether every line of a label-shaped run comes from **one** known language's set.

    This is the i18n gap's test as the design words it ("its labels are NOT all from one
    known language set"): a run whose lines are all in the English set but whose order is not
    canonical is *not* a block and *not* the i18n gap either -- it is simply not a block.
    """
    for language in LANGUAGES:
        if all(slot_of_line(line, language) is not None for line in lines):
            return True
    return False
