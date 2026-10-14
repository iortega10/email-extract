# Turn 1b.8 fix: two wrong constants in `rtf.py` (the prebuf and the CRC), found against a real vector

Status: correction brief for the **uncommitted** Turn 1b.8 working tree. Author: reviewer session, 2026-10-14. Builder: hearth. Do not
commit. This is a small fix turn: change the two constants, add real vectors, rebuild what depends on them, re-run. **Do not start
1b.9.**

## What the reviewer found, and how it was checked

Turn 1b.8 stopped, correctly, because it could not verify the [MS-OXRTFCP] prebuf offline, and it shipped a 167-byte best-known form.
The reviewer had network access and checked the format against a public, independent implementation (`delimitry/compressed_rtf`,
its `INIT_DICT` literal and its README vectors). Result, run by the reviewer on this machine (scripts in the reviewer's scratchpad):

1. **`PREBUF` is wrong.** The real pre-load is **207 bytes** (the specification's number, which the brief already recorded), and the
   167-byte text in `rtf.py` is not a prefix of it: it is an Outlook-generated RTF header, not the prebuf (the module docstring's "first
   80 bytes are certain" is false). Every real Outlook `LZFu` stream starts with references into the prebuf, so with the wrong text a
   real stream decodes to wrong bytes or to a fault.
2. **The CRC is not `zlib.crc32`.** [MS-OXRTFCP]'s CRC is the plain table-driven CRC-32 with polynomial `0xEDB88320`, **initial value
   0 and no final XOR**, over the bytes after the 16-byte header. `zlib.crc32` (initial `0xFFFFFFFF`, final XOR) gives a different
   number for the same bytes. The module's claim that the two are equal, and the `tests/support` assertion that appeared to show it,
   were built from the same wrong definition on both sides. As written, **every real `LZFu` stream would raise `rtf_crc_mismatch`** and
   truncate its document.
3. **Why 2111+ round-trip tests could not see either.** The test-side compressor (`tests/support/rtf_compress.py`) shares `PREBUF` and
   the CRC with the decoder, so encode then decode agrees with itself whatever the constants are. The brief asked for hand-typed vectors
   from the specification; this fix supplies two real ones, and they must be asserted **against the decoder, not against the sibling
   encoder**.

## The constants (type them exactly; verify as below before relying on them)

`PREBUF`, 207 bytes, four concatenated literals, backslashes single, the `\r\n` a real CR LF pair, exactly this text:

    {\rtf1\ansi\mac\deff0\deftab720{\fonttbl;}{\f0\fnil \froman \fswiss \fmodern \fscript \fdecor MS Sans SerifSymbolArialTimes New RomanCourier{\colortbl\red0\green0\blue0<CR><LF>\par \pard\plain\f0\fs20\b\i\u\tab\tx

(as a Python literal use raw bytes for the text and `b"\r\n"` for the break; `assert len(PREBUF) == 207`). `INITIAL_WRITE_POSITION` stays
`len(PREBUF)` (207). The dictionary is 4096 bytes; the reference implementation fills the rest with spaces. **This package keeps its own
stricter rule**: a reference that reads a dictionary byte not yet written is the fault `rtf_dictionary_underrun` (the byte past the prebuf
is "unwritten", not a space). A real Outlook stream never reads there; if the real vectors below ever need a space fill, stop and report.

CRC: `crc = 0; for byte in data: crc = TABLE[(crc ^ byte) & 0xFF] ^ (crc >> 8)`, `TABLE` the standard reflected `0xEDB88320` table,
result unmasked beyond 32 bits, **no initial `0xFFFFFFFF`, no final XOR**. Implement it in `rtf.py` (a 256-entry table built once at
import is fine, bounded and stdlib-only; `zlib` is no longer used for the CRC). The module docstring's claim about `zlib.crc32` is wrong
and must be corrected.

## Two real vectors (commit them as hand-typed test constants, with provenance in a comment)

Provenance comment: "from the README of `delimitry/compressed_rtf` (public), also a worked example of the format; checked 2026-10-14".

* **Compressed (`LZFu`)**, 39 bytes. As a Python `bytes` literal: `b'#\x00\x00\x00"\x00\x00\x00LZFu3\\\xe8t\x03\x00\n\x00rcpg125\x922\n\xf3 t\x07\x90t}\x0f\x10'`.
  Header: `COMPSIZE` 35 (= stream length - 4), `RAWSIZE` 34, `COMPTYPE` `LZFu`, `CRC` `0x74E85C33`. It decompresses to the 34 bytes
  `{\rtf1\ansi\ansicpg1252\pard test}` and ends on the end marker. The reviewer's independent decoder using the 207-byte prebuf and the raw
  CRC reproduces exactly that text and the stored CRC.
* **Uncompressed (`MELA`)**, 50 bytes: `b'.\x00\x00\x00"\x00\x00\x00MELA \xdf\x12\xce{\\rtf1\\ansi\\ansicpg1252\\pard test}'`. Header `COMPSIZE`
  46, `RAWSIZE` 34, `COMPTYPE` `MELA`, `CRC` `0xCE12DF20`, which **is** the same raw-table CRC of the 34 payload bytes.

## What to change

1. `emailextract/rtf.py`: `PREBUF` (207), the CRC function, both docstring paragraphs about the unverified tail and about `zlib.crc32`.
2. **The `MELA` CRC rule.** [MS-OXRTFCP] says an uncompressed stream's CRC is `0`; the real vector above carries the payload's raw CRC
   instead (this implementation writes it). Never guess: a `MELA` stream is accepted when its CRC field is **either** `0` **or** equal to
   the raw-table CRC of its payload (`crc_ok` is `True` in both cases; record which: add a field `crc_kind` in `{"zero", "payload", "none"}`
   to the result, plain data), and any other value is `rtf_crc_mismatch`. State this as a reading in the note and an owner question; it is
   a leniency chosen because the format's own reference writer produces the second form.
3. `tests/support/rtf_compress.py`: use the same corrected `PREBUF` and CRC, and **stop sharing them silently with the decoder**: import the
   constants from one place, but add the two real vectors as tests that go through `rtf.decode` only (no encoder involved).
4. New tests (declared in the 1b.8 block): `test_the_prebuf_is_the_207_byte_text_of_the_specification` (length, first 40 and last 20
   bytes, and the sha256 of the whole constant, typed in the test), `test_the_crc_is_the_raw_table_crc_not_zlib` (the real `LZFu` vector's
   stored CRC equals the raw CRC and **differs** from `zlib.crc32`, asserted both ways), `test_a_real_lzfu_vector_decodes_exactly` and
   `test_a_real_mela_vector_is_accepted`. Both real vectors also go through `MsgContainer` in a built `.msg` (a `0x1009` stream holding
   them): the document is `PARSED` with no `msg.stream_truncated` and with `msg.rtf_to_text_unsupported`, and `rtf_facts` records the
   decompressed length 34 and `decompressed_sha256` of the 34 bytes.
5. Rebuild every artifact that embedded the old constants: the three committed RTF fixtures (`msg_rtf_compressed_body`, `msg_rtf_only`,
   `msg_rtf_bad_crc`) and their `SHA256SUMS` lines, the label-ledger hash for any changed `tests/support` file, and the hand-built vectors in
   `tests/test_msg_rtf.py` that were derived with the wrong prebuf or CRC (each was derived by hand from the old constants: re-derive them
   by hand from the new ones and show the derivation in the comment; a literal that now disagrees with the code is a **finding**, not a
   value to patch). `msg_rtf_bad_crc` stays a stream whose CRC is wrong **under the corrected definition**.
6. The mutation that skipped or altered the CRC must still fail a named test, and add a fourth mutation: change one byte of `PREBUF`, and
   `test_a_real_lzfu_vector_decodes_exactly` and the prebuf test must fail.

## Allow-list

`emailextract/rtf.py`, `tests/support/rtf_compress.py`, `tests/test_msg_rtf.py`, `tests/support/msg_construction.py`,
`tools/make_msg_fixtures.py`, `fixtures/msg/` (the three RTF fixtures and `SHA256SUMS`), `tests/ledger/label_ledger.json`,
`tests/test_turn_declarations.py`, `docs/design/phase1b-ledgers.md` (a short "fix" subsection in the 1b.8 note, and the declaration
block), `docs/design/phase1-turn-declarations.md`. Nothing else; in particular not `msgcontainer.py` unless the new `crc_kind` field
forces a one-line change (name it).

## Report

The full suite on both interpreters, the `--check` tools, the four mutations, and in the note: the old and new constants (length and
sha256), how the corrected decoder handles each real vector, which tests were re-derived and how, and the two owner questions (the
`MELA` CRC leniency, the dictionary's unwritten-byte rule versus the reference's space fill). Do not commit.
