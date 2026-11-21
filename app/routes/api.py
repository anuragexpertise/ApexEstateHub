# app/routes/api.py
from datetime import date

from flask import Blueprint, jsonify, make_response, request

from app.auth.jwt_handler import token_required
from app.services.icai_statements import statements
from app.services.msme_service import msme_payment_compliance
from database.db_manager import db  # ← Fix import
from database.financial_statements_export import export_trial_balance

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/societies', methods=['GET'])
@token_required
def get_societies(current_user):
    """Get all societies (master admin only)"""
    if current_user.role != 'master':
        return jsonify({'error': 'Unauthorized'}), 403

    societies = db._execute(
        "SELECT id, name, email, phone, plan, created_at FROM societies ORDER BY name",
        fetch_all=True
    )
    return jsonify({'societies': societies or []})

@api_bp.route('/societies/<int:society_id>', methods=['GET'])
@token_required
def get_society(current_user, society_id):
    """Get society details"""
    # Own society, or master. (It used to let ANY society's admin read ANY society.)
    if current_user.role != 'master' and current_user.society_id != society_id:
        return jsonify({'error': 'Unauthorized'}), 403

    society = db._execute(
        "SELECT id, name, email, phone, address, plan FROM societies WHERE id = %s",
        (society_id,), fetch_one=True
    )
    return jsonify({'society': society or {}})

@api_bp.route('/dashboard/kpis', methods=['GET'])
@token_required
def get_kpis(current_user):
    """Get KPI data for dashboard"""
    society_id = current_user.society_id

    if not society_id:
        if current_user.role != 'master':
            return jsonify({'error': 'Unauthorized'}), 403
        # Master admin - return global KPIs
        totals = db._execute(
            "SELECT COUNT(*) as societies, SUM(CASE WHEN plan = 'Paid' THEN 1 ELSE 0 END) as paid FROM societies",
            fetch_one=True
        )
        return jsonify({
            'total_societies': totals.get('societies', 0),
            'paid_plan': totals.get('paid', 0),
            'free_plan': totals.get('societies', 0) - totals.get('paid', 0)
        })

    # Society-specific KPIs
    kpis = db._execute("""
        SELECT
            (SELECT COUNT(*) FROM apartments WHERE society_id = %s AND active = TRUE) as total_apartments,
            (SELECT COUNT(*) FROM users WHERE society_id = %s AND role = 'vendor') as total_vendors,
            (SELECT COUNT(*) FROM users WHERE society_id = %s AND role = 'security') as total_security,
            (SELECT COUNT(*) FROM events WHERE society_id = %s AND event_date >= CURRENT_DATE) as upcoming_events,
            (SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE society_id = %s AND status = 'paid' AND trx_date >= date_trunc('month', CURRENT_DATE)) as monthly_receipts
    """, (society_id, society_id, society_id, society_id, society_id), fetch_one=True)

    return jsonify(kpis or {})


@api_bp.route('/msme/compliance', methods=['GET'])
@token_required
def get_msme_compliance(current_user):
    """MSME 45-day payment compliance for one vendor of the user's society.

    Query params: vendor_id (required), asof (optional YYYY-MM-DD).
    Mirrors fn_msme_payment_compliance (s.15/s.16 MSMED Act 2006).
    """
    society_id = current_user.society_id
    vendor_id = request.args.get('vendor_id', type=int)
    if not vendor_id:
        return jsonify({'error': 'vendor_id is required'}), 400
    asof = None
    asof_str = request.args.get('asof')
    if asof_str:
        try:
            asof = date.fromisoformat(asof_str)
        except ValueError:
            return jsonify({'error': 'asof must be YYYY-MM-DD'}), 400
    result = msme_payment_compliance(society_id, vendor_id, asof)
    return jsonify(result or {})


@api_bp.route('/statements', methods=['GET'])
@token_required
def get_icai_statements(current_user):
    """ICAI statutory statements (Balance Sheet, Income & Expenditure,
    Receipts & Payments, Trial Balance) for the user's society.

    Query params: fy (optional, defaults to current FY).
    """
    society_id = current_user.society_id
    fy = request.args.get('fy', type=int)
    return jsonify(statements(society_id, fy))


@api_bp.route('/statements/trial-balance/export', methods=['GET'])
@token_required
def export_icai_trial_balance(current_user):
    """Download the Trial Balance as XLSX (export_trial_balance from
    database/financial_statements_export.py)."""
    society_id = current_user.society_id
    fy = request.args.get('fy', type=int)
    if not fy:
        fy = date.today().year
        if date.today().month < 4:
            fy -= 1
    xlsx = export_trial_balance(db, society_id, fy, format="xlsx")
    response = make_response(xlsx)
    response.headers['Content-Type'] = ('application/vnd.openxmlformats-'
                                        'officedocument.spreadsheetml.sheet')
    response.headers['Content-Disposition'] = (
        f'attachment; filename="trial_balance_fy{fy}.xlsx"')
    return response
