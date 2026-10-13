"""One-off migration: lift the live page's role cards and the verification
facts it carried in prose into the store, so history starts from today rather
than from zero and nothing the digest found by domain-scoped search is lost."""
import html as H, json, re, sys
sys.path.insert(0, '/home/claude/work/radar')
from radar.store import Store, Req
from radar import classify as C

PAGE = '/home/claude/radar/digest.html'
TODAY = '2026-10-12'          # the page's own run date
s = open(PAGE).read()

def find_roles(t):
    out = []
    for m in re.finditer(r'<div class="role( dim)?"((?: hidden)?) data-role-id="([^"]+)" '
                         r'data-company="([^"]*)" data-title="([^"]*)" data-url="([^"]*)">', t):
        i = m.end(); depth = 1
        while depth:
            n = re.search(r'<div\b|</div>', t[i:])
            if not n: break
            depth += -1 if n.group(0) == '</div>' else 1
            i += n.end()
        out.append(dict(dim=bool(m.group(1)), rid=m.group(3),
                        company=H.unescape(m.group(4)), title=H.unescape(m.group(5)),
                        url=H.unescape(m.group(6)), body=t[m.end():i]))
    return out

st = Store('radar.db')
roles = find_roles(s)
seen = set()
imported = 0
for r in roles:
    if r['rid'] in seen:        # pinned-panel duplicates
        continue
    seen.add(r['rid'])
    loc = re.search(r'<div class="loc">(.*?)</div>', r['body'], re.S)
    loc = re.sub(r'<[^>]+>', '', H.unescape(loc.group(1))).strip() if loc else ''
    loc = re.sub(r'\s+', ' ', loc)
    grp, miles = C.group_for(loc)
    st.upsert_seen(Req(role_id=r['rid'], company=r['company'], title=r['title'],
                       url=r['url'], location=loc, group_label=grp, li_miles=miles,
                       sources=['digest-page']), TODAY)
    imported += 1

