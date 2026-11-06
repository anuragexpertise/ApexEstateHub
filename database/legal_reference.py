#!/usr/bin/env python3
# database/legal_reference.py
"""
Legal reference data: the Acts, Rules, Bye-laws and Notifications behind "RWA Compliance (INDIA)" and
"RWA Compliance (UP)", loaded into `legal_instrument_catalog` (and the regime profiles it points at).

TWO SEPARATE MECHANISMS
    1. THIS FILE   platform reference data. No society, no users, no demo anything. Runs on EVERY fresh
                   install (production included), straight after the schema:
                       python3 database/migrate.py                 # schema + this
                       python3 database/migrate.py --seed          # schema + this + demo society
                       python3 database/reset_database.py --yes --after schema
                   and on an existing database, on demand:
                       python3 database/legal_reference.py --check       # compare DB with this file
                       python3 database/legal_reference.py               # add missing rows, refresh candidate links
                       python3 database/legal_reference.py --refresh     # also rewrite UNVERIFIED rows' text from this file
    2. seed.py     the demo society (Sunrise Residency). It no longer defines any law; it calls seed_all() below so that
                   `python3 database/seed.py` on its own still works.

WHAT IS AND IS NOT TRUSTED
    Everything below was researched on RESEARCHED_ON from public sources and is UNVERIFIED. Verification is a human act:
    the Master (or a Treasurer / Auditor) opens the text, then fn_verify_instrument() records notification_no, source_url,
    opinion_ref and the date. This file never sets any of those, never sets `verification`, and never touches a row that
    is already 'verified' except to refresh its candidate_* leads (which are not part of what verification asserts).
    The `candidate_*` columns hold the leads: notification number, link and a reviewer's note.

SAFE TO RE-RUN. Rows are keyed on the table's own unique key (regime_code, title, enactment_year).
"""
from __future__ import annotations

import argparse
import os
import re
import sys

RESEARCHED_ON = "2026-11-05"

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# UP_AOA_2010 and GENERIC come from the scheme packs (schemes/*.toml); CENTRAL is inserted by estatehub.sql.
# Only schemes without a pack yet are listed here.
# (code, state_code, name, primary_law, rules_version, model_bye_laws_version, effective_from, effective_to,
#  status, source_reference, constitution)
EXTRA_REGIME_PROFILES = [('MH_COOP_1965',
  'MH',
  'Maharashtra Co-operative Housing Society',
  'Maharashtra Co-operative Societies Act, 1960',
  'Maharashtra Co-operative Societies Rules, 1961',
  'Model Bye-Laws for Housing Societies',
  '1962-01-26',
  None,
  'draft',
  'MCS Act 1960; MCS Rules 1961; Model Bye-Laws',
  'COOP')]

