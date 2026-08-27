# app/routes/exports.py
from flask import Blueprint, request, make_response
from database.db_manager import db
from app.auth.jwt_handler import token_required
import csv
from io import StringIO

exports_bp = Blueprint('exports', __name__, url_prefix='/export')

@exports_bp.route('/mutuality_report', methods=['GET'])
@token_required
def export_mutuality_report(current_user):
    if current_user.role != 'admin':
        return "Unauthorized", 403

    society_id = current_user.society_id
    fy = request.args.get('fy')
    
    if not fy:
        return "Financial Year (fy) parameter required, e.g., '2026-27'", 400

    rows = db._execute("SELECT * FROM fn_income_tax_summary_fy(%s, %s)", (society_id, fy), fetch_all=True)
    if not rows:
        return "No data found for this financial year.", 404

    si = StringIO()
    # Handle the case where row might be empty even if rows exist
    if len(rows) > 0:
        writer = csv.DictWriter(si, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    else:
        si.write("No data")

    resp = make_response(si.getvalue())
    resp.headers["Content-Disposition"] = f"attachment; filename=mutuality_report_{society_id}_{fy}.csv"
    resp.headers["Content-Type"] = "text/csv"
    return resp
