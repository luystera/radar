"""The traps this digest exists to catch. Each case is a real bullet from a
requisition the page has judged, so a regression here is a regression in the
thing that actually matters."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from radar import classify as C


def kinds(body):
    return {g.kind for g in C.find_gates(body)}


# ---- walls: real professional floors -------------------------------------

def test_imc_early_career_is_a_wall():
    body = "1-3 years of full-time professional work experience post-graduation"
    gs = C.blocking_gates(body)
    assert gs and gs[0].kind == "floor"
    assert "post-graduation" in gs[0].why


def test_travelers_additional_years_is_a_wall():
    # "additional" does the work: two years on top of the degree.
    body = "Bachelor's degree. 2 additional years of software engineering experience."
    assert C.blocking_gates(body)


def test_pathai_test_infra_floor():
    body = ("1-2 years of hands-on experience writing and maintaining "
            "automated tests with frameworks such as Playwright or Cypress")
    assert C.blocking_gates(body)


def test_yext_one_plus_years():
    assert C.blocking_gates("1+ years of professional software engineering experience")


# ---- ceilings and routes: not walls --------------------------------------

def test_openai_zero_to_one_is_a_ceiling():
    body = "0-1 years of experience in software engineering or a relevant field"
    assert not C.blocking_gates(body)
    assert "ceiling" in kinds(body)


def test_doordash_ceiling_plus_route():
    body = ("No more than two years of full-time professional experience\n"
            "At least two previous software engineering internships or "
            "equivalent practical experience")
    assert not C.blocking_gates(body)


def test_energy_solutions_names_academic_projects():
    body = ("1 year of relevant experience, which may include internships, "
            "co-op programs, academic projects, open-source contributions, "
            "or professional software development experience.")
    assert not C.blocking_gates(body)
    assert "route" in kinds(body)


def test_leidos_zero_plus_years():
    assert not C.blocking_gates("0+ years of C++ or Java software development")


def test_aspentech_ceiling_with_projects():
    body = ("0-2 years of software development experience, including "
            "internships, co-op programs, academic projects, or equivalent")
    assert not C.blocking_gates(body)


# ---- internship gates: the four words that separate them -----------------

def test_harvey_flat_internship_required_is_a_gate():
    g = C.internship_gate("Previous internship experience is required")
    assert g and g.kind == "floor"


def test_sentry_equivalence_clause_is_a_route():
    g = C.internship_gate("At least 1 previous internship or equivalent practical experience")
    assert g and g.kind == "route"


# ---- cohort timing: the JPMorgan pair ------------------------------------

def test_jpmorgan_february_req_is_flagged():
    r = C.cohort_risk(
        "2027 Software Engineer Program - Full-Time - February Start",
        "expected graduation between July 2026 and December 2026; must have "
        "graduated by December 2026 and be available to start February 2027")
    assert r["risky"] and "february" in r["early_starts"]


def test_jpmorgan_july_req_is_clean():
    r = C.cohort_risk("2027 Software Engineer Program - Full-Time - July Start",
                      "The rest of the class starts in July.")
    assert not r["risky"]


def test_fidelity_january_leap_is_flagged():
    assert C.cohort_risk("January 2027 - Leap Software Engineer", "")["risky"]


def test_cigna_july_start_is_clean():
    r = C.cohort_risk("Technology Development Program - Software Engineering Track",
                      "Schedule: Full-time, 40 hours/week, Monday-Friday "
                      "starting July 12, 2027.")
    assert not r["risky"]


def test_google_year_label_detected_in_title():
    assert C.cohort_risk("Software Engineer, Early Career, 2027 Start", "")["year_in_title"]
    assert not C.cohort_risk("Software Engineer II, Early Career", "")["year_in_title"]


# ---- internships wearing other titles ------------------------------------

def test_assured_guaranty_summer_2027_is_an_internship():
    assert C.is_internship(
        "Product Software Developer, Front-End and Back-End, Summer 2027",
        "The salary for the position is expected to be from $30 per hour to $32 per hour.")


def test_astranis_associate_is_a_twelve_week_placement():
    assert C.is_internship(
        "Network Software Associate, Summer 2027",
        "Associate Engineer positions typically last for twelve weeks and are "
        "salaried roles. $1,925 per week.")


def test_idme_summer_2027_start_is_not_an_internship():
    # "Summer 2027" here is the start date of a full-time role.
    assert not C.is_internship(
        "Software Development Engineer - New Grad",
        "This is a full-time role. Graduating May/June 2027.")


# ---- comp basis -----------------------------------------------------------

def test_posting_base_band():
    c = C.parse_comp("The salary range for this role is $120,000-$150,000 USD.")
    assert (c["comp_min"], c["comp_max"]) == (120000, 150000)
    assert c["comp_basis"] == "posting_base"


def test_tracker_estimate_is_labelled_estimated():
    c = C.parse_comp("$242k/yr", source="speedyapply")
    assert c["comp_basis"] == "estimated_total"


def test_akuna_minimum_is_a_floor_not_a_band():
    c = C.parse_comp("the minimum base salary starts at $145,000")
    assert c["comp_basis"] == "posting_min"


def test_flat_figure():
    c = C.parse_comp("The base pay for this role will be between $225,000 and $225,000.")
    assert c["comp_min"] == c["comp_max"] == 225000


# ---- location grouping ----------------------------------------------------

def test_long_island_gets_miles():
    assert C.group_for("East Setauket, NY") == ("LI", 20)
    assert C.group_for("Greenlawn, New York, United States") == ("LI", 3)


def test_nyc_is_group_a():
    assert C.group_for("New York, NY")[0] == "A"
    assert C.group_for("Jersey City, NJ")[0] == "A"


def test_boston_is_group_b():
    assert C.group_for("Boston, MA")[0] == "B"


def test_elsewhere_is_group_c():
    assert C.group_for("Mountain View, CA")[0] == "C"


# ---- state round-trip ------------------------------------------------------

def test_export_import_round_trip(tmp_path):
    """The migration's load-bearing guarantee: judgement and history survive a
    trip through an ephemeral container."""
    from radar.store import Store, Req
    a = Store(str(tmp_path / "a.db"))
    a.upsert_seen(Req(role_id="cigna-26010470", company="The Cigna Group",
                      title="TECDP", url="https://x/26010470",
                      group_label="B", sources=["digest-page"]), "2026-10-12")
    a.verify("cigna-26010470", {"live": "live", "comp_min": 72400,
                                "comp_basis": "posting_base", "verdict": "apply"},
             "2026-10-12")
    a.db.execute("UPDATE requisitions SET clean_reads=12 WHERE role_id='cigna-26010470'")
    a.db.commit()
    state = a.export_state()

    # unjudged candidates are not exported -- they are re-derivable
    a.upsert_seen(Req(role_id="noise-1234", company="Noise", url="https://y/1234",
                      sources=["speedyapply"]), "2026-10-12")
    assert len(a.export_state()["requisitions"]) == 1

    b = Store(str(tmp_path / "b.db"))          # a fresh container
    b.import_state(state)
    r = b.get("cigna-26010470")
    assert r["verdict"] == "apply" and r["clean_reads"] == 12
    assert r["comp_min"] == 72400 and r["comp_basis"] == "posting_base"
    assert len(b.history("cigna-26010470")) == len(a.history("cigna-26010470"))

    b.import_state(state)                       # idempotent
    assert len(b.history("cigna-26010470")) == len(a.history("cigna-26010470"))
    a.close(); b.close()


def test_import_rejects_unknown_version(tmp_path):
    from radar.store import Store
    s = Store(str(tmp_path / "c.db"))
    try:
        s.import_state({"version": 99})
        assert False, "should have rejected"
    except ValueError as e:
        assert "unsupported state version" in str(e)
    s.close()


def test_rederived_candidates_are_not_new_discoveries(tmp_path):
    """The candidate pool is rebuilt from the trackers every run. Without a
    persisted seen-set every one of ~1,400 rows would read as new each morning
    and the delta section would be worthless."""
    from radar.store import Store, Req
    a = Store(str(tmp_path / "a.db"))
    r = Req(role_id="nvidia-2027337", company="NVIDIA", url="https://x/2027337",
            sources=["speedyapply"])
    assert a.upsert_seen(r, "2026-10-12") == "new"
    state = a.export_state()
    assert "nvidia-2027337" in state["seen"]

    b = Store(str(tmp_path / "b.db"))          # tomorrow's fresh container
    b.import_state(state)
    assert b.get("nvidia-2027337") is None     # row was not persisted...
    assert b.upsert_seen(r, "2026-10-13") == "seen"   # ...but it is not "new"
    assert b.get("nvidia-2027337")["first_seen"] == "2026-10-12"
    assert b.new_since("2026-10-12") == []     # and it stays out of the delta
    a.close(); b.close()


def test_applied_collator(tmp_path):
    """ArtifactData writes one JSON file per document; the renderer wants one
    object. The CLI does it so the daily run never improvises a script."""
    import json as J
    from radar.cli import main
    d = tmp_path / "apps" / "applications"; d.mkdir(parents=True)
    (d / "cigna-26010470.json").write_text(J.dumps(
        {"id": "cigna-26010470", "data": {"status": "applied", "company": "Cigna"}}))
    (d / "twosigma-14014.json").write_text(J.dumps(
        {"id": "twosigma-14014", "data": {"status": "interviewing", "company": "Two Sigma"}}))
    (d / "junk.json").write_text("not json")
    out = tmp_path / "applied.json"
    assert main(["applied", "--dir", str(tmp_path / "apps"), "--out", str(out)]) == 0
    got = J.load(open(out))
    assert set(got) == {"cigna-26010470", "twosigma-14014"}
    assert got["twosigma-14014"]["status"] == "interviewing"


# ---- the candidate pool must not fill with non-software noise -------------

def test_rejects_non_software_titles():
    # the row the first unsupervised run actually let into the store
    assert not C.is_software_role("Coordinator - Custodial Services- Manhattan Site")
    assert not C.is_software_role("Technical Recruiter, University")
    assert not C.is_software_role("Account Executive, Enterprise")
    assert not C.is_software_role("Registered Nurse - Melville")
    assert not C.is_software_role("Engineering Manager, Platform")   # not a seat he writes code in
    assert not C.is_software_role("Sales Engineer")
    assert not C.is_software_role("")


def test_keeps_every_shape_the_digest_actually_carries():
    for t in [
        "Software Engineer - New Grad",
        "2027 Graduate Software Engineer (DV Commodities)",
        "Campus Full Time 2027 - Software Developer",
        "Data Programmer",
        "Real-Time Trading Programmer",
        "Research Engineer",
        "Quantitative Researcher - Full-Time Campus Hire",
        "Markets - Quantitative Analysis, Full-Time Analyst",
        "2027 | Americas | New York City Area | Engineering | New Analyst",
        "Associate Engineer - 2027 Start",
        "Embedded Software Engineer - New Grad (2027)",
        "New Grad Software Engineer (Backend Rust)",
        "Associate Platform Engineer (College Grad 2027)",
        "Software Development Engineer I",
        "Technology Development Program (TECDP) - Software Engineering Track",
    ]:
        assert C.is_software_role(t), t


def test_filter_keeps_bank_programme_shapes_that_hide_the_engineering():
    """These two were deleted by an over-eager first version of the filter."""
    assert C.is_software_role("2027 Full-Time Analyst Program - AMRS")          # BlackRock
    assert C.is_software_role("Opportunistic - speculative application")        # Boerboel
    assert C.is_software_role("2027 | Americas | New York City Area | Engineering | New Analyst")
    assert C.is_software_role("Digital & Technology Rotational Program, Associate")
    assert C.is_software_role("Engineering Graduate Programme - New York Office")
    # and still rejects the row that prompted the filter
    assert not C.is_software_role("Coordinator - Custodial Services- Manhattan Site")


def test_filter_is_intake_only_never_a_pruner(tmp_path):
    """A judged row must survive regardless of what the title filter thinks, so
    the filter can never again delete something an agent decided to keep."""
    from radar.store import Store, Req
    st = Store(str(tmp_path / "s.db"))
    st.upsert_seen(Req(role_id="odd-1", company="Odd Co", title="Coordinator, Something",
                       sources=["digest-page"]), "2026-10-13")
    st.verify("odd-1", {"verdict": "apply", "verdict_why": "agent judged this wanted"},
              "2026-10-13")
    kept = st.export_state()["requisitions"]
    assert any(r["role_id"] == "odd-1" for r in kept)
    st.close()


def test_page_order_roles_first_then_changes_then_applied(tmp_path):
    """He acts on the location groups; the changes log and the applied ledger are
    reference and belong at the end. Asserted because it is easy to regress when
    editing the renderer."""
    from radar.store import Store, Req
    from radar import render
    st = Store(str(tmp_path / "o.db"))
    st.upsert_seen(Req(role_id="x-1234", company="Acme", title="Software Engineer",
                       url="https://x/1234", location="New York, NY",
                       group_label="A", sources=["digest-page"]), "2026-10-13")
    html = render.page(st, {"y-9999": {"status": "applied", "company": "Zeta",
                                       "title": "Software Engineer"}},
                       [], [], [], "2026-10-13")
    i_group = html.index("Group A")
    i_changes = html.index("Since yesterday")
    i_applied = html.index('id="applied-ledger"')
    assert i_group < i_changes < i_applied, (i_group, i_changes, i_applied)
    st.close()
