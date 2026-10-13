"""Render the digest page: delta on top, carried list below.

The design system is not generated — it lives in templates/base.css and is
copied verbatim, so a run can never "improve" the page's look by accident.
Only content varies.
"""
from __future__ import annotations
import html
import json
import pathlib
from datetime import date

_T = pathlib.Path(__file__).parent / "templates"
_TPL = _T / "base.css"


def _ledger(applied: dict) -> str:
    """The applied panel. Rows are baked in statically so the page is correct on
    first paint; the tracker script then re-renders them live from the database."""
    tpl = (_T / "ledger.html").read_text()
    if not applied:
        return tpl
    order = {"applied": 0, "interviewing": 1, "offer": 2, "rejected": 3}
    ids = sorted(applied, key=lambda k: (order.get(applied[k].get("status"), 9),
                                         applied[k].get("appliedOn") or ""))
    rows = []
    for rid in ids:
        r = applied[rid]
        st = r.get("status") or "applied"
        co = (f'<a href="{e(r.get("url"))}">{e(r.get("company"))}</a>'
              if r.get("url") else e(r.get("company")))
        when = f'applied {e(r["appliedOn"])}' if r.get("appliedOn") else ""
        if r.get("updatedOn") and r.get("updatedOn") != r.get("appliedOn"):
            when += (" &middot; " if when else "") + f'updated {e(r["updatedOn"])}'
        rows.append(
            f'      <div class="led">\n'
            f'        <div class="role-top"><div>\n'
            f'          <div class="co">{co}</div>\n'
            f'          <div class="title">{e(r.get("title"))}</div>\n'
            f'          <div class="loc">{when}</div>\n'
            f'        </div></div>\n'
            f'        <div class="chips"><span class="chip {e(st)}">{e(st)}</span></div>\n'
            + (f'        <p class="note">{e(r["note"])}</p>\n' if r.get("note") else "")
            + f'        <div class="track">'
            + "".join(f'<button class="tbtn sec" data-set="{k}" data-id="{e(rid)}">{k.title()}</button>'
                      for k in order if k != st)
            + f'<button class="tbtn sec" data-clear="{e(rid)}">Untrack</button></div>\n'
            f'      </div>\n')
    counts: dict[str, int] = {}
    for r in applied.values():
        counts[r.get("status") or "applied"] = counts.get(r.get("status") or "applied", 0) + 1
    intro = (f'<b>{len(applied)}</b> role{"s" if len(applied) != 1 else ""} tracked &mdash; '
             + ", ".join(f"<b>{v}</b> {k}" for k, v in counts.items())
             + ". Hidden from the sections below and left out of the daily email.")
    return (tpl.replace('<section class="ledger" id="applied-ledger" hidden>',
                        '<section class="ledger" id="applied-ledger">')
               .replace('<p class="sec-note" id="applied-intro"></p>',
                        f'<p class="sec-note" id="applied-intro">{intro}</p>')
               .replace('<div id="applied-rows"></div>',
                        '<div id="applied-rows">\n' + "".join(rows) + '    </div>'))

GROUP_TITLES = {
    "A": ("Group A &mdash; New York City metro",
          "NYC &middot; Jersey City &middot; Stamford &middot; Greenwich &middot; Westport"),
    "LI": ("Long Island", "Road miles from Huntington, NY"),
    "B": ("Group B &mdash; Rest of East Coast",
          "Philadelphia &middot; Boston &middot; Hartford &middot; Baltimore/DC &middot; New Jersey &middot; upstate NY"),
    "C": ("Group C &mdash; Everywhere else", "Listed for completeness &middot; shorter notes"),
}


def e(v) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def money(lo, hi, basis) -> str:
    if not lo:
        return ""
    def f(n):
        return f"${n/1000:.0f}k" if n % 1000 == 0 else f"${n:,}"
    band = f(lo) if (not hi or hi == lo) else f"{f(lo)}&ndash;{f(hi)}"
    label = {"posting_base": "base (posting)", "posting_min": "minimum base (posting)",
             "estimated_total": "tracker-estimated TOTAL comp &mdash; not a base"}.get(basis, basis or "")
    return f"{band} {label}".strip()


def arrangement_chip(row) -> str:
    a = (row["arrangement"] or "").lower()
    cls = {"in-person": "inperson", "hybrid": "hybrid", "remote": "remote"}.get(a)
    if not cls:
        return '<span class="chip">Arrangement not stated</span>'
    how = "stated" if row["arr_stated"] else "inferred"
    return f'<span class="chip {cls}">{e(a.title())} ({how})</span>'


