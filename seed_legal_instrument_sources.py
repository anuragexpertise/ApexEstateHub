# ---------------------------------------------------------------------------
# PASTE INTO database/seed.py, directly BELOW seed_legal_instrument_catalog().
# Then: (1) delete the hard-coded "UPDATE ... source_url" block at the end of
# seed_legal_instrument_catalog(), and (2) call seed_legal_instrument_sources(cur, conn)
# right after seed_legal_instrument_catalog(cur, conn) wherever seed() calls it.
#
# Compiled 5 Nov 2026 from web searches. EVERYTHING HERE IS A CANDIDATE FOR HUMAN
# VERIFICATION. Nothing sets verification='verified': fn_verify_instrument still
# demands an opinion_ref (advocate/CA) and a person to click Verify.
# ---------------------------------------------------------------------------

# Key = the table's unique key (regime_code, title, enactment_year) - the same triple
# seed_legal_instrument_catalog() uses, and titles must match LEGAL_INSTRUMENTS_* exactly.
# Value = (notification_no, source_url, note). None = not found / not official: left untouched.
# `note` is for reviewers reading this file only; it is not written to the DB.
LEGAL_INSTRUMENT_SOURCES = {
    # ── UP_AOA_2010 (page: RWA Compliance (UP)) ──────────────────────────────
    ("UP_AOA_2010", "Uttar Pradesh Apartment (Promotion of Construction, Ownership and Maintenance) Act, 2010", 2010): (
        "UP Act 16 of 2010 (assent 18 Mar 2010; Gazette 19 Mar 2010; in force 21 Jul 2010)",
        "https://www.indiacode.nic.in/handle/123456789/16832",
        "India Code record. The old seed URL (/1962) did not match; PDF: .../bitstream/123456789/16832/1/english16of2010.pdf. "
        "India Code header says 'amended by UP Act 30 of 2016'; one commentary says that amendment was never brought into force. Ask an advocate."),
    ("UP_AOA_2010", "Uttar Pradesh Apartment Rules, 2011", 2011): (
        "3975/8-1-11-115D.A./02T.C.-I dated 16 Nov 2011",
        "https://greaternoidaauthority.in/pdf/attachments/up_apartment_act_2010.pdf",
        "Hosted by Greater Noida Authority, not the Gazette. Replace with a Gazette / Housing Dept copy if you find one."),
    ("UP_AOA_2010", "Model Bye-Laws for Uttar Pradesh Apartment Owners' Associations, 2011", 2011): (
        "3977/8-1-11-115D.A./02T.C.-I dated 16 Nov 2011",
        "https://up-rera.in/pdf/Model-By-Laws.pdf",
        "Official UP-RERA PDF; text carries the notification number and date."),
    ("UP_AOA_2010", "UP RERA General Regulations 2019 - Regulation 47 as amended: Interest Free Maintenance Security (IFMS)", 2026): (
        None,
        None,
        "Press confirms '12th amendment to UP RERA (General) Regulations 2019, Reg 47' (Business Standard 16 Jul 2026). "
        "The number '7098/U.P. RERA/Regulation/2026-27' and date 13.07.2026 in the seed were NOT found in any source; "
        "no official PDF found. Base regulations: https://up-rera.in/pdf/UPRERA_Regulation_2019.pdf (original Reg 47 is about fees). "
        "Fetch the notification from up-rera.in before verifying."),
    ("UP_AOA_2010", "Societies Registration Act, 1860 (as applicable in Uttar Pradesh)", 1860): (
        "Central Act 21 of 1860, as amended in UP",
        "https://indiacode.nic.in/handle/123456789/18446",
        "India Code lists several state-department records for this Act (18446 and 21579 both say Location: Uttar Pradesh); pick the one you prefer. "
        "UP has amended it repeatedly (e.g. UP Act 52 of 1975, UP Act 8 of 2022). Watch: UP CM said (Sep 2025) the Act should be replaced."),
    ("UP_AOA_2010", "Uttar Pradesh Societies Registration Rules, 1976", 1976): (
        None,
        None,
        "No official copy found; only secondary text (legitquest.com). Made under s.33 of the Act as amended by UP Act 52 of 1975. "
        "Notification number not found."),

    # ── CENTRAL (page: RWA Compliance (INDIA)) ───────────────────────────────
    ("CENTRAL", "Real Estate (Regulation and Development) Act, 2016 (RERA)", 2016): (
        "Act 16 of 2016; S.O. 1544(E) dated 26 Apr 2016 and S.O. 1216(E) dated 19 Apr 2017 (commencement)",
        "https://www.indiacode.nic.in/handle/123456789/17064",
        "Amended by Jan Vishwas (Amendment of Provisions) Act, 2026 (Act 8 of 2026), w.e.f. 7 May 2026 per a publisher's note - confirm and update key_provisions."),
    ("CENTRAL", "Central Goods and Services Tax Act, 2017", 2017): (
        "Central Tax Notification 1/2017 dated 19 Jun 2017 (sections in force 22 Jun 2017)",
        "https://www.gstcouncil.gov.in/central-gst",
        "Index page of the GST Council (Act, Rules, Tax and Rate notifications). Not a direct link to the Act text."),
    ("CENTRAL", "Central Goods and Services Tax Rules, 2017", 2017): (
        "Central Tax Notifications 3/2017 (19 Jun 2017), 10/2017 (28 Jun 2017), 15/2017 (1 Jul 2017)",
        "https://www.gstcouncil.gov.in/central-gst",
        "Same index page."),
    ("CENTRAL", "Integrated Goods and Services Tax Act, 2017", 2017): (
        "Integrated Tax Notification 1/2017 dated 19 Jun 2017 (in force 22 Jun 2017)",
        None,
        "No official URL retrieved."),
    ("CENTRAL", "Income-tax Act, 1961", 1961): (
        "Act 43 of 1961; repealed by s.536(1) of the Income-tax Act, 2025 w.e.f. 1 Apr 2026",
        "https://www.incometaxindia.gov.in/w/section-536-1",
        "This URL proves the repeal and savings (s.536), it is not the 1961 text. Add the 1961 text link if you want one."),
    ("CENTRAL", "Income-tax Act, 2025", 2025): (
        "Act 30 of 2025 (assent 21 Aug 2025; in force 1 Apr 2026)",
        "https://www.incometaxindia.gov.in/w/section-1-269",
        "Income Tax Dept page, 'as amended by Finance Act, 2026'. Income-tax Rules, 2026 (notified 20 Mar 2026) are not in the catalogue yet."),
    ("CENTRAL", "Digital Personal Data Protection Act, 2023", 2023): (
        "Act 22 of 2023; commencement notification G.S.R. 843(E) dated 13 Nov 2025",
        "https://www.meity.gov.in/static/uploads/2024/06/2bf1f0e9f04e6fb4f8fef35e82c42aa5.pdf",
        "MeitY Gazette print. Also India Code: https://indiacode.gov.in/act/c058fa9f-eaf0-4ca3-98f1-3443b087bca9/sections. "
        "Removal of Difficulties Order S.O. 5458(E) (5 Oct 2026) only fixes wording in ss.9 and 10; read, no date changes."),
    ("CENTRAL", "Digital Personal Data Protection Rules, 2025", 2025): (
        "G.S.R. 846(E) dated 13 Nov 2025; corrigendum G.S.R. 892(E) dated 10 Dec 2025",
        "https://egazette.gov.in/WriteReadData/2025/267650.pdf",
        "eGazette; MeitY copy: https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf. "
        "Phases: Rules 1,2,17-21 on 13 Nov 2025; Rule 4 on 13 Nov 2026; Rules 3,5-16,22,23 on 13 May 2027. "
        "Some sites count from 14 Nov; one tracker calls the third date an interpretation. Ask an advocate."),
    ("CENTRAL", "Information Technology Act, 2000", 2000): (
        "Act 21 of 2000",
        "https://indiacode.gov.in/server/api/core/bitstreams/770a7d02-48f2-4274-bab9-10d0f48ee264/content",
        "India Code consolidated print as on 27 Jun 2025 (link taken from a DPDP reference site; open it once to check)."),
    ("CENTRAL", "Indian Contract Act, 1872", 1872): (
        "Act 9 of 1872 (in force 1 Sep 1872)",
        "https://indiacode.nic.in/handle/123456789/2187",
        "India Code record, Ministry of Law and Justice."),
    ("CENTRAL", "Indian Stamp Act, 1899", 1899): (
        "Act 2 of 1899",
        None,
        "India Code lists it but I did not get the handle. Duty is a State matter: also check the UP stamp schedule and e-stamping rules."),
    ("CENTRAL", "Private Security Agencies (Regulation) Act, 2005", 2005): (
        "Act 29 of 2005; S.O. 317(E) dated 15 Mar 2006 (in force 14 Mar 2006)",
        "https://www.indiacode.nic.in/handle/123456789/2024",
        "UP Police also hosts the Act: https://www.uppolice.gov.in/Site-Content/uploaded-content/pdf/private_security_agencies_etc_act_2005.pdf. "
        "Central Model Rules 2006 and UP's own rules are not in the catalogue."),
    ("CENTRAL", "Code on Social Security, 2020", 2020): (
        "Act 36 of 2020; S.O. 5319(E) dated 21 Nov 2025; Social Security (Central) Rules, 2026 notified 8 May 2026",
        None,
        "No official URL retrieved (try labour.gov.in). Seed text 'rules still being notified' is out of date for the Central Rules; UP state rules not checked."),
    ("CENTRAL", "Code on Wages, 2019", 2019): (
        "S.O. 5322(E) dated 21 Nov 2025; Code on Wages (Central) Rules, 2026 G.S.R. 343(E) dated 8 May 2026",
        None,
        "No official URL retrieved (try labour.gov.in). UP state rules not checked."),
    ("CENTRAL", "Bharatiya Sakshya Adhiniyam, 2023", 2023): (
        "Act 47 of 2023 (assent 25 Dec 2023); S.O. 849(E) dated 23 Feb 2024 (in force 1 Jul 2024)",
        "https://indiacode.nic.in/handle/123456789/20063",
        "India Code record."),
}

