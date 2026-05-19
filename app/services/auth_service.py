# app/services/auth_service.py
"""
Complete Authentication Service for EsateHub
- JWT token generation
- Password/PIN/9-dot-pattern authentication
- Push notification (FCM/VAPID)
- Forgot password flow
- Integration with app/config.py settings
"""

import secrets
import hashlib
import jwt
import logging
import json
import re
import os
import time
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from werkzeug.security import check_password_hash, generate_password_hash

# Import project configs
from app.config import (
    JWT_SECRET_KEY,
    VAPID_PRIVATE_KEY,
    VAPID_PUBLIC_KEY,
    VAPID_CLAIM_EMAIL
)
from database.db_manager import db

# Setup logging
logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24
RESET_TOKEN_EXPIRY_HOURS = 2
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

# ── JWT Token Management ───────────────────────────────────────────────────

def generate_jwt_token(user_id, email, role, society_id=None):
    """
    Generate JWT access token.

    Returns: encoded JWT string
    """
    now = int(time.time())
    payload = {
        "sub": str(user_id),         # Subject (user_id as string per JWT spec)
        "email": email,              # User email
        "role": role,                # User role (admin/apartment/vendor/security)
        "society_id": society_id,    # Associated society
        "iat": now,                  # Issued at (Unix timestamp)
        "exp": now + (JWT_EXPIRY_HOURS * 3600),  # Expiry (Unix timestamp)
        "type": "access"             # Token type
    }

    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token


