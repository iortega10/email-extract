"""Turn 1.0d: the HTML decision experiment (build spec decision 1).

This is the spike the HTML parser choice rests on. It runs **candidate A** (the
stdlib ``html.parser`` plus a minimal own stack-based element tree) and **candidate
B** (``lxml.html``, imported here only, never by the package) over

* every committed fixture whose ``text/html`` part the script's own tiny,
  walker-independent MIME extractor finds, and
* the seven synthetic quote snippets of the quote catalogue (verbatim in
  :data:`QUOTE_SNIPPETS`).

Per input and per candidate it records the event sequence, the element tree (tag,
attributes, child count, the projected-text span each element covers, its ``cid:``
references), the projection text and a hash of each. For B it also records the
libxml2 and lxml versions and the parser's ``error_log``.

The projection rule (stated once, used by both candidates): **the concatenation, in
document order, of every text node whose ancestors exclude ``<style>`` and
``<script>``, verbatim -- whitespace and case are preserved, character references are
resolved.** The A event sequence is the parser's own callback sequence
``(event, text, get_starttag_text())``; the B event sequence is the same shape derived
from B's element tree, because libxml2 exposes a tree and not callbacks.

The decision rule (decision 1): **B is chosen only if its tree puts every quote
container at the same node -- same tag path, same projected-text span -- as A on the
quote snippets.** Otherwise A is chosen with the named unclosed-container rule
:data:`UNCLOSED_CONTAINER_RULE`, which records the gap
``body.html_quote_rule_gap`` instead of silently closing the container.

Run ``python tools/html_experiment.py`` for a summary, or ``--json`` for the machine
report (the test uses ``--json`` under both interpreters and compares candidate A).
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"

#: The named gap the unclosed-container rule records (registered in the design).
GAP_HTML_QUOTE_RULE_GAP = "body.html_quote_rule_gap"

#: The exact wording of A's unclosed-container rule (decision 1, "if neither is clean").
UNCLOSED_CONTAINER_RULE = (
    "An unclosed quote container is recorded, never closed: the element tree keeps "
    "the container open to the end of its parent, its projected-text span ends at the "
    "end of the projection, every following text node stays inside that span, and the "
    "DOM quote rule records the gap body.html_quote_rule_gap instead of emitting a "
    "synthetic end tag. libxml2's repair (which auto-closes the element and can move "
    "the following text out of the container) is deliberately not used."
)

_VOID_ELEMENTS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
_SKIPPED_TEXT_ELEMENTS = frozenset({"style", "script"})
_WRAPPER_TAGS = frozenset({"#document", "html", "head", "body"})

#: The seven quote snippets the quote catalogue will need (the quote fixtures do not
#: exist yet; creating one is not this turn's to do).
QUOTE_SNIPPETS: dict[str, bytes] = {
    "blockquote": b"<blockquote>Earlier message text.</blockquote><p>New reply.</p>",
    "gmail_quote": b'<div class="gmail_quote">Earlier message text.</div><p>New reply.</p>',
    "outlook_divRplyFwdMsg": (
        b'<div id="divRplyFwdMsg">Earlier message text.</div><p>New reply.</p>'
    ),
    "unclosed_blockquote": (
        b"<blockquote>Earlier message text.<p>New reply after the unclosed container.</p>"
    ),
    "misnested_b_i": b"<p><b>bold <i>and italic</b> still italic</i> tail</p>",
    "table_in_blockquote": (
        b"<blockquote><table><tr><td>cell text</td></tr></table></blockquote>"
        b"<p>New reply.</p>"
    ),
    "br_run": b"<p>line one<br><br>line three<br>line four</p>",
}

#: Which snippet holds a quote container, and how to recognise that container.
QUOTE_CONTAINERS: dict[str, tuple[str, object]] = {
    "blockquote": ("blockquote", lambda node: node.tag == "blockquote"),
    "gmail_quote": (
        "div.gmail_quote",
        lambda node: node.tag == "div"
        and "gmail_quote" in dict(node.attrs).get("class", "").split(),
    ),
    "outlook_divRplyFwdMsg": (
        "div#divRplyFwdMsg",
        lambda node: node.tag == "div" and dict(node.attrs).get("id") == "divRplyFwdMsg",
    ),
    "unclosed_blockquote": ("blockquote", lambda node: node.tag == "blockquote"),
    "table_in_blockquote": ("blockquote", lambda node: node.tag == "blockquote"),
}


# ------------------------------------------------------------------ the tree


@dataclass
class Node:
    """One element: its tag, its attributes, its projected-text span, its cid refs."""

    tag: str
    attrs: tuple[tuple[str, str], ...]
    parent: "Node | None" = None
    children: list["Node"] = field(default_factory=list)
    start: int = 0
    end: int = 0
    closed: bool = False
    cid_refs: set[str] = field(default_factory=set)

    def subtree_cid_refs(self) -> set[str]:
        found = set(self.cid_refs)
        for child in self.children:
            found |= child.subtree_cid_refs()
        return found


class _Projection:
    """The appended text and its running length."""

    def __init__(self) -> None:
        self._chunks: list[str] = []
        self.length = 0

    def append(self, text: str) -> None:
        self._chunks.append(text)
        self.length += len(text)

    def text(self) -> str:
        return "".join(self._chunks)


def _tag_path(node: Node) -> list[str]:
    """The tag path from the root, wrapper tags (``html``/``body``/``head``) dropped."""
    path: list[str] = []
    current: Node | None = node
    while current is not None:
        path.append(current.tag)
        current = current.parent
    path.reverse()
    index = 0
    while index < len(path) and path[index] in _WRAPPER_TAGS:
        index += 1
    return path[index:]


def _record(node: Node) -> dict:
    """The node's recorded shape: tag, attrs, child count, span, cid refs, closed."""
    return {
        "tag": node.tag,
        "attrs": [list(pair) for pair in node.attrs],
        "children": len(node.children),
        "text_span": [node.start, node.end],
        "cid_refs": sorted(node.subtree_cid_refs()),
        "closed": node.closed,
    }