def role_card(row, applied: dict | None = None) -> str:
    rid = row["role_id"]
    app = (applied or {}).get(rid)
    chips = [arrangement_chip(row)]
    if row["clean_reads"]:
        n = row["clean_reads"]
        chips.append(f'<span class="chip fresh">{n} clean read{"s" if n != 1 else ""}'
                     f'{" &middot; last " + e(row["last_verified"]) if row["last_verified"] else ""}</span>')
    comp = money(row["comp_min"], row["comp_max"], row["comp_basis"])
    if comp:
        chips.append(f'<span class="chip comp">{comp}</span>')
    if row["start_date"]:
        chips.append(f'<span class="chip fresh">Start {e(row["start_date"])}</span>')
    gates = json.loads(row["gates"] or "[]")
    for g in gates:
        if g.get("kind") == "floor":
            chips.append('<span class="chip gate">Experience floor &mdash; read it</span>')
            break
    if row["li_miles"] is not None:
        chips.append(f'<span class="chip">~{row["li_miles"]} mi from Huntington</span>')

    dim = " dim" if row["verdict"] == "skip" else ""
    hidden = " hidden" if app else ""
    quoted = ""
    for g in gates:
        if g.get("kind") in ("floor", "route") and g.get("text"):
            quoted = f'<div class="quote">{e(g["text"])}</div>'
            break
    note = row["verdict_why"] or row["notes"] or ""
    # Built outside the f-string on purpose: nesting the same quote character
    # and escaping a backslash inside an f-string expression is PEP 701, which
    # landed in Python 3.12. This package supports 3.10, where that is a
    # SyntaxError at import time.
    open_a = '<a href="%s">' % e(row["url"]) if row["url"] else ""
    close_a = "</a>" if row["url"] else ""
    return (
        f'    <div class="role{dim}"{hidden} data-role-id="{e(rid)}" '
        f'data-company="{e(row["company"])}" data-title="{e(row["title"])}" data-url="{e(row["url"])}">\n'
        f'      <div class="role-top"><div>\n'
        f'        <div class="co">{open_a}{e(row["company"])}{close_a}</div>\n'
        f'        <div class="title">{e(row["title"])}</div>\n'
        f'        <div class="loc">{e(row["location"])}</div>\n'
        f'      </div></div>\n'
        f'      <div class="chips">{"".join(chips)}</div>\n'
        f'{quoted}\n'
        + (f'      <p class="note">{e(note)}</p>\n' if note else "")
        + '      <div class="track"><button class="tbtn" data-act="applied">Mark applied</button></div>\n'
        f'    </div>\n'
    )


def delta_section(new_rows, changes, closed) -> str:
    if not (new_rows or changes or closed):
        body = ('<p class="sec-note"><b>Nothing opened, nothing closed and nothing changed '
                'on a tracked requisition today.</b> The carried list below is unchanged; '
                'the queue at the top of it still holds.</p>')
        return f'  <section>\n    <div class="sec-head"><h2>&#9889; Since yesterday</h2>'\
               f'<span class="sec-sub">the only part written fresh today</span></div>\n{body}\n  </section>\n'
    out = ['  <section>\n    <div class="sec-head"><h2>&#9889; Since yesterday</h2>'
           '<span class="sec-sub">the only part written fresh today</span></div>\n']
    if new_rows:
        out.append(f'    <p class="sec-note"><b>{len(new_rows)} newly discovered</b> '
                   '&mdash; first time any source has carried these.</p>\n')
        for r in new_rows:
            out.append(role_card(r))
    if changes:
        out.append('    <div class="watch"><dl>\n')
        for c in changes:
            out.append(f'      <dt>{e(c["company"])} &mdash; {e(c["title"])[:90]}</dt>\n'
                       f'      <dd><code>{e(c["kind"])}</code> {e(c["detail"])[:300]}</dd>\n')
        out.append('    </dl></div>\n')
    if closed:
        out.append('    <p class="sec-note"><b>Closed since the last run:</b> '
                   + ", ".join(e(r["company"]) for r in closed) + '.</p>\n')
    out.append('  </section>\n')
    return "".join(out)


def page(store, applied: dict, new_rows, changes, closed, today: str | None = None) -> str:
    today = today or date.today().isoformat()
    css = _TPL.read_text()
    groups = {g: store.curated(g) for g in ("A", "LI", "B", "C")}
    # counts describe only what is open to him: applied, skipped and closed
    # reqs are all excluded, which is why the headline is not a row count.
    open_to_him = {g: [r for r in store.actionable(g) if r["role_id"] not in applied]
                   for g in groups}
    n_a, n_li = len(open_to_him["A"]), len(open_to_him["LI"])
    verified = sum(1 for r in store.all() if r["clean_reads"])
    candidates = len(store.all())

    parts = [
        "<title>2027 New Grad Radar</title>\n",
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;700;800&'
        'family=Public+Sans:ital,wght@0,400;0,500;0,600;1,400&'
        'family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">\n',
        f"<style>{css}</style>\n",
        '<div class="wrap">\n',
        '  <div class="masthead">\n',
        f'    <div class="kicker">2027 New Grad Radar &nbsp;&middot;&nbsp; {e(today)}</div>\n',
        f'    <h1>{n_a} open in New York, {n_li} on Long Island, '
        f'{len(applied)} tracked as applied.</h1>\n',
        '    <p class="verdict">Rendered from the requisition store rather than retyped. '
        'Facts below carry their own verification counts and dates; the section at the top '
        'is the only part written fresh today.</p>\n',
        '  </div>\n',
        '  <div class="stats">\n',
        f'    <div class="stat"><div class="n">{n_a}</div><div class="l">NYC-metro roles open to you</div></div>\n',
        f'    <div class="stat"><div class="n">{len(applied)}</div><div class="l">Applications tracked</div></div>\n',
        f'    <div class="stat"><div class="n">{verified}</div><div class="l">Reqs with a verification history</div></div>\n',
        f'    <div class="stat"><div class="n">{candidates:,}</div><div class="l">Candidates in the store, awaiting judgement</div></div>\n',
        '  </div>\n',
    ]
    for g in ("A", "LI", "B", "C"):
        rows = groups[g]
        title, sub = GROUP_TITLES[g]
        parts.append(f'  <section>\n    <div class="sec-head"><h2>{title}</h2>'
                     f'<span class="sec-sub">{sub}</span></div>\n')
        if not rows:
            parts.append('    <p class="sec-note">Nothing open here that you have not already applied to.</p>\n')
        for r in rows:
            parts.append(role_card(r, applied))
        parts.append('  </section>\n')
    # The location groups come first because they are what he acts on. The
    # changes log and the applied ledger are reference, so they sit at the end.
    parts.append(delta_section(new_rows, changes, closed))
    parts.append(_ledger(applied))
    parts.append('<script>\n' + (_T / 'tracker.js').read_text() + '</script>\n')
    parts.append('</div>\n')
    return "".join(parts)
