# GOLD STANDARD IMPLEMENTATION PLAN - ApexEstateHub Compliance Upgrade

**Objective:** Transform ApexEstateHub into a gold-standard platform for RWA/AOA management that meets the needs of authorities, legal professionals, Income Tax officials, GST authorities, Chartered Accountants, and government authorities.

**Date:** 2025-10-23  
**Scope:** Comprehensive review of requirements from todo.txt + current codebase state analysis

---

## EXECUTIVE SUMMARY

Based on the extensive todo.txt and codebase analysis, this plan identifies gaps across governance, compliance, portals, funds management, legal hierarchy, and audit requirements. The codebase has strong foundations (immutable ledger, hash chains, role-based access) but several critical areas need implementation/fixing.

---

## 1. GOVERNANCE & LEGAL HIERARCHY RESTRUCTURING (CRITICAL - PRIORITY 1)

### 1.1 Legal Hierarchy Verification (UP-Specific)
**Current State:** Partially implemented in regime_rules_admin.py, setup_wizard.py  
**Issues from todo:**
- Need to verify hierarchy: Central Acts → UP_AOA Acts → UPAOA Rules → UP Model Bye-Laws → Society Policy
- Central Acts (Income Tax, GST, RERA) are mandatory - category "Central Acts Compliance" can be removed
- State Acts need choice of constitution: ['AOA', 'Registered Society', 'Cooperative', 'Generic'], default='AOA'
- Rules applied based on applicable acts (AOA → UP Apartment Rules, RERA → Rera Rules, Society Registration → Society Registration Rules)
- Society Bye-laws = Model Bye-Laws adopted by society
- Society Policy needs 2/3 majority, Society Resolution needs 1/2 majority, Board Meetings by committee/board

**Actions Required:**
- [ ] **Verify and document** UP legal hierarchy (fetch gazette texts where possible)
- [ ] **Restructure Legal Regime Selection** in setup wizard - remove "Central Acts Compliance" category, make Central Acts mandatory/read-only banner
- [ ] **Add Constitution type selector** (AOA/Registered Society/Cooperative/Generic) with default AOA
- [ ] **Implement rule application logic** based on constitution type and applicable acts
- [ ] **Fix Society Governance tabs** in admin/owner settings per the detailed spec in todo
- [ ] **Clarify voting majorities** in resolution system (2/3 for policy/bye-law changes, 1/2 for resolutions, committee decisions for board)
- [ ] **Add weighted voting tallying** at GBM (currently missing per todo)

### 1.2 Setup Wizard Restructuring
**Current State:** WIZARD_GROUPS in setup_wizard.py (line ~263) needs reordering per todo  
**Required Order:** ['Instructions', 'Society Details', 'Administrator', 'TAN & TDS Rates', 'GSTIN & GST Rates', 'Compliance (UP_AOA)', 'By-Laws Adoption', 'Apartment Charges', 'Vendor Charges', 'Accounts', 'Brought Forward', 'Agreement']

**Actions Required:**
- [ ] Reorder CATEGORIES array to match required order
- [ ] Update WIZARD_GROUPS to align with legal hierarchy
- [ ] Rename steps: 'Adminstrator' → 'Administrator', 'Bye-Laws Adoption' clarity
- [ ] Add "Constitution" selection (integrate with Legal Regime)
- [ ] Make Registration Number read-only (fed by master, like Name/PAN)
- [ ] Fix TDS/RERA toggles - they only skip steps currently, not stored for Review
- [ ] Update Review step to show all selections

### 1.3 Society Governance KPI & Tabs (Admin/Owner)
**Current State:** governance_settings.py exists but needs restructuring per todo  
**Required:** Settings tab with 4 dcc.tabs ['RWA Compliance (UP)', 'Rules', 'Society By-Laws', 'Meetings & Resolutions']

