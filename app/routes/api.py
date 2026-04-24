# app/routes/api.py
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from database.db_manager import db  # ← Fix import
from app.auth.jwt_handler import token_required, role_required

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/societies', methods=['GET'])
@token_required
def get_societies(current_user):
    """Get all societies (master admin only)"""
    if current_user.role != 'admin' or current_user.society_id is not None:
        return jsonify({'error': 'Unauthorized'}), 403

    societies = db.execute_query(
        "SELECT id, name, email, phone, plan, created_at FROM societies ORDER BY name",
        fetch_all=True
    )
    return jsonify({'societies': societies or []})

@api_bp.route('/societies/<int:society_id>', methods=['GET'])
@token_required
def get_society(current_user, society_id):
    """Get society details"""
    if current_user.society_id != society_id and current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    society = db.execute_query(
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
        # Master admin - return global KPIs
        totals = db.execute_query(
            "SELECT COUNT(*) as societies, SUM(CASE WHEN plan = 'Paid' THEN 1 ELSE 0 END) as paid FROM societies",
            fetch_one=True
        )
        return jsonify({
            'total_societies': totals.get('societies', 0),
            'paid_plan': totals.get('paid', 0),
            'free_plan': totals.get('societies', 0) - totals.get('paid', 0)
        })

    # Society-specific KPIs
    kpis = db.execute_query("""
        SELECT
            (SELECT COUNT(*) FROM apartments WHERE society_id = %s AND active = TRUE) as total_apartments,
            (SELECT COUNT(*) FROM users WHERE society_id = %s AND role = 'vendor') as total_vendors,
            (SELECT COUNT(*) FROM users WHERE society_id = %s AND role = 'security') as total_security,
            (SELECT COUNT(*) FROM events WHERE society_id = %s AND event_date >= CURRENT_DATE) as upcoming_events,
            (SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE society_id = %s AND status = 'paid' AND trx_date >= date_trunc('month', CURRENT_DATE)) as monthly_receipts
    """, (society_id, society_id, society_id, society_id, society_id), fetch_one=True)

    return jsonify(kpis or {})