# Verification facts the page carried as prose, with the clean-read counters it
# had been incrementing by hand. These become columns and stop being guesses.
VERIFIED = {
 'cigna-26010470': dict(live='live', comp_min=72400, comp_max=120600, comp_basis='posting_base',
   arrangement='hybrid', arr_stated=1, cohort='bachelor\'s/master\'s complete at time of hire',
   start_date='2027-07-12', verdict='apply',
   verdict_why='Only published deadline anywhere on the page: closes mid-October 2026 or once filled.',
   notes='Expected base stated as $86,000 for bachelor\'s inside the posted band.', reads=1),
 'citi-97890231744': dict(live='live', comp_min=110000, comp_max=125000, comp_basis='posting_base',
   arrangement='hybrid', arr_stated=1, cohort='graduating Fall 2026 - Spring 2027',
   start_date='Summer 2027', verdict='apply',
   verdict_why='Eighth accepting read in nine days; structured Job Type says On-Site/Resident while the body says up to two days remote.', reads=8),
 'dvtrading-4719126005': dict(live='live', comp_min=135000, comp_max=150000, comp_basis='posting_base',
   arrangement='in-person', arr_stated=1, cohort='graduate by Summer 2027', verdict='apply',
   verdict_why='C++ and Python on Linux named outright; no years-of-experience bullet.', reads=12),
 'fiverings-5349839008': dict(live='live', comp_min=300000, comp_max=300000, comp_basis='posting_base',
   arrangement='in-person', arr_stated=0, verdict='apply',
   verdict_why='No bullet list at all; C++ on Linux. Interview month five weeks past and still accepting.', reads=9),
 'marshallwace-8646937002': dict(live='live', comp_min=150000, comp_max=150000, comp_basis='posting_base',
   arrangement='in-person', arr_stated=0, start_date='2027-09-06', verdict='apply',
   verdict_why='Only req with a stated 2027 start comfortably after a May graduation.', reads=4),
 'seatgeek-8227548': dict(live='live', comp_min=120000, comp_max=150000, comp_basis='posting_base',
   arrangement='hybrid', arr_stated=1, cohort='spring/summer 2027 graduates', verdict='apply',
   verdict_why='Experience "preferred, but not required". Published 23 Sep.', reads=3),
 'twosigma-14014': dict(live='live', comp_min=225000, comp_max=225000, comp_basis='posting_base',
   arrangement='hybrid', arr_stated=1, verdict='apply',
   verdict_why='Apply to 14014 not 13355: identical bullets, $35-60k more. No start year stated - confirm May 2027.', reads=6),
 'twosigma-13946': dict(live='live', comp_min=300000, comp_max=300000, comp_basis='posting_base',
   arrangement='hybrid', arr_stated=1, verdict='apply',
   verdict_why='Bachelor\'s explicitly qualifies; asks for a research project rather than an internship.', reads=1),
 'twosigma-13355': dict(live='live', comp_min=165000, comp_max=190000, comp_basis='posting_base',
   arrangement='hybrid', arr_stated=1, verdict='skip',
   verdict_why='The cheaper twin of 14014 - same words, same city, $35-60k less.', reads=1),
 'optiver-2027': dict(live='live', comp_min=200000, comp_max=200000, comp_basis='posting_base',
   cohort='graduate December 2026 - June 2027', verdict='apply',
   verdict_why='C++ named, bachelor\'s first, no years gate. Body states no city - ask which.', reads=4),
 'akuna-8013085': dict(live='live', comp_min=145000, comp_max=145000, comp_basis='posting_min',
   cohort='graduating by August 2027', verdict='apply',
   verdict_why='Modern C++ (C++20+, C++23 preferred); no years, internship or GPA bullet.', reads=2),
 'imc-4818790101': dict(live='live', comp_min=200000, comp_max=200000, comp_basis='posting_base',
   arrangement='in-person', arr_stated=0, cohort='graduating September 2026 - July 2027',
   start_date='February or August 2027', verdict='apply',
   verdict_why='Ask for the August start; February falls before graduation. One application per role per year.', reads=2),
 'imc-4796143101': dict(live='live', comp_min=200000, comp_max=200000, comp_basis='posting_base',
   verdict='skip',
   verdict_why='"1-3 years of full-time professional work experience post-graduation" - IMC itself points students to the graduate req.', reads=1),
 'rentec-dataprogrammer': dict(live='live', comp_min=129000, comp_max=224000, comp_basis='posting_base',
   arrangement='in-person', arr_stated=0, verdict='apply',
   verdict_why='Both majors in bullet one; C/C++17 on Linux. No years, citizenship, start date or graduation window.', reads=14),
 'rentec-financialinfrastructureprogrammer': dict(live='live', comp_min=168000, comp_max=204000,
   comp_basis='posting_base', arrangement='in-person', arr_stated=0, verdict='apply',
   verdict_why='Cleanest gate of the five and the only one with a New York option.', reads=2),
 'rentec-realtimetradingprogrammer': dict(live='live', comp_min=173000, comp_max=191000,
   comp_basis='posting_base', arrangement='in-person', arr_stated=0, verdict='apply',
   verdict_why='Same template as Data Programmer; most systems-flavoured of the five.', reads=2),
 'rentec-researchinfraprogrammer': dict(live='live', comp_min=157000, comp_max=186000,
   comp_basis='posting_base', arrangement='in-person', arr_stated=0, verdict='watch',
   verdict_why='"Expert-level knowledge of C++11/14/17" - one adjective above the Data Programmer bar.', reads=2),
 'rentec-researchengineer': dict(live='live', comp_min=185000, comp_max=224000,
   comp_basis='posting_base', arrangement='in-person', arr_stated=0, verdict='watch',
   verdict_why='Highest band within 30 miles and the hardest bar: documented history in C/C++23 or Rust.', reads=2),
 'baesystems-128932br': dict(live='closed', verdict='skip',
   verdict_why='Returns "This position has been filled and/or is no longer accepting applications."', reads=0),
}
applied_v = 0
for rid, v in VERIFIED.items():
    if st.get(rid) is None:
        continue
    reads = v.pop('reads', 0)
    st.verify(rid, v, TODAY)
    if reads > 1:
        st.db.execute("UPDATE requisitions SET clean_reads=? WHERE role_id=?", (reads, rid))
        st.log(rid, 'verified', f'carried {reads} clean reads forward from the prose page', TODAY)
    applied_v += 1

# dim cards on the page were explicit skips
for r in roles:
    if r['dim'] and st.get(r['rid']) and not st.get(r['rid'])['verdict']:
        st.verify(r['rid'], {'verdict': 'skip',
                             'verdict_why': 'Carried as a dim skip on the prose page.'}, TODAY)
st.db.commit()
print(json.dumps({'page_roles_imported': imported, 'verified_seeded': applied_v}, indent=1))
st.close()
