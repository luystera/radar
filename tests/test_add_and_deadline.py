"""Tests for the two gaps the 13 Oct test-fire run found:

  1. `verify` could not create a row, so STEP 4's domain-scoped finds -- the
     quant firms, the bank analyst programmes, Long Island -- had no intake
     path at all. `radar add` is that path.
  2. `deadline` was in the prompt's field list and in sources/boards.py but was
     neither a column nor verifiable, so a close date could only live in prose.

The render test is here deliberately: threading `today` into role_card broke
delta_section, and all 36 existing tests passed anyway because none of them
rendered that section.
"""
from __future__ import annotations
import json
import sqlite3

import pytest

from radar.ids import role_id
from radar.render import closes_within, page
from radar.store import SCHEMA, Store, Req


def mk(tmp_path, name="t.db") -> Store:
    return Store(str(tmp_path / name))


def req(company, url, **kw) -> Req:
    return Req(role_id=role_id(company, url), company=company, url=url, **kw)


# ---------------------------------------------------------------- fix 1: add

def test_add_creates_a_row_that_verify_can_then_judge(tmp_path):
    st = mk(tmp_path)
    r = req("Hudson River Trading",
            "https://www.hudsonrivertrading.com/careers/job/?gh_jid=8052122",
            title="Software Engineer (C++ or Python) - 2027 Grads",
            location="New York, NY", group_label="A", sources=["agent"])
    assert st.add(r, "2026-10-13") == "added"
    changed = st.verify(r.role_id, {"live": "live", "verdict": "apply"}, "2026-10-13")
    assert set(changed) == {"live", "verdict"}
    assert st.get(r.role_id)["clean_reads"] == 1


def test_verify_still_refuses_an_unknown_id(tmp_path):
    """The KeyError is the point: a typo must fail, not silently create a row."""
    st = mk(tmp_path)
    with pytest.raises(KeyError):
        st.verify("typo-999", {"live": "live"})


def test_add_never_clobbers_judgement(tmp_path):
    st = mk(tmp_path)
    r = req("Belvedere Trading", "https://jobs.lever.co/belvederetrading/2f6480e5",
            title="Software Engineer - Entry Level 2027", sources=["agent"])
    st.add(r, "2026-10-13")
    st.verify(r.role_id, {"verdict": "apply", "comp_min": 140000}, "2026-10-13")
    again = Req(role_id=r.role_id, company="Belvedere Trading",
                title="WRONG", url=r.url, sources=["agent"])
    assert st.add(again, "2026-10-14") == "existing"
    row = st.get(r.role_id)
    assert row["title"] == "Software Engineer - Entry Level 2027"
    assert row["verdict"] == "apply" and row["comp_min"] == 140000


def test_added_row_merges_with_a_later_tracker_sync(tmp_path):
    """The whole reason add() computes role_id the same way sync does: when a
    tracker finally carries the req, it must land on the SAME row, not a twin."""
    st = mk(tmp_path)
    url = "https://job-boards.greenhouse.io/mw-tech-grad/jobs/8646937002"
    r = req("Marshall Wace", url, title="Software/Infrastructure Graduate - 2027",
            sources=["agent"])
    st.add(r, "2026-10-13")
    st.verify(r.role_id, {"verdict": "apply"}, "2026-10-13")
    # Same company and URL arriving from a tracker the next day.
    tracked = req("Marshall Wace", url, title="Software/Infrastructure Graduate",
                  sources=["vanshb03"])
    assert st.upsert_seen(tracked, "2026-10-14") == "seen"
    assert st.db.execute("SELECT COUNT(*) c FROM requisitions").fetchone()["c"] == 1
    row = st.get(r.role_id)
    assert set(json.loads(row["sources"])) == {"agent", "vanshb03"}
    assert row["verdict"] == "apply"          # judgement untouched by the sync