def _walk(node: Node) -> list[Node]:
    out = [node]
    for child in node.children:
        out.extend(_walk(child))
    return out


def _hash(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


# --------------------------------------------------------- candidate A: html.parser


class _CandidateA(HTMLParser):
    """``HTMLParser`` plus a minimal stack tree (void elements, implied ends only)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.events: list[tuple] = []
        self.projection = _Projection()
        self.root = Node("#document", ())
        self._stack: list[Node] = [self.root]
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        self._start(tag, attrs, "starttag")

    def handle_startendtag(self, tag: str, attrs) -> None:
        node = self._start(tag, attrs, "startendtag")
        node.end = self.projection.length
        node.closed = True

    def _start(self, tag: str, attrs, event: str) -> Node:
        pairs = tuple((name, "" if value is None else value) for name, value in attrs)
        node = Node(tag, tuple(sorted(pairs)), parent=self._stack[-1])
        node.start = self.projection.length
        self._stack[-1].children.append(node)
        for name, value in pairs:
            if value.lower().startswith("cid:"):
                node.cid_refs.add(value)
        self.events.append((event, tag, pairs, self.get_starttag_text()))
        if tag in _VOID_ELEMENTS:
            node.end = node.start
            node.closed = True
            return node
        self._stack.append(node)
        if tag in _SKIPPED_TEXT_ELEMENTS:
            self._skip_depth += 1
        return node

    def handle_endtag(self, tag: str) -> None:
        self.events.append(("endtag", tag, self.get_starttag_text()))
        depth = len(self._stack)
        for index in range(depth - 1, 0, -1):
            if self._stack[index].tag == tag:
                while len(self._stack) > index:
                    node = self._stack.pop()
                    if not node.closed:
                        node.end = self.projection.length
                        node.closed = True
                    if node.tag in _SKIPPED_TEXT_ELEMENTS:
                        self._skip_depth -= 1
                return

    def handle_data(self, data: str) -> None:
        self.events.append(("data", data, self.get_starttag_text()))
        if self._skip_depth == 0:
            self.projection.append(data)

    def handle_comment(self, data: str) -> None:
        self.events.append(("comment", data, self.get_starttag_text()))

    def handle_decl(self, decl: str) -> None:
        self.events.append(("decl", decl, self.get_starttag_text()))

    def handle_pi(self, data: str) -> None:
        self.events.append(("pi", data, self.get_starttag_text()))

    def finish(self) -> None:
        while len(self._stack) > 1:
            node = self._stack.pop()
            if not node.closed:
                node.end = self.projection.length
                node.closed = False  # unclosed: recorded, never closed
        self.root.end = self.projection.length
        self.root.closed = True


# ------------------------------------------------------------- candidate B: lxml


def _build_b(element, parent: Node, projection: _Projection, skip_depth: int) -> None:
    tag = element.tag if isinstance(element.tag, str) else "#comment"
    attrs = tuple(sorted((name, value) for name, value in element.attrib.items()))
    node = Node(tag, attrs, parent=parent)
    node.start = projection.length
    parent.children.append(node)
    for _name, value in attrs:
        if value.lower().startswith("cid:"):
            node.cid_refs.add(value)
    local_skip = skip_depth + (1 if tag in _SKIPPED_TEXT_ELEMENTS else 0)
    if element.text and local_skip == 0:
        projection.append(element.text)
    for child in element.iterchildren():
        _build_b(child, node, projection, local_skip)
        if child.tail and local_skip == 0:
            projection.append(child.tail)
    node.end = projection.length
    node.closed = True


def _candidate_b(html_text: str) -> tuple[dict | None, Node | None]:
    """The B record and its tree root, or ``(None, None)`` when lxml is absent."""
    try:
        import lxml.etree as etree
        import lxml.html as lxml_html
    except Exception:  # pragma: no cover - environment dependent
        return None, None
    parser = lxml_html.HTMLParser()
    root = lxml_html.document_fromstring(html_text, parser=parser)
    projection = _Projection()
    document = Node("#document", ())
    _build_b(root, document, projection, 0)
    document.end = projection.length
    document.closed = True
    nodes = _walk(document)
    return (
        _record_candidate(
            events=_b_events(document),
            nodes=nodes,
            projection=projection,
            extra={
                "libxml2_version": list(etree.LIBXML_VERSION),
                "lxml_version": ".".join(str(part) for part in etree.LXML_VERSION),
                "error_log": str(parser.error_log),
            },
        ),
        document,
    )


def _b_events(document: Node) -> list[tuple]:
    """B's tree as a start/end event sequence (libxml2 offers a tree, not callbacks)."""
    events: list[tuple] = []

    def walk(node: Node) -> None:
        for child in node.children:
            events.append(("starttag", child.tag, child.attrs, None))
            walk(child)
            if child.tag not in _VOID_ELEMENTS:
                events.append(("endtag", child.tag, None))

    walk(document)
    return events


def _record_candidate(
    *, events: list[tuple], nodes: list[Node], projection: _Projection, extra: dict
) -> dict:
    record = {
        "event_sequence_hash": _hash([[list(event), ] for event in events]),
        "tree": [_record(node) for node in nodes],
        "tree_hash": _hash([_record(node) for node in nodes]),
        "projection": projection.text(),
        "projection_hash": hashlib.sha256(projection.text().encode("utf-8")).hexdigest(),
    }
    record.update(extra)
    return record


# ----------------------------------------------------- fixture HTML extraction


def _split_part(raw: bytes):
    """``(headers dict lowercased, body bytes)`` for one MIME part, or ``None``."""
    split = raw.find(b"\r\n\r\n")
    skipped = 4
    if split == -1:
        split = raw.find(b"\n\n")
        skipped = 2
    if split == -1:
        return {}, raw
    head = raw[:split].decode("latin-1")
    headers: dict[str, str] = {}
    for line in head.splitlines():
        if ":" in line:
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()
    return headers, raw[split + skipped :]


def _media_type(headers: dict[str, str]) -> str:
    return headers.get("content-type", "").split(";", 1)[0].strip().lower()


def _boundary(headers: dict[str, str]) -> str | None:
    content_type = headers.get("content-type", "")
    for piece in content_type.split(";")[1:]:
        name, _, value = piece.partition("=")
        if name.strip().lower() == "boundary":
            return value.strip().strip('"')


def _decode_part(headers: dict[str, str], body: bytes) -> str:
    charset = "utf-8"
    content_type = headers.get("content-type", "")
    for piece in content_type.split(";")[1:]:
        name, _, value = piece.partition("=")
        if name.strip().lower() == "charset":
            charset = value.strip().strip('"') or "utf-8"
    try:
        return body.decode(charset)
    except (LookupError, UnicodeDecodeError):
        return body.decode("latin-1")


def html_parts(raw: bytes) -> list[str]:
    """Every ``text/html`` part's decoded body, from the raw message bytes.

    A tiny, independent MIME walker -- its own header/body split and boundary scan,
    deliberately sharing no code with the package walker (the experiment must not use
    the thing it is deciding for).
    """
    headers, body = _split_part(raw)
    media = _media_type(headers)
    if media == "text/html":
        return [_decode_part(headers, body)]
    if media.startswith("multipart/"):
        boundary = _boundary(headers)
        if not boundary:
            return []
        marker = b"--" + boundary.encode("latin-1")
        found: list[str] = []
        for piece in body.split(marker)[1:]:
            if piece[:2] == b"--":
                break
            piece = piece.lstrip(b"\r\n")
            found.extend(html_parts(piece))
        return found
    return []


def html_fixture_names() -> list[str]:
    """Committed ``.eml`` fixtures (excluding ``real/``) that carry a ``text/html`` part."""
    names: list[str] = []
    for path in sorted(FIXTURES.rglob("*.eml")):
        if "real" in path.relative_to(FIXTURES).parts:
            continue
        try:
            raw = path.read_bytes()
        except OSError:  # pragma: no cover - unreadable file
            continue
        if html_parts(raw):
            names.append(path.relative_to(ROOT).as_posix())
    return names


# ------------------------------------------------------------------- the run


def _run_a(html_text: str) -> tuple[dict, Node]:
    parser = _CandidateA()
    parser.feed(html_text)
    parser.close()
    parser.finish()
    nodes = _walk(parser.root)
    return (
        _record_candidate(
            events=parser.events, nodes=nodes, projection=parser.projection, extra={}
        ),
        parser.root,
    )


def run() -> dict:
    """The full, deterministic experiment report."""
    inputs: list[dict] = []
    roots: dict[str, tuple[Node, Node | None]] = {}
    for name in html_fixture_names():
        for index, html_text in enumerate(html_parts((ROOT / name).read_bytes())):
            key = f"fixture:{name}#{index}"
            inputs.append(_input_record(key, html_text, roots))
    for name, html_bytes in QUOTE_SNIPPETS.items():
        inputs.append(_input_record(f"snippet:{name}", html_bytes.decode("utf-8"), roots))

    quote_results: dict[str, dict] = {}
    unclosed_clean: dict[str, bool | None] = {}
    for name, (selector_name, matches) in QUOTE_CONTAINERS.items():
        key = f"snippet:{name}"
        a_root, b_root = roots[key]
        record = next(item for item in inputs if item["name"] == key)
        a_locator = _locate(a_root, matches)
        b_locator = _locate(b_root, matches)
        a_clean = _does_not_swallow(a_locator, len(record["A"]["projection"]))
        b_clean = (
            _does_not_swallow(b_locator, len(record["B"]["projection"]))
            if record["B"]
            else None
        )
        quote_results[name] = {
            "selector": selector_name,
            "A": a_locator,
            "B": b_locator,
            "match": a_locator == b_locator and a_locator is not None,
            "A_clean": a_clean,
            "B_clean": b_clean,
        }
        if name == "unclosed_blockquote":
            unclosed_clean = {"A": a_clean, "B": b_clean}

    b_available = any(item["B"] is not None for item in inputs)
    closed_match = all(
        result["match"] for name, result in quote_results.items() if name != "unclosed_blockquote"
    )
    # Decision 1: B is chosen only if it places every quote container at the same node as A
    # AND neither candidate swallows the following text through the unclosed container.
    # Measured: BOTH A and B leave the unclosed blockquote open to the end (neither is
    # clean), so A is used with the named unclosed-container rule.
    b_clean = b_available and closed_match and bool(unclosed_clean.get("B"))
    neither_clean = not bool(unclosed_clean.get("A")) and not bool(unclosed_clean.get("B"))
    decision = "B" if b_clean else "A"

    return {
        "cpython": ".".join(str(part) for part in sys.version_info[:3]),
        "cpython_minor": ".".join(str(part) for part in sys.version_info[:2]),
        "implementation": sys.implementation.name,
        "lxml": (
            {
                "available": True,
                "lxml_version": inputs[0]["B"]["lxml_version"],
                "libxml2_version": inputs[0]["B"]["libxml2_version"],
            }
            if b_available
            else {"available": False, "reason": "lxml_not_installed"}
        ),
        "projection_rule": (
            "concatenation, in document order, of every text node whose ancestors "
            "exclude <style> and <script>, verbatim (whitespace and case preserved, "
            "character references resolved)"
        ),
        "inputs": inputs,
        "quote_containers": quote_results,
        "closed_snippets_match": closed_match,
        "neither_clean": neither_clean,
        "decision": decision,
        "decision_rule": (
            "B is chosen only if it places every quote container at the same node "
            "(tag path, projected-text span) as A on the closed quote snippets AND "
            "neither candidate swallows the following text through an unclosed "
            "container; otherwise neither is clean and A is used with the named "
            "unclosed-container rule"
        ),
        "unclosed_container_rule": UNCLOSED_CONTAINER_RULE if decision == "A" else None,
        "gap_id": GAP_HTML_QUOTE_RULE_GAP if decision == "A" else None,
    }


def _does_not_swallow(locator: dict | None, projection_length: int) -> bool:
    """True if the container was closed before the end -- it does not swallow the tail."""
    if locator is None:
        return False
    return locator["span"][1] < projection_length


def _input_record(name: str, html_text: str, roots: dict) -> dict:
    encoded = html_text.encode("utf-8")
    a_record, a_root = _run_a(html_text)
    b_record, b_root = _candidate_b(html_text)
    roots[name] = (a_root, b_root)
    return {
        "name": name,
        "html_sha256": hashlib.sha256(encoded).hexdigest(),
        "html_length": len(html_text),
        "A": a_record,
        "B": b_record,
    }


def _locate(root: Node | None, matches) -> dict | None:
    """The first node ``matches`` accepts, with its tag path and projected-text span."""
    if root is None:
        return None

    def search(node: Node) -> dict | None:
        for child in node.children:
            if matches(child):
                return {"path": _tag_path(child), "span": [child.start, child.end]}
            found = search(child)
            if found is not None:
                return found
        return None

    return search(root)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    report = run()
    if "--json" in args:
        print(json.dumps(report, sort_keys=True, indent=2))
        return 0
    print(f"html_experiment: CPython {report['cpython']} ({report['implementation']})")
    print(f"  inputs: {len(report['inputs'])}")
    print(f"  lxml: {report['lxml']}")
    for item in report["inputs"]:
        a = item["A"]
        b = item["B"]
        print(
            f"  {item['name']}: A event={a['event_sequence_hash'][:12]} "
            f"proj={a['projection_hash'][:12]}" + (
                f" | B proj={b['projection_hash'][:12]}" if b else " | B not run"
            )
        )
    for name, quote in report["quote_containers"].items():
        print(f"  quote {name}: match={quote['match']} A={quote['A']} B={quote['B']}")
    print(f"  decision: {report['decision']}")
    if report["decision"] == "A":
        print(f"  rule: {UNCLOSED_CONTAINER_RULE}")
        print(f"  gap: {GAP_HTML_QUOTE_RULE_GAP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