# One dict per catalogue row; keys are the table's column names. `applies_when` defaults to 'always'.
# candidate_* = researched leads for the verifier (see module docstring); absent = nothing found.
INSTRUMENTS = [
    {
        'regime_code': 'UP_AOA_2010',
        'instrument_type': 'Act',
        'title': (
            'Uttar Pradesh Apartment (Promotion of Construction, Ownership and Maintenance)'
            ' Act, 2010'
        ),
        'enactment_year': 2010,
        'issuing_authority': 'Government of Uttar Pradesh',
        'applicability': (
            'Buildings with 4+ apartments (freehold or leasehold), excluding shopping malls'
            ' and multiplexes'
        ),
        'key_provisions': (
            'Primary statute for apartment ownership in UP. Sec 3 defines common '
            "areas/limited common areas/promoter; Sec 12 requires promoter's Declaration of"
            ' layout; Sec 14 mandates formation of an Association of Apartment Owners '
            '(joint promoter+owner responsibility) and its Bye-laws for managing common '
            'areas/facilities; Sec 18/20 govern common expenses and common profits.'
        ),
        'source_reference': 'UP Act 16 of 2010 (India Code / PRS Legislative Research)',
        'display_order': 10,
        'status': 'active',
        'applies_when': 'always',
        'candidate_notification_no': (
            'UP Act 16 of 2010 (assent 18 Mar 2010; Gazette 19 Mar 2010; in force 21 Jul '
            '2010)'
        ),
        'candidate_source_url': 'https://www.indiacode.nic.in/handle/123456789/16832',
        'candidate_note': (
            'India Code record. The old seed URL (/1962) did not match; PDF: '
            '.../bitstream/123456789/16832/1/english16of2010.pdf. India Code header says '
            "'amended by UP Act 30 of 2016'; one commentary says that amendment was never "
            'brought into force. Ask an advocate.'
        ),
    },
    {
        'regime_code': 'UP_AOA_2010',
        'instrument_type': 'Rules',
        'title': 'Uttar Pradesh Apartment Rules, 2011',
        'enactment_year': 2011,
        'issuing_authority': 'Government of Uttar Pradesh',
        'applicability': 'Same scope as the 2010 Act',
        'key_provisions': (
            "Complete procedural code under the Act: Sec 2 defines 'Competent Authority' as"
            ' the Development Authority Vice-Chairman (or District Collector where none '
            'exists); prescribes Forms/Annexures for the Declaration (common areas, limited'
            ' common areas, independent areas) and Deed of Apartment; sets out amendment '
            'and violation-complaint procedures.'
        ),
        'source_reference': 'Notified 16 Nov 2011 in the UP Gazette',
        'display_order': 20,
        'status': 'active',
        'applies_when': 'always',
        'candidate_notification_no': '3975/8-1-11-115D.A./02T.C.-I dated 16 Nov 2011',
        'candidate_source_url': (
            'https://greaternoidaauthority.in/pdf/attachments/up_apartment_act_2010.pdf'
        ),
        'candidate_note': (
            'Hosted by Greater Noida Authority, not the Gazette. Replace with a Gazette / '
            'Housing Dept copy if you find one.'
        ),
    },
    {
        'regime_code': 'UP_AOA_2010',
        'instrument_type': 'Bye-laws',
        'title': "Model Bye-Laws for Uttar Pradesh Apartment Owners' Associations, 2011",
        'enactment_year': 2011,
        'issuing_authority': 'Government of Uttar Pradesh (under Sec 14(6) of the 2010 Act)',
        'applicability': "Every registered Apartment Owners' Association (AOA) in UP",
        'key_provisions': (
            'Governs internal AOA administration — membership, Board of Management, general'
            ' body/AGM procedure, voting rights, common seal, and the financial framework: '
            'common expenses, Reserve Fund (bye-laws 3(1)(d), 46), share capital (bye-laws '
            '5, 46), staff benefits (bye-law 3(1)(h)), the 1/2% transfer fee to the major-'
            'repair fund and No Dues deemed grant (bye-law 39), statements/audit (bye-law '
            '49). Bye-law 55: the Act prevails wherever a bye-law conflicts with it. '
            'Amendment needs approval by owners of at least 2/3rd of the units AND the '
            "competent authority's prior approval (Bye-law 58) — an AOA cannot simply amend"
            ' and file bye-laws without this.'
        ),
        'source_reference': (
            'Notified 16 Nov 2011 under Sec 14(6); interpreted in Olive Country Apartment '
            'Owners Association vs State of UP, WP No. 12110/2013, Allahabad HC, 14-11-2013'
        ),
        'display_order': 30,
        'status': 'active',
        'applies_when': 'always',
        'candidate_notification_no': '3977/8-1-11-115D.A./02T.C.-I dated 16 Nov 2011',
        'candidate_source_url': 'https://up-rera.in/pdf/Model-By-Laws.pdf',
        'candidate_note': 'Official UP-RERA PDF; text carries the notification number and date.',
    },
    {
        'regime_code': 'UP_AOA_2010',
        'instrument_type': 'Notification',
        'title': (
            'UP RERA General Regulations 2019 - Regulation 47 as amended: Interest Free '
            'Maintenance Security (IFMS)'
        ),
        'enactment_year': 2026,
        'issuing_authority': 'Uttar Pradesh Real Estate Regulatory Authority',
        'applicability': (
            'Promoters collecting interest-free maintenance security (IFMS) on projects in '
            'Uttar Pradesh; the corpus passes to the Association / RWA at handover of the '
            'common areas'
        ),
        'key_provisions': (
            'Notification 7098/U.P. RERA/Regulation/2026-27 dated 13.07.2026 sets project-'
            'wise IFMS rates; the promoter collects the IFMS at registration of the deed '
            'into a separate scheduled-bank account and invests it at the highest FD rate; '
            'at handover the whole corpus and a unit-wise statement go to the RWA; spend is'
            ' limited to operation, maintenance, repair and replacement of common areas; '
            'the RWA keeps separate books and a CA audit reported to the AGM within three '
            'months. Rates and unit (sq ft vs sq m) reported inconsistently - PROVISIONAL '
            'until checked against the notification text.'
        ),
        'source_reference': (
            'Reported by Business Standard (16 Jul 2026), India TV (20 Aug 2026), Zeus Law '
            'newsletter (Aug 2026); notification text not yet read. Builds on UP Apartment '
            'Act 2010 s.14(5) proviso.'
        ),
        'display_order': 35,
        'status': 'active',
        'applies_when': 'always',
        'candidate_notification_no': None,
        'candidate_source_url': None,
        'candidate_note': (
            "Press confirms '12th amendment to UP RERA (General) Regulations 2019, Reg 47' "
            "(Business Standard 16 Jul 2026). The number '7098/U.P. "
            "RERA/Regulation/2026-27' and date 13.07.2026 in the seed were NOT found in any"
            ' source; no official PDF found. Base regulations: https://up-'
            'rera.in/pdf/UPRERA_Regulation_2019.pdf (original Reg 47 is about fees). Fetch '
            'the notification from up-rera.in before verifying.'
        ),
    },
    {
        'regime_code': 'UP_AOA_2010',
        'instrument_type': 'Act',
        'title': 'Societies Registration Act, 1860 (as applicable in Uttar Pradesh)',
        'enactment_year': 1860,
        'issuing_authority': 'Government of India / adapted by UP',
        'applicability': (
            'RWAs/AOAs choosing registration as a society rather than (or in addition to) '
            'an AOA under the 2010 Act — minimum 7 members in UP'
        ),
        'key_provisions': (
            'Central registration statute administered in UP by the Registrar of Firms, '
            'Societies & Chits. Requires a Memorandum of Association (name, address, '
            'objects, governing-body members) and Rules & Regulations (membership, meeting '
            'procedure, managing-committee roles). Registration is valid 5 years and must '
            'be renewed within one month of expiry; a public notice with an objection '
            'window precedes approval.'
        ),
        'source_reference': 'UP Societies Registration Rules, 1976 govern the UP-specific procedure',
        'display_order': 40,
        'status': 'active',
        'applies_when': 'always',
        'candidate_notification_no': 'Central Act 21 of 1860, as amended in UP',
        'candidate_source_url': 'https://indiacode.nic.in/handle/123456789/18446',
        'candidate_note': (
            'India Code lists several state-department records for this Act (18446 and '
            '21579 both say Location: Uttar Pradesh); pick the one you prefer. UP has '
            'amended it repeatedly (e.g. UP Act 52 of 1975, UP Act 8 of 2022). Watch: UP CM'
            ' said (Sep 2025) the Act should be replaced.'
        ),
    },
    {
        'regime_code': 'UP_AOA_2010',
        'instrument_type': 'Rules',
        'title': 'Uttar Pradesh Societies Registration Rules, 1976',
        'enactment_year': 1976,
        'issuing_authority': 'Government of Uttar Pradesh',
        'applicability': 'Societies (including RWAs) registering under the 1860 Act in UP',
        'key_provisions': (
            'State procedural rules for the 1860 Act in UP: application format to the '
            'Deputy Registrar, required annexures, the public-notice/objection window '
            "(15-30 days, at the Registrar's discretion), and annual return/renewal filing."
        ),
        'source_reference': 'UP Society Registration Rules, 1976',
        'display_order': 50,
        'status': 'active',
        'applies_when': 'always',
        'candidate_notification_no': None,
        'candidate_source_url': None,
        'candidate_note': (
            'No official copy found; only secondary text (legitquest.com). Made under s.33 '
            'of the Act as amended by UP Act 52 of 1975. Notification number not found.'
        ),
    },
    {
        'regime_code': 'CENTRAL',
        'instrument_type': 'Central Act',
        'title': 'Real Estate (Regulation and Development) Act, 2016 (RERA)',
        'enactment_year': 2016,
        'issuing_authority': 'Government of India',
        'applicability': (
            'Promoters and Associations of Allottees for any RERA-registered project '
            '(enforced by state RERA authorities)'
        ),
        'key_provisions': (
            'Sec 11(4)(e): promoter must enable formation of the Association within 3 '
            'months of a majority of allottees booking units. Sec 11(4)(a)/(g): promoter '
            'remains responsible for obligations and outgoings (taxes, water/electricity, '
            'maintenance) until conveyance/handover.'
        ),
        'source_reference': 'RERA Act, 2016 (Central Act 16 of 2016)',
        'display_order': 70,
        'status': 'active',
        'applies_when': 'central_rera',
        'candidate_notification_no': (
            'Act 16 of 2016; S.O. 1544(E) dated 26 Apr 2016 and S.O. 1216(E) dated 19 Apr '
            '2017 (commencement)'
        ),
        'candidate_source_url': 'https://www.indiacode.nic.in/handle/123456789/17064',
        'candidate_note': (
            'Amended by Jan Vishwas (Amendment of Provisions) Act, 2026 (Act 8 of 2026), '
            "w.e.f. 7 May 2026 per a publisher's note - confirm and update key_provisions."
        ),
    },
    {
        'regime_code': 'CENTRAL',
        'instrument_type': 'Central Act',
        'title': 'Central Goods and Services Tax Act, 2017',
        'enactment_year': 2017,
        'issuing_authority': 'Government of India',
        'applicability': (
            'Societies/AOAs collecting maintenance from members; exemption threshold '
            'applies per member'
        ),
        'key_provisions': (
            'Notification No. 12/2017-CT (Rate) exempts RWA maintenance contributions up to'
            ' ₹7,500 per month per member from GST; registration required once aggregate '
            'turnover crosses the GST threshold.'
        ),
        'source_reference': 'CGST Act 2017; Notification No. 12/2017-Central Tax (Rate)',
        'display_order': 90,
        'status': 'active',
        'applies_when': 'central_gst',
        'candidate_notification_no': (
            'Central Tax Notification 1/2017 dated 19 Jun 2017 (sections in force 22 Jun '
            '2017)'
        ),
        'candidate_source_url': 'https://www.gstcouncil.gov.in/central-gst',
        'candidate_note': (
            'Index page of the GST Council (Act, Rules, Tax and Rate notifications). Not a '
            'direct link to the Act text.'
        ),
    },
    {
        'regime_code': 'CENTRAL',
        'instrument_type': 'Central Act',
        'title': 'Income-tax Act, 1961',
        'enactment_year': 1961,
        'issuing_authority': 'Government of India',
        'applicability': (
            'RWAs/AOAs assessing surplus from member contributions; applies to tax years up'
            ' to 2025-26'
        ),
        'key_provisions': (
            'Superseded by the Income-tax Act, 2025 from 1 Apr 2026. Still applies to '
            'income earned up to 31 Mar 2026 and to pending proceedings under the doctrine '
            'of mutuality.'
        ),
        'source_reference': 'Income-tax Act, 1961 (repealed w.e.f. 1 Apr 2026)',
        'display_order': 100,
        'status': 'superseded',
        'applies_when': 'central_it_tan',
        'candidate_notification_no': (
            'Act 43 of 1961; repealed by s.536(1) of the Income-tax Act, 2025 w.e.f. 1 Apr '
            '2026'
        ),
        'candidate_source_url': 'https://www.incometaxindia.gov.in/w/section-536-1',
        'candidate_note': (
            'This URL proves the repeal and savings (s.536), it is not the 1961 text. Add '
            'the 1961 text link if you want one.'
        ),
    },
    {
        'regime_code': 'CENTRAL',
        'instrument_type': 'Central Act',
        'title': 'Income-tax Act, 2025',
        'enactment_year': 2025,
        'issuing_authority': 'Government of India',
        'applicability': 'RWAs/AOAs assessing income from tax year 2026-27 onward',
        'key_provisions': (
            'Replaces the Income-tax Act, 1961 from 1 Apr 2026. TDS sections are renumbered'
            ' (Ss. 392-397). Both 1961 and 2025 section numbers are shown during the '
            'transition.'
        ),
        'source_reference': 'Income-tax Act, 2025 (as assented)',
        'display_order': 105,
        'status': 'active',
        'applies_when': 'central_it_tan',
        'candidate_notification_no': 'Act 30 of 2025 (assent 21 Aug 2025; in force 1 Apr 2026)',
        'candidate_source_url': 'https://www.incometaxindia.gov.in/w/section-1-269',
        'candidate_note': (
            "Income Tax Dept page, 'as amended by Finance Act, 2026'. Income-tax Rules, "
            '2026 (notified 20 Mar 2026) are not in the catalogue yet.'
        ),
    },
    {
        'regime_code': 'CENTRAL',
        'instrument_type': 'Central Act',
        'title': 'Digital Personal Data Protection Act, 2023',
        'enactment_year': 2023,
        'issuing_authority': 'Government of India',
        'applicability': (
            "Every society: it is the Data Fiduciary for members', tenants', vendors', "
            "guards' and staff data; the Platform Operator is its Data Processor"
        ),
        'key_provisions': (
            'Notice and consent for processing, purpose limitation, security safeguards, '
            'breach intimation, retention limits, rights of the Data Principal and a '
            "grievance officer. The Agreement's Annex D records the Fiduciary/Processor "
            'roles and sub-processors.'
        ),
        'source_reference': 'Digital Personal Data Protection Act, 2023 (Central Act 22 of 2023)',
        'display_order': 110,
        'status': 'active',
        'applies_when': 'always',
        'candidate_notification_no': (
            'Act 22 of 2023; commencement notification G.S.R. 843(E) dated 13 Nov 2025'
        ),
        'candidate_source_url': (
            'https://www.meity.gov.in/static/uploads/2024/06/2bf1f0e9f04e6fb4f8fef35e82c42aa5.pdf'
        ),
        'candidate_note': (
            'MeitY Gazette print. Also India Code: '
            'https://indiacode.gov.in/act/c058fa9f-eaf0-4ca3-98f1-3443b087bca9/sections. '
            'Removal of Difficulties Order S.O. 5458(E) (5 Oct 2026) only fixes wording in '
            'ss.9 and 10; read, no date changes.'
        ),
    },
    {
        'regime_code': 'CENTRAL',
        'instrument_type': 'Central Rules',
        'title': 'Digital Personal Data Protection Rules, 2025',
        'enactment_year': 2025,
        'issuing_authority': 'Ministry of Electronics and Information Technology',
        'applicability': (
            'Every society and the Platform Operator, in phases from the November 2025 '
            'notification'
        ),
        'key_provisions': (
            'Operational rules for notice, consent, security safeguards, breach intimation,'
            " retention and children's data. Commencement is phased (consent managers from "
            '13 Nov 2026; most duties from May 2027). EstateHub applies the duties early '
            'and the Agreement says so. Exact dates to be confirmed by an advocate.'
        ),
        'source_reference': 'DPDP Rules, 2025 (notified 13 Nov 2025)',
        'display_order': 111,
        'status': 'active',
        'applies_when': 'always',
        'candidate_notification_no': (
            'G.S.R. 846(E) dated 13 Nov 2025; corrigendum G.S.R. 892(E) dated 10 Dec 2025'
        ),
        'candidate_source_url': 'https://egazette.gov.in/WriteReadData/2025/267650.pdf',
        'candidate_note': (
            'eGazette; MeitY copy: '
            'https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf.'
            ' Phases: Rules 1,2,17-21 on 13 Nov 2025; Rule 4 on 13 Nov 2026; Rules '
            '3,5-16,22,23 on 13 May 2027. Some sites count from 14 Nov; one tracker calls '
            'the third date an interpretation. Ask an advocate.'
        ),
    },
    {
        'regime_code': 'CENTRAL',
        'instrument_type': 'Central Act',
        'title': 'Information Technology Act, 2000',
        'enactment_year': 2000,
        'issuing_authority': 'Government of India',
        'applicability': (
            'Electronic records, electronic signatures and cyber offences; governs the '
            'Agreement as an electronic contract'
        ),
        'key_provisions': (
            's.3A and the Second Schedule (electronic signature), s.4 to s.10A (electronic '
            'records and contracts), cyber offences and penalties.'
        ),
        'source_reference': 'Information Technology Act, 2000 (Central Act 21 of 2000)',
        'display_order': 120,
        'status': 'active',
        'applies_when': 'always',
        'candidate_notification_no': 'Act 21 of 2000',
        'candidate_source_url': (
            'https://indiacode.gov.in/server/api/core/bitstreams/770a7d02-48f2-4274-bab9-10d0f48ee264/content'
        ),
        'candidate_note': (
            'India Code consolidated print as on 27 Jun 2025 (link taken from a DPDP '
            'reference site; open it once to check).'
        ),
    },
    {
        'regime_code': 'CENTRAL',
        'instrument_type': 'Central Act',
        'title': 'Indian Contract Act, 1872',
        'enactment_year': 1872,
        'issuing_authority': 'Government of India',
        'applicability': (
            'Validity of the Agreement between the Society and the Platform Operator'
        ),
        'key_provisions': 'Offer, acceptance, consideration, capacity and free consent.',
        'source_reference': 'Indian Contract Act, 1872 (Central Act 9 of 1872)',
        'display_order': 125,
        'status': 'active',
        'applies_when': 'always',
        'candidate_notification_no': 'Act 9 of 1872 (in force 1 Sep 1872)',
        'candidate_source_url': 'https://indiacode.nic.in/handle/123456789/2187',
        'candidate_note': 'India Code record, Ministry of Law and Justice.',
    },
    {
        'regime_code': 'CENTRAL',
        'instrument_type': 'Central Act',
        'title': 'Indian Stamp Act, 1899',
        'enactment_year': 1899,
        'issuing_authority': 'Government of India',
        'applicability': (
            'Stamp duty on the Agreement, at the rate in the State schedule; e-stamping '
            'where available'
        ),
        'key_provisions': (
            'Duty is payable per the State schedule for the instrument. Rate to be '
            'confirmed by an advocate.'
        ),
        'source_reference': 'Indian Stamp Act, 1899 (as applied and amended in the State)',
        'display_order': 130,
        'status': 'active',
        'applies_when': 'always',
        'candidate_notification_no': 'Act 2 of 1899',
        'candidate_source_url': None,
        'candidate_note': (
            'India Code lists it but I did not get the handle. Duty is a State matter: also'
            ' check the UP stamp schedule and e-stamping rules.'
        ),
    },
    {
        'regime_code': 'CENTRAL',
        'instrument_type': 'Central Rules',
        'title': 'Central Goods and Services Tax Rules, 2017',
        'enactment_year': 2017,
        'issuing_authority': 'Government of India',
        'applicability': 'Societies registered or liable to register under GST',
        'key_provisions': (
            'Registration, invoicing, returns and reverse-charge procedure for societies '
            'that are GST-registered.'
        ),
        'source_reference': 'CGST Rules, 2017',
        'display_order': 91,
        'status': 'active',
        'applies_when': 'central_gst',
        'candidate_notification_no': (
            'Central Tax Notifications 3/2017 (19 Jun 2017), 10/2017 (28 Jun 2017), 15/2017'
            ' (1 Jul 2017)'
        ),
        'candidate_source_url': 'https://www.gstcouncil.gov.in/central-gst',
        'candidate_note': 'Same index page.',
    },
    {
        'regime_code': 'CENTRAL',
        'instrument_type': 'Central Act',
        'title': 'Integrated Goods and Services Tax Act, 2017',
        'enactment_year': 2017,
        'issuing_authority': 'Government of India',
        'applicability': (
            'Inter-State supplies; relevant where a society buys or sells across a State '
            'border'
        ),
        'key_provisions': 'Place of supply and IGST levy on inter-State supplies.',
        'source_reference': 'IGST Act, 2017',
        'display_order': 92,
        'status': 'active',
        'applies_when': 'central_gst',
        'candidate_notification_no': (
            'Integrated Tax Notification 1/2017 dated 19 Jun 2017 (in force 22 Jun 2017)'
        ),
        'candidate_source_url': None,
        'candidate_note': 'No official URL retrieved.',
    },
    {
        'regime_code': 'CENTRAL',
        'instrument_type': 'Central Act',
        'title': 'Private Security Agencies (Regulation) Act, 2005',
        'enactment_year': 2005,
        'issuing_authority': 'Government of India',
        'applicability': 'Societies that engage security guards through an agency',
        'key_provisions': (
            'A security agency must be licensed; the society should engage only a licensed '
            'agency.'
        ),
        'source_reference': (
            'Private Security Agencies (Regulation) Act, 2005 (Central Act 29 of 2005)'
        ),
        'display_order': 140,
        'status': 'active',
        'applies_when': 'has_security_agency',
        'candidate_notification_no': 'Act 29 of 2005; S.O. 317(E) dated 15 Mar 2006 (in force 14 Mar 2006)',
        'candidate_source_url': 'https://www.indiacode.nic.in/handle/123456789/2024',
        'candidate_note': (
            'UP Police also hosts the Act: https://www.uppolice.gov.in/Site-'
            'Content/uploaded-content/pdf/private_security_agencies_etc_act_2005.pdf. '
            "Central Model Rules 2006 and UP's own rules are not in the catalogue."
        ),
    },
    {
        'regime_code': 'CENTRAL',
        'instrument_type': 'Central Act',
        'title': 'Code on Social Security, 2020',
        'enactment_year': 2020,
        'issuing_authority': 'Government of India',
        'applicability': (
            'Societies that employ staff: provident fund, ESI and gratuity thresholds (in '
            'force 21 Nov 2025)'
        ),
        'key_provisions': (
            'Replaces the EPF Act, 1952 and the ESI Act, 1948. Rules of the Centre and '
            'State are still being notified; to be confirmed.'
        ),
        'source_reference': 'Code on Social Security, 2020',
        'display_order': 150,
        'status': 'active',
        'applies_when': 'has_employees',
        'candidate_notification_no': (
            'Act 36 of 2020; S.O. 5319(E) dated 21 Nov 2025; Social Security (Central) '
            'Rules, 2026 notified 8 May 2026'
        ),
        'candidate_source_url': None,
        'candidate_note': (
            "No official URL retrieved (try labour.gov.in). Seed text 'rules still being "
            "notified' is out of date for the Central Rules; UP state rules not checked."
        ),
    },
    {
        'regime_code': 'CENTRAL',
        'instrument_type': 'Central Act',
        'title': 'Code on Wages, 2019',
        'enactment_year': 2019,
        'issuing_authority': 'Government of India',
        'applicability': (
            'Societies that employ staff: minimum wages, timely payment and bonus (in force'
            ' 21 Nov 2025)'
        ),
        'key_provisions': (
            'Replaces the Payment of Wages Act, 1936 and the Minimum Wages Act, 1948.'
        ),
        'source_reference': 'Code on Wages, 2019',
        'display_order': 151,
        'status': 'active',
        'applies_when': 'has_employees',
        'candidate_notification_no': (
            'S.O. 5322(E) dated 21 Nov 2025; Code on Wages (Central) Rules, 2026 G.S.R. '
            '343(E) dated 8 May 2026'
        ),
        'candidate_source_url': None,
        'candidate_note': (
            'No official URL retrieved (try labour.gov.in). UP state rules not checked.'
        ),
    },
    {
        'regime_code': 'CENTRAL',
        'instrument_type': 'Central Act',
        'title': 'Bharatiya Sakshya Adhiniyam, 2023',
        'enactment_year': 2023,
        'issuing_authority': 'Government of India',
        'applicability': (
            'Admissibility of electronic records, including the signed Agreement and the '
            'ledger anchor'
        ),
        'key_provisions': (
            's.63 sets the conditions for electronic records as evidence. Replaced the '
            'Indian Evidence Act, 1872.'
        ),
        'source_reference': 'Bharatiya Sakshya Adhiniyam, 2023',
        'display_order': 160,
        'status': 'active',
        'applies_when': 'info',
        'candidate_notification_no': (
            'Act 47 of 2023 (assent 25 Dec 2023); S.O. 849(E) dated 23 Feb 2024 (in force 1'
            ' Jul 2024)'
        ),
        'candidate_source_url': 'https://indiacode.nic.in/handle/123456789/20063',
        'candidate_note': 'India Code record.',
    },
]


