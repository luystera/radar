# radar

Structured state for the 2027 new-grad software job digest.

## Why this exists

The first version of this digest kept all of its state **inside the page's
prose**. Facts like *"DV Trading, 12th clean read, first published 10 Aug,
deadline null, $135–150k"* existed nowhere except as English sentences inside
~380KB of HTML. Every morning the scheduled run had to read ~90k tokens of its
own writing back, re-type nearly all of it, and maintain counters like
*"ninth accepting read"* by reading yesterday's number and adding one.

Three consequences:

- **Drift.** Every regenerated sentence is a chance to drop a detail. The old
  prompt conceded this: on its forced-overwrite path, a role that had closed
  could end up *absent rather than marked closed*.
- **No history.** "What was Five Rings' base on 14 September?" was
  unanswerable. Only what survived into today's prose existed.
- **Counters were fiction.** "Twelfth clean read" was a model-remembered
  integer, not a count.

`radar` moves the facts into SQLite. The page becomes a *rendering* of the
store, and the agent writes only what changed.

## The division of labour — and why the line is where it is

This is a hybrid on purpose. Code does what code does well; the agent does the
judgement. But the boundary is also forced by one hard constraint:

> In the Anthropic cloud container the egress proxy answers **403 to CONNECT**
> for `boards-api.greenhouse.io`, `api.lever.co` and `api.ashbyhq.com`. That is
> an organisation egress-policy denial, not a transient error, and per
> `/root/.ccr/README.md` it must not be retried or routed around.

So:

| Work | Who | Where |
|---|---|---|
| Fetch the 3 GitHub trackers, parse ~2,300 rows | **code** | anywhere (raw.githubusercontent.com is allowed) |
| Store, diff, history, clean-read counters | **code** | anywhere, no network |
| Flag experience gates, cohort traps, comp basis, location group | **code** | anywhere, no network |
| Render the page | **code** | anywhere, no network |
| Read a requisition body from an ATS board API | `sources/boards.py` **locally**; the **agent** via WebFetch in the cloud | see above |
| Read robots-blocked portals (Goldman, Capital One, Altice, LinkedIn) | **agent only**, by domain-scoped search | never code |
| Decide whether a bullet is a wall, a ceiling or a route | **agent** | always |

`sources/boards.py` is real, working code that runs fine on your machine. In
the cloud it raises `EgressBlocked`, and the agent reads the same endpoint and
pipes the result back through `radar verify`. That contract is the reason the
`verify` subcommand exists.

**Never add a LinkedIn fetcher.** Every `linkedin.com/jobs` URL is
ROBOTS_DISALLOWED by design. LinkedIn is a discovery-only source for the agent
and nothing is ever quoted from it.

## Quickstart

```bash
python3 -m pytest tests/ -q           # 36 tests, no network needed
python3 -m radar.cli sync --baseline  # first import: backdates discoveries
python3 -m radar.cli stats
python3 -m radar.cli worklist --limit 40 > work.json
python3 -m radar.cli verify cigna-26010470 --json '{"live":"live","comp_min":72400}'
python3 -m radar.cli render --out digest.html --applied applied.json
python3 -m radar.cli log rentec-dataprogrammer   # full history of one req
```

Offline development against the committed fixtures, no network at all:

```bash
python3 -m radar.cli --db /tmp/dev.db sync --offline fixtures --baseline
```

## The daily run contract

1. `sync` — trackers in, new/seen counted. Tracker comp is **never** written:
   those are estimated totals, postings publish base, and the two are not
   comparable. Comp enters only through `verify`.
2. `worklist` — the agent's queue, ordered by location priority (Group A, then
   Long Island, then B, then C), then verdict, then staleness.
3. For each item the agent opens the requisition and calls `verify` with what
   it read. `verify` increments `clean_reads` on a live read, resets it on a
   close, and writes one `events` row per changed field.
4. `render` — the four location groups first, because they are what gets acted
   on; the changes log and the applied ledger last, as reference. Applied roles
   are emitted `hidden` rather than dropped, so "Untrack" on the page is
   instant. A test asserts that three-way order.

## Role ids

`<company-slug>-<req-id>`, matching the convention already stored in the
artifact database so the migration keeps continuity. `slug` applies the alias
map in `config.py`; `req_id` prefers a `selectedPosition` value, then the last
run of 4+ digits in the URL, then the final path segment. Ids double as
artifact-database document ids, so `ids.is_valid` enforces that grammar.

## Schema

- `requisitions` — one row per req: current verified facts, `clean_reads`,
  `live`, comp band **plus its basis**, arrangement **plus whether it was
  stated or inferred**, cohort, flagged `gates`, `verdict`.
- `events` — append-only. `discovered | backfill | seen | verified | changed |
  closed | reopened`. This is the history the prose could not keep.
- `runs` — one row per pipeline run.

`verify` rejects any field outside `store.VERIFIABLE`, so a typo in a `--json`
payload fails loudly instead of being silently dropped.

## What the tests cover

`tests/test_classify.py` encodes the judgement traps this digest exists to
catch, each from a real requisition:

- IMC's *"1-3 years of full-time professional work experience post-graduation"*
  is a wall; OpenAI's *"0-1 years"* is a ceiling.
- Travelers' *"2 **additional** years"* — the adjective does the work.
- Energy Solutions names academic projects, so its "1 year" is a route.
- Harvey's flat *"internship required"* is a gate; Sentry's *"or equivalent
  practical experience"* is not.
- The JPMorgan February req is flagged wrong-cohort, the July req is not.
- Assured Guaranty's hourly "Summer 2027" and Astranis's twelve-week
  "Associate" are internships whatever the title says.
- A tracker's `$242k/yr` is labelled `estimated_total`, never a base.

## Repository layout and CI

```
radar/            the package: store, classify, render, cli, sources, templates
tests/            36 tests, no network needed
fixtures/         committed tracker snapshots, so the pipeline runs offline
seed_from_page.py one-off migration that seeded the store from the old prose page
```

`.github/workflows/tests.yml` runs the suite on Python 3.10 and 3.12 on every
push and pull request, then runs the offline pipeline end to end — sync, stats,
render — and asserts the page is non-empty. That second step is the one that
catches what unit tests cannot: a renderer that emits a page but silently drops
a section has shipped here before.

## Configuration and privacy

This repository is public, so nothing personal is committed:

- `applied.json` — the applied-role ledger, with company, status and dates — is
  **gitignored**. So are `state.json` exports, which carry the full verdict
  history, and the SQLite database itself.
- `ARTIFACT_URL` is read from `RADAR_ARTIFACT_URL` and defaults to empty. The
  page it publishes to is private; the URL is not in the source.
- `config.py` still carries a Long Island distance table keyed on one home
  town, and `render.py` names that town in two strings. Those are the only
  personal values left in the source, and parameterizing them is a small,
  test-covered change if the repo is ever handed to someone else.

```bash
export RADAR_ARTIFACT_URL="https://claude.ai/code/artifact/..."
```
