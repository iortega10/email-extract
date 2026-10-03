# Turn 0.0 spike — measured facts

Two measurements, recorded before any contract freezes (spec: *Turn 0.0: measure
the stdlib*):

- **A — stdlib `email` + lxml**, `tools/email_spike.py`: hand-written byte
  strings only, no real mail. One row per measurement id, run on every
  interpreter present.
- **B — real `.msg` structure**, `tools/real_probe.py`: run against local samples outside the
  repository (in this session by hearth, which searched the owner's Downloads folder; the owner
  has confirmed these sample mails carry no confidentiality concern). Structure only: stream names/sizes, storage
  layout, property tags/types/sizes, counts, presence. **No content is read or
  printed** — no property values, no header text, no body bytes, no decoded
  filenames. Samples are described only by structure (S01–S11 below).

Environment: CPython **3.14.3** (default `python`) and CPython **3.11.15**
(uv Astral build) for A; CPython 3.14.3 + olefile **0.47** for B. `olefile` is
imported by `real_probe.py` only. lxml is installed under 3.14.3 only.

Reproduce:

```
python tools/email_spike.py            # section A, every id; > file to record
python tools/email_spike.py --list     # ids and questions
py -V:Astral/CPython3.11.15 tools/email_spike.py
python tools/real_probe.py <path-outside-repo>   # section B; refuses in-repo paths
```

`real_probe.py` exit codes: `0` ok, `2` usage/refused/nonexistent path,
`3` olefile missing, `4` not an OLE file. Both tools print structure only;
`real_probe.py` reconfigures stdout to UTF-8. It prints the probed file's path in its header; that is acceptable for these samples and is not content.

Run summary: A on 3.14.3 → `measured=24 not_measurable=1 spike_error=0`;
A on 3.11.15 → `measured=21 not_measurable=4 spike_error=0` (three of the four
are the lxml rows — lxml absent under 3.11 — the fourth is g01 by design).
Every jointly measurable row is **byte-identical between the two
interpreters** (diff: interpreter banner + the lxml rows only).

---

## A. stdlib `email` + lxml — per-id table

Status per interpreter: **M** = measured, **N** = not measurable here (reason).