**Actions Required:**
- [ ] **Tab 1 - RWA Compliance (UP):** Informative only, show 10 instruments, "Edit a catalog entry" only for master
- [ ] **Tab 2 - Rules:** Show 'Rules in force today', 'Scheduled changes' (scoped), 'Audit log (last 25)' (scoped), 'Change a rule' (admin only), 'Cash-limit enforcement' (scoped)
- [ ] **Tab 3 - Society By-laws:** List with [clause-no, title, Layer, variation, Effective, state, Resolution] + action buttons → profile for "Provisional Bye-Law Choice" with clause, definition, options, layer, effective_date, reason. Add "Record Policy Choice" for Society Policy settings
- [ ] **Tab 4 - Meetings & Resolutions:** 3 lists - Meetings (+New→Record Meetings), Resolutions (+New→Record Resolutions), Resolutions-Enacted (pending with Execute button)
- [ ] **Deduplicate** overlapping functionality between master_rules_page and governance_settings
- [ ] **Streamline** Rules/Society By-Laws/Meetings tabs per detailed spec

---

## 2. FUNDS MANAGEMENT & BROUGHT FORWARDS (CRITICAL)

### 2.1 Funds Category Restructuring
**From todo:** "The Category 'Funds' and Category 'Brought Forwards' should have all Funds and their rates and applicability statute or provisional and their brought forwards should be labelled according to UP AOA."

**UP AOA Funds (to verify):**
- Sinking Fund Reserve
- Repair Fund Reserve  
- Corpus Fund
- Major Repair Fund
- Need parameters, when to levy, rates, etc.

**Current Issues:**
- Brought Forward asks for Sinking Fund Reserve, Repair Fund Reserve, Corpus Fund, Major Repair Fund - need to understand why and if correct per UP AOA
- Sinking fund default = 'Undivided interest of surplus' - check UP AOA
- Major Repair & Maintenance fund default 'Undivided interest of surplus' - check UP AOA
- Mislabelled in schemes/UP_AOA_2010.toml (bye-law 46(d) cited for depreciation fund but 46(d) is about raising loans; no depreciation fund in Model Bye-Laws)
- Rent reserve booking assumed goes to Major Repair Fund (bye-law 3(1)(d)) - design choice to confirm

**Actions Required:**
- [ ] **Research UP AOA 2010 Model Bye-Laws** for correct fund provisions (bye-laws 3, 46, etc.)
- [ ] **Verify prescribed vs optional funds** per UP_AOA regime via web search/gazette
- [ ] **Correct fund labels** in Funds and Brought Forward categories per UP AOA
- [ ] **Fix mislabeling** in schemes/UP_AOA_2010.toml (depreciation fund issue)
- [ ] **Determine correct defaults** (undivided interest of surplus vs other methods)
- [ ] **Label brought forwards** according to UP AOA requirements
- [ ] **Clarify rates and applicability** (statute vs provisional)
- [ ] **Review IFMS rates** - marked provisional, need verification against UP RERA notification 7098 of 13.07.2026

### 2.2 Apartment Charges Redesign
**From todo:** Detailed redesign required

**Proposed Flow:**
1. Part A - society defaults (optional): Construction Cost of Project (₹), Default Rate per sq ft (₹), Default Fixed Amount (₹), Monthly Common-Expense Budget (₹)
2. Part B - "Maintenance Billing Basis" selector default Undivided Interest. Show/require only needed field: Undivided needs monthly budget; Per Sq Ft needs rate; Fixed needs amount. Block Next if needed field is 0
3. State "this is society default. Individual apartments can be given their own basis at enrolment"
4. Add columns for construction cost, allow fixed in CHECK constraint and engine, pass new values through fn_complete_society_setup
5. After enrolment, flats need undivided % (backfill gives area share until Declaration figures entered)

**Actions Required:**
- [ ] Redesign Apartment Charges step in wizard
- [ ] Update database schema (add construction cost columns, allow fixed in constraints)
- [ ] Update fn_complete_society_setup to handle new values
- [ ] Update billing engine for fixed charges
- [ ] Update enrollment to support per-apartment basis
- [ ] Fix backfill for undivided percentages

