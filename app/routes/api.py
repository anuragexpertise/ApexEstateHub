# app/routes/api.py
import logging
from datetime import date

import psycopg2
from flask import Blueprint, jsonify, make_response, request

from app.auth.jwt_handler import token_required
from app.security.roles import MASTER_ROLE
from app.services.icai_statements import StatementUnavailable, statements, export_gate
from app.services.msme_service import msme_payment_compliance
from database.db_manager import db  # ← Fix import
from database.financial_statements_export import export_trial_balance

api_bp = Blueprint('api', __name__, url_prefix='/api')

log = logging.getLogger(__name__)

# Coarse roles allowed to read a society's financial statements / MSME
# compliance. A treasurer is an admin who holds the treasurer RBAC post, so
# role 'admin' covers it; 'master' (platform, no society) is allowed only
# with an explicit society_id query param.
FINANCIAL_ROLES = {"admin", "accountant", MASTER_ROLE}
_FY_MIN, _FY_MAX = 2000, 2100


def _financial_society_id(current_user):
    """Resolve the society id for a financial-data call.

    Returns (society_id, None) or (None, (response, status)) for master
    callers without a valid explicit society_id.
    """
    if current_user.role == MASTER_ROLE:
        sid = request.args.get('society_id', type=int)
        if not sid:
            return None, (jsonify({'error': 'master caller must pass society_id'}), 400)
        society = db._execute(
            "SELECT id FROM societies WHERE id = %s", (sid,), fetch_one=True)
        if not society:
            return None, (jsonify({'error': 'unknown society_id'}), 400)
        return sid, None
    sid = current_user.society_id
    if not sid:
        return None, (jsonify({'error': 'no society on user'}), 400)
    return sid, None


def _parse_fy():
    fy = request.args.get('fy', type=int)
    if fy is None:
        fy = date.today().year
        if date.today().month < 4:
            fy -= 1
    if not isinstance(fy, int) or fy < _FY_MIN or fy > _FY_MAX:
        return None, (jsonify({'error': f'fy must be an integer between {_FY_MIN} and {_FY_MAX}'}), 400)
    return fy, None

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
    if current_user.role not in FINANCIAL_ROLES:
        return jsonify({'error': 'Insufficient permissions'}), 403
    society_id, err = _financial_society_id(current_user)
    if err:
        return err
    vendor_id = request.args.get('vendor_id', type=int)
    if not vendor_id:
        return jsonify({'error': 'vendor_id is required'}), 400
    # The vendor must belong to the caller's society (no cross-society reads).
    vendor = db._execute(
        "SELECT id FROM vendors WHERE id = %s AND society_id = %s",
        (vendor_id, society_id), fetch_one=True)
    if not vendor:
        return jsonify({'error': 'vendor not found in your society'}), 404
    asof = None
    asof_str = request.args.get('asof')
    if asof_str:
        try:
            asof = date.fromisoformat(asof_str)
        except ValueError:
            return jsonify({'error': 'asof must be YYYY-MM-DD'}), 400
    try:
        result = msme_payment_compliance(society_id, vendor_id, asof)
    except StatementUnavailable as exc:
        return jsonify({'error': exc.message,
                        'society_id': exc.society_id, 'fy': exc.fy}), 404
    except psycopg2.Error:
        log.exception("msme compliance query failed for society %s vendor %s",
                      society_id, vendor_id)
        return jsonify({'error': 'msme compliance unavailable'}), 500
    return jsonify(result or {})


@api_bp.route('/statements', methods=['GET'])
@token_required
def get_icai_statements(current_user):
    """ICAI statutory statements (Balance Sheet, Income & Expenditure,
    Receipts & Payments, Trial Balance) for the user's society.

    Query params: fy (optional, defaults to current FY).
    Master callers must pass an explicit society_id.
    """
    if current_user.role not in FINANCIAL_ROLES:
        return jsonify({'error': 'Insufficient permissions'}), 403
    society_id, err = _financial_society_id(current_user)
    if err:
        return err
    fy, err = _parse_fy()
    if err:
        return err
    try:
        return jsonify(statements(society_id, fy))
    except StatementUnavailable as exc:
        return jsonify({'error': exc.message,
                        'society_id': exc.society_id, 'fy': exc.fy}), 404
    except psycopg2.Error:
        log.exception("statements query failed for society %s fy %s",
                      society_id, fy)
        return jsonify({'error': 'statement unavailable'}), 500


@api_bp.route('/statements/trial-balance/export', methods=['GET'])
@token_required
def export_icai_trial_balance(current_user):
    """Download the Trial Balance as XLSX (export_trial_balance from
    database/financial_statements_export.py)."""
    if current_user.role not in FINANCIAL_ROLES:
        return jsonify({'error': 'Insufficient permissions'}), 403
    society_id, err = _financial_society_id(current_user)
    if err:
        return err
    fy, err = _parse_fy()
    if err:
        return err
    try:
        gate = export_gate(society_id, fy)
    except psycopg2.Error:
        log.exception("export gate failed for society %s fy %s", society_id, fy)
        return jsonify({'error': 'export gate unavailable'}), 500
    if not gate["allowed"]:
        return jsonify({"error": "Export refused: " + gate["reason"], "gate": gate}), 409
    xlsx = export_trial_balance(db, society_id, fy, format="xlsx")
    response = make_response(xlsx)
    response.headers['Content-Type'] = ('application/vnd.openxmlformats-'
                                        'officedocument.spreadsheetml.sheet')
    response.headers['Content-Disposition'] = (
        f'attachment; filename="trial_balance_fy{fy}.xlsx"')
    return response
