"""Phase 0 Turn 0.0 spike: measure stdlib ``email`` + lxml behavior before any contract freezes.

Answers the design's Open risk 4 (``policy.default`` defect handling, obs-fold, raw header
recovery) and the D2 raw-offset assumption with *observations*, one measurement per id, built
from hand-written byte strings only -- no real mail ever enters this script.  The recorded
table lives in ``docs/design/email-spike.md``; every row there cites the id measured here.

`.msg` structure is measured separately by ``tools/real_probe.py`` (owner-run, structure only).

Run:  python tools/email_spike.py             # every measurement
      python tools/email_spike.py a01 c02     # selected ids
      python tools/email_spike.py --list      # ids and questions
      python tools/email_spike.py > out.txt   # record per interpreter

Exit status: 0 unless a measurement itself crashed (``spike_error``) -- a crash is a bug in
this tool, not a measured fact; anything the interpreter refuses to do is reported as the
observation it is.
"""
from __future__ import annotations

import email
import email.policy
import email.utils
import sys
import warnings
from dataclasses import dataclass
from typing import Callable

MEASUREMENTS: list["Measurement"] = []


class NotMeasurable(Exception):
    """The row cannot be measured in this interpreter/environment; carries the reason."""


@dataclass
class Measurement:
    mid: str
    section: str
    question: str
    fn: Callable[[], "list[str]"]


def measurement(mid: str, section: str, question: str):
    def register(fn):
        MEASUREMENTS.append(Measurement(mid, section, question, fn))
        return fn

    return register


def parse(raw: bytes):
    return email.message_from_bytes(raw, policy=email.policy.default)


def caught(fn, *args, **kwargs):
    """Call fn; return (value, exception_type_name_or_None, warning_messages)."""
    with warnings.catch_warnings(record=True) as record:
        warnings.simplefilter("always")
        try:
            value = fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - the exception *is* the observation
            return None, type(exc).__name__, [str(w.message) for w in record]
        return value, None, [str(w.message) for w in record]


# =====================================================================================
# A: headers parsed with policy.default
# =====================================================================================


@measurement("a01", "A headers", "obs-fold unfolding: is a folded header one field, and what survives")
def a01():
    raw = (
        b"From: a@example.com\r\n"
        b"X-Obs-Fold: first part\r\n"
        b"  second part\r\n"
        b"Subject: s\r\n"
        b"\r\n"
        b"body\r\n"
    )
    m = parse(raw)
    raw_items = [(n, v) for n, v in m.raw_items() if n.lower() == "x-obs-fold"]
    str_m = str(m).replace("\r\n", "\\r\\n").replace("\n", "\\n")
    return [
        f"get('X-Obs-Fold') = {m.get('X-Obs-Fold')!r}",
        f"raw_items entries = {raw_items!r}",
        f"defects = {m.defects!r}",
        f"keys() = {m.keys()!r}  (exactly one field? {m.keys().count('X-Obs-Fold') == 1})",
        f"str(m) = {str_m!r}",
    ]


@measurement("a02", "A headers", "duplicate headers: order kept for repeated Received?")
def a02():
    raw = (
        b"Received: from a.example by b.example; Tue, 1 Sep 2026 00:00:00 +0000\r\n"
        b"Received: from c.example by d.example; Tue, 1 Sep 2026 00:00:01 +0000\r\n"
        b"Received: from e.example by f.example; Tue, 1 Sep 2026 00:00:02 +0000\r\n"
        b"Subject: s\r\n"
        b"\r\n"
        b"body\r\n"
    )
    m = parse(raw)
    return [
        f"get_all('Received') = {m.get_all('Received')!r}",
        f"header order = {[n for n, _ in m.raw_items()]!r}",
        f"defects = {m.defects!r}",
    ]