| id | measurement | 3.14.3 | 3.11.15 | observation (measured) |
|----|-------------|--------|---------|------------------------|
| a01 | obs-fold unfolding | M | M | `get()` returns one unfolded field with the fold collapsed to two spaces; `raw_items` keeps the original `CRLF + 2sp` text; `defects = []`; `keys()` shows the field exactly once. `str(m)` shows the header block re-serialized with `\n` (not the input bytes). |
| a02 | duplicate headers, order | M | M | three `Received` kept in order via `get_all()`; header order preserved (`Received ×3`, then `Subject`); `defects = []`. |
| a03 | non-`name: value` header line | M | M | the bad line and everything after it fall into the payload; the `Subject` after it is **not** readable (`None`); `MissingHeaderBodySeparatorDefect()` recorded; no warnings. |
| a04 | message with no blank line | M | M | both headers parsed; `get_payload() = ''`; `is_multipart() = False`; **`defects = []`** — stdlib silently accepts headers-to-EOF. |
| a05 | `Date: -0000` vs `+0000` | M | M | public `parsedate_tz` returns the identical tuple (tz slot `0`) for `-0000`, `+0000`, `GMT` and no-zone, while **`parsedate_to_datetime('-0000')` is naive** (`tzinfo=None`, `utcoffset=None`) and `+0000`/`GMT` are aware UTC; the internal `_parsedate_tz('-0000')[-1]` is `None` (public `parsedate_tz` rewrites it to `0`) and `_parsedate_tz('+0000')[-1] = 0`. |
| a06 | `parseaddr`/`getaddresses`: group, IDN, SMTPUTF8, garbage | M | M | empty group → `getaddresses=[('', '')]`; group with members → members returned, group name dropped (`parseaddr('Team: ...')` = `('', '')`); IDN/unicode-domain/SMTPUTF8 local pass through verbatim; garbage → `('','just')` (first token); trailing comma → `getaddresses=[('','')]` **disagrees** with `parseaddr=('','a@example.com')`; unclosed `<a@b` → `('Name','a@example.com')`. |
| a07 | RFC 2047 encoded words | M | M | valid Q/B decode with `defects=[]`; folded pair joins to `onetwo`; **unknown charset, bad base64 and bad `%` escapes all decode silently** (`x-nope` passes through, bad base64 → `i<U+FFFD>`, bad escape stays `%ZZ`) with `defects = []`. |
| a08 | RFC 2231 `filename*` continuations | M | M | continuations joined (`part one and two.txt`); percent-encoded charset decoded (`naïve file.txt`); plain quoted and escaped-quote names correct; `defects = []`. |
| a09 | `Thread-Index` raw value | M | M | `get()` returns the unfolded value (fold point becomes spaces); `raw_items` keeps the original `CRLF + 2sp`; `decoded != raw`; `defects = []` — the verbatim value lives only in `raw_items`. |
| b01 | malformed MIME boundaries | M | M | missing close delimiter → `CloseBoundaryNotFoundDefect()`, still `is_multipart=True`, 2 parts, second part clean; wrong start → `StartBoundaryNotFoundDefect()` + `MultipartInvariantViolationDefect()`, `is_multipart=False`, payload stays a `str`. |
| b02 | truncated/invalid base64 | M | M | truncated padding → `InvalidBase64PaddingDefect()` yet `decode=True` returns `b'ABCD'`; invalid chars → `InvalidBase64LengthDefect()` yet `decode=True` returns the still-encoded source bytes `b'QUJ$RA=='` — **defects and returned bytes disagree**; decode is best-effort either way. |
| b03 | bad/missing charset | M | M | unknown declared charset `x-no-such-charset`: `decode=True` fine, but **`get_content()` raises `LookupError`** with `defects=[]`; invalid UTF-8 bytes: `decode=True` returns raw bytes, `get_content()` returns U+FFFD replacements with `defects=[]`. |
| c01 | raw header byte-offset API | M | M | no `offset`/`position`/`span` attribute on `Message` or on header objects; only the `policy.header_source_parse` hook exists (input-side, reports no positions); headers are `email.headerregistry` typed objects. |
| c02 | `as_bytes()` round-trip | M | M | LF-only input round-trips byte-identical; **CRLF input never does** (serialization uses `\n`; lengths shrink: 33→29, 50→45 …); obs-fold, trailing header whitespace, duplicate headers and the no-colon line all differ from input; the no-colon line gains an extra blank line. |
| c03 | `preamble` / `epilogue` | M | M | with content: `preamble='this is the preamble'` (str), `epilogue='this is the epilogue\r\n'`; without: `preamble=None`, `epilogue=''`. |
| c04 | raw bytes between boundaries | M | M | no API yields a part byte span; delimiter trailing whitespace is lost by `as_bytes()`; `part.as_bytes() != raw slice`; `raw.find()` gives only a search heuristic (103), not a parser-reported offset. |
| d01 | QP: stray `=`, soft break | M | M | stray `=zz` passes through (`b'a=zz b'`), soft break joins (`line1line2`), trailing `=` at EOF stripped (`end`), valid QP decodes to UTF-8 bytes — **no defects raised for any of them**. |
| d02 | `iso-8859-1` quoted-printable | M | M | `decode=True` → `b'Caf\xe9 na\xefve\r\n'`; `get_content()` → `'Café naïve\r\n'`; `defects=[]`. |
| d03 | unknown declared CTE | M | M | `x-unknown`: `decode=True` returns the raw payload bytes, `get_content()` returns the raw text, `charset=None`, **`defects=[]`** — the fallback is silent. |
| e01 | `message/rfc822`, no filename | M | M | `iter_attachments` yields it (`filename=None`, `disposition='inline'`); it counts as 1 attachment; `iter_parts` and `walk` show the full tree. |
| e02 | `text/calendar` in alternative next to `.ics` attachment | M | M | `.ics` with `Content-ID` appears as the attachment (`application/octet-stream`, cid preserved); the alternative's `text/calendar` does **not** leak into `iter_attachments`; `walk` shows `multipart/alternative` → `text/plain`, `text/calendar`, then the attachment. |
| f01 | lxml: Gmail quote block | M | N | 3.14.3: `blockquote.gmail_quote[type=cite]` found; `<style>`/`<script>` appear as elements and **`text_content()` includes their text** (extraction must drop them); `error_log` empty for both the valid and the broken variant. 3.11.15: lxml not installed. |
| f02 | lxml: Outlook `divRplyFwdMsg` | M | N | `divRplyFwdMsg` found via xpath (1), inner `MsoNormal` present, unclosed `<font>` reported as `error_log = [('ERROR', 'Opening and ending tag mismatch: body and font')]`; `text_content()` still returns the text despite the error. 3.11.15: lxml not installed. |
| f03 | lxml: `blockquote type=cite` nesting | M | N | two nested blockquotes, `type=cite` preserved, second's parent is the first; `error_log=[]`. 3.11.15: lxml not installed. |
| g01 | `.msg` structure | N | N | by design not measurable in this script: run `tools/real_probe.py <path-to-.msg>` on a local sample outside the repo — see section B. |