_TYPES = ("Act", "Rules", "Bye-laws", "Notification", "Central Act", "Central Rules")
_STATUS = ("active", "superseded", "draft")
_WHEN = ("always", "central_it_tan", "central_tds", "central_gst", "central_rera",
         "has_employees", "has_security_agency", "info")
_URL = re.compile(r"^https?://\S+$", re.IGNORECASE)
_SUBSTANCE = ("instrument_type", "issuing_authority", "applicability", "key_provisions", "source_reference",
              "display_order", "status", "applies_when")
_CANDIDATE = ("candidate_notification_no", "candidate_source_url", "candidate_note", "candidate_checked_on")


def key_of(row: dict) -> tuple:
    return (row["regime_code"], row["title"], row["enactment_year"])


def validate_instruments(rows=None) -> list[str]:
    """Problems with the data above (empty list = fine). Checked before anything is written."""
    rows = INSTRUMENTS if rows is None else rows
    problems, seen = [], set()
    for r in rows:
        k = key_of(r)
        label = f"{r.get('regime_code')} / {r.get('title', '?')[:60]}"
        if k in seen:
            problems.append(f"{label}: duplicate (regime_code, title, enactment_year)")
        seen.add(k)
        if r.get("instrument_type") not in _TYPES:
            problems.append(f"{label}: instrument_type {r.get('instrument_type')!r} not allowed")
        if r.get("status", "active") not in _STATUS:
            problems.append(f"{label}: status {r.get('status')!r} not allowed")
        if r.get("applies_when", "always") not in _WHEN:
            problems.append(f"{label}: applies_when {r.get('applies_when')!r} not allowed")
        for fld in ("title", "key_provisions", "source_reference"):
            if not (r.get(fld) or "").strip():
                problems.append(f"{label}: {fld} is required (NOT NULL)")
        if len(r.get("title", "")) > 300:
            problems.append(f"{label}: title longer than 300 characters")
        url = r.get("candidate_source_url")
        if url and not _URL.match(url):
            problems.append(f"{label}: candidate_source_url must start with http:// or https://")
        nn = r.get("candidate_notification_no")
        if nn and len(nn) > 255:
            problems.append(f"{label}: candidate_notification_no longer than 255 characters")
    return problems


