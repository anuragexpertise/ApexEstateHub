# Portal Testing - Quick Start Guide

## 5 Portals to Test

### 1️⃣ Master Admin Portal
- **URL:** http://localhost:8050/dashboard/master
- **Login:** master@estatehub.com / Master@2024
- **KPIs:** Total Societies, Paid/Free Plans, Apartments, Vendors, Security
- **Features:** Platform overview, manage all societies

### 2️⃣ Admin Portal
- **URL:** http://localhost:8050/dashboard/admin-portal
- **Login:** admin@lakesidetowers.com / Admin@123
- **Password:** Admin@123
- **KPIs:** 10 cards (Apartments, Vendors, Security, Events, Concerns, Gate Logs, Receipts, Expenses, Balance)
- **Tabs:** Dashboard, Enroll, Cashbook, Receipts, Expenses, Events, Concerns, Settings

### 3️⃣ Owner Portal
- **URL:** http://localhost:8050/dashboard/owner-portal
- **Login:** resident@lakesidetowers.com / Resident@123
- **KPIs:** Pending Dues, My Concerns, Events, Gate Logs, Paid, Balance
- **Tabs:** Dashboard, Cashbook, Payments, Charges, Events, Concerns, Settings

### 4️⃣ Vendor Portal
- **URL:** http://localhost:8050/dashboard/vendor-portal
- **Features:** Job tracking, payment tracking, event info

### 5️⃣ Security Portal
- **URL:** http://localhost:8050/dashboard/pass-evaluation
- **Features:** Pass evaluation, gate logs, attendance

---

## Test Flow (15 minutes)

### Step 1: Login & Access Master Portal (2 min)
```
1. Open http://localhost:8050/dashboard/
2. Login: master@estatehub.com / Master@2024
3. Should see Master Admin Portal
4. Verify 6 KPI cards display
```

### Step 2: Test KPI Interaction (3 min)
```
1. Click on "Total Societies" KPI card
2. Should see list of all societies
3. Click on "Lakeside Towers" row
4. Should navigate to society detail page
5. Verify detail card shows society info
6. Verify breadcrumb shows: Dashboard > Societies > Lakeside Towers
```

### Step 3: Test Profile Actions (2 min)
```
1. On society detail page, look for action buttons
2. Test Edit button → edit form should appear
3. Modify one field
4. Click Save
5. Verify success message and navigate back
```

### Step 4: Test Admin Portal (3 min)
```
1. Logout
2. Login: admin@lakesidetowers.com / Admin@123
3. Should see Admin Portal with 10 KPI cards
4. Click "Apartments" KPI
5. Should see list of apartments in this society
6. Test search: Type "A-" → should filter results
7. Click an apartment row → go to detail
8. Verify edit/delete/QR code buttons present
```

### Step 5: Test List Features (3 min)
```
1. Back to apartment list
2. Test pagination: Change "20" to "50" rows per page
3. Test sort: Click column header
4. Test search: Filter by apartment number
5. Test row selection: Click checkbox on a row
6. Bulk action should appear (delete/export)
```

### Step 6: Test Owner Portal (2 min)
```
1. Logout
2. Login: resident@lakesidetowers.com / Resident@123
3. Should see Owner Portal (6 KPIs)
4. Verify "Pending Dues" shows payment amount
5. Click "My Payments" tab
6. Should show payment history
7. Verify payment form/gateway available
```

---

## Key Things to Verify

### Visual Design
- [ ] Portal colors match role (Master: Orange, Admin: Blue, Owner: Green, Vendor: Gold)
- [ ] KPI cards have correct icons
- [ ] Cards are responsive (grid layout adapts)
- [ ] Breadcrumbs show current navigation
- [ ] Sidebar shows active tab highlighted

### Functionality
- [ ] KPI cards display numbers/values (not dashes)
- [ ] Click KPI → navigate to list
- [ ] Click list row → navigate to detail
- [ ] Edit button → form pre-filled with current data
- [ ] Save → success message → back to list
- [ ] Delete → confirmation modal → removed from list
- [ ] Search filters results in real-time
- [ ] Pagination next/prev works

### Data Accuracy
- [ ] Apartment count matches database
- [ ] Vendor count matches database
- [ ] Security staff count matches database
- [ ] Payment amounts are correct
- [ ] Dates display correctly

### User Experience
- [ ] No error messages visible
- [ ] Buttons are clickable
- [ ] Forms are easy to fill
- [ ] Loading states visible during operations
- [ ] Success/error messages clear

---

## Common Issues to Look For

### ❌ KPI Shows "—" (dash)
- **Cause:** Data not loading
- **Fix:** Refresh page, check network tab

### ❌ Can't Click KPI Card
- **Cause:** Card not interactive
- **Fix:** Check browser console for JS errors

### ❌ List Doesn't Load
- **Cause:** API error or no data
- **Fix:** Check browser network tab for 500 errors

### ❌ Edit Form Doesn't Submit
- **Cause:** Validation error or API issue
- **Fix:** Check form for red error messages