### 2.3 Interest Calculation Fixes
**Issues:**
- Two sources of truth: wizard stores apt_interest_pct, interest engine reads arrears_interest_pct and skips if empty. Make apt_interest_pct the only source of truth.
- Remove cap max=1.75 from Setup wizard. Rate set by General Body resolution per UP Model Bye-Laws 2011 bye-law 46(a). Need citation/case name to display.
- Cap only enforced in wizard, not in DB CHECK

**Actions Required:**
- [ ] Make apt_interest_pct the single source of truth
- [ ] Update interest engine to read apt_interest_pct (not arrears_interest_pct)
- [ ] Remove 1.75% cap from wizard UI/validation
- [ ] Add proper legal text referencing bye-law 46(a)
- [ ] Add DB CHECK if needed or rely on GB resolution
- [ ] Update UI to show correct source

---

## 3. NEW PORTALS & TEAM MANAGEMENT (CRITICAL)

### 3.1 Create 4 New Portals
**Required:** 'Accountant', 'Supervisor', 'Staff', 'Auditor'  
**Colors:** { 'Accountant': purple, 'Supervisor': orange, 'Staff': white, 'Auditor': red}

**Current State:** 
- team_page.py exists for creating logins (added recently per todo)
- auditors_page.py exists
- Need full portal implementations

**Actions Required:**
- [ ] **Add to portal routing** in shell_callbacks.py and app structure
- [ ] **Create portal page functions** (similar to other portals in portal_pages.py)
- [ ] **Add themes/colors** to _C dict
- [ ] **Define permissions/role matrix** for each portal
- [ ] **Suggest and implement tabs** for each portal
- [ ] **Update login/routing** to support new roles
- [ ] **Add to RBAC/policy system**

**Suggested Tabs:**
- **Accountant:** Financials preparation, Receivables/Payables, TDS/GST exports, Ledger review (read-only posting prep), Bank reconciliation prep
- **Supervisor:** Staff management, Shifts/Attendance oversight, Patrol monitoring, Concerns assignment oversight
- **Staff:** Limited operational tasks as assigned, attendance, basic concerns
- **Auditor:** Verification dashboard per the checklist in todo (ledger chain, integrity, cash vouchers, anchors, receipt chains, resolution tallies, legal instruments). Read-only comprehensive audit tools.

### 3.2 Team Logins Screen (Admin Portal)
**Current State:** team_page.py exists, team_callbacks.py exists - appears implemented per todo  
**Issues mentioned:** 
- "still no screen to create accountant, auditor, supervisor or staff logins" was mentioned earlier but seems addressed
- Missing KPI cards for accountant/supervisor/staff/committee in admin Enrolled tab default layout
- Lists point to profile_user page that doesn't exist

**Actions Required:**
- [ ] Verify Team Logins tab is properly integrated in admin portal
- [ ] Add KPI cards to Enrolled tab layout (kpi_accountant_total, kpi_supervisor_total, kpi_staff_total, kpi_committee_bearers already exist in card_catalogue)
- [ ] Create profile_user page/form for viewing/editing team member profiles
- [ ] Ensure all 4 roles can be created/managed
- [ ] Test disable/enable functionality with users.active column

---

## 4. LEGAL COMPLIANCE & DOCUMENTATION (CRITICAL)

### 4.1 Links in Legal Hierarchy Table
**Issue:** Hard-coded links need to be replaced with dynamic data from kpi_rule_links and legal_instrument_catalog

**Required:**
- Central Acts: Income Tax Act 1961, GST Act 2017, RERA 2016 from kpi_rule_links
- State Act and AOA Rules: society's state instruments from catalog (not hard-coded UP)
- Model Bye-laws: notified model bye-laws link for state
- Society Adopted Bye-laws, Resolutions, Board Meetings: Internal links

**Verify:** Check seeded URLs (Designarch link looks like placeholder)