# ── regime profiles ──────────────────────────────────────────────────────────────────────────────────────────────

def _pack_regime_profiles() -> list[tuple]:
    """Profiles of the schemes that have a pack (single source: schemes/*.toml)."""
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    from schemes.loader import load_all
    return [(sc.code, sc.state_code, sc.name, sc.primary_law, sc.rules_version, sc.model_bye_laws_version,
             sc.effective_from.isoformat(), None, sc.status, sc.source_reference, sc.constitution)
            for sc in load_all()]


def _val(row, name: str, pos: int = 0):
    """Read one column from a tuple row or a dict row (the installers use both cursor kinds)."""
    return row[name] if isinstance(row, dict) else row[pos]


def seed_regime_profiles(cur) -> int:
    """Insert missing legal_regime_profiles rows. Existing rows are left alone. Returns rows inserted."""
    n = 0
    for (code, state_code, name, primary_law, rules_version, bye_laws_version,
         eff_from, eff_to, status, source_ref, constitution) in _pack_regime_profiles() + EXTRA_REGIME_PROFILES:
        cur.execute(
            """INSERT INTO legal_regime_profiles
                   (code, state_code, constitution, name, primary_law, rules_version, model_bye_laws_version,
                    effective_from, effective_to, status, source_reference)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (code) DO NOTHING""",
            (code, state_code, constitution, name, primary_law, rules_version, bye_laws_version,
             eff_from, eff_to, status, source_ref))
        n += cur.rowcount
    return n


