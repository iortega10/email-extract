# Phase 1 fixtures (Turn 1.0a catalogue; typed in Turns 1.0c and the quote increment)

Turn 1.0c types fixtures and hand-typed sidecars **by fact family, non-quote first**, in three commits of
**at most 30 pairs each**:

| commit | family | the parts it opens |
|---|---|---|
| 1.0c-1 | **headers / date / address** | `headers.py` (1.1), `addresses.py` (1.2), `dates.py` (1.3) |
| 1.0c-2 | **body / HTML** | `text.py` (1.4), selection + `htmltree.py`/`htmltext.py` (1.5) |
| 1.0c-3 | **attachments / caps** | `attach.py` (1.8) and the structural caps (1.0d/1.8) |

The **quote catalogue** is a separate table (below): those fixtures are **not** typed in 1.0c, they are
typed after Turn 1.5 and **owner-reviewed before any quote rule is written** (decision 13).

Rules for every fixture here, all of which a test enforces or a reviewer checks:

- **Every fixture is synthetic and tiny.** No real or employer mail, ever.
- **Generated** fixtures use the declarative generator's **own byte renderer**
  (`tools/make_fixtures.py`), **never** the stdlib `email` serializer: a wrong MIME emitter must not be
  able to produce a self-consistent wrong fixture (D11).
- **Raw** fixtures are hand-written byte literals (`tools/write_raw_fixtures.py`), frozen in
  `fixtures/raw/SHA256SUMS` and checked by `tests/test_fixtures.py` -- used wherever the generator would
  encode the assumption under test (malformed MIME, broken charset, folding, preamble-only, truncated
  base64).
- **Any zip or png inside an attachment is STORED, not compressed**, so no fixture byte depends on the
  zlib build (operating rule 2).
