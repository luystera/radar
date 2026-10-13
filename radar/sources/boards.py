"""Deterministic clients for the public ATS board APIs.

IMPORTANT — where these can run. Greenhouse, Lever and Ashby all answer these
endpoints without auth, and they are the cleanest source of truth for a
requisition (published/updated timestamps, an explicit application_deadline,
the full body). But in the Anthropic cloud container the egress proxy answers
403 to CONNECT for these hosts, so calling them from code there is a policy
denial, not a transient failure, and must not be retried or routed around.

So: these work when you run the pipeline on your own machine. In the scheduled
cloud run they raise EgressBlocked, and the agent reads the same endpoints with
WebFetch and feeds the result back via `radar verify`. That is the whole
reason the verify CLI exists.
"""
from __future__ import annotations
import json
import re
import ssl
import urllib.error
import urllib.request
from typing import Any

_CA = "/root/.ccr/ca-bundle.crt"


class EgressBlocked(RuntimeError):
    """The environment's egress policy refused this host (proxy 403/407)."""


def _get(url: str, timeout: int = 25) -> Any:
    try:
        ctx = ssl.create_default_context(cafile=_CA)
    except Exception:
        ctx = None
    req = urllib.request.Request(url, headers={"User-Agent": "radar/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.URLError as e:
        msg = str(e)
        if "403" in msg or "407" in msg or "Tunnel connection failed" in msg:
            raise EgressBlocked(
                f"egress policy refused {url!r}. Run this locally, or let the "
                f"agent fetch it and pipe the result into `radar verify`."
            ) from e
        raise


def strip_html(s: str) -> str:
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s or "", flags=re.S | re.I)
    s = re.sub(r"<li[^>]*>", "\n• ", s, flags=re.I)
    s = re.sub(r"</(p|div|li|h\d)>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    import html as H
    return re.sub(r"[ \t]+", " ", H.unescape(s)).strip()


def greenhouse(board: str, job_id: str) -> dict:
    d = _get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}")
    return {
        "title": d.get("title", ""),
        "location": (d.get("location") or {}).get("name", ""),
        "first_published": d.get("first_published"),
        "updated_at": d.get("updated_at"),
        "deadline": d.get("application_deadline"),
        "body": strip_html(d.get("content", "")),
        "live": "live",
    }


def lever(site: str, post_id: str) -> dict:
    d = _get(f"https://api.lever.co/v0/postings/{site}/{post_id}")
    cat = d.get("categories") or {}
    return {
        "title": d.get("text", ""),
        "location": cat.get("location", ""),
        "first_published": d.get("createdAt"),
        "updated_at": None,
        "deadline": None,
        "body": strip_html(d.get("descriptionPlain") or d.get("description", "")),
        "live": "live",
    }


def ashby(board: str, job_id: str) -> dict:
    d = _get(f"https://api.ashbyhq.com/posting-api/job-board/{board}")
    for j in d.get("jobs", []):
        if j.get("id") == job_id or job_id in (j.get("jobUrl") or ""):
            return {
                "title": j.get("title", ""),
                "location": j.get("location", ""),
                "first_published": j.get("publishedAt"),
                "updated_at": None,
                "deadline": None,
                "body": strip_html(j.get("descriptionHtml") or ""),
                "live": "live" if j.get("isListed") else "closed",
            }
    return {"live": "closed", "body": "", "title": "", "location": ""}


BOARD_PATTERNS = (
    (re.compile(r"(?:job-)?boards?(?:-api)?\.greenhouse\.io/(?:embed/job_board\?for=)?([\w-]+)/jobs/(\d+)"), "greenhouse"),
    (re.compile(r"jobs\.lever\.co/([\w.-]+)/([0-9a-f-]{8,})"), "lever"),
    (re.compile(r"jobs\.ashbyhq\.com/([\w.-]+)/([0-9a-f-]{8,})"), "ashby"),
)


def route(url: str) -> tuple[str, str, str] | None:
    """Map an application URL to (kind, board, id) when a public API exists."""
    for pat, kind in BOARD_PATTERNS:
        m = pat.search(url or "")
        if m:
            return kind, m.group(1), m.group(2)
    return None


def fetch_req(url: str) -> dict:
    r = route(url)
    if not r:
        raise ValueError(f"no public board API for {url!r}")
    kind, board, jid = r
    return {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}[kind](board, jid)
