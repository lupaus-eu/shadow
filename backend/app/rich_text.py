"""The formatted-description subset (Yearclock V2 P11, ADR-0033).

Bold ``**x**``, italic ``*x*``, ``- `` bullet and ``1. `` numbered lists, ``[text](https://…)`` links,
bare web addresses, paragraphs, and line breaks. Everything else is literal text, a backslash before
punctuation shows that character, and no HTML is ever produced. The frontend has a matching parser
(``frontend/src/yearclock/rich-text.ts``); both are tested against the same cases.

A parsed description is a list of blocks:

- ``{"p": [line, ...]}``: a paragraph, one list of inline nodes per line,
- ``{"ul": [item, ...]}`` and ``{"ol": [item, ...]}``: lists, one list of inline nodes per item.

An inline node is a string, ``{"b": [nodes]}``, ``{"i": [nodes]}``, or ``{"a": text, "href": address}``.
"""
import re
from typing import Any

Node = Any
PUNCTUATION = set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")
URL = re.compile(r'https?://[^\s<>"]+')
LINK = re.compile(r"\[([^\[\]]+)\]\((https?://[^\s)]+)\)")
TRAILING = re.compile(r"[).,;:!?\]]+$")
BULLET = re.compile(r"^- (.*)$")
NUMBERED = re.compile(r"^(\d{1,3})\. (.*)$")


def _push(nodes: list[Node], text: str) -> None:
    if not text:
        return
    if nodes and isinstance(nodes[-1], str):
        nodes[-1] += text
    else:
        nodes.append(text)


def _closing(text: str, start: int, marker: str) -> int:
    """Index of the unescaped ``marker`` that closes one opened before ``start``, or -1."""
    index = start
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if marker == "**" and text.startswith("**", index):
            return index
        if marker == "*" and char == "*":
            if text.startswith("**", index):
                index += 2
                continue
            return index
        index += 1
    return -1


def inline(text: str) -> list[Node]:
    nodes: list[Node] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text) and text[index + 1] in PUNCTUATION:
            _push(nodes, text[index + 1])
            index += 2
            continue
        if char == "*":
            marker = "**" if text.startswith("**", index) else "*"
            end = _closing(text, index + len(marker), marker)
            body = text[index + len(marker): end] if end != -1 else ""
            if end != -1 and body and not body[0].isspace() and not body[-1].isspace():
                nodes.append({"b" if marker == "**" else "i": inline(body)})
                index = end + len(marker)
                continue
            _push(nodes, marker)
            index += len(marker)
            continue
        if char == "[":
            match = LINK.match(text, index)
            if match:
                nodes.append({"a": match.group(1), "href": match.group(2)})
                index = match.end()
                continue
        if char == "h":
            match = URL.match(text, index)
            if match:
                address = match.group(0)
                trailing = TRAILING.search(address)
                if trailing:
                    address = address[: trailing.start()]
                if address:
                    nodes.append({"a": address, "href": address})
                    index += len(address)
                    continue
        _push(nodes, char)
        index += 1
    return nodes


def parse(text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for line in lines:
        bullet, numbered = BULLET.match(line), NUMBERED.match(line)
        if bullet or numbered:
            kind = "ul" if bullet else "ol"
            item = inline((bullet or numbered).group(1) if bullet else numbered.group(2))
            if blocks and kind in blocks[-1]:
                blocks[-1][kind].append(item)
            else:
                blocks.append({kind: [item]})
        elif line.strip() == "":
            if blocks and "gap" not in blocks[-1]:
                blocks.append({"gap": True})
        else:
            if blocks and "p" in blocks[-1]:
                blocks[-1]["p"].append(inline(line))
            else:
                blocks.append({"p": [inline(line)]})
    return [block for block in blocks if "gap" not in block]


def _plain(nodes: list[Node]) -> str:
    out = []
    for node in nodes:
        if isinstance(node, str):
            out.append(node)
        elif "b" in node:
            out.append(_plain(node["b"]))
        elif "i" in node:
            out.append(_plain(node["i"]))
        else:
            out.append(node["href"] if node["a"] == node["href"] else f"{node['a']} ({node['href']})")
    return "".join(out)


def plain_text(text: str | None, description_format: str = "markdown") -> str:
    """The text without markers: for search, exports, the calendar file, email, and print."""
    if not text:
        return ""
    if description_format != "markdown":
        return text
    parts = []
    for block in parse(text):
        if "p" in block:
            parts.append("\n".join(_plain(line) for line in block["p"]))
        elif "ul" in block:
            parts.append("\n".join(f"- {_plain(item)}" for item in block["ul"]))
        else:
            parts.append("\n".join(f"{number}. {_plain(item)}" for number, item in enumerate(block["ol"], start=1)))
    return "\n\n".join(parts)
