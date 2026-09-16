import sys
import re

def patch():
    file_path = 'app/dash_apps/callbacks/drilldown_callbacks.py'
    with open(file_path, 'r') as f:
        content = f.read()

    # 1. Gate Logs
    content = re.sub(
        r'("INSERT INTO gate_access\(society_id,role,entity_id,time_in,created_by\) "\\s*"VALUES\(%s,%s,%s,NOW\(\),%s\)",\\s*\(sid, d\.get\("role", "v"\), eid, d\.get\("user_id"\)\),)',
        '"INSERT INTO gate_access(society_id,role,entity_id,time_in,time_out,created_by) "\\n        "VALUES(%s,%s,%s,COALESCE(%s::timestamp, NOW()),%s,%s)",\\n        (sid, d.get("role", "v"), eid, d.get("time_in"), d.get("time_out"), d.get("user_id")),',
        content
    )

    # 2. Assets
    content = re.sub(
        r'("UPDATE assets SET asset_name=%s, asset_SNo=%s, company_name=%s, "\\s*"updated_by=%s "\\s*"WHERE id=%s AND society_id=%s",\\s*\(asset_name, d\.get\("asset_SNo"\), d\.get\("company_name"\), d\.get\("user_id"\), pk, sid\),)',
        '"UPDATE assets SET asset_name=%s, asset_SNo=%s, company_name=%s, depreciation_rate=%s, itc_claimed=%s, gst_disposal_liability=%s, "\\n            "updated_by=%s "\\n            "WHERE id=%s AND society_id=%s",\\n            (asset_name, d.get("asset_sno") or d.get("asset_SNo"), d.get("company_name"), d.get("depreciation_rate"), d.get("itc_claimed"), d.get("gst_disposal_liability"), d.get("user_id"), pk, sid),',
        content
    )

    content = re.sub(
        r'(asset_id = \(r or \{\}\)\.get\("asset_id"\)\\s*expense_id = \(r or \{\}\)\.get\("expense_id"\))',
        '\\1\\n        if asset_id:\\n            db._execute("UPDATE assets SET depreciation_rate=%s, itc_claimed=%s, gst_disposal_liability=%s WHERE id=%s", (d.get("depreciation_rate"), d.get("itc_claimed"), d.get("gst_disposal_liability"), asset_id))',
        content
    )

    # 3. Patrol Locations
    content = re.sub(
        r'("UPDATE patrol_locations\\s*SET location_name=%s, description=%s, active=%s, scan_interval=%s, latitude=%s, longitude=%s, nfc_enabled=%s\\s*WHERE id=%s AND society_id=%s",\\s*\(loc_name, description, active, scan_interval, lat, lon, nfc, pk, sid\))',
        '"UPDATE patrol_locations\\n               SET location_name=%s, description=%s, active=%s, scan_interval=%s, latitude=%s, longitude=%s, nfc_enabled=%s, schedule_start=%s, schedule_end=%s\\n               WHERE id=%s AND society_id=%s",\\n            (loc_name, description, active, scan_interval, lat, lon, nfc, d.get("schedule_start"), d.get("schedule_end"), pk, sid)',
        content
    )

    content = re.sub(
        r'("INSERT INTO patrol_locations \(society_id, location_name, description, active, scan_interval, latitude, longitude, nfc_enabled, created_by\)\\s*VALUES \(%s, %s, %s, %s, %s, %s, %s, %s, %s\)",\\s*\(sid, loc_name, description, active, scan_interval, lat, lon, nfc, get_current_user_id\(\)\))',
        '"INSERT INTO patrol_locations (society_id, location_name, description, active, scan_interval, latitude, longitude, nfc_enabled, schedule_start, schedule_end, created_by)\\n               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",\\n            (sid, loc_name, description, active, scan_interval, lat, lon, nfc, d.get("schedule_start"), d.get("schedule_end"), get_current_user_id())',
        content
    )

    # 4. Societies
    content = re.sub(
        r'("registration_number=%s,tan_number=%s,"\\s*"payment_qr=COALESCE\(NULLIF\(%s, \'\'\), payment_qr\) "\\s*"WHERE id=%s",\\s*\(\\s*d\.get\("name"\),\\s*d\.get\("email"\),\\s*d\.get\("phone"\),\\s*d\.get\("address"\),\\s*d\.get\("plan", "Free"\),\\s*d\.get\("logo"\),\\s*d\.get\("login_background"\),\\s*d\.get\("secretary_sign"\),\\s*d\.get\("secretary_name"\),\\s*d\.get\("secretary_phone"\),\\s*d\.get\("plan_validity"\),\\s*d\.get\("calc_start_date"\),\\s*d\.get\("pan_number"\),\\s*d\.get\("gstin"\),\\s*d\.get\("registration_number"\),\\s*d\.get\("tan_number"\),\\s*d\.get\("payment_qr"\),\\s*pk,\\s*\),)',
        '"registration_number=%s,tan_number=%s,"\\n                "payment_qr=COALESCE(NULLIF(%s, \'\'), payment_qr), "\\n                "secretary_email=%s, gate_logic=%s, duty_hrs=%s, primary_bank_account_id=%s "\\n                "WHERE id=%s",\\n                (\\n                    d.get("name"),\\n                    d.get("email"),\\n                    d.get("phone"),\\n                    d.get("address"),\\n                    d.get("plan", "Free"),\\n                    d.get("logo"),\\n                    d.get("login_background"),\\n                    d.get("secretary_sign"),\\n                    d.get("secretary_name"),\\n                    d.get("secretary_phone"),\\n                    d.get("plan_validity"),\\n                    d.get("calc_start_date"),\\n                    d.get("pan_number"),\\n                    d.get("gstin"),\\n                    d.get("registration_number"),\\n                    d.get("tan_number"),\\n                    d.get("payment_qr"),\\n                    d.get("secretary_email"),\\n                    d.get("gate_logic"),\\n                    d.get("duty_hrs"),\\n                    d.get("primary_bank_account_id"),\\n                    pk,\\n                ),',
        content
    )
    
    content = re.sub(
        r'("secretary_name=%s,secretary_phone=%s,"\\s*"payment_qr=COALESCE\(NULLIF\(%s, \'\'\), payment_qr\) "\\s*"WHERE id=%s",\\s*\(\\s*d\.get\("email"\),\\s*d\.get\("phone"\),\\s*d\.get\("address"\),\\s*d\.get\("logo"\),\\s*d\.get\("login_background"\),\\s*d\.get\("secretary_sign"\),\\s*d\.get\("secretary_name"\),\\s*d\.get\("secretary_phone"\),\\s*d\.get\("payment_qr"\),\\s*pk,\\s*\),)',
        '"secretary_name=%s,secretary_phone=%s,"\\n                "payment_qr=COALESCE(NULLIF(%s, \'\'), payment_qr), "\\n                "secretary_email=%s, gate_logic=%s, duty_hrs=%s, primary_bank_account_id=%s "\\n                "WHERE id=%s",\\n                (\\n                    d.get("email"),\\n                    d.get("phone"),\\n                    d.get("address"),\\n                    d.get("logo"),\\n                    d.get("login_background"),\\n                    d.get("secretary_sign"),\\n                    d.get("secretary_name"),\\n                    d.get("secretary_phone"),\\n                    d.get("payment_qr"),\\n                    d.get("secretary_email"),\\n                    d.get("gate_logic"),\\n                    d.get("duty_hrs"),\\n                    d.get("primary_bank_account_id"),\\n                    pk,\\n                ),',
        content
    )

    # 5. Accounts
    content = re.sub(
        r'("is_depreciable=%s, tds_section=%s "\\s*"WHERE id=%s AND society_id=%s",\\s*\(\\s*name,\\s*d\.get\("tab_name"\),\\s*d\.get\("header"\),\\s*d\.get\("drcr_account", False\),\\s*d\.get\("drcr_bf", False\),\\s*d\.get\("depreciation_percent"\),\\s*d\.get\("is_depreciable", False\),\\s*d\.get\("tds_section"\),\\s*pk,\\s*sid,\\s*\),)',
        '"is_depreciable=%s, tds_section=%s, "\\n            "parent_account_id=%s, has_bf=%s, mutuality_nature=%s "\\n            "WHERE id=%s AND society_id=%s",\\n            (\\n                name,\\n                d.get("tab_name"),\\n                d.get("header"),\\n                d.get("drcr_account", False),\\n                d.get("drcr_bf", False),\\n                d.get("depreciation_percent"),\\n                d.get("is_depreciable", False),\\n                d.get("tds_section"),\\n                d.get("parent_account_id"),\\n                d.get("has_bf", False),\\n                d.get("mutuality_nature"),\\n                pk,\\n                sid,\\n            ),',
        content
    )
    content = re.sub(
        r'("tds_section\) "\\s*"VALUES\(%s, %s, %s, %s, %s, %s, %s, %s, %s\)",\\s*\(\\s*sid,\\s*name,\\s*d\.get\("tab_name"\),\\s*d\.get\("header"\),\\s*d\.get\("drcr_account", False\),\\s*d\.get\("drcr_bf", False\),\\s*d\.get\("depreciation_percent"\),\\s*d\.get\("is_depreciable", False\),\\s*d\.get\("tds_section"\),\\s*\),)',
        '"tds_section, parent_account_id, has_bf, mutuality_nature) "\\n            "VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",\\n            (\\n                sid,\\n                name,\\n                d.get("tab_name"),\\n                d.get("header"),\\n                d.get("drcr_account", False),\\n                d.get("drcr_bf", False),\\n                d.get("depreciation_percent"),\\n                d.get("is_depreciable", False),\\n                d.get("tds_section"),\\n                d.get("parent_account_id"),\\n                d.get("has_bf", False),\\n                d.get("mutuality_nature"),\\n            ),',
        content
    )

    # 6. Security Roster
    content = re.sub(
        r'("UPDATE security_roster SET shift_type=%s WHERE id=%s AND society_id=%s",\\s*\(d\.get\("shift_type"\), pk, sid\),)',
        '"UPDATE security_roster SET shift_type=%s, attendance_status=%s WHERE id=%s AND society_id=%s",\\n            (d.get("shift_type"), d.get("attendance_status"), pk, sid),',
        content
    )
    content = re.sub(
        r'("INSERT INTO security_roster \(society_id, security_id, roster_date, shift_type, created_by\) "\\s*"VALUES \(%s, %s, %s, %s, %s\)",\\s*\(sid, sec_id, d\.get\("roster_date"\), d\.get\("shift_type"\), get_current_user_id\(\)\),)',
        '"INSERT INTO security_roster (society_id, security_id, roster_date, shift_type, attendance_status, created_by) "\\n            "VALUES (%s, %s, %s, %s, %s, %s)",\\n            (sid, sec_id, d.get("roster_date"), d.get("shift_type"), d.get("attendance_status"), get_current_user_id()),',
        content
    )

    # 7. Channels
    content = re.sub(
        r'("UPDATE channels SET channel_type=%s, name=%s, identifier=%s, apartment_id=%s, is_recurring=%s "\\s*"WHERE id=%s AND society_id=%s",\\s*\(c_type, name, ident, d\.get\("apartment_id"\), d\.get\("is_recurring", False\), pk, sid\),)',
        '"UPDATE channels SET channel_type=%s, name=%s, identifier=%s, apartment_id=%s, is_recurring=%s, active=%s "\\n            "WHERE id=%s AND society_id=%s",\\n            (c_type, name, ident, d.get("apartment_id"), d.get("is_recurring", False), d.get("active", True), pk, sid),',
        content
    )
    content = re.sub(
        r'("INSERT INTO channels \(society_id, channel_type, name, identifier, apartment_id, is_recurring\) "\\s*"VALUES \(%s, %s, %s, %s, %s, %s\)",\\s*\(sid, c_type, name, ident, d\.get\("apartment_id"\), d\.get\("is_recurring", False\)\),)',
        '"INSERT INTO channels (society_id, channel_type, name, identifier, apartment_id, is_recurring, active) "\\n            "VALUES (%s, %s, %s, %s, %s, %s, %s)",\\n            (sid, c_type, name, ident, d.get("apartment_id"), d.get("is_recurring", False), d.get("active", True)),',
        content
    )
    
    # 8. TDS Rates
    content = re.sub(
        r'("UPDATE tds_rates SET section=%s, nature_of_income=%s, rate=%s, rate_no_pan=%s, single_bill_threshold=%s, annual_aggregate_threshold=%s, effective_from=%s "\\s*"WHERE id=%s",\\s*\(\\s*section,\\s*nature_of_income,\\s*rate,\\s*rate_no_pan,\\s*single_thr,\\s*annual_thr,\\s*eff_from,\\s*pk,\\s*\),)',
        '"UPDATE tds_rates SET section=%s, nature_of_income=%s, rate=%s, rate_no_pan=%s, single_bill_threshold=%s, annual_aggregate_threshold=%s, effective_from=%s, effective_to=%s "\\n            "WHERE id=%s",\\n            (\\n                section,\\n                nature_of_income,\\n                rate,\\n                rate_no_pan,\\n                single_thr,\\n                annual_thr,\\n                eff_from,\\n                d.get("effective_to"),\\n                pk,\\n            ),',
        content
    )
    content = re.sub(
        r'("INSERT INTO tds_rates \(section, nature_of_income, rate, rate_no_pan, single_bill_threshold, annual_aggregate_threshold, effective_from, created_by\)\\s*VALUES \(%s, %s, %s, %s, %s, %s, %s, %s\)",\\s*\(\\s*section,\\s*nature_of_income,\\s*rate,\\s*rate_no_pan,\\s*single_thr,\\s*annual_thr,\\s*eff_from,\\s*get_current_user_id\(\),\\s*\),)',
        '"INSERT INTO tds_rates (section, nature_of_income, rate, rate_no_pan, single_bill_threshold, annual_aggregate_threshold, effective_from, effective_to, created_by)\\n            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",\\n            (\\n                section,\\n                nature_of_income,\\n                rate,\\n                rate_no_pan,\\n                single_thr,\\n                annual_thr,\\n                eff_from,\\n                d.get("effective_to"),\\n                get_current_user_id(),\\n            ),',
        content
    )


    with open(file_path, 'w') as f:
        f.write(content)

if __name__ == '__main__':
    patch()
