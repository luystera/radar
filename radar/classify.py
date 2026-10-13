"""Deterministic *flagging*, never judgement.

The valuable part of this digest is reading a qualification bullet properly:
"1-3 years of full-time professional work experience post-graduation" is a
wall, "0-1 years" is a ceiling, and "or equivalent practical experience" is a
route. No regex decides that. What code can do is find the candidate bullets
and surface the distinguishing features, so the agent spends its judgement on
a short list instead of re-reading a whole page.

Every function here returns evidence. `verdict` stays None until an agent or a
human sets it.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, asdict

# "N years", "N+ years", "N-M years"
YEARS = re.compile(
    r"(?P<lo>\d+)\s*(?:\+|\s*(?:-|–|to)\s*(?P<hi>\d+))?\s*(?:additional\s+)?year", re.I
)
# Phrases that turn a count into an alternative route rather than a floor.
ROUTES = (
    "or equivalent", "equivalent practical experience", "academic project",
    "personal project", "class project", "coursework", "open source",
    "open-source", "research", "hackathon", "co-op", "or projects",
    "personal work", "club",
)
# Phrases that make a count unambiguously professional and therefore a wall.
WALLS = ("post-graduation", "postgraduation", "professional", "commercial",
         "industry", "full-time professional")
CEILING = ("no more than", "up to", "less than", "fewer than", "at most")

MONTHS = ("january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december")
# Start months that fall before a May 2027 graduation.
EARLY_STARTS = ("january", "february", "march", "april")


@dataclass
class Gate:
    text: str
    lo: int | None = None
    hi: int | None = None
    kind: str = "unclear"     # ceiling | floor | route | unclear
    why: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _sentences(body: str) -> list[str]:
    parts = re.split(r"(?:\n+|(?<=[.;])\s+|•|\u2022)", body or "")
    return [re.sub(r"\s+", " ", p).strip() for p in parts if p and p.strip()]


def find_gates(body: str) -> list[Gate]:
    """Surface every experience-count bullet with the features that decide
    whether it is a wall, a ceiling, or a route."""
    gates: list[Gate] = []
    for s in _sentences(body):
        if "experien" not in s.lower() and "year" not in s.lower():
            continue
        m = YEARS.search(s)
        if not m:
            continue
        low = s.lower()
        lo = int(m.group("lo"))
        hi = int(m.group("hi")) if m.group("hi") else None
        route = next((r for r in ROUTES if r in low), None)
        wall = next((w for w in WALLS if w in low), None)
        ceil = next((c for c in CEILING if c in low), None)

        if route:
            kind, why = "route", f"names an alternative route: {route!r}"
        elif ceil or lo == 0:
            kind, why = "ceiling", (
                f"reads as a ceiling ({ceil!r})" if ceil else "floor is zero"
            )
        elif wall:
            kind, why = "floor", f"professional floor: {wall!r}"
        else:
            kind, why = "unclear", "count with no route and no ceiling wording"
        gates.append(Gate(text=s[:400], lo=lo, hi=hi, kind=kind, why=why))
    return gates


def blocking_gates(body: str) -> list[Gate]:
    """Gates that would actually exclude a candidate with no professional SWE
    experience. Ceilings and routes are not blocking."""
    return [g for g in find_gates(body)
            if g.kind == "floor" or (g.kind == "unclear" and (g.lo or 0) >= 1)]


def internship_gate(body: str) -> Gate | None:
    """A hard internship count with no equivalence clause."""
    for s in _sentences(body):
        low = s.lower()
        if "internship" not in low and "co-op" not in low:
            continue
        if any(r in low for r in ("or equivalent", "equivalent practical")):
            return Gate(text=s[:400], kind="route",
                        why="internship named but an equivalence clause is offered")
        if re.search(r"\b(required|must have|at least (one|two|\d+))\b", low):
            return Gate(text=s[:400], kind="floor",
                        why="internship required with no equivalence clause")
    return None


def cohort_risk(title: str, body: str) -> dict:
    """Flag wrong-cohort candidates. The JPMorgan February/July pair is the
    canonical trap: near-identical reqs, one of which starts before May 2027."""
    blob = f"{title}\n{body}".lower()
    starts = sorted({m for m in EARLY_STARTS if re.search(rf"\b{m}\b\s*20?27", blob)})
    graduate_by = bool(re.search(
        r"graduat\w*\s+(?:by|before)\s+(?:dec|december|jan|january)\w*\s*20?26", blob))
    year_labelled = bool(re.search(r"\b20?27\b", title or ""))
    risky = bool(starts) or graduate_by
    why = []
    if starts:
        why.append("early 2027 start month named: " + ", ".join(starts))
    if graduate_by:
        why.append("requires graduation by late 2026")
    return {
        "risky": risky,
        "year_in_title": year_labelled,
        "early_starts": starts,
        "why": "; ".join(why),
    }


MONEY = re.compile(r"\$\s?(\d{2,3})(?:,(\d{3}))?(?:\s*(k))?", re.I)


def parse_comp(text: str, source: str | None = None) -> dict:
    """Extract a band. Basis matters more than the number: a posting's base and
    a tracker's estimated total comp are not comparable."""
    vals: list[int] = []
    for m in MONEY.finditer(text or ""):
        n = int(m.group(1) + (m.group(2) or ""))
        if m.group(3) or n < 1000:
            n *= 1000
        if 30_000 <= n <= 1_000_000:
            vals.append(n)
    if not vals:
        return {"comp_min": None, "comp_max": None, "comp_basis": None}
    from .config import ESTIMATED_COMP
    basis = "estimated_total" if source in ESTIMATED_COMP else "posting_base"
    lo, hi = min(vals), max(vals)
    if re.search(r"\b(starts at|minimum base|at least)\b", (text or "").lower()):
        basis = "posting_min"
    return {"comp_min": lo, "comp_max": hi, "comp_basis": basis}