- Each sidecar is `labels_provenance: spec` (a model typed it from the design rules, never from the
  walker's output) and is pinned in the **label ledger** (`docs/design/phase1-ledgers.md`).
- Every sidecar also carries the Phase 0 facts (`container.sha256`, `container.size_bytes`,
  `headers.fields`, `part.tree`, `part.regions`, `part.gaps`, `body.preamble_epilogue`, `decode.chain`,
  `body.content_sha256`) and the Phase 1 fact `document.axes`; the columns below name the **fact family's
  own** facts and any **gap ids**.

## Family A: headers, date and address (Turn 1.0c, commit 1)

| fixture | dir | what it exercises (one thing) | Phase 1 facts / gap ids | turn |
|---|---|---|---|---|
| `headers_plain_baseline` | generated | the whole header projection on a well-formed message (raw beside parsed) | `headers.projection`, `headers.addresses`, `headers.date`, `headers.decoded` | 1.1-1.3 |
| `duplicate_header_mime_version` | generated | two `MIME-Version` fields | `headers.projection`; gap `headers.duplicate_header` | 1.1 |
| `duplicate_content_type_header` | raw | two `Content-Type` fields (the duplicate-header mutation) | `headers.projection`; gap `headers.duplicate_header` | 1.1 |
| `mime_version_missing` | generated | no `MIME-Version` at all (not a gap) | `headers.projection`, `document.axes` | 1.1 |
| `leading_utf8_bom` | raw | a UTF-8 BOM at byte 0 (tolerated as a prelude) | gap `headers.leading_bom` | 1.1 |
| `mbox_from_line_at_zero` | raw | an mbox `From ` envelope line at byte 0 | gap `headers.mbox_from_line` | 1.1 |
| `lone_cr_in_header_region` | raw | a lone CR as a line terminator in the header region | gap `body.lone_cr_line_terminator` | 1.1 |
| `header_line_over_998_bytes` | raw | one header line longer than 998 bytes | `headers.projection` (recorded, no id) | 1.1 |
| `nul_in_header_value` | raw | a NUL in a header value (one field, `ok`) | `headers.projection` | 1.1 |
| `nul_in_header_name` | raw | a NUL in a field name (unknown paragraph) | gap `headers.malformed_line` | 1.1 |
| `header_8bit_raw_bytes` | raw | 8-bit bytes in header values (lossless latin-1 view) | `headers.projection` | 1.1 |
| `mixed_case_header_and_param_names` | generated | mixed-case field and parameter names | `headers.projection`, `headers.parameters` | 1.1 |
| `encoded_word_valid` | generated | one valid encoded word | `headers.decoded` | 1.1 |
| `encoded_word_invalid` | raw | a B-word with wrong padding / a Q-word with a stray `=` | gap `headers.encoded_word_invalid` | 1.1 |
| `encoded_word_mixed_charsets` | generated | two adjacent encoded words, different charsets (no join) | `headers.decoded` | 1.1 |
| `encoded_word_split_across_fold` | generated | one multibyte char split across two encoded words over a fold | `headers.decoded` | 1.1 |
| `rfc2231_segment0_charset` | generated | a charset carried on segment 0 only | `headers.parameters` | 1.1 |
| `rfc2231_continuations` | generated | numbered continuations (`name*0*`, `name*1`) reassembled by index | `headers.parameters` | 1.1 |
| `rfc2231_empty_charset_fallback` | generated | `filename*=''...` (an empty charset) as a recorded fallback | `headers.parameters`, `attach.filename` | 1.1 |
| `date_stated_zone` | generated | a stated zone (`+0000`) | `headers.date` | 1.3 |
| `date_minus_zero` | generated | `-0000` (never read as `+0000`) | `headers.date` | 1.3 |
| `date_absent` | generated | no `Date` header | `headers.date`; gap `headers.no_date` | 1.3 |
| `date_invalid` | raw | an invalid date (never repaired) | `headers.date`; gap `headers.invalid_date` | 1.3 |
| `date_offset_out_of_range` | raw | an offset outside +/-9959 | `headers.date` | 1.3 |
| `address_group` | generated | a group with members | `headers.addresses` | 1.2 |
| `address_undisclosed_recipients` | generated | `undisclosed-recipients:;` (a zero-member group) | `headers.addresses` | 1.2 |
| `address_unparsable` | raw | an unparseable address (raw kept beside it) | `headers.addresses`; gap `headers.address_unparsable` | 1.2 |
| `address_quoted_comma_display_name` | generated | a quoted display name containing a comma | `headers.addresses` | 1.2 |
| `address_idn_domain` | generated | an IDN domain kept verbatim (never IDNA-normalised) | `headers.addresses` | 1.2 |
| `address_smtputf8_local_part` | generated | an SMTPUTF8 local part kept verbatim | `headers.addresses` | 1.2 |

**30 pairs** (the ceiling). The three gap ids `headers.duplicate_header`, `headers.leading_bom`,
`headers.mbox_from_line` and `body.lone_cr_line_terminator` are first emitted in Turn 1.1 and each has a
mutation case here (a duplicate `Content-Type` for the first, a BOM with no field after it, `From ` with
no colon, a CR-only header split).

## Family B: body and HTML (Turn 1.0c, commit 2)

| fixture | dir | what it exercises (one thing) | Phase 1 facts / gap ids | turn |
|---|---|---|---|---|
| `body_plain_multipart_baseline` | generated | a plain multipart/alternative body (text projection) | `body.text`, `body.alternative_group` | 1.4-1.5 |
| `plain_effectively_empty` | generated | a real HTML body next to an effectively-empty plain alternative | `body.plain_effectively_empty`, `body.selection` | 1.5 |
| `nested_alternative_in_related_in_mixed` | generated | nested multipart alternative/related/mixed and the selection rule | `body.alternative_group`, `body.selection` | 1.5 |
| `content_location_in_related` | generated | `Content-Location` in a related part (recorded, never fetched) | `body.html_spans`, gap `security.remote_content_present` | 1.5 |
| `text_calendar_alternative` | generated | a `text/calendar` alternative beside plain and html (a view, not an attachment) | `body.alternative_group`, `body.selection` | 1.5 |
| `html_style_and_script` | generated | an HTML body with `<style>` and `<script>` (dropped from the projection) | `body.html_spans` | 1.5 |
| `html_href_img_remote_and_cid` | generated | `<a href>`, an `<img src>` remote and a `cid:` `<img>` | `body.html_spans`, `body.cid_refs`, gap `security.remote_content_present` | 1.5 |
| `html_data_uri_and_tracking_pixel` | generated | a `data:` URI and a 1x1 remote tracking pixel | `body.html_spans`, gap `body.inline_data_uri` | 1.5 |
| `base64_with_whitespace_and_bad_padding` | raw | base64 with embedded whitespace and wrong padding | `body.text`; gap `body.decode_fallback_used` | 1.4 |
| `qp_raw_8bit` | raw | raw 8-bit bytes in a quoted-printable body | `body.text` | 1.4 |
| `iso_2022_jp_stateful` | raw | `iso-2022-jp` (stateful: no offset map) | `body.text` (`multibyte_without_offset_map`) | 1.4 |
| `gb2312_declared_gbk_bytes` | raw | `gb2312` declared with `gbk` bytes (a lower rung) | `body.text`; gap `body.decode_fallback_used` | 1.4 |
| `windows_1252_declared_iso_8859_1` | raw | `windows-1252` bytes declared `iso-8859-1` (C1 bytes) | `body.text` | 1.4 |
| `boundary_with_tspecials` | generated | a boundary parameter with tspecials or quotes | `part.tree`, `headers.parameters` | 1.4 |
| `multipart_with_cte` | generated | a multipart with a `Content-Transfer-Encoding` (a claim, never decoded) | `part.tree`, `decode.chain` | 1.4 |
| `multipart_signed` | generated | a `multipart/signed` (the signature part never repaired) | `part.tree` | 1.4 |
| `multipart_digest_content_type_less_child` | generated | a `multipart/digest` child with no `Content-Type` | gap `body.digest_default_not_applied` | 1.5 |
| `flowed_unstuffed_soft_break` | generated | `format=flowed` space-unstuffing (the join deferred) | `body.text`; gap `body.flowed_reflow_unresolved` | 1.4 |
| `preamble_only_message` | raw | a preamble that is the whole message | gap `body.preamble_bytes` | 1.4 |
| `body_no_text_part` | generated | a message with no part that reads as text | gap `body.no_text_part` | 1.5 |
| `inline_interleaved_reply_body` | generated | a non-contiguous, interleaved reply (bottom-posting) | `body.quote_boundaries`, `body.view_levels` | 1.6 |
| `text_part_with_body_parts_tree` | generated | a `message/rfc822` body part (recorded, not recursed) | `part.tree`, `document.axes` (`children` not built) | 1.5 |

*(This family is deliberately smaller than the 30-pair ceiling; the quote-shaped cases live in the quote
catalogue, not here, so a body fixture is never a back-door quote label.)*

## Family C: attachments and caps (Turn 1.0c, commit 3)

| fixture | dir | what it exercises (one thing) | Phase 1 facts / gap ids | turn |
|---|---|---|---|---|
| `attach_manifest_baseline` | generated | a manifest over a pdf + png pair (identity, occurrence, classification) | `attach.manifest`, `attach.types` | 1.8 |
| `attach_inline_referenced` | generated | an inline part referenced by `cid:` in the HTML | `attach.cid_use`, `body.cid_refs` | 1.8 |
| `attach_inline_unreferenced` | generated | an inline part no `cid:` mentions | `attach.cid_use`; gap `attach.cid_unreferenced` | 1.8 |
| `attach_cid_dangling` | generated | a `cid:` reference with no matching part | `body.cid_refs`; gap `attach.cid_dangling` | 1.8 |
| `attach_duplicate_content_id` | generated | the same `Content-ID` on two parts | gap `attach.duplicate_content_id` | 1.8 |
| `attach_duplicate_filename_in_one_message` | generated | two occurrences with the same filename in one message | `attach.manifest`; gap `attach.occurrence_repeated` | 1.8 |
| `attach_message_rfc822_no_filename` | generated | a `message/rfc822` attachment with no filename | `attach.manifest`; gap `attach.filename_absent` | 1.8 |
| `attach_zip_magic_declared_disagree` | generated | a zip whose magic and declared type disagree (winner `magic`) | `attach.types`; gap `attach.type_disagreement` | 1.8 |
| `attach_unrecognized_magic` | raw | a part with an unrecognized magic and a declared MIME | `attach.types` (`VALUE("unrecognized")`) | 1.8 |
| `attach_zero_length_part` | generated | a zero-length attachment | `attach.manifest`, `attach.types` | 1.8 |
| `attach_disposition_size_and_date` | generated | `Content-Disposition` `size` and `date` (recorded, never trusted) | `attach.manifest`, `headers.parameters` | 1.8 |
| `attach_filename_rfc2231_fallback` | generated | a `filename*=` with an empty charset (fallback) | `attach.filename` | 1.8 |
| `attach_decoration_tracking_pixel` | generated | an inline unreferenced 1x1 png | `attach.decorative`; gap `attach.cid_unreferenced` | 1.8 |
| `attach_ole_cfb_magic` | raw | an OLE-CFB attachment | `attach.types`; gap `attach.ole_container_unknown` | 1.8 |
| `attach_tnef_winmail` | raw | a `winmail.dat` TNEF attachment | `attach.types`; gap `attach.tnef_present` | 1.8 |
| `attach_macro_docm` | raw | a macro-bearing `.docm` (inert) | `attach.manifest`; gap `security.macro_present` | 1.8 |
| `cap_deep_nesting` | generated | nesting far deeper than the depth cap (tiny bytes) | `document.axes`; status `skipped(depth_cap)` | 1.0d/1.8 |
| `cap_large_part_count` | generated | a part count far over the cap (tiny bytes) | status `skipped` + the new part-count reason | 1.0d/1.8 |
| `cap_enormous_header_block` | generated | a header block far over the header-bytes cap | status `skipped` + the new header-bytes reason | 1.0d/1.8 |
| `cap_encoded_word_bomb` | raw | a nested encoded-word bomb | `headers.decoded`; the work budget holds | 1.0d |
| `cap_very_long_base64_run` | raw | a very long base64 run (tiny source bytes) | `body.text`; the work budget holds | 1.0d |
| `attach_remote_image_only` | generated | an HTML part whose only image is remote | gap `security.remote_content_present` | 1.8 |

**22 pairs.** The five cap fixtures are the **hostile set**; each is recorded at the caps with a
work-per-input-byte budget asserted non-superlinear (never absolute seconds, single-threaded stated), and
the socket guard fails loudly if anything tries to fetch (exit criteria).

## The quote catalogue (typed after Turn 1.5; owner-reviewed before any quote rule)

**Not typed in Turn 1.0c.** Each row is reviewed by the owner (minutes per row: does the marked line or
element look like the boundary in the bytes; is the **kind** right; is any **new** text at level >= 1).
The review columns are filled in **after Turn 1.5**, so the four expectation cells read "typed after 1.5"
here. The catalogue is typed as its own small increment (<= 3 tests) and the agent that writes the rules
does not see the labels it typed.

| fixture | consuming turn | the raw line or element the fact hinges on | expected (rule_id, kind, ordinal) and level | why (typed after 1.5) |
|---|---|---|---|---|
| `quoted_outlook_flat` | 1.6 | the English `From:`/`Sent:`/`To:`/`Subject:` flat block after the new text | `outlook_flat_en`, quote, ordinal 1; plain level 1 | decision 3: a maximal run of >= 2 adjacent labels from one language's set, in canonical order as a subsequence |
| `quoted_prefix_gt_deep` | 1.6 | `> level one` / `>> level two` / `>>> level three` | `gt_family`, quote, ordinal 1; plain level 3 (deepest prefix depth) | decision 3: the `>`-family alphabet counted on decoded text; per-line prefix depth [1, 2, 3] |
| `inline_reply_interleaved` | 1.6 | `> first question` then `> second question`, new text between | `gt_family`, quote, ordinals 1 and 2; plain level 2; gap `body.inline_reply_interleaved` | decision 3: only a non-contiguous alternation is that gap; non-contiguous views are legal |
| `html_only` | 1.5 | `&lt;p&gt;Hello Ben. No quoting here at all.&lt;/p&gt;` | no boundary (control): no quote rule may fire | a bare `p` is not a quote container |
| `html_gmail_quote` | 1.7 | `div class="gmail_quote"` on the container and on the nested `blockquote` | plain `on_wrote_en` quote 1 (level 1); html `gmail_quote` quote 1 (level 1) | decision 3: `gmail_quote` on a `div` or a `blockquote`; the attribution wrapper adds no second ordinal |
| `html_outlook_divrplyfwd` | 1.7 | `id="divRplyFwdMsg"` | plain `outlook_flat_en` quote 1; html `outlook_divrplyfwd` quote 1 (each level 1) | decision 3: the Outlook `divRplyFwdMsg` container (kind quote) and the flat block |
| `no_boundary_found` | 1.5 | `No quoting anywhere in this message.` | no boundary (control): no quote rule fires; gap `body.no_boundary_found` | decision 3 amendment: the absence answer, not inferred from silence |
| `i18n_reply_marker` | 1.6 | `Am 4. Marz 2025 schrieb Ada Sender:` then a `Name:`/`Datum:`/`Betreff:` run | no quote rule; gap `body.i18n_reply_marker` | decision 3: a label-shaped unknown-language block, never `no_boundary_found` |
| `forwarded_inline_marker` | 1.6 | `Begin forwarded message:` plus a From/Date/Subject block | `forward_banner`, forward, ordinal 0; plain level 0 | owner decision 15: a forward reads as level 0 and an inline forward is never the sender's quoted words |
| `headers_only` | 1.5 | the whole header block (blank line, empty body) | no boundary (control): no quote rule may fire | no body content; a headers-only message is a legal state |
| `gmail_reply_quoting_outlook_authored` | 1.7 | Gmail `div.gmail_quote` + `blockquote` + `divRplyFwdMsg` in the HTML; in the plain alternative an `On ... wrote:` line, Outlook `From:`/`Sent:` blocks and a forward banner, **no `>` prefix at all** | plain `on_wrote_en` quote 1, `outlook_flat_en` quote 2, `forward_banner` forward 0 (level 2); html `gmail_quote` quote 1 (level 1) | design D3: the plain view's all-zero `>` depth beside fired structural rules is a normal state; mixed origin keeps one ordinal per view |
| `gmail_short_reply_gt_and_on_wrote` | 1.6 | both `>` prefixes (`>>`) and an `On ... wrote:` line in the plain part | plain `on_wrote_en` quote 1 and `gt_family` quote 2 (level 2); html `gmail_quote` quote 1 | decision 2: `view.quote_level_disagreement` is recorded (the two families' ranks differ: `>>` depth 2 beside ordinal 1); recorded, never averaged |
| `mixed_origin_quote` | 1.7 | a Gmail container wrapping an Outlook block (one ordinal per view) | plain `on_wrote_en` quote 1; html `gmail_quote` quote 1; gap `body.mixed_origin_quoting` | design D3: boundaries of mixed origin keep one ordinal sequence per view with a per-boundary rule id |
| `outlook_labels_de` | 1.6 | `Von:`/`Gesendet:`/`An:`/`Betreff:` run | `outlook_flat_de`, quote, ordinal 1; plain level 1 | decision 3: the German set, the date slot accepting `Gesendet`/`Datum`, the language per block |
| `outlook_labels_fr` | 1.6 | `De :`/`Envoyé :`/`À :`/`Objet :` run (NBSP before `:`) | `outlook_flat_fr`, quote, ordinal 1; plain level 1 | decision 3: the French set, separators accepting a whitespace run before `:` including U+00A0 after NFC |
| `unknown_language_label_block` | 1.6 | a header-like run of short `Label:` lines after a boundary-looking line | no quote rule; gap `body.i18n_reply_marker` | decision 3: a label-shaped unknown-language block, never `no_boundary_found` |
| `gmail_quote_on_blockquote` | 1.7 | `class="gmail_quote"` on a `blockquote` | plain `on_wrote_en` quote 1; html `gmail_quote` quote 1 | decision 3: `gmail_quote` fires on a `blockquote` too |
| `outlook_com_appendonsend` | 1.7 | `#appendonsend` / `#x_appendonsend` | plain `on_wrote_en` quote 1; html `outlook_appendonsend` quote 1 | decision 3: `#appendonsend` with the `x_` prefix Outlook adds on rewrite |
| `thunderbird_moz_cite_prefix` | 1.7 | `div.moz-cite-prefix` | plain `on_wrote_en` quote 1; html `thunderbird_moz_cite_prefix` quote 1 | decision 3: the `moz-cite-prefix` rule (the following bare `blockquote` has no `type=cite`) |
| `thunderbird_moz_forward_container` | 1.7 | `div.moz-forward-container` | plain `forward_banner` forward 0; html `thunderbird_moz_forward_container` forward 0 (each level 0) | decision 3 + owner decision 15: a forward container reads as level 0 |
| `begin_forwarded_message` | 1.6 | `Begin forwarded message:` plus a From/Date/Subject block | `forward_banner` forward 0 and `outlook_flat_en` quote 1; plain level 1 | decision 3 + 15; the flat block under the banner also fires (open question 4) |
| `original_message_dashes` | 1.6 | `-----Original Message-----` | `original_message_dashes`, forward, ordinal 0; plain level 0 | decision 3 groups it with the Begin-forwarded banner (open question 5) |
| `signature_dash_dash_space` | 1.6 | the `-- ` line (exactly dash dash space) | `dash_dash_space`, signature, ordinal 0; plain level 0 | decision 3 / RFC 3676 4.3: a candidate only, never stripped |
| `list_footer_underscores` | 1.6 | a line of at least 30 `_` and the "You received this message because you are subscribed" sentence | `list_footer_underscores` list_footer 0 and `list_footer_subscribed` list_footer 0; plain level 0 | decision 3: list footers are detection-only candidates |
| `bottom_posted_reply` | 1.6 | a quoted-first message with a later level-0 span (**legal, not a gap**) | `gt_family`, quote, ordinal 1; plain level 1 | decision 3: bottom-posting is legal, not a gap (only a non-contiguous alternation is one) |
| `vendor_prefix_class_no_table_row` | 1.7 | a class matching a known vendor prefix with no table row | plain `on_wrote_en` quote 1; html no quote rule; gap `body.html_quote_rule_gap` (expected but not asserted: the tree records it only for an unclosed container -- see the review document, open question 6) | decision 3: a vendor-prefix class with no table row is a gap, never `no_boundary_found` |

| `on_wrote_hard_wrapped` | 1.6 | a hard-wrapped `On ... wrote:` attribution: two physical lines (fires) and a second three-line attribution (must NOT fire) | plain `on_wrote_en` quote 1 (level 2) spanning the two-line attribution and its quoted line; `gt_family` quote 2 for the three-line window's `>` line | the plan debate (section 3): the `N = 2` window joins two physical lines and never three |
| `flowed_quote_depth` | 1.6 | a `format=flowed` part: two `>`-prefixed lines with a stuffed space after the `>` run and soft-break trailing spaces | `gt_family` quote 1, per-line depths [1, 1] (level 1); gap `body.flowed_reflow_unresolved` | decision 2/3: depth is per PHYSICAL line on the unjoined `body.text`; the soft-break join is deferred |
| `gt_spacing_variants` | 1.6 | `> a`, `>> b`, `> > c`, `>` TAB `> d`, `>>> e`, and a U+00A0 separator line | `gt_family` quote 1, per-line depths [1, 2, 2, 2, 3, 1] (level 3) | decision 3: a `>`-family prefix is a run of `>` separated by SP or TAB only; U+00A0 is not a separator |

**(29 rows; approximately 15-20 of them carry a real quote boundary, the rest are the controls.)**

**NOT v1 (decision 13).** These two rows are **deliberately not in the catalogue** until the owner
confirms them from a structure-only probe of their own mail (class and id names, never content). Neither
is a rule in v1; both raise `body.html_quote_rule_gap` meanwhile.

| fixture | status | notes |
|---|---|---|
| `apple_attribution` | **NOT v1** | the Apple attribution shape (`On 3 Jun 2024, at 10:12, X <a@b> wrote:`) is the least-trusted row and is not named in the design; it raises `body.html_quote_rule_gap` |
| `yahoo_quoted` | **NOT v1** | Yahoo `div.yahoo_quoted` and `----- Original Message -----` are not confirmed from a probe; they raise `body.html_quote_rule_gap` |

## Turn 1.12: the header-less part (RFC 2045 5.2)

The reviewer found, installing the published `0.1.0rc1` into a clean venv, that a part with **no**
`Content-Type` got no quote analysis. RFC 2045 section 5.2 makes such a part `text/plain;
charset=us-ascii`; RFC 2046 section 5.1.5 makes a `multipart/digest` child `message/rfc822`. These
seven fixtures pin both defaults and the stages that read them.

| fixture | how | what it labels | turn |
|---|---|---|---|
| `headerless_plain_on_wrote` | generated | the reproduction: no `Content-Type`, an `On ... wrote:` attribution and a `>` block | `body.quote_boundaries`, `body.view_levels`, `body.text`, `body.selection` | 1.12 |
| `headerless_plain_gt_only` | generated | no `Content-Type`, a bare `>` run with no attribution | `body.quote_boundaries` (gt_family), `body.view_levels`, `body.text`, `body.selection` | 1.12 |
| `headerless_plain_mime_version_only` | generated | the reproduction with `MIME-Version: 1.0` alone (no `Content-Type`) | the same facts as `headerless_plain_on_wrote` | 1.12 |
| `headerless_alternative_text_part` | generated | a `multipart/alternative` whose text child declares no `Content-Type` | `body.alternative_group`, `body.selection`, `body.quote_boundaries` | 1.12 |
| `headerless_mixed_text_and_attachment` | generated | a header-less inline text body beside a `Content-Type`-less disposition-attachment | `body.selection`, `attach.manifest`, `attach.types` | 1.12 |
| `headerless_digest_child` | generated | a `multipart/digest` child with no `Content-Type` (the recorded walker/RFC disagreement) | gap `body.digest_default_not_applied`, `attach.manifest`; `body.text`/`body.quote_boundaries`/`body.view_levels` undetermined | 1.12 |
| `headerless_plain_8bit` | generated | no `Content-Type` with 8-bit non-ASCII bytes (the decode-chain outcome) | `decode.chain`, `body.selection`; `body.text`/quote facts undetermined | 1.12 |

## Census: the fixture set is a superset of the design's Phase 1 list

The design (`docs/design/email-extraction-design.md`, "Phasing", the **Phase 1** paragraph) names ten
fixtures. All ten are rows of the **quote catalogue** above (the design groups them together; four of
them -- `html_only`, `no_boundary_found`, `headers_only` and the two "no quote" controls -- are the
fixtures whose bodies the quote rules must leave alone). The union of the three 1.0c families and the
quote catalogue is therefore a **superset** of the design's list.

**How a test checks it** (`tests/test_fixture_census.py`, Turn 1.0c): it parses the backticked names out
of the design's Phase 1 "Fixtures:" paragraph (the single line after "**Phase 1:**" in "Phasing"), and for
each name asserts **both**

- a row exists for it in **this document** (the catalogue, either family table or the quote catalogue); and
- once the fixtures exist, a committed `.eml` with that stem exists under `fixtures/**` and has a sidecar.

So a design fixture silently dropped from the catalogue, or a catalogue row with no fixture, fails the
test by name. The census is deliberately one-directional (the design's list is the floor, not the
ceiling): the corpus may add fixtures the design never named, and it does -- the twenty-plus rows above
that the debate's topic 6 added.

## Topic-6 coverage: every item the debate's topic 6 lists

The debate's "what the draft missed entirely" (section 6) enumerates items the fixture set must carry.
Each is a row above:

| topic-6 item | fixture |
|---|---|
| nested multipart alternative / related / mixed | `nested_alternative_in_related_in_mixed` |
| `Content-Location` in related (recorded, never fetched) | `content_location_in_related` |
| missing and duplicate `MIME-Version` | `mime_version_missing`, `duplicate_header_mime_version` |
| 8-bit raw bytes in header values | `header_8bit_raw_bytes` |
| base64 with embedded whitespace and wrong padding | `base64_with_whitespace_and_bad_padding` |
| QP raw 8-bit | `qp_raw_8bit` |
| `iso-2022-jp` (stateful) | `iso_2022_jp_stateful` |
| `gb2312` declared with `gbk` bytes | `gb2312_declared_gbk_bytes` |
| `windows-1252` declared `iso-8859-1` | `windows_1252_declared_iso_8859_1` |
| RFC 2231 charset on segment 0 only, and continuations | `rfc2231_segment0_charset`, `rfc2231_continuations` |
| a multibyte character split across two encoded words | `encoded_word_split_across_fold` |
| `Content-Disposition` `size` and `date` | `attach_disposition_size_and_date` |
| the same `Content-ID` twice | `attach_duplicate_content_id` |
| `text/calendar` alternative beside plain and html | `text_calendar_alternative` |
| mixed-case header and parameter names | `mixed_case_header_and_param_names` |
| a boundary with tspecials or quotes | `boundary_with_tspecials` |
| a multipart with a `Content-Transfer-Encoding` | `multipart_with_cte` |
| `multipart/signed` | `multipart_signed` |
| `multipart/digest` with a Content-Type-less child | `multipart_digest_content_type_less_child` |
| a leading UTF-8 BOM | `leading_utf8_bom` |
| an mbox `From ` line at byte 0 | `mbox_from_line_at_zero` |
| a lone CR | `lone_cr_in_header_region` |
| a duplicate header | `duplicate_content_type_header` (and `duplicate_header_mime_version`) |
| a header line over 998 bytes | `header_line_over_998_bytes` |
| a NUL in a value | `nul_in_header_value` (and `nul_in_header_name` for a name) |
| Date: `-0000` / missing / invalid / a stated zone / an out-of-range offset | `date_minus_zero`, `date_absent`, `date_invalid`, `date_stated_zone`, `date_offset_out_of_range` |
| address: a group / `undisclosed-recipients:;` / unparseable / a quoted comma display name / an IDN domain / an SMTPUTF8 local part | `address_group`, `address_undisclosed_recipients`, `address_unparsable`, `address_quoted_comma_display_name`, `address_idn_domain`, `address_smtputf8_local_part` |
| encoded words: valid / invalid / mixed charsets / split across a fold | `encoded_word_valid`, `encoded_word_invalid`, `encoded_word_mixed_charsets`, `encoded_word_split_across_fold` |
| attachments: inline referenced / inline unreferenced / dangling cid / a duplicate filename in one message / a `message/rfc822` with no filename / a zip whose magic and declared type disagree / an unrecognized magic / a zero-length part | `attach_inline_referenced`, `attach_inline_unreferenced`, `attach_cid_dangling`, `attach_duplicate_filename_in_one_message`, `attach_message_rfc822_no_filename`, `attach_zip_magic_declared_disagree`, `attach_unrecognized_magic`, `attach_zero_length_part` |
| structural caps: deep nesting / a very large part count / an enormous header block / an encoded-word bomb / a very long base64 run | `cap_deep_nesting`, `cap_large_part_count`, `cap_enormous_header_block`, `cap_encoded_word_bomb`, `cap_very_long_base64_run` |
| HTML with style and script / `<a href>` / `<img src>` remote and cid / a `data:` URI and a tracking pixel / a plain alternative that is effectively empty next to real HTML | `html_style_and_script`, `html_href_img_remote_and_cid`, `html_data_uri_and_tracking_pixel`, `plain_effectively_empty` |

Every item maps to at least one fixture above; a reviewer can walk this table against the family tables.

## Counts, and the coverage floors

| family | pairs | commit |
|---|---|---|
| headers / date / address | 30 | 1.0c-1 |
| body / HTML | 22 | 1.0c-2 |
| attachments / caps | 22 | 1.0c-3 |
| quote catalogue (typed after 1.5) | 29 | the quote increment |
| **total committed sidecars** | **103** | |

Every floor in `docs/design/phase1-facts.md` is met with room: the tightest are `document.axes` (floor
80, on every one of the ~100 sidecars), `headers.projection` and `body.text` (floor 60 each; every
message has headers and almost every one has a text part), and `body.plain_effectively_empty` (floor 2,
carried by `plain_effectively_empty` and `attach_remote_image_only`'s sibling case). The floor for each
fact and the observed count are checked by `tests/test_facts_coverage.py` (Turn 1.10); a fact that falls
below its floor fails, and a fact that moves its phase fails against the pinned ledger
(`docs/design/phase1-ledgers.md`).

> **Floors re-based after the quote increment (owner decision, Turn 1.0c review).** Family A, B and C carry
> far fewer sidecars per fact than the floors in `phase1-facts.md` assumed (e.g. `headers.projection` 12 of 60,
> `attach.types` 5 of 12, `attach.filename` 2 of 10): the floors were set before the catalogue. They are not
> loosened silently: when the quote catalogue lands, `tests/test_facts_coverage.py` (Turn 1.10) takes each fact's
> floor as the COUNT ACHIEVED by the committed corpus at that point (a ratchet: coverage may never fall), and
> `phase1-facts.md` is updated in the same commit with each fact's new floor and the reason. `document.axes` is 80
> in both documents. The attach.types winner rule: the winner is the first verdict in the order magic,
> declared_mime, container_introspection that yields a media-type family (`unrecognized` yields none), `null` if
> none does.
