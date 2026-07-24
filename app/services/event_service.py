# app/services/event_service.py

import logging
from datetime import date
from database.db_manager import db
from app.services.qr_service import generate_qr_code

logger = logging.getLogger(__name__)


def create_event(
    society_id: int,
    title: str,
    event_date: str,
    venue: str = None,
    description: str = None,
    event_time: str = None,
    ticket_price: float = 0.0,
    ticket_price2: float = 0.0,
    ticket_name: str = "Adult",
    ticket_name2: str = "Child",
    parent_account_id: int = None,
    open_to: str = "all",
    image: str = None,
    created_by: int = None,
):
    """Create an event in society."""
    try:
        row = db._execute("""
            INSERT INTO events (
                society_id, title, description, venue, event_date, event_time,
                open_to, parent_account_id, ticket_name, ticket_price,
                ticket_name2, ticket_price2, image, created_at, created_by
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s)
            RETURNING id
        """, (
            society_id, title, description, venue, event_date, event_time,
            open_to, parent_account_id, ticket_name, ticket_price,
            ticket_name2, ticket_price2, image, created_by,
        ), fetch_one=True)
        return row["id"], "Event created successfully"
    except Exception as e:
        logger.error(f"Error creating event: {e}")
        return None, str(e)


def book_event_tickets(
    society_id: int,
    event_id: int,
    user_id: int,
    quantity_adult: int = 0,
    quantity_child: int = 0,
    mode: str = "cash",
    created_by: int = None,
    issued_date: str = None,
    particulars: str = None,
):
    """
    Book event tickets via fn_sell_event_ticket and generate N individual
    ticket item QRs (<society_id>-EVT-<ticket_item_id>).
    """
    try:
        r = db._execute(
            "SELECT * FROM fn_sell_event_ticket(%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                int(user_id),
                int(event_id),
                int(quantity_adult),
                int(quantity_child),
                mode,
                created_by,
                issued_date or date.today().isoformat(),
                particulars,
            ),
            fetch_one=True,
        )
        ticket_id = (r or {}).get("ticket_id")
        if not ticket_id:
            return None, "Failed to book tickets"

        event_ticket_id = ticket_id
        created_items = []

        for i in range(quantity_adult):
            item_row = db._execute("""
                INSERT INTO event_ticket_items (event_ticket_id, society_id, ticket_type, qr_payload, status)
                VALUES (%s, %s, 'ADULT', 'TEMP_QR', 'active')
                RETURNING id
            """, (event_ticket_id, society_id), fetch_one=True)

            item_id = item_row["id"]
            qr_img, payload = generate_qr_code(society_id, "EVT", item_id)

            db._execute("UPDATE event_ticket_items SET qr_payload = %s WHERE id = %s", (payload, item_id))
            created_items.append({
                "item_id": item_id,
                "ticket_type": "ADULT",
                "qr_payload": payload,
                "qr_img": qr_img,
            })

        for i in range(quantity_child):
            item_row = db._execute("""
                INSERT INTO event_ticket_items (event_ticket_id, society_id, ticket_type, qr_payload, status)
                VALUES (%s, %s, 'CHILD', 'TEMP_QR', 'active')
                RETURNING id
            """, (event_ticket_id, society_id), fetch_one=True)

            item_id = item_row["id"]
            qr_img, payload = generate_qr_code(society_id, "EVT", item_id)

            db._execute("UPDATE event_ticket_items SET qr_payload = %s WHERE id = %s", (payload, item_id))
            created_items.append({
                "item_id": item_id,
                "ticket_type": "CHILD",
                "qr_payload": payload,
                "qr_img": qr_img,
            })

        booking_ref = f"EVT-REF-{society_id}-{user_id}-{event_id}"
        return {
            "event_ticket_id": event_ticket_id,
            "booking_reference": booking_ref,
            "total_amount": float((r or {}).get("amount") or 0),
            "items": created_items,
        }, "Tickets booked successfully"

    except Exception as e:
        logger.error(f"Error booking event tickets: {e}")
        return None, str(e)


def get_user_event_tickets(society_id: int, user_id: int):
    """
    Fetch all active event bookings for a user with their individual scannable QR ticket items.
    """
    try:
        bookings = db._execute("""
            SELECT et.*, e.title as event_title, e.event_date, e.event_time, e.venue
              FROM event_tickets et
              JOIN events e ON e.id = et.event_id
             WHERE et.society_id = %s AND et.user_id = %s
             ORDER BY et.created_at DESC
        """, (society_id, user_id))

        results = []
        for b in (bookings or []):
            items = db._execute("""
                SELECT * FROM event_ticket_items WHERE event_ticket_id = %s ORDER BY ticket_type, id
            """, (b["id"],))

            item_list = []
            for it in (items or []):
                qr_img, _ = generate_qr_code(society_id, "EVT", it["id"])
                item_list.append({
                    "item_id": it["id"],
                    "ticket_type": it["ticket_type"],
                    "qr_payload": it["qr_payload"],
                    "status": it["status"],
                    "qr_img": qr_img,
                    "scanned_at": str(it.get("scanned_at") or ""),
                })

            results.append({
                "booking_id": b["id"],
                "event_title": b["event_title"],
                "event_date": str(b["event_date"]),
                "event_time": str(b.get("event_time") or ""),
                "venue": b.get("venue") or "",
                "total_amount": float(b["amount"]),
                "booking_reference": b["booking_reference"],
                "status": b["status"],
                "items": item_list,
            })

        return results
    except Exception as e:
        logger.error(f"Error fetching user event tickets: {e}")
        return []