# ── instruments ──────────────────────────────────────────────────────────────────────────────────────────────────

_UPSERT = """
INSERT INTO legal_instrument_catalog
    (regime_code, instrument_type, title, enactment_year, issuing_authority, applicability, key_provisions,
     source_reference, display_order, status, applies_when,
     candidate_notification_no, candidate_source_url, candidate_note, candidate_checked_on)
VALUES
    (%(regime_code)s, %(instrument_type)s, %(title)s, %(enactment_year)s, %(issuing_authority)s, %(applicability)s,
     %(key_provisions)s, %(source_reference)s, %(display_order)s, %(status)s, %(applies_when)s,
     %(candidate_notification_no)s, %(candidate_source_url)s, %(candidate_note)s, %(candidate_checked_on)s)
ON CONFLICT ON CONSTRAINT uq_legal_instrument DO UPDATE SET
    candidate_notification_no = EXCLUDED.candidate_notification_no,
    candidate_source_url      = EXCLUDED.candidate_source_url,
    candidate_note            = EXCLUDED.candidate_note,
    candidate_checked_on      = EXCLUDED.candidate_checked_on,
    updated_at                = NOW()
WHERE (legal_instrument_catalog.candidate_notification_no, legal_instrument_catalog.candidate_source_url,
       legal_instrument_catalog.candidate_note, legal_instrument_catalog.candidate_checked_on)
      IS DISTINCT FROM
      (EXCLUDED.candidate_notification_no, EXCLUDED.candidate_source_url,
       EXCLUDED.candidate_note, EXCLUDED.candidate_checked_on)
RETURNING (xmax = 0) AS inserted
"""