def verify_jwt_token(token):
    """
    Verify and decode JWT token.
    
    Returns: payload dict or None if invalid
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        return None


def generate_refresh_token():
    """Generate secure refresh token."""
    return secrets.token_urlsafe(64)


# ── Authentication Methods ─────────────────────────────────────────────────

def authenticate_user(email, password, society_id):
    """
    Authenticate with email/password.
    
    Returns: user dict with token or None
    """
    return _authenticate(
        email, password, society_id, 
        hash_field="password_hash",
        method="password"
    )


def authenticate_pin(email, pin, society_id):
    """
    Authenticate with 4-digit PIN.
    
    Returns: user dict with token or None
    """
    return _authenticate(
        email, pin, society_id,
        hash_field="pin_hash",
        method="pin"
    )


def authenticate_pattern(email, pattern, society_id):
    """
    Authenticate with 9-dot pattern.
    
    Returns: user dict with token or None
    """
    if not _validate_pattern(pattern):
        logger.warning(f"Invalid pattern format: {pattern}")
        return None
    
    return _authenticate(
        email, pattern, society_id,
        hash_field="pattern_hash",
        method="pattern"
    )


def _authenticate(email, credential, society_id, hash_field, method):
    """
    Generic authentication function.
    
    Args:
        email: User email
        credential: Password/PIN/Pattern
        society_id: Society ID (None for master admin)
        hash_field: Database field (password_hash/pin_hash/pattern_hash)
        method: 'password', 'pin', or 'pattern'
    
    Returns:
        User dict with JWT token or None
    """
    try:
        # Check if account is locked
        if _is_account_locked(email):
            logger.warning(f"Account locked: {email}")
            return None
        
        # Build query with SQLAlchemy-style named parameters
        query = f"""
            SELECT id, email, role, society_id, {hash_field}, 
                   push_subscription, login_method
            FROM users
            WHERE email = :email
              AND login_method IN (:method, 'all')
        """
        params = {"email": email, "method": method}
        
        # Add society filter (admins can bypass)
        if society_id:
            query += " AND (society_id = :society_id OR role = 'admin')"
            params["society_id"] = society_id
        else:
            query += " AND society_id IS NULL"
        
        # Execute query
        user = db._execute(query, params, fetch_one=True)
        
        # Verify credentials
        if not user or not user.get(hash_field):
            _increment_failed_attempts(user.get('id') if user else None)
            return None
        
        if not check_password_hash(user[hash_field], credential):
            _increment_failed_attempts(user['id'])
            return None
        
        # Successful login
        _reset_failed_attempts(user['id'])
        _update_last_login(user['id'])
        
        # Generate JWT
        token = generate_jwt_token(
            user['id'], user['email'], user['role'], user['society_id']
        )
        
        return {
            "user_id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "society_id": user["society_id"],
            "linked_id": user.get("linked_id"),
            "push_subscription": user.get("push_subscription"),
            "token": token,
            "authenticated": True
        }
        
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        return None


# ── 9-Dot Pattern Validation ───────────────────────────────────────────────

def _validate_pattern(pattern):
    """
    Validate Android-style 9-dot pattern.
    
    Rules:
    - Format: "1-2-5-8" (4-9 dots)
    - Dots 1-9, no duplicates
    - Must follow grid connectivity (no jumping over unused dots)
    
    Grid:
       1  2  3
       4  5  6
       7  8  9
    """
    try:
        if not pattern or not isinstance(pattern, str):
            return False
        
        dots = pattern.split('-')
        
        # Must use 4-9 dots
        if len(dots) < 4 or len(dots) > 9:
            logger.warning(f"Pattern wrong length: {len(dots)} dots")
            return False
        
        # All must be integers
        try:
            positions = [int(d) for d in dots]
        except ValueError:
            logger.warning(f"Pattern contains non-integers: {pattern}")
            return False
        
        # Must be 1-9
        if any(p < 1 or p > 9 for p in positions):
            logger.warning(f"Pattern out of range 1-9: {pattern}")
            return False
        
        # No duplicates
        if len(set(positions)) != len(positions):
            logger.warning(f"Pattern has duplicates: {pattern}")
            return False
        
        # Check connectivity (no jumps over unused dots)
        def crosses_unused(dot_a, dot_b, used_dots):
            """
            Check if line from dot_a to dot_b crosses an unused dot.
            
            Returns True if crossing invalid (dot not in used_dots)
            """
            # Convert to grid coordinates (row, col)
            r1, c1 = (dot_a - 1) // 3, (dot_a - 1) % 3
            r2, c2 = (dot_b - 1) // 3, (dot_b - 1) % 3
            
            # Same row, skip middle (e.g., 1->3 crosses 2)
            if r1 == r2 and abs(c1 - c2) == 2:
                middle = dot_a + (dot_b - dot_a) // 2
                return middle not in used_dots
            
            # Same column, skip middle (e.g., 1->7 crosses 4)
            if c1 == c2 and abs(r1 - r2) == 2:
                middle = dot_a + ((dot_b - dot_a) // 2) * 3
                return middle not in used_dots
            
            # Diagonal skip (e.g., 1->9 crosses 5)
            if abs(r1 - r2) == 2 and abs(c1 - c2) == 2:
                return 5 not in used_dots
            
            return False
        
        used = set()
        for i in range(len(positions) - 1):
            current = positions[i]
            next_dot = positions[i + 1]
            used.add(current)
            
            if crosses_unused(current, next_dot, used):
                logger.warning(f"Pattern crosses unused dot: {current} -> {next_dot}")
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"Pattern validation error: {e}")
        return False


# ── Account Security ───────────────────────────────────────────────────────

def _is_account_locked(email):
    """Check if account is locked due to failed attempts."""
    try:
        result = db._execute(
            "SELECT locked_until FROM users WHERE email = :email",
            {"email": email},
            fetch_one=True
        )
        
        if not result or not result.get("locked_until"):
            return False
        
        locked_until = result["locked_until"]
        
        # Check if lockout expired
        if datetime.utcnow() > locked_until:
            db._execute(
                "UPDATE users SET locked_until = NULL, failed_login_attempts = 0 WHERE email = :email",
                {"email": email}
            )
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Account lock check error: {e}")
        return False


def _increment_failed_attempts(user_id):
    """Increment failed login count and lock if threshold exceeded."""
    if not user_id:
        return
    
    try:
        # Increment counter
        db._execute(
            "UPDATE users SET failed_login_attempts = failed_login_attempts + 1 WHERE id = :user_id",
            {"user_id": user_id}
        )
        
        # Check if locked
        result = db._execute(
            "SELECT failed_login_attempts FROM users WHERE id = :user_id",
            {"user_id": user_id},
            fetch_one=True
        )
        
        if result and result["failed_login_attempts"] >= MAX_LOGIN_ATTEMPTS:
            lockout_time = datetime.utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
            db._execute(
                "UPDATE users SET locked_until = :lockout_time WHERE id = :user_id",
                {"lockout_time": lockout_time, "user_id": user_id}
            )
            logger.warning(f"Account {user_id} locked for {LOCKOUT_MINUTES} minutes")
            
    except Exception as e:
        logger.error(f"Failed attempt increment error: {e}")


def _reset_failed_attempts(user_id):
    """Reset failed login counter."""
    try:
        db._execute(
            "UPDATE users SET failed_login_attempts = 0, locked_until = NULL WHERE id = :user_id",
            {"user_id": user_id}
        )
    except Exception as e:
        logger.error(f"Failed attempt reset error: {e}")


def _update_last_login(user_id):
    """Update last login timestamp."""
    try:
        db._execute(
            "UPDATE users SET last_login = NOW() WHERE id = :user_id",
            {"user_id": user_id}
        )
    except Exception as e:
        logger.error(f"Last login update error: {e}")


# ── Password Reset ─────────────────────────────────────────────────────────

def request_password_reset(email, society_id):
    """
    Generate password reset token and send email.
    
    Returns: (success, message, token)
    """
    try:
        # Fetch user
        query = "SELECT id, email FROM users WHERE email = :email"
        params = {"email": email}
        
        if society_id:
            query += " AND society_id = :society_id"
            params["society_id"] = society_id
        
        user = db._execute(query, params, fetch_one=True)
        
        # Security: Don't reveal if email exists
        if not user:
            # Still generate a fake token to prevent timing attacks
            secrets.token_urlsafe(32)
            return True, "If that email exists, a reset link has been sent", None
        
        # Generate real token
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        expires_at = datetime.utcnow() + timedelta(hours=RESET_TOKEN_EXPIRY_HOURS)
        
        # Store hashed token
        db._execute(
            """UPDATE users 
               SET reset_token = :token_hash, reset_token_expires = :expires_at 
               WHERE id = :user_id""",
            {"token_hash": token_hash, "expires_at": expires_at, "user_id": user["id"]}
        )
        
        # Send email (implement based on your setup)
        _send_reset_email(user["email"], token)
        
        logger.info(f"Password reset requested for {user['email']}")
        return True, "Reset email sent", token
        
    except Exception as e:
        logger.error(f"Password reset request error: {e}")
        return False, "Error processing request", None


def reset_password(token, new_password):
    """
    Reset password using token.
    
    Returns: (success, message)
    """
    try:
        # Validate password strength
        if not _validate_password_strength(new_password):
            return False, "Password does not meet requirements"
        
        # Hash token to match stored hash
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        # Find user with valid token
        user = db._execute(
            """SELECT id FROM users 
               WHERE reset_token = :token_hash 
                 AND reset_token_expires > NOW()""",
            {"token_hash": token_hash},
            fetch_one=True
        )
        
        if not user:
            return False, "Invalid or expired reset token"
        
        # Hash new password
        password_hash = generate_password_hash(new_password)
        
        # Update password and clear token
        db._execute(
            """UPDATE users 
               SET password_hash = :password_hash,
                   reset_token = NULL,
                   reset_token_expires = NULL,
                   failed_login_attempts = 0
               WHERE id = :user_id""",
            {"password_hash": password_hash, "user_id": user["id"]}
        )
        
        logger.info(f"Password reset for user {user['id']}")
        return True, "Password reset successful"
        
    except Exception as e:
        logger.error(f"Password reset error: {e}")
        return False, "Error resetting password"


def _validate_password_strength(password):
    """Validate password meets security requirements."""
    if len(password) < 8:
        return False
    
    checks = [
        r'[A-Z]',  # uppercase
        r'[a-z]',  # lowercase
        r'[0-9]',  # number
        r'[!@#$%^&*(),.?":{}|<>]'  # special char
    ]
    
    return all(re.search(pattern, password) for pattern in checks)


def _send_reset_email(email, token):
    """
    Send password reset email via SMTP.
    Reads SMTP_USER and SMTP_PASSWORD from environment variables.
    Auto-detects Gmail vs Outlook vs generic SMTP host.
    """
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")

    if not smtp_user or not smtp_password:
        logger.warning("SMTP_USER or SMTP_PASSWORD not set — reset email not sent")
        return

    # Build reset URL using the app's public domain if available
    domain = os.environ.get("REPLIT_DEV_DOMAIN") or os.environ.get("REPLIT_DOMAINS", "").split(",")[0].strip()
    if domain:
        reset_url = f"https://{domain}/dashboard/?reset_token={token}"
    else:
        reset_url = f"https://apexestatehub.com/dashboard/?reset_token={token}"

    # Choose SMTP server based on sender domain
    sender_domain = smtp_user.split("@")[-1].lower() if "@" in smtp_user else ""
    if "gmail" in sender_domain:
        smtp_host, smtp_port = "smtp.gmail.com", 587
    elif "outlook" in sender_domain or "hotmail" in sender_domain or "live" in sender_domain:
        smtp_host, smtp_port = "smtp.office365.com", 587
    elif "yahoo" in sender_domain:
        smtp_host, smtp_port = "smtp.mail.yahoo.com", 587
    else:
        smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))

    # Build email
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Reset your EsateHub password"
    msg["From"] = f"EsateHub <{smtp_user}>"
    msg["To"] = email

    plain = (
        f"You requested a password reset for your EsateHub account.\n\n"
        f"Click the link below to set a new password (valid for 1 hour):\n\n"
        f"{reset_url}\n\n"
        f"If you did not request this, please ignore this email. "
        f"Your password will not change.\n\n"
        f"— EsateHub Team"
    )

    html = f"""
    <html><body style="font-family:Arial,sans-serif;background:#f4f4f4;padding:30px;">
      <div style="max-width:520px;margin:auto;background:#fff;border-radius:10px;
                  padding:36px;box-shadow:0 2px 12px rgba(0,0,0,0.1);">
        <h2 style="color:#6c3fc5;margin-top:0;">EsateHub</h2>
        <p style="font-size:16px;color:#333;">Hi,</p>
        <p style="font-size:15px;color:#555;">
          You requested a password reset. Click the button below to set a new password.
          This link is valid for <strong>1 hour</strong>.
        </p>
        <div style="text-align:center;margin:32px 0;">
          <a href="{reset_url}"
             style="background:linear-gradient(135deg,#6c3fc5,#9b59b6);
                    color:#fff;padding:14px 32px;border-radius:8px;
                    text-decoration:none;font-size:16px;font-weight:bold;">
            Reset Password
          </a>
        </div>
        <p style="font-size:13px;color:#999;">
          If you didn't request this, you can safely ignore this email.<br>
          Your password will remain unchanged.
        </p>
        <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
        <p style="font-size:12px;color:#bbb;text-align:center;">
          &copy; 2025 EsateHub. All rights reserved.
        </p>
      </div>
    </body></html>
    """

    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, email, msg.as_string())
        logger.info(f"Password reset email sent to {email}")
    except smtplib.SMTPAuthenticationError:
        logger.error(
            "SMTP authentication failed. "
            "For Gmail, use an App Password (not your normal password). "
            "Generate one at myaccount.google.com/apppasswords"
        )
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error sending reset email to {email}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error sending reset email to {email}: {e}")


# ── Push Notifications ───────────────────────────────────────────────────────

def register_push_token(user_id, token, platform="fcm"):
    """
    Register device for push notifications.
    
    Args:
        user_id: User ID
        token: FCM/APNS device token
        platform: 'fcm' (Android) or 'apns' (iOS)
    
    Returns: (success, message)
    """
    try:
        # Store as JSON in push_subscription field
        subscription = json.dumps({
            "token": token,
            "platform": platform,
            "created_at": datetime.utcnow().isoformat()
        })
        
        db._execute(
            "UPDATE users SET push_subscription = :subscription, push_enabled = TRUE WHERE id = :user_id",
            {"subscription": subscription, "user_id": user_id}
        )
        
        logger.info(f"Push token registered for user {user_id}")
        return True, "Push notifications enabled"
        
    except Exception as e:
        logger.error(f"Push token registration error: {e}")
        return False, "Error registering device"


def send_push_notification(user_id, title, body, data=None):
    """
    Send push notification to user.
    
    Args:
        user_id: Target user ID
        title: Notification title
        body: Notification body
        data: Optional custom data payload
    
    Returns: (success, message)
    """
    try:
        # Fetch user's push subscription
        user = db._execute(
            "SELECT push_subscription FROM users WHERE id = :user_id",
            {"user_id": user_id},
            fetch_one=True
        )
        
        if not user or not user.get("push_subscription"):
            return False, "No push token registered"
        
        subscription = json.loads(user["push_subscription"])
        token = subscription.get("token")
        platform = subscription.get("platform", "fcm")
        
        # Send via appropriate service
        if platform == "fcm":
            return _send_fcm_notification(token, title, body, data or {})
        
        return False, f"Unsupported platform: {platform}"
        
    except Exception as e:
        logger.error(f"Push notification error: {e}")
        return False, "Error sending notification"


def _send_fcm_notification(token, title, body, data):
    """
    Send notification via Firebase Cloud Messaging.
    
    Requires: pip install firebase-admin
    """
    try:
        import firebase_admin
        from firebase_admin import credentials, messaging
        
        # Initialize Firebase (do once)
        if not firebase_admin._apps:
            # Use your Firebase service account key
            cred = credentials.Certificate("path/to/serviceAccountKey.json")
            firebase_admin.initialize_app(cred)
        
        # Create message
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body
            ),
            data=data,
            token=token
        )
        
        # Send
        response = messaging.send(message)
        logger.info(f"FCM sent: {response}")
        return True, "Notification sent"
        
    except Exception as e:
        logger.error(f"FCM error: {e}")
        return False, "FCM delivery failed"


# ── User Management ─────────────────────────────────────────────────────────

def set_user_pin(user_id, pin):
    """Set or update user's 4-digit PIN."""
    if not pin or len(pin) != 4 or not pin.isdigit():
        return False, "PIN must be exactly 4 digits"
    
    pin_hash = generate_password_hash(pin)
    
    db._execute(
        """UPDATE users 
           SET pin_hash = :pin_hash,
               login_method = CASE 
                   WHEN login_method = 'password' THEN 'all'
                   WHEN login_method = 'pattern' THEN 'all'
                   ELSE 'pin'
               END
           WHERE id = :user_id""",
        {"pin_hash": pin_hash, "user_id": user_id}
    )
    
    return True, "PIN set successfully"