**Actions Required:**
- [ ] Replace hard-coded legal hierarchy links with dynamic rendering
- [ ] Pull from kpi_rule_links by category/state
- [ ] Pull from legal_instrument_catalog
- [ ] Add internal links to wizard steps and governance settings
- [ ] Verify all URLs are valid

### 4.2 Compliance Documentation
**Need:** conversation.xlsx updates, NEWS.xlsx for fetching rates/acts

**From todo:**
- "write conversation.xlsx accordingly" for onboarding flow
- "create prompts - [1) Fetch latest TDS Rates for webapp, 2) Fetch latest Acts and bye-laws for KPI_Rule_links of web App, etc 3) Fetch various rates as prescribed by Indian laws] store this tabulated as 'NEWS.xlsx'"

**Actions Required:**
- [ ] Update conversation.xlsx with correct onboarding flow
- [ ] Create NEWS.xlsx with prompts for fetching rates/acts
- [ ] Document data sources
- [ ] Create automation scripts/prompts

### 4.3 Remove Central Acts Category
Per todo: "The Central Acts ['Income Tax, GST, RERA] are mandatory. So Cateory 'Central Acts Compliance can be removed."
Currently in WIZARD_GROUPS as "Central Acts": ["TAN & TDS Rates", "GSTIN & GST Rate"] - need to restructure

**Actions Required:**
- [ ] Remove "Central Acts Compliance" category
- [ ] Make Central Acts mandatory banner/info (read-only)
- [ ] Integrate TDS/GST steps differently
- [ ] Update wizard flow

---

## 5. FINANCIAL CONTROLS & ACCOUNTING (HIGH PRIORITY)

### 5.1 Cash Management
**From ER.md:**
- Explicit Cash-in-Hand leg not done (intentionally - caused double bugs before)
- Cash voucher controls implemented
- ₹2,00,000 cash receipt limit enforced
- Need to ensure proper controls

**Actions Required:**
- [ ] Review cash voucher controls
- [ ] Ensure cashbook reconciliation works
- [ ] Verify daily cash book signing
- [ ] Test cash receipt limits

### 5.2 Receipts & Expenses Workflows
**Detailed requirements in todo:**
- Creation of Receipts by Admin
- Creation of Expenses by Admin
- Receipts by Security Guard / initiation by Apartment owner
- FIFO vs Selective payments by Apartment owners
- Simple interest calculation
- TDS calculation
- Appropriation into Sinking Fund, Repair Fund etc per parameters
- Verification by Admin / Fulfillment by Apartment owner
- Display in 'My Transactions' on Apartment portal
- Transaction in Cashbook
- As per Indian RWA Acts and bye-laws
- Selective payments under protest (hold disputed penalty)

**Actions Required:**
- [ ] Implement/verify receipt creation workflows for all roles
- [ ] Implement expense creation
- [ ] Implement FIFO and selective payment logic
- [ ] Add functions for selective payments (proposed in todo)
- [ ] Implement interest calculation (simple interest)
- [ ] Implement TDS calculation integration
- [ ] Implement fund appropriation logic
- [ ] Build verification/fulfillment workflow
- [ ] Ensure proper display in My Transactions
- [ ] Update Cashbook integration

### 5.3 Asset Management
**Buying/Selling Assets:**
- Selling requires GST output tax calculation (Sec 18(6) CGST, Rule 44(6)) - todo says "system implements this perfectly via fn_asset_gst_disposal_liability PL/pgSQL function" - verify
- Need to ensure complete workflow

**Actions Required:**
- [ ] Verify asset purchase workflow
- [ ] Verify asset sale with GST calculation
- [ ] Test fn_asset_gst_disposal_liability
- [ ] Ensure proper accounting entries

### 5.4 Vendor Passes, Events, Tickets
**Requirements:**
- Creation of Vendor Pass, Sale/Buy, Receipts, QR generation, Scanning
- Creation of Events, Sale/Buy tickets, Receipts, QR generation, Scanning individual tickets
- Involving all non-master portals