@measurement("a03", "A headers", "a non-blank line that is not 'name: value' inside the header block")
def a03():
    raw = b"From: a@b.c\r\nno colon here\r\nSubject: s\r\n\r\nbody\r\n"
    m, err, warns = caught(parse, raw)
    if m is None:
        return [f"message_from_bytes raised {err}", f"warnings = {warns!r}"]
    return [
        f"keys() = {m.keys()!r}",
        f"'Subject' still readable = {m.get('Subject')!r}",
        f"defects = {m.defects!r}",
        f"payload = {m.get_payload()!r}",
        f"warnings = {warns!r}",
    ]


@measurement("a04", "A headers", "a message with no blank line at all (headers to EOF)")
def a04():
    raw = b"From: a@b.c\r\nSubject: s\r\n"
    m = parse(raw)
    return [
        f"keys() = {m.keys()!r}",
        f"defects = {m.defects!r}",
        f"get_payload() = {m.get_payload()!r}",
        f"is_multipart() = {m.is_multipart()!r}",
    ]


@measurement("a05", "A headers", "Date: -0000 vs +0000 via email.utils (parsedate_tz / parsedate_to_datetime)")
def a05():
    cases = [
        "Sun, 6 Sep 2026 12:34:56 -0000",
        "Sun, 6 Sep 2026 12:34:56 +0000",
        "Sun, 6 Sep 2026 12:34:56 GMT",
        "Sun, 6 Sep 2026 12:34:56",
    ]
    out = []
    out.append(
        "mechanism: _parsedate_tz maps '-0000' to tz=None but public "
        "parsedate_tz rewrites None->0;"
        f" _parsedate_tz('-0000')[-1] = {email.utils._parsedate_tz(cases[0])[-1]!r};"
        f" _parsedate_tz('+0000')[-1] = {email.utils._parsedate_tz(cases[1])[-1]!r};"
        f" parsedate_tz('-0000')[-1] = {email.utils.parsedate_tz(cases[0])[-1]!r};"
        f" parsedate_tz('+0000')[-1] = {email.utils.parsedate_tz(cases[1])[-1]!r}"
    )
    for hdr in cases:
        tz_tuple, err1, w1 = caught(email.utils.parsedate_tz, hdr)
        dt, err2, w2 = caught(email.utils.parsedate_to_datetime, hdr)
        line = f"input={hdr!r}"
        if err1:
            line += f"; parsedate_tz raised {err1}"
        else:
            line += f"; parsedate_tz full tuple = {tz_tuple!r}"
            if isinstance(tz_tuple, tuple) and len(tz_tuple) > 9:
                line += f" (tz slot = {tz_tuple[9]!r})"
        if err2:
            line += f"; parsedate_to_datetime raised {err2}"
        else:
            line += (
                f"; parsedate_to_datetime = {dt!r}"
                f" tzinfo={dt.tzinfo!r} utcoffset={dt.utcoffset()!r}"
            )
        warns = w1 + w2
        if warns:
            line += f"; warnings = {warns!r}"
        out.append(line)
    return out


@measurement("a06", "A headers", "parseaddr/getaddresses on a group, IDN, SMTPUTF8 local part and garbage")
def a06():
    cases = {
        "group_empty": "undisclosed-recipients:;",
        "group_with_members": "Team: a@example.com, b@example.com;",
        "idn_domain": "user@xn--bcher-kva.example",
        "unicode_domain": "user@b\u00fccher.example",
        "smtputf8_local": "\u7528\u6237@example.com",
        "garbage_text": "just some text",
        "no_at": "foo",
        "trailing_comma": "a@example.com,",
        "unclosed_angle": "Name <a@example.com",
        "empty": "",
    }
    out = []
    for name, hdr in cases.items():
        addrs, err1, w1 = caught(email.utils.getaddresses, [hdr])
        pair, err2, w2 = caught(email.utils.parseaddr, hdr)
        line = f"{name}: input={hdr!r}"
        line += f"; getaddresses raised {err1}" if err1 else f"; getaddresses={addrs!r}"
        line += f"; parseaddr raised {err2}" if err2 else f"; parseaddr={pair!r}"
        warns = w1 + w2
        if warns:
            line += f"; warnings = {warns!r}"
        out.append(line)
    return out