### A. stdlib vs the design — disagreements and named fallbacks (Open risk 4)

| stdlib behavior (id) | design assumption | fallback named here |
|----------------------|-------------------|---------------------|
| no byte-offset API anywhere (c01, c04); `as_bytes()` never byte-identical for CRLF input (c02) | D2: raw byte spans per header field and part | stands as designed: the walker's own raw-header scanner over the raw container bytes; stdlib is never re-serialized to recover spans |
| no-blank-line message carries no defect (a04); unknown CTE and stray-QP fallbacks are silent (d03, d01); bad-charset paths raise `LookupError` or emit replacements with no defect (b03) | `msg.defects` detects malformed input | defects are advisory only; the decode chain records `declared_cte/used_cte/fallback_fired` itself and guards `get_content()` with try/except |
| b64 defects and `decode=True` disagree (b02) | decoded payload trustworthy when no defect | decode result never trusted on its own; byte-accurate source kept, defect recorded as a signal not a verdict |
| `parsedate_to_datetime('-0000')` is naive (a05) | `Date` maps to `TimeEvent.when_utc` | naive datetime never becomes `when_utc`; `when_utc = unknown(reason=no_utc_offset)`; the `parsedate_tz` tuple is the source |
| `parseaddr`/`getaddresses` disagree on garbage and trailing commas (a06); invalid RFC 2047 words decode silently (a07) | address/subject decoding | `getaddresses` is primary, raw header text (`raw_items`) is kept for verbatim citation; invalid encoded-words are treated as best-effort decode + raw record |
| `<style>`/`<script>` text leaks into `text_content()` (f01) | HTML→text body | the HTMLTEXT step strips `style`/`script` elements before text extraction |

No other stdlib/design disagreement was found in this turn. Rows a01, a02, a08,
a09, b01, c03, d02, e01, e02 confirm the design's assumptions as stated.

---

## B. real `.msg` structure — measured facts

### B0. Protocol

`tools/real_probe.py <path>` opens one OLE/CFB file with `olefile`, walks the
directory, and prints: stream/storage names and sizes, counts, the body /
transport-header presence, the string-property type census, per-table property
**tags and types only** (fixed vs stream-backed vs storage-backed, sizes), the
code-page/flag presence lines, and the observed `tag:type` set. It refuses any
path inside the repository (`is_relative_to` check → exit 2), never opens a
stream for reading except `__properties_version1.0` tables (whose content is
structural: tag words, sizes, counts — values are not interpreted), and prints
no message content anywhere.

Eleven local `.msg` samples were probed, all OLE/CFB. Samples are identified
only by structure:

| id | bytes | streams | recip storages (top-level) | attach storages (top-level) | embedded msg | body streams present | suffixed streams |
|----|------:|--------:|---------------------------:|----------------------------:|-------------:|----------------------|-----------------:|
| S01 | 196608 | 129 | 1 (1) | 0 (0) | 0 | `0x1013` | 4 |
| S02 | 155136 | 248 | 2 (1) | 1 (1) | 1 | `0x1013` | 4 |
| S03 | 444416 | 138 | 1 (1) | 1 (1) | 0 | `0x1013` | 4 |
| S04 | 96256 | 119 | 1 (1) | 0 (0) | 0 | `0x1013` | 0 |
| S05 | 68096 | 132 | 1 (1) | 0 (0) | 0 | `0x1013` | 4 |
| S06 | 109568 | 133 | 1 (1) | 0 (0) | 0 | `0x1013` | 5 |
| S07 | 96768 | 122 | 1 (1) | 0 (0) | 0 | `0x1013` | 0 |
| S08 | 70656 | 130 | 1 (1) | 0 (0) | 0 | `0x1013` | 0 |
| S09 | 70656 | 132 | 1 (1) | 0 (0) | 0 | `0x1000 + 0x1009` | 0 |
| S10 | 122880 | 132 | 1 (1) | 0 (0) | 0 | `0x1013` | 4 |
| S11 | 225792 | 128 | 1 (1) | 0 (0) | 0 | `0x1013` | 4 |