# URLs an earlier seed wrote that are known to be wrong; they may be replaced even when source_url is already set.
_KNOWN_WRONG_SOURCE_URLS = [
    "https://www.indiacode.nic.in/handle/123456789/1962",
]

# Not yet in the catalogue but cited by the instruments above - consider adding as their own rows:
#   Notification 12/2017-Central Tax (Rate) dated 28 Jun 2017, entry 77 (RWA exemption), as amended by 2/2018-CT(Rate) dated 25 Jan 2018
#   Income-tax Rules, 2026 (CBDT, 20 Mar 2026)
#   Code on Social Security / Code on Wages / IR Code / OSH Code (Central) Rules, 2026 (8-9 May 2026)
#   DPDP Act commencement G.S.R. 843(E); DPDP (Removal of Difficulties) Order, 2026, S.O. 5458(E)
#   Occupational Safety, Health and Working Conditions Code, 2020; Industrial Relations Code, 2020


def seed_legal_instrument_sources(cur, conn):
    """
    Fill notification_no / source_url on catalogue rows from LEGAL_INSTRUMENT_SOURCES.

    Safe to re-run, and it backfills rows seeded earlier (seed_legal_instrument_catalog skips existing rows):
      * never touches a row whose verification = 'verified' (editing substance un-verifies it via trg_instrument_unverify);
      * never overwrites a value the Master has already typed in (only fills NULL/blank, or a known-wrong URL);
      * never sets verification, opinion_ref, verified_by or last_verified_on.
    """
    touched = 0
    for (regime_code, title, year), (notification_no, source_url, _note) in LEGAL_INSTRUMENT_SOURCES.items():
        if not notification_no and not source_url:
            continue
        cur.execute(
            """UPDATE legal_instrument_catalog
                  SET notification_no = COALESCE(NULLIF(BTRIM(notification_no), ''), %s::text),
                      source_url = CASE WHEN source_url IS NULL OR BTRIM(source_url) = '' OR source_url = ANY(%s::text[])
                                        THEN COALESCE(%s::text, source_url) ELSE source_url END
                WHERE regime_code = %s AND title = %s AND enactment_year = %s
                  AND verification <> 'verified'""",
            (notification_no, _KNOWN_WRONG_SOURCE_URLS, source_url, regime_code, title, year),
        )
        touched += cur.rowcount
    conn.commit()
    if touched:
        print(f"  ✓ Legal instrument sources filled for {touched} unverified rows (candidates only; verify in the Master portal)")