@measurement("a07", "A headers", "RFC 2047 encoded words: valid Q/B, folded pair, invalid charset/encoding")
def a07():
    cases = {
        "valid_q": "=?utf-8?Q?Caf=C3=A9?=",
        "valid_b": "=?utf-8?B?Q2Fmw6k=?=",
        "folded_pair": "=?utf-8?Q?one?=\r\n  =?utf-8?Q?two?=",
        "unknown_charset": "=?x-nope?Q?hi?=",
        "bad_base64_length": "=?utf-8?B?abc?=",
        "bad_pct_escape": "=?utf-8?Q?%ZZ?=",
    }
    out = []
    for name, subject in cases.items():
        raw = f"From: a@b.c\r\nSubject: {subject}\r\n\r\nbody\r\n".encode("utf-8", "surrogateescape")
        m, err, _ = caught(parse, raw)
        if m is None:
            out.append(f"{name}: parse raised {err}")
            continue
        value, err2, warns = caught(m.get, "Subject")
        raw_value = [v for n, v in m.raw_items() if n.lower() == "subject"]
        line = f"{name}: get() raised {err2}" if err2 else f"{name}: get() = {value!r}"
        line += f"; raw_items = {raw_value!r}; defects = {m.defects!r}"
        if warns:
            line += f"; warnings = {warns!r}"
        out.append(line)
    return out


@measurement("a08", "A headers", "RFC 2231 filename continuations and charset-encoded filename")
def a08():
    cases = {
        "continuations": b'attachment; filename*0="part one "; filename*1="and two.txt"',
        "pct_encoded": b"attachment; filename*=UTF-8''na%C3%AFve%20file.txt",
        "plain_quoted": b'attachment; filename="plain.txt"',
        "escaped_quotes": b'attachment; filename="na\\"ive.txt"',
    }
    out = []
    for name, disp in cases.items():
        raw = b"From: a@b.c\r\nContent-Disposition: " + disp + b"\r\n\r\nbody\r\n"
        m = parse(raw)
        value, err, warns = caught(m.get_filename)
        line = f"{name}: get_filename() raised {err}" if err else f"{name}: get_filename() = {value!r}"
        line += f"; defects = {m.defects!r}"
        if warns:
            line += f"; warnings = {warns!r}"
        out.append(line)
    return out


@measurement("a09", "A headers", "Thread-Index: is the raw value returned verbatim (binary-ish header)?")
def a09():
    raw = (
        b"From: a@b.c\r\n"
        b"Thread-Index: AQH0abc123DEF456ghi789JKL012mno345\r\n"
        b"  PQR678stu901vwx234\r\n"
        b"\r\n"
        b"body\r\n"
    )
    m = parse(raw)
    raw_value = [v for n, v in m.raw_items() if n.lower() == "thread-index"]
    return [
        f"get() = {m.get('Thread-Index')!r}",
        f"raw_items = {raw_value!r}",
        f"defects = {m.defects!r}",
        f"decoded? same as raw? {m.get('Thread-Index') == (raw_value[0] if raw_value else None)}",
    ]


# =====================================================================================
# B: defect handling
# =====================================================================================


