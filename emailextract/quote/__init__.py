"""The quote stage: text rules, the label tables and the resolution rule (Turn 1.6).

The package is split so each piece has one job:

* :mod:`emailextract.quote.i18n` -- the closed English/German/French label tables, an NFC
  match of a label head before a colon, and the "one language per block, canonical order as a
  subsequence" test;
* :mod:`emailextract.quote.text_rules` -- the single-pass scanner over
  :func:`emailextract.walk.iter_lines` and the TEXT family's rules (the ``>``-family prefix
  depth, ``On ... wrote:`` with its two-line hard-wrap window, the Outlook flat block, the two
  forward shapes, the ``-- `` signature, the list footers), plus the deterministic work
  counter and the part-level budget;
* :mod:`emailextract.quote.resolve` -- ordinals, the derived per-view level, the
  ``view.quote_level_disagreement`` predicate and the fact rows.

Turn 1.6 builds the **text half**: the plain view's rules and the per-view level. The DOM
family (``gmail_quote``, ``blockquote[type=cite]``, Outlook ``divRplyFwdMsg``/``#appendonsend``,
Thunderbird ``moz-cite-prefix``/``moz-forward-container``) and the cross-family resolution are
Turn 1.7's, and nothing here measures the ``html`` view.

``QUOTE_RULES_VERSION`` (:mod:`emailextract.versions`) names the projection these rules are:
the label tables, the span conventions and the level rule.
"""

from __future__ import annotations

__all__: tuple[str, ...] = ()