**Actions Required:**
- [ ] Verify vendor pass workflow end-to-end
- [ ] Verify event/ticket workflow
- [ ] Ensure QR generation and scanning work
- [ ] Check all portals can participate

---

## 6. SECURITY, ATTENDANCE & PATROL (HIGH PRIORITY)

### 6.1 Security Salary Calculation
**Complex requirements:**
- From shifts_count, appointment of shifts, clock-in/clock-out
- Attendance as per security_roster
- Timed QR scanning or NFC scanning for Attendance
- Scanning of Patrol Locations
- Missing patrol locations penalties
- Ultimate salary calculation by shift status + deductions/penalties
- Review by Admin, confirmation of payables, Salary receipt generation

**Actions Required:**
- [ ] Implement/verify shift management
- [ ] Implement attendance tracking (QR/NFC)
- [ ] Implement patrol location scanning
- [ ] Implement penalty logic for missed patrols
- [ ] Implement salary calculation engine
- [ ] Build admin review/confirmation workflow
- [ ] Generate salary receipts/payables

### 6.2 Patrol Locations
**Create patrol locations and randomised patrol scan allotted to on-duty security guards**

**Actions Required:**
- [ ] Implement patrol location management
- [ ] Implement randomization/allocation logic
- [ ] Integrate with attendance/scanning
- [ ] Track compliance

---

## 7. COMMUNITY FEATURES (MEDIUM-HIGH PRIORITY)

### 7.1 Concerns Workflow
**All stages, bidding, assignment, completion, resolution/closure. No financial side-effects.**

**Actions Required:**
- [ ] Verify all concern stages
- [ ] Verify bidding workflow
- [ ] Verify assignment and completion
- [ ] Ensure no financial side effects

### 7.2 Polls
**Requirements:**
- Selection of voters as 'ALL members' vs 'Members with no dues' (default)
- Voting one-per-apartment
- 15min notification before endtime
- Automatic declaration of results on end-time
- No financial side-effects
- Ability to print list_polls by every member for records and transparency

**Actions Required:**
- [ ] Verify voter selection logic
- [ ] Verify one-per-apartment enforcement
- [ ] Implement 15min notifications
- [ ] Implement auto-declaration of results
- [ ] Add print functionality for poll lists
- [ ] Ensure transparency

---

## 8. UI/UX FIXES & CLEANUP

### 8.1 Dashboard Issues
**From first message:** "on master portall, 'Dashboard' tab: KPIs are showing filtered list of master_society, but the list opened by the filtered KPIs is not filtered according to society plan_validity"

**Actions Required:**
- [ ] Investigate KPI filtering for master_society on master portal dashboard
- [ ] Fix drilldown/list filtering for plan_validity
- [ ] Check drilldown_callbacks.py and related code

### 8.2 Admin Portal Fixes
**From todo:** "Admin Portal >> Dashboard - Remove 'Body Text' from list_issued_noc"  
**Admin Portal >> Financials - Financials >> Securities Salaries due >> list has duplicated columns. There should be edit button to change 'Shift Fraction'"

**Actions Required:**
- [ ] Fix list_issued_noc to remove Body Text
- [ ] Fix Securities Salaries due list - remove duplicates, add edit button for Shift Fraction

### 8.3 Remove ALTER TABLE statements
**"Remove 'ALTER TABLE' statements and create them INLINE with CREATE TABLE,, except those which have circular references eg users and apartments etc"**

**Current State:** ER.md says "estatehub.sql is now the only SQL in the repository. Tables carry their columns and constraints inline; the only ALTER TABLE left is societies.fk_primary_bank_account (societies and accounts reference each other, so one side cannot be declared inline)."

**Actions Required:**
- [ ] Verify all ALTER TABLE removed except circular refs
- [ ] Ensure everything inline in CREATE TABLE
- [ ] Check migrate.py still works

---

