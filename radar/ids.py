"""Stable role ids.

The convention predates this package: it is the one already written into the
artifact database and into the scheduled task's prompt, so it must not drift.

    <company-slug>-<req-id>

company-slug: company name lowercased, non-alphanumerics stripped, aliased.
req-id:       rentec selectedPosition value; else the LAST run of 4+ digits in
              the URL; else the final path segment, alphanumerics only.
"""
from __future__ import annotations
import html
import re
from urllib.parse import unquote

from .config import ALIASES


def slug(company: str) -> str:
    v = re.sub(r"[^a-z0-9]+", "", html.unescape(company or "").lower())
    return ALIASES.get(v, v)


def req_id(url: str) -> str:
    u = unquote(html.unescape(url or ""))
    m = re.search(r"selectedPosition=([A-Za-z0-9_]+)", u)
    if m:
        return m.group(1).lower()
    nums = re.findall(r"\d{4,}", u)
    if nums:
        return nums[-1]
    parts = [p for p in re.split(r"[/?#]", u) if p]
    tail = parts[-1] if parts else ""
    return re.sub(r"[^a-z0-9]+", "", tail.lower())[:40] or "x"


def role_id(company: str, url: str) -> str:
    return f"{slug(company)}-{req_id(url)}"


_SEG = re.compile(r"^[A-Za-z0-9_\-.~:@+]{1,200}$")


def is_valid(rid: str) -> bool:
    """Role ids double as artifact-database document ids, which must be a
    single path segment in that store's grammar."""
    return bool(rid) and rid not in {".", ".."} and bool(_SEG.match(rid))
