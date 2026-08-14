# app/routes/presumed_visitor.py
"""
Owner-initiated pre-registration of visitors (presumed visitors).

Owner fills expected visitor details → inserts a visitors row with
status='pending' and source='owner'. Security's existing
get_presumed_visitors() query already surfaces these, so no new reader
is needed there.
"""

from flask import Blueprint, request, jsonify
from flask_login import login_required
import logging

from app.services.alert_service import create_walk_in_visitor, get_presumed_visitors
from app.services.redis_broker import broker

logger = logging.getLogger(__name__)
presumed_bp = Blueprint('presumed_visitor', __name__)


@presumed_bp.route('/api/owner/presumed-visitors', methods=['POST'])
@login_required
def create_presumed_visitor():
    """
    Owner pre-registers an expected visitor.

    Body: {
        name: str,
        mobile: str (optional),
        purpose: str (optional),
        vehicle_number: str (optional),
        visit_date: str (YYYY-MM-DD, optional, defaults today),
        visit_time_from: str (HH:MM, optional),
        visit_time_to: str (HH:MM, optional),
    }
    """
    try:
        data = request.get_json() or {}
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'success': False, 'message': 'Visitor name is required'}), 400

        user_id = int(current_user.get_id())
        role = getattr(current_user, 'role', '')
        if role != 'apartment':
            return jsonify({'success': False, 'message': 'Only apartment owners can pre-register visitors'}), 403

        society_id = getattr(current_user, 'society_id', None)
        linked_id = getattr(current_user, 'linked_id', None)
        if not society_id or not linked_id:
            return jsonify({'success': False, 'message': 'Owner profile incomplete'}), 400

        apartment_id = linked_id
        mobile = (data.get('mobile') or '').strip() or None
        purpose = (data.get('purpose') or '').strip() or None
        vehicle_number = (data.get('vehicle_number') or '').strip() or None
        visit_date = data.get('visit_date') or None
        visit_time_from = data.get('visit_time_from') or None
        visit_time_to = data.get('visit_time_to') or None

        visitor_id, msg = create_walk_in_visitor(
            society_id=society_id,
            name=name,
            mobile=mobile,
            purpose=purpose,
            apartment_id=apartment_id,
            vehicle_number=vehicle_number,
            security_user_id=None,
        )
        if not visitor_id:
            return jsonify({'success': False, 'message': msg}), 500

        from database.db_manager import db
        db._execute(
            """UPDATE visitors SET source = 'owner', visit_date = COALESCE(%s, CURRENT_DATE),
               visit_time_from = %s, visit_time_to = %s WHERE id = %s""",
            (visit_date, visit_time_from, visit_time_to, visitor_id),
        )

        broker.publish({
            "type": "presumed_visitor_created",
            "society_id": society_id,
            "user_id": user_id,
            "data": {
                "visitor_id": visitor_id,
                "name": name,
                "flat_number": None,
                "apartment_id": apartment_id,
            },
        })

        return jsonify({'success': True, 'visitor_id': visitor_id, 'message': 'Presumed visitor pre-registered'}), 201

    except Exception as e:
        logger.error(f"Create presumed visitor error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@presumed_bp.route('/api/owner/presumed-visitors', methods=['GET'])
@login_required
def list_presumed_visitors():
    user_id = int(current_user.get_id())
    role = getattr(current_user, 'role', '')
    if role != 'apartment':
        return jsonify({'success': False, 'message': 'Only apartment owners can view presumed visitors'}), 403

    society_id = getattr(current_user, 'society_id', None)
    linked_id = getattr(current_user, 'linked_id', None)
    if not society_id or not linked_id:
        return jsonify({'success': False, 'message': 'Owner profile incomplete'}), 400

    rows = get_presumed_visitors(society_id)
    apt_ids = {r.get("apartment_id") for r in rows if r.get("apartment_id")}
    if linked_id in apt_ids:
        rows = [r for r in rows if r.get("apartment_id") == linked_id]
    else:
        rows = []

    return jsonify({'success': True, 'visitors': rows or []})
