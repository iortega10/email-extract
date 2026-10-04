# The HTML parser decision (Phase 1 Turn 1.0d)

Decision 1 of `docs/design/phase1-build-spec.md` says the HTML parser is **decided by a
recorded experiment, not by preference**. This document is that experiment: its question,
its candidates, its inputs, its method, its recorded results on both interpreters, and
the decision the rule produced. The script that produces every number here lives at
`tools/html_experiment.py`; the test that re-runs it is
`tests/test_html_parser_experiment.py`.

## The question

Rendering an HTML body to text needs an element tree. The package may not take a parser
on faith: the tree has to place a **quote container** (`<blockquote>`, Gmail's
`div.gmail_quote`, Outlook's `divRplyFwdMsg`, …) at a node whose projected-text span the
quote rules can trust. Two candidates were put to the test:

* **Candidate A** — the stdlib `html.parser.HTMLParser`, subclassed to emit the
  `(event, text, get_starttag_text())` sequence, plus a **minimal own stack-based element
  tree** (void elements handled; an end tag pops to the matching open element; no repair
  beyond recording). This is the experiment's own builder, **not** `emailextract/htmltree.py`
  (that module is Turn 1.5).
* **Candidate B** — `lxml.html` (libxml2's HTML4 parser). `lxml` is **not** a runtime
  dependency of this package and this turn does not add it: the script imports it behind
  `try/except`, records absence as a closed reason, and the test skips B when it is absent.

## The inputs

**Committed fixtures.** Every `.eml` under `fixtures/` (excluding the machine-local
`real/`) whose bytes carry a `text/html` `Content-Type` part. The script finds them with
its own tiny MIME walker (`html_experiment.html_parts`), sharing no code with the package
walker — the experiment must not use the thing it is deciding for. The 16 covered
fixtures, by their `<Content-Type>` bytes:

```
fixtures/generated/alternative_text_html.eml
fixtures/generated/attach_cid_dangling.eml
fixtures/generated/attach_decoration_tracking_pixel.eml
fixtures/generated/attach_inline_referenced.eml
fixtures/generated/attach_inline_unreferenced.eml
fixtures/generated/attach_remote_image_only.eml
fixtures/generated/content_location_in_related.eml
fixtures/generated/html_data_uri_and_tracking_pixel.eml
fixtures/generated/html_href_img_remote_and_cid.eml
fixtures/generated/html_style_and_script.eml
fixtures/generated/inline_cid_referenced_and_not.eml
fixtures/generated/multipart_mixed_wraps_alternative.eml
fixtures/generated/nested_alternative_in_related_in_mixed.eml
fixtures/generated/plain_effectively_empty.eml
fixtures/generated/text_calendar_alternative.eml
fixtures/raw/duplicate_content_type_header.eml
```

**Synthetic snippets.** The quote containers the quote catalogue will need — the quote
fixtures do not exist yet and this turn may not create fixtures — plus the malformed
shapes the debate's focus list names. Verbatim:

```
blockquote                 <blockquote>Earlier message text.</blockquote><p>New reply.</p>
gmail_quote                <div class="gmail_quote">Earlier message text.</div><p>New reply.</p>
outlook_divRplyFwdMsg      <div id="divRplyFwdMsg">Earlier message text.</div><p>New reply.</p>
unclosed_blockquote        <blockquote>Earlier message text.<p>New reply after the unclosed container.</p>
misnested_b_i              <p><b>bold <i>and italic</b> still italic</i> tail</p>
table_in_blockquote        <blockquote><table><tr><td>cell text</td></tr></table></blockquote><p>New reply.</p>
br_run                     <p>line one<br><br>line three<br>line four</p>
```

## The method

* **Projection rule (stated, used by both candidates).** The concatenation, in document
  order, of every text node whose ancestors exclude `<style>` and `<script>`, verbatim —
  whitespace and case preserved, character references resolved (`convert_charrefs=True`
  for A; `.text`/`.tail` for B). The projection's sha256 is the **projection hash**.
* **Event sequence.** For A, the parser's own `(event, text, get_starttag_text())`
  callbacks. libxml2 exposes a tree, not callbacks, so B's event sequence is the same
  shape **derived from its tree** (`starttag`/`endtag` in document order). It is an honest
  A-vs-B fingerprint, not a claim about libxml2's callbacks.
* **Element tree.** Per element: tag, attributes (sorted), child count, the projected-text
  span it covers, the set of `cid:` references in its subtree, and whether it is closed.
  The tree's sha256 is the **tree hash**.
* **Quote-container locator.** For each snippet with a container, the first node the
  snippet's selector matches, recorded as `(tag path, projected-text span)`. Wrapper tags
  (`html`, `head`, `body`, the synthetic `#document`) are dropped from the front of the
  path so a bare fragment and a full document compare equal.
* **Interpreters.** Both runs: CPython **3.14.3** (`python`) and CPython **3.11.15**
  (`py -V:Astral/CPython3.11.15`). The command is
  `python tools/html_experiment.py --json`; run on both:

  ```
  python tools/html_experiment.py --json                        # CPython 3.14.3
  py -V:Astral/CPython3.11.15 tools/html_experiment.py --json   # CPython 3.11.15
  ```

* **The libxml2/wheel fact.** B is pinned by the **wheel**, not the interpreter: the run
  used **lxml 6.1.3.0** on **libxml2 2.11.9**, identical under both interpreters. A
  two-interpreter identity test therefore says **nothing** about libxml2 — it only shows
  the wheel was the same. A's identity across the two interpreters *is* meaningful,
  because A is the interpreter's own `html.parser`.

## Recorded results

Full report: `python tools/html_experiment.py --json`. The two JSON outputs are
byte-identical except for the recorded interpreter string; their sha256s are
`0aa5114256c157757efbe73ccde0c2786c857f9fd2366f8a2b0ddff652db49ea` (CPython 3.14.3) and
`1a9b21e0f7f1b5cc85e2ae510bcc3205df12cb7f6f0fedc3bbe0bca9ab736657` (CPython 3.11.15).
Hash columns are 16-hex prefixes; `B` columns are as reported by the lxml run.

| input | html sha256 | A event | A tree | A proj | B event | B tree | B proj |
|---|---|---|---|---|---|---|---|
| fixture:alternative_text_html.eml | 421701c1cd47f9dc | f138c3ec852de876 | aa6028d97f6eb6bb | ea21b0b732fde3f9 | c9549f4b3f82b501 | 27decc11238dd0e0 | ea21b0b732fde3f9 |
| fixture:attach_cid_dangling.eml | 4430135462222302 | 67de913207afa920 | d3dadb81fd958389 | d9b028813062c452 | 357685a15cc0ed67 | 1e1f9ffd939e1963 | d9b028813062c452 |
| fixture:attach_decoration_tracking_pixel.eml | 607f8ae5d3df7bf0 | 1f55af3c263cae99 | b5a9e80ea3dce02a | 8e150939b58f5500 | 4da754430b14b848 | bb3964a4781cc999 | 8e150939b58f5500 |
| fixture:attach_inline_referenced.eml | f2ae4cb65a9460a0 | 875acba32e8a65e9 | ba7c11bd1563b92b | eef2d56f76350d10 | c050cf81a97f97ca | 238e00fef74d139b | eef2d56f76350d10 |
| fixture:attach_inline_unreferenced.eml | 3345db92aedbbe92 | 49cbdbbf78f3b1ad | 57f0bf734cfa209d | fc75bf2651eed550 | 4da754430b14b848 | 648db6f45e24d5e0 | fc75bf2651eed550 |
| fixture:attach_remote_image_only.eml | 67acc5c0b6e9bddd | 123c60b935854f06 | d2e31920008fe9d4 | d3d9178a14944d6e | fea0eb6d2447299f | a90fa7679948eed9 | d3d9178a14944d6e |
| fixture:content_location_in_related.eml | d1b10faeb8909025 | d398b963c8652e8c | f2a3b502d595cb08 | 770517de75563768 | 6ca950f19a3e0a25 | 26851ad474ba5974 | 770517de75563768 |
| fixture:html_data_uri_and_tracking_pixel.eml | f99a2891f8e0072e | 0526dab156f055f0 | 83e967842a9f536d | dba5166ad9db9ba6 | 1274951650865321 | 23a8887d2d4c116c | dba5166ad9db9ba6 |
| fixture:html_href_img_remote_and_cid.eml | 776b9bc890c6ffd2 | 16d373ba94fe8280 | 20fdb62ebbd55ae4 | 05719f2f9c145d4e | 8a1c5c4b992c52b0 | 2f8431fecab9c459 | 05719f2f9c145d4e |
| fixture:html_style_and_script.eml | 637d91670cce444c | e288301e04028b13 | e2c57d2e6911a0da | 9157795535833323 | 3ce94cbbc20b8149 | c908cf4612d101e1 | bedaa9b96f84a1f0 |
| fixture:inline_cid_referenced_and_not.eml | f2ae4cb65a9460a0 | 875acba32e8a65e9 | ba7c11bd1563b92b | eef2d56f76350d10 | c050cf81a97f97ca | 238e00fef74d139b | eef2d56f76350d10 |
| fixture:multipart_mixed_wraps_alternative.eml | 421701c1cd47f9dc | f138c3ec852de876 | aa6028d97f6eb6bb | ea21b0b732fde3f9 | c9549f4b3f82b501 | 27decc11238dd0e0 | ea21b0b732fde3f9 |
| fixture:nested_alternative_in_related_in_mixed.eml | f7880eecf3e57d14 | 2f1512e5f631adcd | e465614fa9219652 | 62fa778912079588 | 4da754430b14b848 | 078a16acab0abba5 | 62fa778912079588 |
| fixture:plain_effectively_empty.eml | 91aec1f4e96e1f9f | bea8f4f305a98d09 | 3f85c8f37d6cbbff | a93d53258eb7f556 | 4da754430b14b848 | 54b9d657b7e3ba93 | a93d53258eb7f556 |
| fixture:text_calendar_alternative.eml | f7880eecf3e57d14 | 2f1512e5f631adcd | e465614fa9219652 | 62fa778912079588 | 4da754430b14b848 | 078a16acab0abba5 | 62fa778912079588 |
| fixture:duplicate_content_type_header.eml | 719d0959235d1125 | 1f001c322cd2585c | 27f443fbb6240e7e | 719d0959235d1125 | 4da754430b14b848 | 5482f32f816e7756 | 719d0959235d1125 |
| snippet:blockquote | 1ab5be83090e603a | 8b1a9df9cffe8244 | efd0edee43b57a73 | 572dec855139bc80 | 32d96b98e77feb32 | d8cdacc402c46508 | 572dec855139bc80 |
| snippet:gmail_quote | d5c1f5ea47289c59 | 3f2b4d378881587d | 796e798fa94dff09 | 572dec855139bc80 | 50b9abdc869d9063 | 48a9747a9da605d3 | 572dec855139bc80 |
| snippet:outlook_divRplyFwdMsg | c6c187192a3661ac | 09c94e8f06bed4c1 | 7948177ade71841d | 572dec855139bc80 | 8fbf784f2a4e3151 | e5f00ddb9e812e9d | 572dec855139bc80 |
| snippet:unclosed_blockquote | c27a0bc4202a0f36 | e72a450738cf73cd | 744c48c8b113b1e5 | 73cfdc2886a4b84c | 691307f4b4d876c4 | a82480ed52945f66 | 73cfdc2886a4b84c |
| snippet:misnested_b_i | b58bb4f3317a4cca | ebb273c5b610f4ca | d45f725ade8b82bb | c294fd3f25045ee1 | bcf6edd0eeb1c573 | 640701f88ce1e74e | c294fd3f25045ee1 |
| snippet:table_in_blockquote | 36c9b9748dc12665 | 6ad4abf0ba73100e | 9665bcf609bf3b86 | 00e3b9ce22f35c5f | 3d142304f1cc7847 | 5f3653c476753754 | 00e3b9ce22f35c5f |
| snippet:br_run | e6d340f98583a8f4 | 56228c0e78fbbd19 | 7b6786386e5ebc42 | f252d1bd9e976691 | ab7000def6663273 | d8767f4c136a9097 | f252d1bd9e976691 |

Two recorded findings stand out:

* **A is identical on both interpreters.** Every A hash matches between CPython 3.14.3
  and 3.11.15 for all 23 inputs. The recorded fingerprint is what lets that claim be made
  at all (decision 1: "no claim about `html.parser` version differences without the
  fingerprint").
* **A and B project the same text on 22 of 23 inputs.** The one difference is
  `html_style_and_script.eml`: text after the closing `</html>` is kept by A (its trailing
  `\r\n`) and dropped by libxml2 (nothing follows the document element) — a projecting
  difference, not a quote-container one.

### Quote-container placement

| snippet | selector | A node (path, span) | B node (path, span) | same node |
|---|---|---|---|---|
| blockquote | blockquote | (['blockquote'], [0, 21]) | (['blockquote'], [0, 21]) | yes |
| gmail_quote | div.gmail_quote | (['div'], [0, 21]) | (['div'], [0, 21]) | yes |
| outlook_divRplyFwdMsg | div#divRplyFwdMsg | (['div'], [0, 21]) | (['div'], [0, 21]) | yes |
| table_in_blockquote | blockquote | (['blockquote'], [0, 9]) | (['blockquote'], [0, 9]) | yes |
| unclosed_blockquote | blockquote | (['blockquote'], [0, 60]) | (['blockquote'], [0, 60]) | yes |

So B **does** place every quote container at A's node — but on the unclosed snippet
**neither candidate is clean**: both leave the container open to the end of the projection,
so its span covers the following *new* text (`[0, 60]` is the whole projection). libxml2
does not fix the swallowing either; it silently closes the element while keeping the tail
inside its span.

### lxml facts

```
lxml    6.1.3.0
libxml2 2.11.9
error_log  ""   (empty for every input)
```

## The decision

**Candidate A (stdlib `html.parser` plus the own stack tree) is used.** The rule as
implemented:

> **B is chosen only if it places every quote container at the same node (tag path,
> projected-text span) as A on the closed quote snippets AND neither candidate swallows
> the following text through an unclosed container; otherwise neither is clean and A is
> used with the named unclosed-container rule.**

B satisfies the first half (it matches A on all four closed containers), but the second
half fails for **both** candidates: `neither_clean` is true on the unclosed snippet.
Decision 1's own rationale names exactly this — "an unclosed `<blockquote>` otherwise
swallows following new text" — and prescribes A with a **named unclosed-container rule**:

> An unclosed quote container is recorded, never closed: the element tree keeps the
> container open to the end of its parent, its projected-text span ends at the end of the
> projection, every following text node stays inside that span, and the DOM quote rule
> records the gap `body.html_quote_rule_gap` instead of emitting a synthetic end tag.
> libxml2's repair (which auto-closes the element and can move the following text out of
> the container) is deliberately not used.

`body.html_quote_rule_gap` is registered in the design's known-gap registry (the
`body.*` bullet), so no new id is invented here.

## Risks and the reading that was not taken

* **The alternative reading of decision 1.** Read purely as "B is chosen iff B matches A on
  every quote container", the rule would choose **B**, since B matches A on all five
  containers. That reading makes the rule's own second clause ("if neither is clean")
  pointless and would force a runtime dependency (`lxml`) the design forbids
  ("runtime dependencies stay `docextract-core` only"). The reading taken — "clean" means
  the container does not swallow the following text — is the one the rationale sentence
  supports, and it keeps A. This is **recorded as an owner decision** (see the turn
  report): if the owner wants B after all, that is a deliberate addition of an `lxml`
  runtime dependency and a new `HTMLTEXT_VERSION` key over the wheel.
* **The quote fixtures do not exist yet.** The snippets are a proxy; a real quote catalogue
  fixture may expose a container placement the snippets miss. The decision is revisitable
  by the quote-catalogue turn, whose own rule is A only (the turn table).
* **A mis-nested *container* is not covered by the snippets.** A probe
  (`<blockquote><div>a</blockquote>b</div>c`) shows A and B **differ** there (A closes the
  blockquote at its own end tag, span `[0, 1]`; libxml2 repairs, span `[0, 3]`). The fixed
  snippet set contains no such container, so it does not enter the decision; it is recorded
  here as a known unmeasured case for the quote-catalogue review.
* **Only A is meaningful across interpreters.** B's identity across the two runs only shows
  the same wheel was loaded.