@measurement("b01", "B defects", "malformed boundaries: missing close delimiter, wrong start delimiter")
def b01():
    out = []
    missing_close = (
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="b1"\r\n'
        b"\r\n"
        b"--b1\r\n"
        b"Content-Type: text/plain\r\n"
        b"\r\n"
        b"first\r\n"
        b"--b1\r\n"
        b"Content-Type: text/plain\r\n"
        b"\r\n"
        b"second\r\n"
    )
    m = parse(missing_close)
    parts = m.get_payload() if isinstance(m.get_payload(), list) else []
    out.append(
        f"missing_close: msg.defects = {m.defects!r}; is_multipart = {m.is_multipart()!r};"
        f" n_parts = {len(parts)}"
        + (f"; part[1].defects = {getattr(parts[1], 'defects', None)!r}" if len(parts) > 1 else "")
    )
    wrong_start = (
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="b1"\r\n'
        b"\r\n"
        b"--totally-wrong\r\n"
        b"Content-Type: text/plain\r\n"
        b"\r\n"
        b"orphan\r\n"
        b"--b1--\r\n"
    )
    m2 = parse(wrong_start)
    pl = m2.get_payload()
    out.append(
        f"wrong_start: msg.defects = {m2.defects!r}; is_multipart = {m2.is_multipart()!r};"
        f" payload_type = {type(pl).__name__}; payload = {pl!r}"[:400]
    )
    return out


@measurement("b02", "B defects", "truncated / invalid base64: defects recorded, what decode=True returns")
def b02():
    out = []
    cases = {
        "truncated_padding": b"QUJDRA",          # valid would be QUJDRA==
        "invalid_chars": b"QUJ$RA==\r\n",        # $ is not base64
    }
    for name, body in cases.items():
        raw = (
            b"MIME-Version: 1.0\r\n"
            b"Content-Type: text/plain\r\n"
            b"Content-Transfer-Encoding: base64\r\n"
            b"\r\n" + body
        )
        m = parse(raw)
        decoded, err, _ = caught(m.get_payload, decode=True)
        out.append(
            f"{name}: defects = {m.defects!r}; get_payload(decode=True)"
            + (f" raised {err}" if err else f" = {decoded!r}")
        )
    return out


@measurement("b03", "B defects", "bad charset: get_payload(decode=True) vs get_content() on missing/invalid charset")
def b03():
    out = []
    cases = {
        "missing_charset": (b"Content-Type: text/plain; charset=\"x-no-such-charset\"\r\n"
                            b"Content-Transfer-Encoding: 7bit\r\n\r\nplain text\r\n"),
        "invalid_utf8": (b"Content-Type: text/plain; charset=\"utf-8\"\r\n"
                         b"Content-Transfer-Encoding: 8bit\r\n\r\nbad: \xff\xfe\x80 bytes\r\n"),
    }
    for name, raw in cases.items():
        m = parse(raw)
        decoded, e1, _ = caught(m.get_payload, decode=True)
        content, e2, _ = caught(m.get_content)
        out.append(
            f"{name}: get_content_charset() = {m.get_content_charset()!r};"
            f" get_payload(decode=True)" + (f" raised {e1}" if e1 else f" = {decoded!r}")
            + f"; get_content()" + (f" raised {e2}" if e2 else f" = {content!r}")
            + f"; defects = {m.defects!r}"
        )
    return out


# =====================================================================================
# C: raw recovery (D2 assumption)
# =====================================================================================


@measurement("c01", "C raw recovery", "is any raw header byte-offset API present on the parsed object?")
def c01():
    m = parse(b"From: a@b.c\r\nSubject: s\r\n\r\nbody\r\n")
    header_obj = m.get("Subject")
    msg_offsets = [a for a in dir(m) if any(t in a.lower() for t in ("offset", "position", "span"))]
    hdr_offsets = [a for a in dir(header_obj) if any(t in a.lower() for t in ("offset", "position", "span"))]
    policy_hooks = [a for a in dir(m.policy) if "header_source" in a or "offset" in a]
    return [
        f"Message attrs matching offset/position/span = {msg_offsets!r}",
        f"header object attrs matching offset/position/span = {hdr_offsets!r}",
        f"policy hooks matching header_source/offset = {policy_hooks!r}",
        f"policy.header_source_parse signature hook exists = {hasattr(m.policy, 'header_source_parse')!r}"
        " (input-side hook: (source, defects_dict); it reports no positions)",
        f"str(type(header object)) = {type(header_obj)!r}",
    ]


