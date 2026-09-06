#!/usr/bin/env python3
"""
Randomized Patrol Routing Engine & Notifications Cron Script.
Runs periodically (e.g. hourly) to assign random patrol locations
to on-duty security guards and send push notifications.
Also checks for expired tasks and generates missed alerts.
"""

import sys
import os
import random
from datetime import datetime, timedelta

# Ensure app path is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.db_manager import db
from app.services.push_service import send_push_notification

def init_db():
    db._execute("""
        CREATE TABLE IF NOT EXISTS patrol_tasks (
            id SERIAL PRIMARY KEY,
            society_id INTEGER REFERENCES societies(id),
            security_user_id INTEGER REFERENCES users(id),
            location_id INTEGER REFERENCES patrol_locations(id),
            assigned_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
            expires_at TIMESTAMP WITHOUT TIME ZONE,
            status VARCHAR(20) DEFAULT 'PENDING'
        )
    """)

def check_missed_tasks():
    """Mark expired pending tasks as MISSED and alert admins."""
    expired_tasks = db._execute("""
        SELECT pt.id, pt.society_id, pt.security_user_id, u.name AS guard_name, pl.location_name
        FROM patrol_tasks pt
        JOIN users u ON pt.security_user_id = u.id
        JOIN patrol_locations pl ON pt.location_id = pl.id
        WHERE pt.status = 'PENDING' AND pt.expires_at < NOW()
    """, fetch_all=True) or []

    for task in expired_tasks:
        db._execute("UPDATE patrol_tasks SET status = 'MISSED' WHERE id = %s", (task["id"],))
        
        # Optionally send an alert to Admin (role='admin' or 'master')
        # For simplicity, we just generate a missed event or notification
        admin_users = db._execute(
            "SELECT id FROM users WHERE society_id = %s AND role IN ('admin', 'master')",
            (task["society_id"],), fetch_all=True
        ) or []
        
        for admin in admin_users:
            send_push_notification(
                user_id=admin["id"],
                title="Missed Patrol Alert",
                body=f"Guard {task['guard_name']} missed patrol at {task['location_name']}."
            )

def assign_random_patrols():
    """Assign a random active patrol location to each on-duty guard."""
    # Find all on-duty security guards (checked in but not checked out)
    on_duty_guards = db._execute("""
        SELECT u.id AS user_id, u.society_id, u.name AS guard_name
        FROM gate_access ga
        JOIN users u ON ga.entity_id = u.linked_id AND u.role = 'security' AND u.society_id = ga.society_id
        WHERE ga.role = 'SEC' AND ga.time_out IS NULL
    """, fetch_all=True) or []

    for guard in on_duty_guards:
        user_id = guard["user_id"]
        society_id = guard["society_id"]
        
        # Don't assign a new task if they already have a PENDING task
        pending = db._execute(
            "SELECT id FROM patrol_tasks WHERE security_user_id = %s AND status = 'PENDING'",
            (user_id,), fetch_one=True
        )
        if pending:
            continue

        # Get a random active patrol location
        locations = db._execute(
            "SELECT id, location_name FROM patrol_locations WHERE society_id = %s AND active = TRUE",
            (society_id,), fetch_all=True
        ) or []

        if not locations:
            continue
            
        loc = random.choice(locations)
        expires_at = datetime.now() + timedelta(minutes=15)
        
        db._execute("""
            INSERT INTO patrol_tasks (society_id, security_user_id, location_id, assigned_at, expires_at, status)
            VALUES (%s, %s, %s, NOW(), %s, 'PENDING')
        """, (society_id, user_id, loc["id"], expires_at))

        send_push_notification(
            user_id=user_id,
            title="New Patrol Assignment",
            body=f"Please scan {loc['location_name']} within the next 15 minutes."
        )

if __name__ == "__main__":
    init_db()
    check_missed_tasks()
    assign_random_patrols()
    print("Ran randomized patrol cron job successfully.")