All 11 carry exactly one top-level recipient storage; S02 additionally has an
embedded message under its attachment which has its own recipient storage
(hence recip 2, top-level 1). S02 has one attachment storage containing the
embedded message; S03 has one attachment storage with file data.

### B1. Storage layout (measured)

- Root child is `Root Entry`; top-level children observed:
  `__properties_version1.0`, `__nameid_version1.0`, `__substg1.0_*`,
  `__recip_version1.0_#00000000`, `__attach_version1.0_#00000000`.
- Recipient/attachment storages are numbered `#%08X` (S02/S03 show `#00000000`).
- `__nameid_version1.0` holds three binary streams: `__substg1.0_00020102`,
  `__substg1.0_00030102`, `__substg1.0_00040102` (160/440/3090 B in S06).
- Data streams are named `__substg1.0_%04X%04X` (`tag:type`). A suffix
  `-NNNNNNNN` occurs for named-property and multi-valued layout (observed
  e.g. `__substg1.0_8005101F-00000000`); per-sample counts 0–5 (column in B0).
- Embedded message = a storage named `__substg1.0_3701000D` under an
  attachment (S02); it has its own `__properties_version1.0` and its own
  `__recip_version1.0_*` child. Observed nesting depth: top → attach →
  embedded → recip-in-embedded (4 levels).
- `PT_OBJECT` (`3701:000D`) = embedded-message storage; the same tag with
  `3701:0102` (`PT_BINARY`) = attachment file data. Both observed.

### B2. Property tables (measured, 26 tables across 11 samples)

- **Header size:** top-level `__properties_version1.0` = **32 B**; recipient,
  attachment and embedded-message tables = **8 B**. `(size − header)` is an
  exact multiple of 16 and equals the reported entry count for **26/26**
  tables (integer-fit holds only for these two header sizes).
- **Entry encoding:** first word `u32 = (tag << 16) | type` matches a known
  type in **2431/2432** entries. The single exception is one entry
  `tag=0x0000, type=PT_NULL(0x0001)` inside S02's embedded-message table.
- **Entry counts in the top-level header** (`@16` recipient count, `@20`
  attachment count) equal the directory-derived top-level counts in
  **11/11** samples (9× `1/0`, 2× `1/1`).
- **Variable entries (1456 total):** the size field is at `d0` (= stream size)
  in **1455**; `d1` in 0; one entry is storage-backed (`3701:000D`, size not
  applicable); 0 entries had a stream declared but absent. Fixed-size entries
  total 976 (data inline, no stream — consistent by construction and observed).
- Totals: 26 tables = 11 top-level + 12 recipient + 3 attachment/embedded-side
  tables (S02: attach + embedded + embedded-recip; S03: attach).

### B3. Observed property-tag set (`tag:type`, union over all 11 samples)