@measurement("c02", "C raw recovery", "as_bytes() round-trip: byte-identical to the input for real-world shapes?")
def c02():
    cases = {
        "crlf_headers": b"From: a@b.c\r\nSubject: s\r\n\r\nbody\r\n",
        "lf_only": b"From: a@b.c\nSubject: s\n\nbody\n",
        "obs_fold": b"From: a@b.c\r\nSubject: folded\r\n  subject\r\n\r\nbody\r\n",
        "trailing_ws": b"From: a@b.c\r\nSubject: s   \r\n\r\nbody\r\n",
        "dup_received": b"Received: one\r\nReceived: two\r\nSubject: s\r\n\r\nbody\r\n",
        "no_colon_line": b"From: a@b.c\r\nno colon here\r\n\r\nbody\r\n",
    }
    out = []
    for name, raw in cases.items():
        m = parse(raw)
        rt = m.as_bytes()
        equal = rt == raw
        first = next((i for i, (x, y) in enumerate(zip(raw, rt)) if x != y), None)
        if first is None and len(raw) != len(rt):
            first = min(len(raw), len(rt))
        detail = ""
        if not equal and first is not None:
            detail = (
                f"; first_diff@{first} orig={raw[first:first + 20]!r}"
                f" rt={rt[first:first + 20]!r}"
            )
        out.append(f"{name}: equal={equal}; len orig={len(raw)} rt={len(rt)}{detail}")
    return out


@measurement("c03", "C raw recovery", "what do msg.preamble and msg.epilogue contain?")
def c03():
    out = []
    raw = (
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="b1"\r\n'
        b"\r\n"
        b"this is the preamble\r\n"
        b"--b1\r\n"
        b"Content-Type: text/plain\r\n"
        b"\r\n"
        b"part\r\n"
        b"--b1--\r\n"
        b"this is the epilogue\r\n"
    )
    m = parse(raw)
    out.append(
        f"with preamble+epilogue: preamble = {m.preamble!r} ({type(m.preamble).__name__});"
        f" epilogue = {m.epilogue!r} ({type(m.epilogue).__name__})"
    )
    raw2 = (
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="b1"\r\n'
        b"\r\n"
        b"--b1\r\n"
        b"Content-Type: text/plain\r\n"
        b"\r\n"
        b"part\r\n"
        b"--b1--\r\n"
    )
    m2 = parse(raw2)
    out.append(
        f"without preamble: preamble = {m2.preamble!r}; epilogue = {m2.epilogue!r}"
    )
    return out


@measurement("c04", "C raw recovery", "raw bytes between boundaries: recoverable from the parse (expect: no)?")
def c04():
    raw = (
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="b1"\r\n'
        b"\r\n"
        b"--b1  \r\n"                      # delimiter line with trailing whitespace
        b"Content-Type: text/plain\r\n"
        b"\r\n"
        b"first part body\r\n"
        b"--b1--   \r\n"                   # closing delimiter with trailing whitespace
    )
    m = parse(raw)
    rt = m.as_bytes()
    part_bytes = m.get_payload()[0].as_bytes()
    return [
        "no API returns a byte span for a part (see c01)",
        f"delimiter trailing whitespace survives as_bytes(): 'b1  ' in rt? {b'--b1  ' in rt};"
        f" '--b1--   ' in rt? {b'--b1--   ' in rt}",
        f"original has trailing spaces on delimiters = {b'--b1  ' in raw!r} / {b'--b1--   ' in raw!r}",
        f"as_bytes() == raw? {rt == raw}; first_diff"
        f" = {next((i for i, (x, y) in enumerate(zip(raw, rt)) if x != y), 'none')}",
        f"locating part body by raw.find() = {raw.find(b'first part body')!r}"
        " (a search heuristic; the parser itself offers no offset)",
        f"part.as_bytes() equals its raw slice? part.as_bytes()={part_bytes!r}",
    ]