def test_added_but_unjudged_row_survives_export(tmp_path):
    """Without the sources LIKE '%agent%' clause the export keep-filter drops a
    row that was added and not yet verified, so the find has to be re-made."""
    st = mk(tmp_path)
    r = req("XTX Markets", "https://www.xtxmarkets.com/careers/1234567",
            title="Graduate Software Engineer", sources=["agent"])
    st.add(r, "2026-10-13")
    assert st.get(r.role_id)["verdict"] is None
    kept = {x["role_id"] for x in st.export_state()["requisitions"]}
    assert r.role_id in kept


def test_export_still_drops_the_unjudged_tracker_pool(tmp_path):
    """The candidate pool stays re-derivable: only agent-added rows are spared."""
    st = mk(tmp_path)
    st.upsert_seen(req("Some Startup", "https://example.com/jobs/4444444",
                       title="Software Engineer", sources=["zapplyjobs"]), "2026-10-13")
    assert st.export_state()["requisitions"] == []


# ----------------------------------------------------------- fix 2: deadline

def test_deadline_is_verifiable_and_round_trips(tmp_path):
    st = mk(tmp_path)
    r = req("The Cigna Group", "https://cigna.wd5.myworkdayjobs.com/job/26010470",
            title="TECDP - Software Engineering Track", sources=["agent"])
    st.add(r, "2026-10-13")
    assert st.verify(r.role_id, {"deadline": "2026-10-16"}, "2026-10-13") == ["deadline"]
    state = st.export_state()
    st2 = mk(tmp_path, "t2.db")
    st2.import_state(state)
    assert st2.get(r.role_id)["deadline"] == "2026-10-16"


def test_deadline_change_is_logged_like_any_other_field(tmp_path):
    st = mk(tmp_path)
    r = req("Perpay", "https://job-boards.greenhouse.io/perpay/jobs/5252881007",
            sources=["agent"])
    st.add(r, "2026-10-13")
    st.verify(r.role_id, {"deadline": "2026-11-02"}, "2026-10-13")
    st.verify(r.role_id, {"deadline": "2026-10-26"}, "2026-10-20")
    details = [e["detail"] for e in st.history(r.role_id) if e["kind"] == "changed"]
    assert any("2026-11-02" in d and "2026-10-26" in d for d in details)


def test_migration_adds_the_column_to_a_pre_existing_db(tmp_path):
    """CREATE TABLE IF NOT EXISTS does nothing to a table that already exists,
    so a db written before the column existed needs the ALTER."""
    path = str(tmp_path / "old.db")
    old = "\n".join(l for l in SCHEMA.splitlines() if "deadline" not in l)
    db = sqlite3.connect(path)
    db.executescript(old)
    db.commit()
    db.close()
    st = Store(path)
    cols = {r[1] for r in st.db.execute("PRAGMA table_info(requisitions)")}
    assert "deadline" in cols


@pytest.mark.parametrize("deadline,today,expected", [
    ("2026-10-24", "2026-10-15", 9),
    ("2026-10-15", "2026-10-15", 0),
    ("2026-10-14", "2026-10-15", -1),          # already closed
    ("2026-12-25", "2026-10-15", None),        # beyond the 14-day window
    ("closes mid-October or once filled", "2026-10-15", None),   # prose
    (None, "2026-10-15", None),
])
def test_closes_within(deadline, today, expected):
    assert closes_within(deadline, today) == expected


def test_near_deadline_outranks_group_in_the_worklist(tmp_path):
    """A Group C req closing this week must be verified before a Group A req
    with no deadline -- a day's delay is the one cost that is unrecoverable."""
    st = mk(tmp_path)
    far = req("Teleskope", "https://jobs.ashbyhq.com/teleskope/f96084cd",
              location="New York City, NY", group_label="A", sources=["agent"])
    near = req("Belvedere Trading", "https://jobs.lever.co/belvederetrading/2f6480e5",
               location="Chicago, IL", group_label="C", sources=["agent"])
    for r in (far, near):
        st.add(r, "2026-10-13")
        st.verify(r.role_id, {"live": "live", "verdict": "apply"}, "2026-10-13")
    st.verify(near.role_id, {"deadline": "2026-10-17"}, "2026-10-13")
    order = [r["role_id"] for r in st.stale("2026-10-14", 10, today="2026-10-15")]
    assert order.index(near.role_id) < order.index(far.role_id)