239 distinct `tag:type` pairs (236 appear as property-table entries; the three
exceptions `0002/0003/0004:0102` are the `__nameid_version1.0` binary streams,
recorded by the probe's tag-set section). This is an observation, not a
frozen contract — **no property tag is frozen by this document**.

```
0000:0001 0002:0102 0003:0102 0004:0102 0017:0003 001A:001F 0023:000B 0026:0003 0029:000B 002E:0003 0036:0003 0037:001F 0039:0040 003B:0102 003D:001F 003F:0102 0040:001F 0041:0102 0042:001F 0043:0102 0044:001F 004F:0102 0050:001F 0051:0102 0052:0102 0057:000B 0058:000B 0059:000B 0064:001F 0065:001F 0070:001F 0071:0102 0075:001F 0076:001F 0077:001F 0078:001F 007D:001F 0C06:000B 0C15:0003 0C19:0102 0C1A:001F 0C1D:0102 0C1E:001F 0C1F:001F 0C24:0102 0C2C:0102 0C2D:0102 0C2E:0102 0E02:001F 0E03:001F 0E04:001F 0E05:001F 0E06:0040 0E07:0003 0E0B:0102 0E0F:000B 0E17:0003 0E1B:000B 0E1D:001F 0E21:0003 0E23:0003 0E2F:0003 0E4B:0102 0E4C:0102 0E4D:0102 0E4E:0102 0E58:0102 0E59:0102 0ECD:000B 0F02:0040 0F03:0102 0F0A:0040 0FF4:0003 0FF6:0102 0FF7:0003 0FF9:0102 0FFE:0003 0FFF:0102 1000:001F 1009:0102 1013:0102 1015:001F 1016:0003 1035:001F 1039:001F 1042:001F 1045:001F 120B:0102 1213:0003 3000:0003 3001:001F 3002:001F 3003:001F 3007:0040 3008:0040 300B:0102 3013:0102 3014:0102 3016:000B 335B:0003 335E:0003 3389:0040 340D:0003 3645:000B 3655:000B 365A:0003 3663:0003 3668:0003 3677:0102 36FA:000B 3701:000D/0102 3703:001F 3704:001F 3705:0003 3707:001F 370B:0003 370E:001F 3712:001F 3714:0003 3900:0003 3905:0003 39FE:001F 3A0C:001F 3A20:001F 3A40:000B 3FD9:001F 3FDE:0003 3FF1:0003 3FF8:001F 3FFA:001F 3FFD:0003 4022:001F 4023:001F 4024:001F 4025:001F 4030:001F 4031:001F 4034:001F 4035:001F 4038:001F 4039:001F 4059:0003 405A:0003 4076:0003 5037:0003 50CF:0102 5110:0102 5111:0102 5114:000B 5D01:001F 5D02:001F 5D07:001F 5D08:001F 5D0A:001F 5D0B:001F 5D15:0102 5D16:0102 5FE5:001F 5FF7:0102 5FFD:0003 6200:0003 6201:0003 64F0:0102 65C6:0003 65E1:0102 65E2:0102 65E3:0102 66C3:0003 66CA:001F 6748:0014 67FE:0014 6827:0003 7082:0040 7097:0102 7FF6:001F 7FFE:000B 8000:0003 8001:000B/001F 8002:000B/001F/0048 8003:0003/000B/001F 8004:001F/0048 8005:0003/000B/0048/101F 8006:0003/001F/0048/0102 8007:0003/000B/0048/0102 8008:0003/000B/0048 8009:000B/0040/0048/0102 800A:0003/000B/0040/0102 800B:0003/000B/0040/0102 800C:000B/0040/0102 800D:000B/0040 800E:001F/0040/0102 800F:000B/001F/0040/0102 8010:000B/001F 8011:000B/001F/0040 8012:001F/0040 8013:001F/0040 8014:0003/001F 8015:001F 8016:001F 8017:001F 8018:001F 8019:0003/001F 801A:0003/000B/001F 801B:0003/000B/001F 801C:0003/000B/001F/0048 801D:0003/000B/001F/0048 801E:000B/001F/0048 801F:0003/001F/0048 8020:000B/001F 8021:0003/000B/001F 8022:0003/000B/0048 8023:0003/000B/001F 8024:0003/000B/001F/0048 8025:0003/000B/001F 8026:0003/001F 8027:0003/000B/001F/0102 8028:0003/001F/0102 8029:0003/000B/001F/0102 802A:0003/001F/0102/101F 802B:0003/001F/0102 802C:0003/001F/0102 802D:0003/001F/0102 802E:001F/0102 802F:001F/0102/101F 8030:000B/001F/0102/101F 8031:000B/001F/0040/101F 8032:0003/000B/001F 8033:000B/001F 8034:000B/001F 8035:0003/000B/001F 8036:000B/001F 8037:000B/001F/0040 8038:000B/001F 8039:000B/001F/0040 803A:000B/001F/0040 803B:001F 803C:001F 803D:001F 803E:001F
```

Reading notes:

- `001E` (**PT_STRING8**) appears **nowhere** — zero 8-bit string streams in
  all 11 samples; every string property is `001F` (UTF-16), with `101F`
  (multi-valued UTF-16) in the suffixed named-property streams.
- Tags `8001`–`803E` are the **named-property range**: 63 were observed in
  these samples, 54 of them with **more than one type across different samples** (e.g. `8005`
  as `0003`/`000B`/`0048`/`101F`). The numeric tag is per-message; identity
  lives in `__nameid_version1.0`, so a reader must not key named properties on
  the tag alone.
- The probe names only a minimal confident set (`0037`, `007D`, `1000`,
  `1009`, `1013`, `3FDE`, `3FFD`); every other tag is reported hex-only.

### B4. Code-page and flag properties (design claim -> measured; **corrected** after review)

> **Correction.** The first draft of this section identified the internet code page as `65C6` and the
> message code page as `3A00`. Both identifications were wrong: `0x65C6` is an unrelated long
> property (observed values 0 and 2) and `0x3A00` is absent because it is not the code page. The
> code pages are **`0x3FDE` (PidTagInternetCodepage) and `0x3FFD` (PidTagMessageCodepage)**. The rows
> below were re-measured on the same 11 samples (presence by the probe after `tools/real_probe.py`
> was fixed; the value sets are code-page numbers only, read from the fixed entries, no content).

| design claim (spec, Turn 0.0) | status | evidence from the 11 samples |
|---|---|---|
| internet code page is a fixed-size property inside `__properties_version1.0`, not a stream; a stream-based reader wrongly concludes absent | **measured, confirmed** | `3FDE:0003` present as a fixed entry in the `[message]` table of **11/11** samples; **no stream named `__substg1.0_3FDE*` exists**. Observed values: **1252, 20127 (us-ascii), 28591 (iso-8859-1), 65001 (UTF-8)** |
| message code page likewise | **measured, confirmed** | `3FFD:0003` present as a fixed entry in **11/11** samples; no stream of that name. Observed values: **1252, 65001** |
| the compressed-RTF-in-sync flag likewise (fixed entry, not a stream) | **measured (general form); specific tag not observed** | zero streams typed `000B` exist anywhere (a boolean property can only be a table entry); 54 distinct boolean-typed tags appear as fixed entries; no sample carries `39E1`/`39E0` |
| body streams (`00001000`, `00001009`, `00001013`) are real streams | **measured** | all three observed as streams: `1000:001F` (UTF-16), `1009:0102`, `1013:0102` |
| real messages exist with HTML only | **measured** | **10/11** samples: `0x1013` present, `0x1000` and `0x1009` absent |
| real messages exist with plain + compressed RTF and no HTML | **measured** | **S09**: `0x1000` (PT_UNICODE, 956 B) + `0x1009` (503 B) present, `0x1013` absent |
| (the RTF is generated from text, `\fromtext`) | **not verified by the probe** | verifying the marker requires reading RTF content, which the probe does not do (it was checked separately by the owner's side on one sample: compressed RTF with `\fromtext`, no `\fromhtml1`) |
| probe parses the table for code-page/flag properties and reports presence only | **implemented** | probe section `code-page / flag properties` prints PRESENT/absent with the containing table label, never a value |

**Consequence for D13's encoding ladder:** both properties are real and present in every sample, and
they **can disagree** in value (internet 28591 or 20127 against message 1252), so the ladder's step 1
(internet code page) and step 2 (message code page) are both exercised; the ladder must read them from
the property table, not from streams.

Additional measured facts:

- `007D` (`TransportMessageHeaders`, `001F`) present as a stream in **11/11**
  samples (S02 has two: top-level + embedded).
- No sample carries all three body streams, and none is plain-only or
  RTF-only (`0x1009` without `0x1000` was not observed).
- Body-shape census by sample is in the B0 table.

### B5. Anomalies and limits

- One non-standard entry: `0000:0001` (tag 0, PT_NULL) in S02's embedded
  table — reported, not interpreted.
- Tags `6200/6201`, `65E1–65E3`, `6748/67FE` (`0014` = PT_I8), `6827` etc.
  are recorded hex-only; no name is asserted for them here.
- `extract-msg` cross-check (design Open risk 9's third-party signal) was not
  run in this turn — it remains the owner's manual check.
- The `.msg` write path (fixture digests) is untouched by this probe.

---

## Status of the design doc's "Open risks" after Turn 0.0 (exit criterion)

| risk | status after this turn |
|---|---|
| 4 — stdlib `email` behavior unmeasured | **measured** — 25 ids × 2 interpreters (section A), disagreements + fallbacks named above. The design's byte-offset fallback (walker's own raw scanner) is confirmed necessary: stdlib offers no offsets. |
| 9 — `.msg` property tags unverified; samples described as "HTML-only, attachment-less"; RTF/embedded/attachments not exercised | **measured, with corrections** — tag set recorded (B3, observation only, nothing frozen); 10/11 samples are HTML-only but **1/11 is plain+RTF with no HTML**; **2/11 carry attachment storages** and **1/11 contains an embedded message with its own recipient table**, so attachments/embedded messages ARE exercised; an RTF-only body (`0x1009` without `0x1000`) was still not observed. |
| 1, 2, 3, 5, 6, 7, 8, 10, 11, 12 | not in Turn 0.0 scope; unmeasurable here (no sibling APIs/corpora in this repo) or measured later per the spec's turn table. |

No contract is frozen by this document.