# =====================================================================================
# D: decode chain
# =====================================================================================


@measurement("d01", "D decode", "get_payload(decode=True) on QP with a stray '=' and a soft line break")
def d01():
    cases = {
        "invalid_hex": b"a=zz b\r\n",
        "soft_break": b"line1=\r\nline2\r\n",
        "trailing_eq_eof": b"end=",
        "qp_valid_cafe": b"Caf=C3=A9\r\n",
    }
    out = []
    for name, body in cases.items():
        raw = (
            b"Content-Type: text/plain\r\n"
            b"Content-Transfer-Encoding: quoted-printable\r\n\r\n" + body
        )
        m = parse(raw)
        decoded, err, _ = caught(m.get_payload, decode=True)
        line = f"{name}: get_payload(decode=True) raised {err}" if err else f"{name}: decode=True = {decoded!r}"
        line += f"; defects = {m.defects!r}"
        out.append(line)
    return out


@measurement("d02", "D decode", "iso-8859-1 quoted-printable: bytes from decode=True, text from get_content()")
def d02():
    raw = (
        b"Content-Type: text/plain; charset=\"iso-8859-1\"\r\n"
        b"Content-Transfer-Encoding: quoted-printable\r\n"
        b"\r\n"
        b"Caf=E9 na=EFve\r\n"
    )
    m = parse(raw)
    decoded, e1, _ = caught(m.get_payload, decode=True)
    content, e2, _ = caught(m.get_content)
    manual = None
    if isinstance(decoded, bytes):
        manual, e3, _ = caught(decoded.decode, "iso-8859-1")
    else:
        e3 = None
    return [
        f"decode=True bytes = {decoded!r} (raised {e1})" if e1 else f"decode=True bytes = {decoded!r}",
        f"bytes.decode('iso-8859-1') = {manual!r}" + (f" (raised {e3})" if e3 else ""),
        f"get_content() = {content!r}" + (f" (raised {e2})" if e2 else ""),
        f"defects = {m.defects!r}",
    ]


@measurement("d03", "D decode", "unknown declared CTE (e.g. 'x-unknown'): what does decode=True return?")
def d03():
    raw = (
        b"Content-Type: text/plain\r\n"
        b"Content-Transfer-Encoding: x-unknown\r\n"
        b"\r\n"
        b"opaque body bytes\r\n"
    )
    m = parse(raw)
    decoded, err, _ = caught(m.get_payload, decode=True)
    content, err2, _ = caught(m.get_content)
    return [
        f"get_content_charset() = {m.get_content_charset()!r}",
        f"get_payload(decode=True)" + (f" raised {err}" if err else f" = {decoded!r}"),
        f"get_content()" + (f" raised {err2}" if err2 else f" = {content!r}"),
        f"defects = {m.defects!r}",
    ]


# =====================================================================================
# E: message shapes the design names
# =====================================================================================


@measurement("e01", "E shapes", "message/rfc822 with no filename: iter_attachments vs iter_parts")
def e01():
    raw = (
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="b1"\r\n'
        b"\r\n"
        b"--b1\r\n"
        b"Content-Type: text/plain\r\n"
        b"\r\n"
        b"outer body\r\n"
        b"--b1\r\n"
        b"Content-Type: message/rfc822\r\n"
        b"Content-Disposition: inline\r\n"
        b"\r\n"
        b"From: inner@b.c\r\n"
        b"Subject: inner\r\n"
        b"\r\n"
        b"inner body\r\n"
        b"--b1--\r\n"
    )
    m = parse(raw)
    attachments = list(m.iter_attachments())
    parts = list(m.iter_parts())

    def describe(p):
        return (
            f"(type={p.get_content_type()!r}, filename={p.get_filename()!r},"
            f" disposition={p.get_content_disposition()!r}, cid={p.get('Content-ID')!r})"
        )

    return [
        f"iter_attachments: {[describe(p) for p in attachments]!r}",
        f"iter_parts: {[p.get_content_type() for p in parts]!r}",
        f"walk: {[p.get_content_type() for p in m.walk()]!r}",
        f"n attachments = {len(attachments)} (1 would mean the filename-less rfc822 counts)",
    ]