_REFRESH = """
UPDATE legal_instrument_catalog SET
    instrument_type = %(instrument_type)s, issuing_authority = %(issuing_authority)s, applicability = %(applicability)s,
    key_provisions = %(key_provisions)s, source_reference = %(source_reference)s, display_order = %(display_order)s,
    status = %(status)s, applies_when = %(applies_when)s, updated_at = NOW()
WHERE regime_code = %(regime_code)s AND title = %(title)s AND enactment_year = %(enactment_year)s
  AND verification <> 'verified'
  AND (instrument_type, issuing_authority, applicability, key_provisions, source_reference, display_order, status, applies_when)
      IS DISTINCT FROM
      (%(instrument_type)s, %(issuing_authority)s, %(applicability)s, %(key_provisions)s, %(source_reference)s,
       %(display_order)s, %(status)s, %(applies_when)s)
"""


def _params(row: dict) -> dict:
    p = {"issuing_authority": None, "applicability": None, "display_order": 100, "status": "active",
         "applies_when": "always", "candidate_notification_no": None, "candidate_source_url": None,
         "candidate_note": None}
    p.update(row)
    has_lead = any(p[c] for c in ("candidate_notification_no", "candidate_source_url", "candidate_note"))
    p["candidate_checked_on"] = RESEARCHED_ON if has_lead else None
    return p


