"""SQLite store: the state that used to live inside the page's prose.

Two tables carry the fix for the two things the prose could not do:

  requisitions — current verified facts, one row per req, including the
                 consecutive-clean-read counter that was previously a number
                 the model re-typed from yesterday's sentence.
  events       — append-only history. "What was Five Rings' base on 14 Sept?"
                 is a query here and was unanswerable before.
"""
from __future__ import annotations
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS requisitions (
  role_id       TEXT PRIMARY KEY,
  company       TEXT NOT NULL,
  title         TEXT NOT NULL DEFAULT '',
  url           TEXT NOT NULL DEFAULT '',
  location      TEXT NOT NULL DEFAULT '',
  group_label   TEXT NOT NULL DEFAULT 'C',     -- A | LI | B | C
  li_miles      INTEGER,
  sources       TEXT NOT NULL DEFAULT '[]',    -- json list
  first_seen    TEXT NOT NULL,
  last_seen     TEXT NOT NULL,
  last_verified TEXT,
  clean_reads   INTEGER NOT NULL DEFAULT 0,
  live          TEXT NOT NULL DEFAULT 'unknown', -- live|closed|unknown
  http_status   INTEGER,
  comp_min      INTEGER,
  comp_max      INTEGER,
  comp_basis    TEXT,                          -- posting_base|posting_min|estimated_total
  arrangement   TEXT,                          -- in-person|hybrid|remote|not-stated
  arr_stated    INTEGER NOT NULL DEFAULT 0,
  cohort        TEXT,
  start_date    TEXT,
  gates         TEXT NOT NULL DEFAULT '[]',    -- json list of flagged bullets
  verdict       TEXT,                          -- apply|skip|watch
  verdict_why   TEXT,
  notes         TEXT,
  judged_on     TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  role_id   TEXT NOT NULL,
  ts        TEXT NOT NULL,
  kind      TEXT NOT NULL,   -- discovered|seen|verified|changed|closed|reopened|applied
  detail    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS events_role ON events(role_id, ts);
CREATE TABLE IF NOT EXISTS seen (
  role_id    TEXT PRIMARY KEY,
  first_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ts        TEXT NOT NULL,
  summary   TEXT NOT NULL DEFAULT ''
);
"""

# Fields a verification may update; anything else is rejected so a typo in a
# --json payload fails loudly instead of being silently dropped.
VERIFIABLE = {
    "title", "url", "location", "group_label", "li_miles", "live",
    "http_status", "comp_min", "comp_max", "comp_basis", "arrangement",
    "arr_stated", "cohort", "start_date", "gates", "verdict", "verdict_why",
    "notes",
}


@dataclass
class Req:
    role_id: str
    company: str
    title: str = ""
    url: str = ""
    location: str = ""
    group_label: str = "C"
    li_miles: int | None = None
    sources: list[str] = field(default_factory=list)


class Store:
    def __init__(self, path: str = "radar.db"):
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    # ---------- writes ----------

    def log(self, role_id: str, kind: str, detail: str = "", ts: str | None = None) -> None:
        self.db.execute(
            "INSERT INTO events(role_id, ts, kind, detail) VALUES (?,?,?,?)",
            (role_id, ts or date.today().isoformat(), kind, detail),
        )

    def upsert_seen(self, r: Req, today: str | None = None) -> str:
        """Record that a source saw this req today. Returns 'new' or 'seen'."""
        today = today or date.today().isoformat()
        cur = self.db.execute(
            "SELECT role_id, sources FROM requisitions WHERE role_id=?", (r.role_id,)
        ).fetchone()
        if cur is None:
            known = self.db.execute(
                "SELECT first_seen FROM seen WHERE role_id=?", (r.role_id,)
            ).fetchone()
            first = known["first_seen"] if known else today
            self.db.execute(
                """INSERT INTO requisitions
                   (role_id, company, title, url, location, group_label, li_miles,
                    sources, first_seen, last_seen)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (r.role_id, r.company, r.title, r.url, r.location, r.group_label,
                 r.li_miles, json.dumps(sorted(set(r.sources))), first, today),
            )
            self.db.execute(
                "INSERT OR IGNORE INTO seen(role_id, first_seen) VALUES (?,?)",
                (r.role_id, first),
            )
            if known is None:
                self.log(r.role_id, "discovered", f"{r.company} — {r.title}", today)
            self.db.commit()
            return "new" if known is None else "seen"
        merged = sorted(set(json.loads(cur["sources"]) + list(r.sources)))
        self.db.execute(
            "UPDATE requisitions SET last_seen=?, sources=? WHERE role_id=?",
            (today, json.dumps(merged), r.role_id),
        )
        self.db.commit()
        return "seen"

    def verify(self, role_id: str, fields: dict[str, Any], today: str | None = None) -> list[str]:
        """Apply a verification. Increments clean_reads when live, resets on
        close, and writes one event per changed field. Returns changed keys."""
        today = today or date.today().isoformat()
        row = self.db.execute(
            "SELECT * FROM requisitions WHERE role_id=?", (role_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown role_id: {role_id}")
        bad = set(fields) - VERIFIABLE
        if bad:
            raise ValueError(f"not verifiable: {sorted(bad)}")

        changed: list[str] = []
        for k, v in fields.items():
            if k in ("gates",) and not isinstance(v, str):
                v = json.dumps(v)
            old = row[k]
            if str(old if old is not None else "") != str(v if v is not None else ""):
                changed.append(k)
                self.db.execute(
                    f"UPDATE requisitions SET {k}=? WHERE role_id=?", (v, role_id)
                )
                self.log(role_id, "changed", f"{k}: {old!r} -> {v!r}", today)

        new_live = fields.get("live", row["live"])
        was_live = row["live"]
        if new_live == "live":
            reads = (row["clean_reads"] or 0) + 1
            self.db.execute(
                "UPDATE requisitions SET clean_reads=?, last_verified=? WHERE role_id=?",
                (reads, today, role_id),
            )
            if was_live == "closed":
                self.log(role_id, "reopened", "", today)
            self.log(role_id, "verified", f"clean read #{reads}", today)
        elif new_live == "closed":
            self.db.execute(
                "UPDATE requisitions SET clean_reads=0, last_verified=? WHERE role_id=?",
                (today, role_id),
            )
            if was_live != "closed":
                self.log(role_id, "closed", fields.get("notes", "") or "", today)
        self.db.commit()
        return changed

    # ---------- reads ----------

    def get(self, role_id: str) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM requisitions WHERE role_id=?", (role_id,)
        ).fetchone()

    def all(self, group: str | None = None) -> list[sqlite3.Row]:
        q = "SELECT * FROM requisitions"
        a: tuple = ()
        if group:
            q += " WHERE group_label=?"
            a = (group,)
        q += " ORDER BY company"
        return list(self.db.execute(q, a))

    def curated(self, group: str | None = None) -> list[sqlite3.Row]:
        """What the page shows. The store holds every candidate a tracker ever
        carried — over a thousand — but a requisition earns a place on the page
        only once something has judged it, or because the digest itself found
        it. Everything else is the work list, not the digest.

        Ordering puts what to do first: apply, then watch, then skips."""
        q = ("SELECT * FROM requisitions WHERE (verdict IS NOT NULL "
             "OR sources LIKE '%digest-page%')")
        a: list = []
        if group:
            q += " AND group_label=?"
            a.append(group)
        q += (" ORDER BY CASE verdict WHEN 'apply' THEN 0 WHEN 'watch' THEN 1 "
              "WHEN 'skip' THEN 3 ELSE 2 END, "
              "COALESCE(comp_min,0) DESC, company")
        return list(self.db.execute(q, tuple(a)))

    def actionable(self, group: str | None = None) -> list[sqlite3.Row]:
        """Reqs genuinely open to him: judged apply/watch, or carried and not
        yet judged. Skips and closures do not count."""
        return [r for r in self.curated(group)
                if r["live"] != "closed" and r["verdict"] != "skip"]

    def new_since(self, since: str) -> list[sqlite3.Row]:
        return list(self.db.execute(
            "SELECT * FROM requisitions WHERE first_seen > ? ORDER BY company", (since,)
        ))

    def changes_on(self, day: str) -> list[sqlite3.Row]:
        return list(self.db.execute(
            """SELECT e.*, r.company, r.title FROM events e
               JOIN requisitions r USING(role_id)
               WHERE e.ts = ? AND e.kind IN ('changed','closed','reopened','discovered')
               ORDER BY e.role_id, e.id""", (day,)
        ))

    def history(self, role_id: str) -> list[sqlite3.Row]:
        return list(self.db.execute(
            "SELECT * FROM events WHERE role_id=? ORDER BY id", (role_id,)
        ))

    # ---------- portable state ----------

    def export_state(self) -> dict:
        """Everything that cannot be re-derived.

        The candidate pool (over a thousand unjudged tracker rows) is
        deliberately NOT exported: re-running `sync` rebuilds it deterministically
        from the trackers in a couple of seconds. What no amount of re-syncing
        can rebuild is the judgement and the history -- verdicts, verified comp
        and arrangement, clean-read counters, and every event ever logged. That
        is what travels between runs.
        """
        reqs = [dict(r) for r in self.db.execute(
            "SELECT * FROM requisitions WHERE verdict IS NOT NULL "
            "OR sources LIKE '%digest-page%' OR clean_reads > 0")]
        keep = {r["role_id"] for r in reqs}
        evs = [dict(r) for r in self.db.execute("SELECT * FROM events ORDER BY id")
               if dict(r)["role_id"] in keep]
        runs = [dict(r) for r in self.db.execute("SELECT * FROM runs ORDER BY id")]
        # The candidate pool's ROWS are re-derivable, but the fact that we have
        # already seen a candidate is not: without it every re-synced tracker row
        # would read as a fresh discovery and the delta would be meaningless. So
        # the ids travel, compactly, even though the rows do not.
        seen = {r["role_id"]: r["first_seen"] for r in self.db.execute(
            "SELECT role_id, first_seen FROM requisitions")}
        seen.update({r["role_id"]: r["first_seen"] for r in self.db.execute(
            "SELECT role_id, first_seen FROM seen")})
        return {"version": 1, "requisitions": reqs, "events": evs,
                "runs": runs, "seen": seen}

    def import_state(self, state: dict) -> dict:
        """Restore an export. Judged facts win over anything a sync wrote, since
        a verified read beats a tracker row."""
        if state.get("version") != 1:
            raise ValueError(f"unsupported state version: {state.get('version')!r}")
        nr = ne = 0
        for r in state.get("requisitions", []):
            cols = [k for k in r if k != "role_id"]
            self.db.execute(
                f"INSERT INTO requisitions (role_id, {','.join(cols)}) "
                f"VALUES (?{',?' * len(cols)}) ON CONFLICT(role_id) DO UPDATE SET "
                + ", ".join(f"{c}=excluded.{c}" for c in cols),
                [r["role_id"]] + [r[c] for c in cols])
            nr += 1
        have = {(e["role_id"], e["ts"], e["kind"], e["detail"])
                for e in (dict(x) for x in self.db.execute("SELECT * FROM events"))}
        for e in state.get("events", []):
            key = (e["role_id"], e["ts"], e["kind"], e["detail"])
            if key in have:
                continue
            self.db.execute(
                "INSERT INTO events(role_id, ts, kind, detail) VALUES (?,?,?,?)", key)
            ne += 1
        for rid, first in (state.get("seen") or {}).items():
            self.db.execute(
                "INSERT OR IGNORE INTO seen(role_id, first_seen) VALUES (?,?)",
                (rid, first))
        for r in state.get("runs", []):
            self.db.execute("INSERT INTO runs(ts, summary) VALUES (?,?)",
                            (r["ts"], r["summary"]))
        self.db.commit()
        return {"requisitions": nr, "events": ne}

    def stale(self, before: str, limit: int = 60) -> list[sqlite3.Row]:
        """Reqs most in need of re-verification: never verified first, then
        oldest last_verified. This is the agent's work list."""
        return list(self.db.execute(
            """SELECT * FROM requisitions
               WHERE live != 'closed'
                 AND verdict IS NOT 'skip'
                 AND (last_verified IS NULL OR last_verified < ?)
               ORDER BY CASE group_label WHEN 'A' THEN 0 WHEN 'LI' THEN 1
                                         WHEN 'B' THEN 2 ELSE 3 END,
                        CASE verdict WHEN 'apply' THEN 0 WHEN 'watch' THEN 1 ELSE 2 END,
                        (last_verified IS NOT NULL), last_verified
               LIMIT ?""", (before, limit)
        ))
