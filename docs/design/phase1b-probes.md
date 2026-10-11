# Phase 1b probes: the owner's structure-only measurements (Turn 1b.0a specification; the script is built in Turn 1b.0b)

These are the six structure-only probes the **owner runs locally** over real `.msg` files that never enter the
repository, never enter a fixture or a commit, and are **never** given to hearth's model. `tools/msg_probe.py`
(built in Turn 1b.0b; it extends `tools/real_probe.py`, which already exists, C) implements them; **this
document is its specification** -- the output schema below is the contract, and the script must print exactly
what is specified and nothing more. Each probe answers a question the design left to measurement, and each
answer changes what a Phase 1b turn can claim (never what it can build).

## Privacy rules (bind the script)

- **The probe refuses a path inside the repository.** `real_probe.py` already does this (`is_relative_to` check
  -> exit 2, C); `msg_probe.py` keeps it, and additionally refuses the `fixtures/` tree. The owner points it at
  a directory **outside** the repo (their own mail folder).
- **It prints nothing it was not specified to print** -- no subject, no address, no body text, no header value,
  no filename, no stream content. It prints **counts, sizes, tag sets, type censuses and presence lines** only:
  a value is never rendered, only its *shape*.
- **The only stream it reads is structural**: the `__properties_version1.0` tables (tag words, sizes, counts --
  values are not interpreted). It never opens a body or header stream for reading.
- **The output is pasted by the owner**, and is recorded as a note in `docs/design/open-inputs.md` (aggregates
  only), never as a fixture, a sidecar or a commit. Hearth's model never reads the owner's files.
- **The command form:** `python tools/msg_probe.py --probe <P1..P6> <DIR> [--limit N]`, run with the primary
  interpreter. `<DIR>` is outside the repository. Output is plain text, one block per probe, paste-ready.

## P1 -- Signed and encrypted mail: is there a readable body, or an opaque attachment?

- **Question:** does an `IPM.Note.SMIME*` / `IPM.Note.Secure*` item carry a readable `0x1013`/`0x1009` body, or
  is it a body-less item with an opaque `smime.p7m` / `data.dat` attachment? **Decides** owner decision O8: the
  default is "class recorded, no body, never verified"; if P1 shows a readable body, O8's split (encrypted-only
  -> `Status.ENCRYPTED`; signed-only readable -> `PARSED`) is re-opened **for the owner**, not decided by a
  build turn.
- **Command:** `python tools/msg_probe.py --probe P1 <DIR>`
- **What it prints (only this):** per file, the message-class **string is NOT printed**; instead a count of
  files whose class begins `IPM.Note.SMIME` / `IPM.Note.Secure` / `IPM.Note` (bucketed, no verbatim class), the
  presence of each body stream (`0x1000`, `0x1009`, `0x1013`) as PRESENT/absent, and the attachment-method
  census (`1`/`2`/`3`/`4`/`5`/`6` counts) with the **size** of each attachment stream (never its name).
- **What to paste back:** the per-bucket counts, the body-stream presence lines and the method/size table.
- **Worked fake example output:**

```
P1 signed/encrypted layout -- <N> files scanned
class buckets: IPM.Note=41  IPM.Note.SMIME*=6  IPM.Note.Secure*=2  other=1
body streams:  0x1000 present=0  0x1009 present=0  0x1013 present=5
attachments:   method=1:5  method=2:0  method=3:0  method=4:0  method=5:0  method=6:0
attachment sizes (bytes, sorted): 8214 8214 8214 16384 16384
```

## P2 -- Time property tags: presence and types