def seed_instruments(cur, refresh: bool = False) -> dict:
    """Insert missing catalogue rows and refresh the candidate_* leads.

    refresh=False (default, and what every install uses): an existing row's text is NOT touched, so a Master's edits
    survive a re-run. refresh=True also rewrites the text of UNVERIFIED rows from this file (never a verified row).
    Returns {"inserted": n, "leads_updated": n, "text_refreshed": n}.
    """
    problems = validate_instruments()
    if problems:
        raise ValueError("legal_reference data is invalid:\n  - " + "\n  - ".join(problems))
    regimes = {r["regime_code"] for r in INSTRUMENTS}
    cur.execute("SELECT code FROM legal_regime_profiles WHERE code = ANY(%s)", (sorted(regimes),))
    have = {_val(r, "code") for r in cur.fetchall()}
    if regimes - have:
        raise RuntimeError(f"Regime profile(s) missing: {sorted(regimes - have)}. The schema is out of date "
                           "(CENTRAL is created by estatehub.sql) or seed_regime_profiles() has not run.")
    out = {"inserted": 0, "leads_updated": 0, "text_refreshed": 0}
    for row in INSTRUMENTS:
        p = _params(row)
        cur.execute(_UPSERT, p)
        r = cur.fetchone()
        if r is not None:
            out["inserted" if _val(r, "inserted") else "leads_updated"] += 1
        if refresh:
            cur.execute(_REFRESH, p)
            out["text_refreshed"] += cur.rowcount
    return out