@measurement("e02", "E shapes", "text/calendar in multipart/alternative next to a .ics attachment with Content-ID")
def e02():
    raw = (
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="outer"\r\n'
        b"\r\n"
        b"--outer\r\n"
        b'Content-Type: multipart/alternative; boundary="inner"\r\n'
        b"\r\n"
        b"--inner\r\n"
        b"Content-Type: text/plain\r\n"
        b"\r\n"
        b"plain invitation\r\n"
        b"--inner\r\n"
        b"Content-Type: text/calendar; method=REQUEST\r\n"
        b"\r\n"
        b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"
        b"--inner--\r\n"
        b"--outer\r\n"
        b"Content-Type: application/octet-stream; name=\"inv.ics\"\r\n"
        b"Content-Disposition: attachment; filename=\"inv.ics\"\r\n"
        b"Content-ID: <inv-1@example.com>\r\n"
        b"Content-Transfer-Encoding: base64\r\n"
        b"\r\n"
        b"QkVHSU46VkNBTEVORFJARQ==\r\n"
        b"--outer--\r\n"
    )
    m = parse(raw)

    def describe(p):
        return (
            f"(type={p.get_content_type()!r}, filename={p.get_filename()!r},"
            f" disposition={p.get_content_disposition()!r}, cid={p.get('Content-ID')!r})"
        )

    attachments = list(m.iter_attachments())
    parts = list(m.iter_parts())
    return [
        f"iter_attachments: {[describe(p) for p in attachments]!r}",
        f"iter_parts: {[p.get_content_type() for p in parts]!r}",
        f"walk: {[p.get_content_type() for p in m.walk()]!r}",
        "question: does the alternative's text/calendar leak into attachments? ->"
        f" {'yes' if any(p.get_content_type() == 'text/calendar' for p in attachments) else 'no'}",
    ]


# =====================================================================================
# F: lxml HTML parsing (quote-rule substrate)
# =====================================================================================


def _lxml():
    try:
        from lxml import etree, html
    except ImportError as exc:
        raise NotMeasurable(f"lxml not installed in this interpreter ({exc})") from None
    return etree, html


@measurement("f01", "F lxml", "Gmail quote block: parse, error_log, and how <style>/<script> appear")
def f01():
    etree, html = _lxml()
    doc = (
        b"<html><body>"
        b'<div class="gmail_quote">'
        b'<blockquote class="gmail_quote" type="cite">'
        b"On Mon, X wrote:<br>"
        b'<div class="gmail_quote">inner quoted</div>'
        b"<style>.x { color: red }</style>"
        b"<script>var a = 1;</script>"
        b"</blockquote></div>"
        b"</body></html>"
    )
    parser = html.HTMLParser()
    tree = html.fromstring(doc, parser=parser)
    text = tree.text_content()
    broken = b"<html><body><div><p>unclosed<span>tail"
    parser2 = html.HTMLParser()
    html.fromstring(broken, parser=parser2)
    return [
        f"blockquotes found = {len(tree.xpath('//blockquote'))};"
        f" attrs = {[dict(el.attrib) for el in tree.xpath('//blockquote')]!r}",
        f"style elements = {[el.tag for el in tree.xpath('//style')]!r};"
        f" script elements = {[el.tag for el in tree.xpath('//script')]!r}",
        f"text_content() includes <style> text? {'color: red' in text};"
        f" includes <script> text? {'var a = 1' in text}",
        f"error_log (valid doc) = {[(e.level_name, e.message) for e in parser.error_log]!r}",
        f"error_log (broken doc) = {[(e.level_name, e.message) for e in parser2.error_log]!r}",
    ]