### ❌ Can't Delete Entity
- **Cause:** Permission error or still has relationships
- **Fix:** Check if entity is referenced elsewhere

---

## Portal-Specific Tests

### Master Portal Tests
- [ ] Can drill into each society
- [ ] Society counts match reality
- [ ] Can edit society information
- [ ] Can view all apartments across all societies
- [ ] Can view all vendors across all societies

### Admin Portal Tests

**Dashboard Tab:**
- [ ] All 10 KPIs display values
- [ ] Apartments count is correct
- [ ] Vendors/Security staff counts correct
- [ ] Events/Concerns/Gate logs count correct
- [ ] Financial figures (Balance, Receipts, Expenses) are correct

**Enroll Tab:**
- [ ] Can see current member counts
- [ ] Can add new apartment/owner
- [ ] Can add new vendor
- [ ] Can add new security staff

**Cashbook Tab:**
- [ ] Can see transaction ledger
- [ ] Receipts and Expenses listed
- [ ] Balance calculated correctly
- [ ] Can filter by date

**Events Tab:**
- [ ] Can see all society events
- [ ] Can create new event
- [ ] Can edit event details
- [ ] Can delete event
- [ ] Can view attendees

**Concerns Tab:**
- [ ] Can see all open concerns
- [ ] Can assign to staff
- [ ] Can change status
- [ ] Can add comments

### Owner Portal Tests
- [ ] Shows only my apartment data
- [ ] Pending Dues shows accurate amount
- [ ] Can view my payment history
- [ ] Can view my maintenance charges
- [ ] Can raise new concern
- [ ] Can view my concerns

---

## Form Testing Checklist

### Required Fields
- [ ] Fields marked with * are required
- [ ] Cannot submit if required field empty
- [ ] Error message appears on invalid field

### Text Fields
- [ ] Accept alphanumeric input
- [ ] Trim whitespace on blur
- [ ] Show character count if limited

### Date Fields
- [ ] Calendar picker opens on click
- [ ] Can select past/future dates (or restricted correctly)
- [ ] Format shown is DD/MM/YYYY

### Select Dropdowns
- [ ] All options visible
- [ ] Can search within options
- [ ] Default value pre-selected (for edit)

### File Upload
- [ ] Correct file types accepted
- [ ] File size limits enforced
- [ ] Preview shown before upload

---

## Profile Actions Quick Test

For any entity (Apartment, Vendor, Event, Concern):

1. **Edit Action**
   - [ ] Click Edit
   - [ ] Form appears with current values
   - [ ] Modify one field
   - [ ] Save → success message

2. **Delete Action**
   - [ ] Click Delete
   - [ ] Confirmation modal appears
   - [ ] Click Confirm → entity removed
   - [ ] Back in list → entity gone

3. **QR Code Action**
   - [ ] Click QR Code button
   - [ ] Modal shows generated QR
   - [ ] QR is scannable (can test with phone camera)
   - [ ] Contains entity ID/information

4. **Print Action**
   - [ ] Click Print
   - [ ] Browser print dialog appears
   - [ ] Print preview shows entity details

---

## Performance Checklist

- [ ] Portal loads in under 3 seconds
- [ ] KPI values display within 1 second
- [ ] List loads with 20 rows visible
- [ ] Search filters instantly (no page refresh)
- [ ] Form submit completes in 1-2 seconds
- [ ] Navigation between tabs is smooth
- [ ] No lag when scrolling lists

---

## Responsive Design

Test on:
- [ ] Desktop (1920x1080)
- [ ] Tablet (iPad, 1024x768)
- [ ] Mobile (iPhone, 375x667)

Verify:
- [ ] KPI cards stack responsively
- [ ] List columns compress on mobile
- [ ] Buttons still accessible
- [ ] Forms are usable
- [ ] Sidebar collapses on mobile

---

## Accessibility Quick Check

- [ ] Can Tab through all elements
- [ ] Form labels associated with inputs
- [ ] Buttons have text/aria-label
- [ ] Colors not sole indicator of status
- [ ] Error messages announced to screen readers

---

## Test Report Template

```
Date: _________
Tester: _________
Portal: [ ] Master [ ] Admin [ ] Owner [ ] Vendor [ ] Security

PASSED TESTS:
- KPI cards load ✅
- Can drill-down ✅
- List displays ✅

FAILED TESTS:
- [Issue]: [Steps to reproduce]

ISSUES FOUND:
1. [Priority] [Issue description]
2. ...

COMMENTS:
```

---

## Quick Navigation

**Master Portal:**
- Dashboard: http://localhost:8050/dashboard/master
- Societies: Click any KPI

**Admin Portal:**
- Dashboard: http://localhost:8050/dashboard/admin-portal
- Tabs: Click sidebar tabs

**Owner Portal:**
- Dashboard: http://localhost:8050/dashboard/owner-portal

---

**🎯 Ready to Start Testing?**

1. Keep this guide open
2. Open http://localhost:8050/dashboard/ in browser
3. Follow the Test Flow (15 min)
4. Note any issues
5. Report findings