def test_prose_deadline_does_not_claim_urgency(tmp_path):
    st = mk(tmp_path)
    prose = req("The Cigna Group", "https://cigna.wd5.myworkdayjobs.com/job/26010470",
                location="Morris Plains, NJ", group_label="B", sources=["agent"])
    dated = req("Teleskope", "https://jobs.ashbyhq.com/teleskope/f96084cd",
                location="New York City, NY", group_label="A", sources=["agent"])
    for r in (prose, dated):
        st.add(r, "2026-10-13")
        st.verify(r.role_id, {"live": "live", "verdict": "apply"}, "2026-10-13")
    st.verify(prose.role_id, {"deadline": "closes mid-October 2026"}, "2026-10-13")
    order = [r["role_id"] for r in st.stale("2026-10-14", 10, today="2026-10-15")]
    # Group A still wins: an unparseable deadline must not fake its way to the top.
    assert order.index(dated.role_id) < order.index(prose.role_id)


# ------------------------------------------------- the regression that slipped

def test_render_covers_the_delta_section(tmp_path):
    """Threading `today` into role_card broke delta_section, and every existing
    test passed because none of them rendered a new/changed/closed row."""
    st = mk(tmp_path)
    r = req("Hudson River Trading",
            "https://www.hudsonrivertrading.com/careers/job/?gh_jid=8052122",
            title="Software Engineer (C++ or Python) - 2027 Grads",
            location="New York, NY", group_label="A", sources=["agent"])
    st.add(r, "2026-10-13")
    st.verify(r.role_id, {"live": "live", "verdict": "apply",
                          "deadline": "2026-10-20"}, "2026-10-13")
    new_rows = st.new_since("2026-10-12")
    changes = st.changes_on("2026-10-13")
    html = page(st, {}, new_rows, changes, [], "2026-10-13")
    assert "Closes in 7 days" in html


def test_deadline_chip_renders_prose_without_a_closes_prefix(tmp_path):
    st = mk(tmp_path)
    r = req("The Cigna Group", "https://cigna.wd5.myworkdayjobs.com/job/26010470",
            location="Morris Plains, NJ", group_label="B", sources=["agent"])
    st.add(r, "2026-10-13")
    st.verify(r.role_id, {"live": "live", "verdict": "apply",
                          "deadline": "closes mid-October 2026 or once filled"},
              "2026-10-13")
    html = page(st, {}, [], [], [], "2026-10-13")
    assert "closes mid-October 2026 or once filled" in html
    assert "Closes closes" not in html


# ------------------------------------------- version skew between code and state

def test_export_declares_version_2(tmp_path):
    st = mk(tmp_path)
    assert st.export_state()["version"] == 2


def test_a_version_1_snapshot_still_imports(tmp_path):
    """Every snapshot published before the deadline column says version 1."""
    st = mk(tmp_path)
    r = req("Teleskope", "https://jobs.ashbyhq.com/teleskope/f96084cd", sources=["agent"])
    st.add(r, "2026-10-13")
    old = st.export_state()
    old["version"] = 1
    for d in old["requisitions"]:
        d.pop("deadline", None)
    st2 = mk(tmp_path, "t2.db")
    assert st2.import_state(old)["requisitions"] == 1
    assert st2.get(r.role_id)["deadline"] is None


def test_an_unknown_future_version_is_refused_not_crashed_on(tmp_path):
    """The failure that matters: stale mirror code meets a newer snapshot. It
    must raise ValueError -- which cmd_import catches and prints -- rather than
    reach the INSERT and die on an unhandled sqlite3.OperationalError."""
    st = mk(tmp_path)
    with pytest.raises(ValueError, match="unsupported state version"):
        st.import_state({"version": 99, "requisitions": [], "events": [],
                         "runs": [], "seen": {}})