## 9. TESTING & QUALITY ASSURANCE

### 9.1 Test Status
**From todo/ER.md:**
- 855 test functions, last run had 1130 passed, 16 failed
- 216 tests fail or error in sandbox (many due to push-notification package)
- 4 live-database tests fail on master
- Some tests skipped

**Actions Required:**
- [ ] Run full test suite to understand current state
- [ ] Fix failing tests where possible
- [ ] Ensure critical compliance tests pass
- [ ] Add tests for new functionality

### 9.2 Security Review
**"Perform a security and functional code review and provide a report with recommendations"** (mentioned in todo)

**Actions Required:**
- [ ] Review authorization/RBAC
- [ ] Review ledger immutability
- [ ] Review SQL injection vectors
- [ ] Review session management
- [ ] Review file uploads
- [ ] Generate security report

---

## 10. IMPLEMENTATION PRIORITY MATRIX

| Priority | Area | Reason | Effort |
|----------|------|--------|--------|
| **P0** | Legal Hierarchy Restructuring | Core compliance, affects all societies | High |
| **P0** | Funds & Brought Forwards (UP AOA compliance) | Critical for correct accounting | High |
| **P0** | Interest calculation fixes (apt_interest_pct source of truth, remove cap) | Legal compliance issue | Medium |
| **P0** | Apartment Charges redesign | Core billing functionality | High |
| **P1** | New Portals (Accountant/Supervisor/Staff/Auditor) | Required by todo, affects operations | High |
| **P1** | Team Logins completion (profile pages, KPI cards) | Needed for new portals | Medium |
| **P1** | Receipts/Expenses/Payments workflows | Core financial operations | High |
| **P1** | Security salary & patrol | Operational requirement | High |
| **P2** | Governance tabs restructuring | Organization/UX improvement | Medium |
| **P2** | Legal hierarchy links dynamic | Documentation/compliance | Medium |
| **P2** | Dashboard fixes | Reported bug | Low |
| **P2** | Admin portal fixes | Reported bugs | Low |
| **P3** | Events/Tickets/Vendor Passes verification | Seems implemented, needs testing | Medium |
| **P3** | Concerns/Polls verification | Seems implemented, needs testing | Medium |

---

## 11. RECOMMENDED APPROACH

### Phase 1: Research & Documentation (Week 1)
1. Research UP AOA 2010, Model Bye-Laws 2011, UP Apartment Rules 2011
2. Verify fund structures, voting majorities, interest rules
3. Check gazette texts for disputed items
4. Document findings
5. Update NEWS.xlsx and conversation.xlsx

### Phase 2: Critical Compliance Fixes (Week 2)
1. Fix legal hierarchy in setup wizard
2. Fix funds/brought forwards for UP AOA
3. Fix interest calculation (single source of truth, remove cap)
4. Redesign apartment charges
5. Fix dashboard KPI filtering bug

### Phase 3: Portals & Team Management (Week 3)
1. Create Accountant/Supervisor/Staff/Auditor portals
2. Complete team logins (profile pages, layouts)
3. Implement role permissions
4. Build Auditor verification dashboard

### Phase 4: Financial Workflows (Week 4)
1. Complete receipts/expenses/payments
2. Implement selective payments
3. Implement fund appropriations
4. Security salary & patrol
5. Verify asset workflows

### Phase 5: Testing & Hardening (Week 5)
1. Run tests, fix failures
2. Security review
3. Integration testing
4. Documentation updates
5. Final compliance check

---

## 12. CRITICAL NOTES

- **No backward compatibility** - existing DBs need reset_database.py per todo
- **TDS figures need CA confirmation**
- **Some items marked provisional** - need advocate/CA input
- **216 tests fail in sandbox** - mostly env issues, but need to verify
- **Estatehub.sql is source of truth** - no more ALTER TABLE except circular refs
- **Ledger immutability is critical** - don't break it
- **Role segregation must be maintained**

---

**END OF PLAN**