- **Question:** which of `0x0039`, `0x0E06`, `0x3007`, `0x3008` are present, and with which property type? (The
  design's `time.<tag-hex>.*` facts assume these; **no tag is frozen by a doc**.) **Decides** the
  `msg.time_facts` tag list for Turn 1b.6.
- **Command:** `python tools/msg_probe.py --probe P2 <DIR>`
- **What it prints (only this):** for each candidate tag, a presence count over the corpus and the observed
  `tag:type` pairs (hex only); no FILETIME value is decoded or printed.
- **What to paste back:** the presence counts and the `tag:type` set.
- **Worked fake example output:**

```
P2 time property tags -- <N> files
0039: present=48  types=0040
0e06: present=48  types=0040
3007: present=12  types=0040
3008: present=12  types=0040
```

## P3 -- CFB layout aggregate (does the extended DIFAT ever occur?)

- **Question:** the version, sector size, miniFAT use, DIFAT length (is the **extended** chain ever present),
  directory size and a stream-size histogram. **Decides** how much owner decision O1's read-through path
  matters (P3's DIFAT length settles whether the extended chain occurs in the owner's corpus) and the weight of
  the `msg_difat_extended` fixture.
- **Command:** `python tools/msg_probe.py --probe P3 <DIR>`
- **What it prints (only this):** version bucket counts (3/4), sector-size bucket counts, miniFAT-used count,
  a DIFAT-length histogram (how many files at each number of DIFAT sectors; "extended present" count), the
  directory-entry-count histogram, and a stream-size histogram (buckets: <4 KiB, 4 KiB-1 MiB, 1-8 MiB, >8 MiB).
- **What to paste back:** the six histograms/counts.
- **Worked fake example output:**

```
P3 CFB layout -- <N> files
version:      3=49  4=1
sector size:  512=49  4096=1
miniFAT used: 50/50
difat length histogram: 1=50   (>1 = extended present: 0)
directory entries histogram: 128=11  129=9  130=30
stream size buckets: <4KiB=44  4KiB-1MiB=6  1-8MiB=0  >8MiB=0
```

## P4 -- Attachment and recipient tag sets (before Turn 1b.7)

- **Question:** the tags a by-value attachment and a recipient actually carry: the method tag, the filename
  ladder (`0x3707`/`0x3704`/`0x3001`), `0x3712` (Content-ID), `0x370E` (MIME tag), the hidden/inline flags; and
  the recipient address types (SMTP versus EX). **Decides** the exact tag set `msg.attachments` /
  `msg.recipients` read in Turn 1b.7. **Every tag here is "verify" until P4 confirms it.**
- **Command:** `python tools/msg_probe.py --probe P4 <DIR>`
- **What it prints (only this):** the union `tag:type` set observed inside `__attach_version1.0_*` storages and
  inside `__recip_version1.0_*` storages (hex only), plus, per corpus, the counts of attachment methods and the
  counts of recipient address-type properties (the type word, not the address).
- **What to paste back:** the two `tag:type` sets and the two counts.
- **Worked fake example output:**

```
P4 attachment/recipient tags -- <N> files
attach tag:type union: 3701:0102 3703:0003 3704:001F 3705:0003 3707:001F
                       370E:001F 3712:001F 3713:0003 3714:0003
recip  tag:type union: 0C15:0003 0C1A:001F 0C1E:001F 0C1F:001F 3001:001F 3003:001F
attach methods: 1=5  2=0  3=0  4=0  5=1  6=0
recipient address types: 3002=001F(smtp)=47  3003=001F(ex)=3
```

## P5 -- 8-bit prevalence

- **Question:** is a `0x007D` transport-header stream ever `001E` (8-bit) rather than `001F` (UTF-16)? Are
  bodies ever `0x1000:001E`? (All 11 spike files are `001F`.) **Decides** the weight of the `msg_string8_*`
  encoding fixtures and the ladder's 8-bit path for `0x007D`.
- **Command:** `python tools/msg_probe.py --probe P5 <DIR>`
- **What it prints (only this):** the type of each of `0x007D`, `0x1000`, `0x1013` as a presence/type census
  (`001F` / `001E` / other counts), no bytes.
- **What to paste back:** the three type censuses.
- **Worked fake example output:**

```
P5 8-bit prevalence -- <N> files
007D type census: 001F=50  001E=0  other=0
1000 type census: 001F=3   001E=0  other=0
1013 type census: 0102=47
```

## P6 -- Vendor HTML classes

- **Question:** does real Outlook/Exchange HTML use `divRplyFwdMsg` and the `x_` class prefix (the DOM quote
  rules' assumed input)? **Decides** the Phase 1b input to the quote rules on `.msg` HTML (spec risk 8) and the
  weight of the HTML fixtures.
- **Command:** `python tools/msg_probe.py --probe P6 <DIR>`
- **What it prints (only this):** over the `0x1013` HTML **streams only**, a count of files whose HTML contains
  each of the literal **class tokens** `divRplyFwdMsg`, `appendonsend`, `x_` (a prefix occurrence count), and
  `blockquote` -- **token presence counts only, never the surrounding HTML**. This is the one probe that reads a
  body stream's bytes, and it reads them **in-process and prints no text**; it matches only the listed literals
  and reports booleans/counts.
- **What to paste back:** the token-presence table.
- **Worked fake example output:**

```
P6 vendor HTML classes -- <N> files with 0x1013
divRplyFwdMsg: 9/47   appendonsend: 4/47   x_ prefix: 31/47   blockquote: 0/47
```

## What each answer decides (summary)

| probe | question | decides |
|---|---|---|
| P1 | signed/encrypted body layout | owner decision O8 (and only the owner re-opens it) |
| P2 | time property tags (`0x0039`, `0x0E06`, `0x3007`, `0x3008`) | the `msg.time_facts` tag list (Turn 1b.6) |
| P3 | CFB layout aggregate incl. DIFAT length | how much O1's read-through matters; the `msg_difat_extended` fixture's weight |
| P4 | attachment / recipient tag sets | the exact tags `msg.attachments` / `msg.recipients` read (Turn 1b.7) |
| P5 | 8-bit prevalence | the weight of the `msg_string8_*` fixtures and the ladder's 8-bit path |
| P6 | vendor HTML classes | the Phase 1b input to the quote rules on `.msg` HTML; the HTML fixtures' weight |

An answer never changes a **committed** fixture retroactively: it changes which synthetic form a **future**
fixture takes (a tag set that P4 shows the corpus uses, a time tag P2 confirms), and it is recorded as a note in
`docs/design/open-inputs.md`. If an answer contradicts a **committed** typed label, that is a finding reported
in the Phase 1b report (never a silent edit), exactly as the Phase 1 rule requires.