def set_user_pattern(user_id, pattern):
    """Set or update user's 9-dot pattern."""
    if not _validate_pattern(pattern):
        return False, "Invalid pattern format"
    
    pattern_hash = generate_password_hash(pattern)
    
    db._execute(
        """UPDATE users 
           SET pattern_hash = :pattern_hash,
               login_method = CASE 
                   WHEN login_method = 'password' THEN 'all'
                   WHEN login_method = 'pin' THEN 'all'
                   ELSE 'pattern'
               END
           WHERE id = :user_id""",
        {"pattern_hash": pattern_hash, "user_id": user_id}
    )
    
    return True, "Pattern set successfully"


def change_password(user_id, old_password, new_password):
    """Change user's password (requires old password)."""
    try:
        # Verify old password
        user = db._execute(
            "SELECT password_hash FROM users WHERE id = :user_id",
            {"user_id": user_id},
            fetch_one=True
        )
        
        if not user or not check_password_hash(user["password_hash"], old_password):
            return False, "Current password is incorrect"
        
        # Validate new password
        if not _validate_password_strength(new_password):
            return False, "New password does not meet requirements"
        
        # Update password
        new_hash = generate_password_hash(new_password)
        db._execute(
            "UPDATE users SET password_hash = :new_hash WHERE id = :user_id",
            {"new_hash": new_hash, "user_id": user_id}
        )
        
        return True, "Password changed successfully"
        
    except Exception as e:
        return False, f"Error: {str(e)}"


def get_user_login_methods(user_id):
    """Get available login methods for a user."""
    try:
        result = db._execute(
            "SELECT login_method, pin_hash, pattern_hash FROM users WHERE id = :user_id",
            {"user_id": user_id},
            fetch_one=True
        )
        
        if not result:
            return {"password": False, "pin": False, "pattern": False}
        
        return {
            "password": True,
            "pin": bool(result.get("pin_hash")),
            "pattern": bool(result.get("pattern_hash"))
        }
        
    except Exception:
        return {"password": True, "pin": False, "pattern": False}