def group_for(location: str) -> tuple[str, int | None]:
    """Return (group_label, long_island_miles)."""
    from .config import GROUP_A, GROUP_B, LONG_ISLAND
    low = (location or "").lower()
    for town, miles in LONG_ISLAND.items():
        if town in low:
            return "LI", miles
    if any(k in low for k in GROUP_A):
        return "A", None
    if any(k in low for k in GROUP_B):
        return "B", None
    return "C", None


# A title has to look like a software-writing seat to earn a place in the store.
# Allowlist-primary on purpose: a title with no engineering token is not for this
# digest, and that is a safer default than trying to enumerate every job in the
# world that is not one. The quant and research tokens are here because Goldman
# Strats, Citi's Quantitative Analysis and Renaissance's Research Engineer all
# belong and none of them says "software" in the title.
ROLE_TOKENS = (
    "software", "developer", "engineer", "engineering", "programmer", "swe",
    "sde", "quantitative", "quant", "strat", "research engineer", "data scientist",
    "machine learning", "infrastructure", "platform", "systems", "compiler",
    "firmware", "embedded", "backend", "back-end", "frontend", "front-end",
    "full stack", "fullstack", "devops", "site reliability",
    # Bank and programme shapes that are software seats without saying so. The
    # first unsupervised run cost BlackRock's 2027 Full-Time Analyst Program and
    # Boerboel's speculative channel when these were missing.
    "analyst program", "new analyst", "technology analyst", "analyst, technology",
    "technology development", "graduate program", "graduate programme",
    "opportunistic", "speculative", "rotational",
)
# Titles that carry an engineering token but are not a software-writing seat, or
# are plainly another profession.
NOT_SOFTWARE = (
    "custodial", "janitor", "facilities", "maintenance technician", "driver",
    "nurse", "paralegal", "recruiter", "recruiting", "talent acquisition",
    "sales", "account executive", "account manager", "business development",
    "marketing", "accountant", "accounting", "payroll", "receptionist",
    "security guard", "warehouse", "barista", "cashier", "teller",
    "engineering manager", "director of engineering", "head of engineering",
    "sales engineer", "solutions engineer", "customer success",
    "technical recruiter", "engineering operations",
)


def is_software_role(title: str, body: str = "") -> bool:
    """Whether a title plausibly describes a seat where writing software is the
    output.

    SCOPE, and this matters: this is a gate on TRACKER INTAKE only. It exists
    because the trackers carry every job their sources publish, and a custodial
    posting reached the store on the first unsupervised run. It must never be
    used to audit or prune rows that already carry a verdict or that an agent
    added deliberately — a title like "2027 Full-Time Analyst Program" is a
    software seat at BlackRock and says nothing engineering-ish at all, and
    running this over the whole store deleted it once already.
    """
    t = (title or "").lower()
    if not t:
        return False
    if any(n in t for n in NOT_SOFTWARE):
        return False
    return any(tok in t for tok in ROLE_TOKENS)


def is_internship(title: str, body: str = "") -> bool:
    """Summer-2027 programmes are useless to a May-2027 graduate however they
    are titled; and an 'Associate' seat can be a twelve-week placement."""
    blob = f"{title}\n{body}".lower()
    if re.search(r"\bintern(ship)?\b", blob):
        return True
    if re.search(r"\b(summer|winter)\s*(analyst|associate)\b", blob):
        return True
    if re.search(r"\b(ten|twelve|10|12)[- ]week\b", blob):
        return True
    if re.search(r"\$\s?\d[\d,.]*\s*(per|/)\s*(hour|week)\b", blob):
        return True
    return False