@measurement("f02", "F lxml", "Outlook divRplyFwdMsg block: xpath reach, error_log on malformed markup")
def f02():
    etree, html = _lxml()
    doc = (
        b"<html><body>"
        b'<div id="divRplyFwdMsg">'
        b'<div class="MsoNormal">quoted text<br>'
        b"</div></div>"
        b'<font size="2">signature without closing font'
        b"</body></html>"
    )
    parser = html.HTMLParser()
    tree = html.fromstring(doc, parser=parser)
    hits = tree.xpath('//*[@id="divRplyFwdMsg"]')
    mso = tree.xpath('//div[@class="MsoNormal"]')
    return [
        f"divRplyFwdMsg found = {len(hits)}; inner MsoNormal count = {len(mso)}",
        f"unclosed <font> element present = {len(tree.xpath('//font'))!r}",
        f"error_log = {[(e.level_name, e.message) for e in parser.error_log]!r}",
        f"text_content() = {tree.text_content()!r}",
    ]


@measurement("f03", "F lxml", "blockquote type=cite: attribute preserved, nesting depth reachable")
def f03():
    etree, html = _lxml()
    doc = (
        b'<blockquote type="cite">level one'
        b'<blockquote type="cite">level two</blockquote>'
        b"</blockquote>"
    )
    parser = html.HTMLParser()
    tree = html.fromstring(doc, parser=parser)
    quotes = tree.xpath("//blockquote")
    return [
        f"n blockquotes = {len(quotes)}; types = {[q.get('type') for q in quotes]!r}",
        f"nesting: parent tag of second = {quotes[1].getparent().tag if len(quotes) > 1 else None!r}",
        f"error_log = {[(e.level_name, e.message) for e in parser.error_log]!r}",
    ]


# =====================================================================================
# G: .msg (owned by tools/real_probe.py)
# =====================================================================================


@measurement("g01", "G msg", ".msg structure: stream names/sizes, property tags (structure only)")
def g01():
    raise NotMeasurable(
        "not measurable in this script: run tools/real_probe.py <path-to-.msg> on a local "
        "sample outside the repo (structure-only; no content is printed)"
    )


# =====================================================================================
# harness
# =====================================================================================


def run(selected):
    statuses = {"measured": 0, "not_measurable": 0, "spike_error": 0}
    for m in selected:
        print(f"## {m.mid} [{m.section}] {m.question}")
        try:
            lines = m.fn()
            status = "measured"
        except NotMeasurable as exc:
            lines = [f"reason: {exc}"]
            status = "not_measurable"
        except Exception as exc:  # noqa: BLE001 - a crash here is a tool bug
            lines = [f"SPIKE ERROR: {type(exc).__name__}: {exc}"]
            status = "spike_error"
        statuses[status] += 1
        print(f"status: {status}")
        for line in lines:
            print(f"  {line}")
        print()
    print(
        f"SUMMARY measured={statuses['measured']}"
        f" not_measurable={statuses['not_measurable']}"
        f" spike_error={statuses['spike_error']}"
    )
    return 1 if statuses["spike_error"] else 0


def main(argv):
    # Recorded output must not depend on the console code page (cp1252 on Windows).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    print(f"python {sys.version.split()[0]} on {sys.platform}")
    if "--list" in argv:
        for m in MEASUREMENTS:
            print(f"{m.mid}  [{m.section}]  {m.question}")
        return 0
    selected_ids = [a for a in argv if not a.startswith("-")]
    if selected_ids:
        known = {m.mid: m for m in MEASUREMENTS}
        unknown = [i for i in selected_ids if i not in known]
        if unknown:
            print(f"unknown measurement id(s): {unknown!r}", file=sys.stderr)
            return 2
        selected = [known[i] for i in selected_ids]
    else:
        selected = MEASUREMENTS
    return run(selected)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
