"""radar CLI.

  radar sync      [--offline DIR]     fetch trackers -> store, report new/seen
  radar add       --company --url     enter a req the trackers do not carry
  radar worklist  [--limit N]         what the agent should verify today (JSON)
  radar verify    ROLE_ID --json ...  apply one verification
  radar render    --out FILE          render the page from the store
  radar log       ROLE_ID             full history of one requisition
  radar stats                         counts by group and verdict
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from datetime import date, timedelta

from . import classify as C
from .ids import role_id, is_valid
from .store import Store, Req
from .sources import trackers


def cmd_sync(a) -> int:
    st = Store(a.db)
    today = a.today or date.today().isoformat()
    data = trackers.load_all(a.offline)
    new = seen = skipped = 0
    for source, rows in data.items():
        for r in rows:
            if not r.url:
                skipped += 1
                continue
            if C.is_internship(r.title):
                skipped += 1
                continue
            if not C.is_software_role(r.title):
                skipped += 1
                continue
            rid = role_id(r.company, r.url)
            if not is_valid(rid):
                skipped += 1
                continue
            grp, miles = C.group_for(r.location)
            res = st.upsert_seen(Req(
                role_id=rid, company=r.company, title=r.title, url=r.url,
                location=r.location, group_label=grp, li_miles=miles,
                sources=[source],
            ), today)
            # Deliberately NOT writing comp here. The trackers publish estimated
            # total comp, the postings publish base salary, and the two are not
            # comparable -- so comp enters the store only through `verify`, from
            # a real read of the requisition.
            new += 1 if res == "new" else 0
            seen += 1 if res != "new" else 0
    if getattr(a, "baseline", False) and new:
        from datetime import date as _d, timedelta as _td
        prev = (_d.fromisoformat(today) - _td(days=1)).isoformat()
        st.db.execute("UPDATE requisitions SET first_seen=? WHERE first_seen=?", (prev, today))
        st.db.execute("UPDATE events SET kind='backfill' WHERE ts=? AND kind IN ('discovered','changed')", (today,))
    st.db.execute("INSERT INTO runs(ts, summary) VALUES (?,?)",
                  (today, f"sync new={new} seen={seen} skipped={skipped}"
                          f"{' BASELINE' if getattr(a, 'baseline', False) else ''}"))
    st.db.commit()
    print(json.dumps({"new": new, "seen": seen, "skipped_internships_or_unusable": skipped,
                      "sources": {k: len(v) for k, v in data.items()}}, indent=1))
    st.close()
    return 0


def cmd_add(a) -> int:
    """Enter a requisition the trackers do not carry.

    This is the intake path for STEP 4 of the daily run: the quant and prop
    firms, the bank analyst programmes and the Long Island employers are not on
    any of the three GitHub trackers, so a req found by searching had nowhere to
    go -- verify() raises KeyError on an unknown role_id, by design, because a
    typo must not create a row. add() creates the row; verify() still owns every
    judged field.
    """
    if not re.match(r"^https?://\S+$", (a.url or "").strip()):
        print("error: --url must be a real http(s) URL to the employer's own "
              "posting -- never a search page and never invented", file=sys.stderr)
        return 1
    rid = role_id(a.company, a.url)
    if not is_valid(rid):
        print(f"error: computed role_id is not a usable document id: {rid!r}",
              file=sys.stderr)
        return 1
    st = Store(a.db)
    grp, miles = C.group_for(a.location or "")
    res = st.add(Req(role_id=rid, company=a.company, title=a.title or "",
                     url=a.url.strip(), location=a.location or "",
                     group_label=grp, li_miles=miles, sources=["agent"]), a.today)
    out = {"role_id": rid, "result": res, "group": grp}
    # Warn, never refuse: these filters gate tracker volume, and is_software_role
    # must not be used to second-guess a row an agent added deliberately.
    warn = []
    if res == "existing":
        # Nothing was written, so report the row as it actually stands rather
        # than the group and title this call would have used.
        row = st.get(rid)
        out["group"] = row["group_label"]
        out["stored_title"] = row["title"]
        out["verdict"] = row["verdict"]
        warn.append("row already exists and was left untouched -- change judged "
                    "fields with `verify`, not by re-adding")
    else:
        if a.title and C.is_internship(a.title):
            warn.append("title reads as an internship -- tracker intake would skip "
                        "it; confirm this is a full-time seat")
        if a.title and not C.is_software_role(a.title):
            warn.append("title carries no software token -- tracker intake would skip it")
    if warn:
        out["warnings"] = warn
    if a.json:
        try:
            out["changed"] = st.verify(rid, json.loads(a.json), a.today)
        except (KeyError, ValueError) as ex:
            print(json.dumps(out, indent=1))
            print(f"error: row exists but verify failed: {ex}", file=sys.stderr)
            st.close()
            return 1
    print(json.dumps(out, indent=1))
    st.close()
    return 0


def cmd_worklist(a) -> int:
    st = Store(a.db)
    # Pre-existing bug, fixed here because the deadline ordering below is
    # otherwise untestable: --today is documented as an override "for tests" but
    # the cutoff was always computed from the real clock, so a --today run
    # silently filtered against the wrong day.
    base = date.fromisoformat(a.today) if a.today else date.today()
    cutoff = (base - timedelta(days=a.days)).isoformat()
    rows = st.stale(cutoff, a.limit, a.today)
    out = [{"role_id": r["role_id"], "company": r["company"], "title": r["title"],
            "url": r["url"], "group": r["group_label"], "deadline": r["deadline"],
            "last_verified": r["last_verified"], "clean_reads": r["clean_reads"]}
           for r in rows]
    print(json.dumps(out, indent=1))
    st.close()
    return 0


def cmd_verify(a) -> int:
    st = Store(a.db)
    fields = json.loads(a.json)
    try:
        changed = st.verify(a.role_id, fields, a.today)
    except (KeyError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        st.close()
        return 1
    print(json.dumps({"role_id": a.role_id, "changed": changed}))
    st.close()
    return 0


def cmd_render(a) -> int:
    from . import render
    st = Store(a.db)
    applied = json.load(open(a.applied)) if a.applied else {}
    today = a.today or date.today().isoformat()
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    new_rows = st.new_since(yesterday)
    changes = [c for c in st.changes_on(today) if c["kind"] in ("changed", "reopened")][:40]
    closed = [r for r in st.all() if r["live"] == "closed" and r["last_verified"] == today]
    htm = render.page(st, applied, new_rows, changes, closed, today)
    open(a.out, "w").write(htm)
    print(json.dumps({"out": a.out, "bytes": len(htm), "new": len(new_rows),
                      "changes": len(changes), "closed": len(closed),
                      "applied_hidden": len(applied)}, indent=1))
    st.close()
    return 0


def cmd_export(a) -> int:
    st = Store(a.db)
    state = st.export_state()
    blob = json.dumps(state, separators=(",", ":"))
    open(a.out, "w").write(blob)
    print(json.dumps({"out": a.out, "bytes": len(blob),
                      "requisitions": len(state["requisitions"]),
                      "events": len(state["events"])}, indent=1))
    st.close()
    return 0


def cmd_import(a) -> int:
    st = Store(a.db)
    try:
        res = st.import_state(json.load(open(a.path)))
    except (ValueError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        st.close()
        return 1
    print(json.dumps(res, indent=1))
    st.close()
    return 0


def cmd_applied(a) -> int:
    """Collate the per-document JSON files an ArtifactData `list --out_dir` writes
    into the single role_id -> row object the renderer wants. Saves the daily run
    from improvising a script for it."""
    import glob
    import os
    out: dict[str, dict] = {}
    for f in sorted(glob.glob(os.path.join(a.dir, "**", "*.json"), recursive=True)):
        try:
            d = json.load(open(f))
        except (json.JSONDecodeError, OSError):
            continue
        rid = d.get("id") or os.path.splitext(os.path.basename(f))[0]
        row = d.get("data", d)
        if isinstance(row, dict):
            out[rid] = row
    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps({"out": a.out, "applied": len(out),
                      "statuses": sorted({r.get("status", "?") for r in out.values()})},
                     indent=1))
    return 0


def cmd_log(a) -> int:
    st = Store(a.db)
    for ev in st.history(a.role_id):
        print(f"{ev['ts']}  {ev['kind']:<11} {ev['detail']}")
    st.close()
    return 0


def cmd_stats(a) -> int:
    st = Store(a.db)
    q = lambda s, *p: list(st.db.execute(s, p))
    print(json.dumps({
        "total": q("SELECT COUNT(*) c FROM requisitions")[0]["c"],
        "by_group": {r["group_label"]: r["c"] for r in
                     q("SELECT group_label, COUNT(*) c FROM requisitions GROUP BY 1")},
        "by_live": {r["live"]: r["c"] for r in
                    q("SELECT live, COUNT(*) c FROM requisitions GROUP BY 1")},
        "verified": q("SELECT COUNT(*) c FROM requisitions WHERE clean_reads>0")[0]["c"],
        "events": q("SELECT COUNT(*) c FROM events")[0]["c"],
    }, indent=1))
    st.close()
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="radar")
    p.add_argument("--db", default="radar.db")
    p.add_argument("--today", default=None, help="override today (ISO) for tests")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sync");      s.add_argument("--offline")
    s.add_argument("--baseline", action="store_true",
                   help="treat this sync as an import: discoveries are backdated "
                        "one day and logged as 'backfill', so the next run's delta is real")
    s.set_defaults(f=cmd_sync)
    s = sub.add_parser("add")
    s.add_argument("--company", required=True)
    s.add_argument("--url", required=True, help="the employer's own posting URL")
    s.add_argument("--title", default="")
    s.add_argument("--location", default="", help="drives group A/LI/B/C and LI miles")
    s.add_argument("--json", help="optional: verify the new row in the same call")
    s.set_defaults(f=cmd_add)
    s = sub.add_parser("worklist");  s.add_argument("--limit", type=int, default=40)
    s.add_argument("--days", type=int, default=1); s.set_defaults(f=cmd_worklist)
    s = sub.add_parser("verify");    s.add_argument("role_id"); s.add_argument("--json", required=True)
    s.set_defaults(f=cmd_verify)
    s = sub.add_parser("render");    s.add_argument("--out", default="digest.html")
    s.add_argument("--applied"); s.set_defaults(f=cmd_render)
    s = sub.add_parser("applied");   s.add_argument("--dir", required=True)
    s.add_argument("--out", default="applied.json"); s.set_defaults(f=cmd_applied)
    s = sub.add_parser("export");    s.add_argument("--out", default="state.json")
    s.set_defaults(f=cmd_export)
    s = sub.add_parser("import");    s.add_argument("path"); s.set_defaults(f=cmd_import)
    s = sub.add_parser("log");       s.add_argument("role_id"); s.set_defaults(f=cmd_log)
    s = sub.add_parser("stats");     s.set_defaults(f=cmd_stats)

    a = p.parse_args(argv)
    return a.f(a)


if __name__ == "__main__":
    raise SystemExit(main())