def seed_all(cur, refresh: bool = False) -> dict:
    """Profiles, then instruments. Runs inside the caller's transaction (the caller commits)."""
    profiles = seed_regime_profiles(cur)
    out = seed_instruments(cur, refresh=refresh)
    out["profiles_inserted"] = profiles
    return out


def install(conn, refresh: bool = False, quiet: bool = False) -> dict:
    """Mechanism 1 entry point for the installers: one transaction, commits on success, rolls back on any error.
    Does not close `conn`."""
    try:
        with conn.cursor() as cur:
            out = seed_all(cur, refresh=refresh)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    if not quiet:
        print(f"  ✓ Legal reference data: {out['inserted']} instruments added, {out['leads_updated']} leads updated, "
              f"{out['profiles_inserted']} regime profiles added"
              + (f", {out['text_refreshed']} rows' text refreshed" if refresh else ""))
    return out


# ── inspection (for the CLI and for tests) ───────────────────────────────────────────────────────────────────────

def status(cur) -> dict:
    """How the database compares with this file."""
    cur.execute("SELECT regime_code, title, enactment_year, verification, candidate_source_url IS NOT NULL AS has_lead "
                "FROM legal_instrument_catalog")
    rows = cur.fetchall()
    db_rows = {(_val(r, "regime_code"), _val(r, "title"), _val(r, "enactment_year")): r for r in rows}
    mine = {key_of(r) for r in INSTRUMENTS}
    return {
        "in_file": len(mine), "in_db": len(db_rows),
        "missing_from_db": sorted(mine - set(db_rows)),
        "only_in_db": sorted(set(db_rows) - mine),          # e.g. added by the Master; left alone
        "verified": sum(1 for r in rows if _val(r, "verification", 3) == "verified"),
        "unverified": sum(1 for r in rows if _val(r, "verification", 3) != "verified"),
        "unverified_without_lead": sum(1 for r in rows if _val(r, "verification", 3) != "verified" and not _val(r, "has_lead", 4)),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Load / inspect the legal reference data (Acts, Rules, Bye-laws, Notifications)")
    ap.add_argument("--check", action="store_true", help="only compare the database with this file; write nothing")
    ap.add_argument("--refresh", action="store_true", help="also rewrite the text of UNVERIFIED rows from this file")
    ap.add_argument("--validate", action="store_true", help="only validate this file's data (no database needed)")
    args = ap.parse_args(argv)

    problems = validate_instruments()
    if problems:
        print("Invalid data:\n  - " + "\n  - ".join(problems))
        return 2
    if args.validate:
        print(f"OK: {len(INSTRUMENTS)} instruments, {len(EXTRA_REGIME_PROFILES)} extra regime profile(s).")
        return 0

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import psycopg2
    import psycopg2.extras
    from dotenv import load_dotenv
    load_dotenv(override=False)
    from db_config import connection_params, describe_target
    print(f"Target: {describe_target()}")
    conn = psycopg2.connect(**connection_params(), cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        with conn.cursor() as cur:
            s = status(cur)
        print(f"  in this file: {s['in_file']}   in database: {s['in_db']}   verified: {s['verified']}   unverified: {s['unverified']}")
        for k in s["missing_from_db"]:
            print(f"  missing from database: {k[0]} / {k[1]} ({k[2]})")
        for k in s["only_in_db"]:
            print(f"  only in database (left alone): {k[0]} / {k[1]} ({k[2]})")
        if args.check:
            return 1 if s["missing_from_db"] else 0
        install(conn, refresh=args.refresh)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
