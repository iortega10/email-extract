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
* :mod:`emailextract.quote.dom_rules` -- the DOM family on the **html** view (the projection's
  code points): ``gmail_quote``, ``blockquote[type=cite]``, the Outlook marker ids, the
  Thunderbird prefix/forward-container class tokens and the ``>``-family rule over the
  projection's physical lines;
* :mod:`emailextract.quote.resolve` -- ordinals, the derived per-view level, the
  ``view.quote_level_disagreement`` predicate and the fact rows for both views.

Turn 1.6 builds the **text half**: the plain view's rules and the per-view level. Turn 1.7 adds
the DOM family (``gmail_quote``, ``blockquote[type=cite]``, Outlook ``divRplyFwdMsg``/
``#appendonsend``, Thunderbird ``moz-cite-prefix``/``moz-forward-container``), the html view's
resolution and the vendor-family/absence gaps.

``QUOTE_RULES_VERSION`` (:mod:`emailextract.versions`) names the projection these rules are:
the label tables, the span conventions and the level rule.
"""

from __future__ import annotations

__all__: tuple[str, ...] = ()
