"""Parsers for the three aggregator trackers.

All three are GitHub raw markdown and are reachable from code. Each has its
own table schema, and each lies in its own way about dates, so the parsers
record the source and leave recency judgement to config.UNTRUSTED_AGE.
"""
from __future__ import annotations
import html
import re
import ssl
import urllib.request
from dataclasses import dataclass
from typing import Iterator

from ..config import TRACKERS

_CA = "/root/.ccr/ca-bundle.crt"


@dataclass
class TrackerRow:
    source: str
    company: str
    title: str
    location: str
    url: str
    age: str = ""
    salary: str = ""


def fetch(url: str, timeout: int = 30) -> str:
    try:
        ctx = ssl.create_default_context(cafile=_CA)
    except Exception:
        ctx = None
    req = urllib.request.Request(url, headers={"User-Agent": "radar/0.1"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", "replace")


def _cells(line: str) -> list[str]:
    s = line.strip()
    if not s.startswith("|"):
        return []
    parts = s.split("|")[1:-1] if s.endswith("|") else s.split("|")[1:]
    return [p.strip() for p in parts]


def _is_rule(line: str) -> bool:
    return bool(re.fullmatch(r"\|[\s:\-|]+\|?", line.strip()))


def _text(cell: str) -> str:
    """Strip markdown bold and HTML tags, keeping </br> as a separator."""
    c = re.sub(r"</?br\s*/?>", " / ", cell, flags=re.I)
    c = re.sub(r"<[^>]+>", "", c)
    c = c.replace("**", "").replace("__", "")
    return re.sub(r"\s+", " ", html.unescape(c)).strip()


def _href(cell: str) -> str:
    m = re.search(r'<a\s+href="([^"]+)"', cell, re.I)
    if m:
        return html.unescape(m.group(1))
    m = re.search(r"\]\((https?://[^)\s]+)\)", cell)      # markdown link
    if m:
        return html.unescape(m.group(1))
    m = re.search(r"(https?://\S+)", cell)
    return html.unescape(m.group(1)) if m else ""


def _strip_utm(url: str) -> str:
    return re.sub(r"[?&]utm_source=[^&]*", "", url)


def _tables(md: str) -> Iterator[tuple[list[str], list[list[str]]]]:
    lines = md.split("\n")
    i = 0
    while i < len(lines):
        head = _cells(lines[i])
        if len(head) >= 4 and i + 1 < len(lines) and _is_rule(lines[i + 1]):
            rows, j = [], i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                c = _cells(lines[j])
                if c and not _is_rule(lines[j]):
                    rows.append(c)
                j += 1
            yield head, rows
            i = j
        else:
            i += 1


def _pick(head: list[str], *names: str) -> int | None:
    low = [_text(h).lower() for h in head]
    for n in names:
        for k, h in enumerate(low):
            if n == h:
                return k
    for n in names:
        for k, h in enumerate(low):
            if n in h:
                return k
    return None


def parse(source: str, md: str) -> list[TrackerRow]:
    out: list[TrackerRow] = []
    for head, rows in _tables(md):
        ic = _pick(head, "company")
        it = _pick(head, "position", "role")
        il = _pick(head, "location")
        iu = _pick(head, "posting", "application/link", "apply", "link")
        ia = _pick(head, "age", "date posted", "posted")
        isal = _pick(head, "salary")
        if ic is None or it is None:
            continue
        for c in rows:
            if max(x for x in (ic, it, il or 0, iu or 0) if x is not None) >= len(c):
                continue
            company = _text(c[ic])
            title = _text(c[it])
            if not company or not title:
                continue
            url = _strip_utm(_href(c[iu])) if iu is not None and iu < len(c) else ""
            out.append(TrackerRow(
                source=source,
                company=company,
                title=title,
                location=_text(c[il]) if il is not None and il < len(c) else "",
                url=url,
                age=_text(c[ia]) if ia is not None and ia < len(c) else "",
                salary=_text(c[isal]) if isal is not None and isal < len(c) else "",
            ))
    return out


def load_all(offline_dir: str | None = None) -> dict[str, list[TrackerRow]]:
    res: dict[str, list[TrackerRow]] = {}
    for name, url in TRACKERS.items():
        if offline_dir:
            md = open(f"{offline_dir}/{name}.md", encoding="utf-8").read()
        else:
            md = fetch(url)
        res[name] = parse(name, md)
    return res
