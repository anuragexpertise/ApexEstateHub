# EstateHub - Error Audit Report
**Generated: May 19, 2026**
**Scope: Complete codebase functionality check**

---

## Executive Summary

Found **5 critical/high errors** and **multiple consistency issues** that could cause runtime failures:

1. **User.query.get() incompatibility** ⚠️ CRITICAL
2. **JWT token generation practices** ⚠️ MINOR (auto-converted by PyJWT)
3. **Database layer inconsistency** ⚠️ HIGH (dual access patterns)
4. **False positives (resolved)** ✅
   - SQL named parameters (working as intended)
   - JWT handler import (module exists)

---

## Critical Errors

### 1. User.query.get() - SQLAlchemy ORM Incompatibility
**Location:** `app/auth/jwt_handler.py:50`  
**Severity:** CRITICAL - Will cause AttributeError at runtime

```python
# ❌ WRONG - User is NOT a SQLAlchemy model
user = User.query.get(payload.get('user_id'))
```

**Issue:** The `User` model (from `app.models.user`) is a custom Flask-Login `UserMixin` class, NOT a SQLAlchemy `db.Model`. It doesn't have a `.query` attribute.

**Fix:**
```python
# ✅ CORRECT
user = User.get(payload.get('user_id'))
```

**Impact:** Token refresh flow will fail when trying to regenerate access tokens.

---

### 2. JWT Token Generation - Datetime Fields (Minor)
**Locations:**
- `app/routes/auth.py:22` (exp field)
- `app/auth/jwt_handler.py:20, 26` (exp field)
- `app/services/auth_service.py:58` (exp field)

**Severity:** MINOR - Works due to PyJWT auto-conversion, but bad practice

```python
# ⚠️ IMPRECISE - Datetime objects (works but not recommended)
'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS)
```

**Issue:** JWT spec requires `exp` to be an integer Unix timestamp. PyJWT library auto-converts, but explicit timestamps are clearer.

**Best Practice:**
```python
# ✅ BETTER - Explicit Unix timestamp
import time
'exp': int(time.time()) + (JWT_EXPIRY_HOURS * 3600)
# OR
from datetime import datetime, timedelta
exp_time = datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS)
'exp': int(exp_time.timestamp())
```

**Impact:** Low - Works correctly, but should follow JWT spec explicitly.

---

## High Severity Issues

### 3. Database Access Pattern Inconsistency
**Severity:** HIGH - Causes maintainability issues and potential connection state problems

#### Issue Summary
The project uses TWO incompatible database access patterns:

**Pattern A: Raw SQL via db_manager._execute()**
```python
# app/services/account_service.py
from database.db_manager import db
user = db._execute(
    "SELECT * FROM users WHERE id = :user_id",
    {"user_id": user_id},
    fetch_one=True
)
```

**Pattern B: SQLAlchemy ORM**
```python
# app/services/payment_service.py, maintenance_service.py
from app import db
from app.models.payment import Payment
payment = Payment.query.filter(...).first()
db.session.add(payment)
db.session.commit()
```

#### Affected Files
- `app/services/payment_service.py` - Uses ORM Pattern B
- `app/services/maintenance_service.py` - Uses ORM Pattern B
- `app/services/account_service.py` - Uses raw SQL Pattern A
- `app/services/auth_service.py` - Uses raw SQL Pattern A

#### Problems
1. **Session management complexity** - ORM Pattern B requires app context
2. **Connection pooling conflicts** - Two different session managers
3. **Difficult to debug** - Mixed patterns make transaction handling unclear
4. **Inconsistent error handling** - Different patterns fail differently

#### Recommendation
Standardize on ONE pattern. Suggested: Use SQLAlchemy ORM Pattern B across all services for consistency with Flask-SQLAlchemy setup.

---

## Resolved False Positives

### ✅ SQL Named Parameters (app/routes/push_routes.py:112)
**Status:** VERIFIED WORKING

The code uses named placeholders with db._execute():
```python
db._execute(
    "UPDATE users SET push_subscription = NULL WHERE id = :user_id",
    {"user_id": user_id}
)
```

This works correctly because `db._execute()` accepts both:
- Positional `%s` placeholders (converted to `:param_0`, `:param_1`, etc.)
- Direct `:named` placeholders (passed as-is)

---

### ✅ JWT Handler Import (app/routes/api.py:5)
**Status:** MODULE EXISTS

The import `from app.auth.jwt_handler import token_required, role_required` works correctly. The module exists at `app/auth/jwt_handler.py`.

---

## Design Issues (Not Errors)

### 1. Timezone Inconsistency
**Locations:** Multiple files use `datetime.now()` vs `datetime.utcnow()`

```python
# Found in multiple locations:
# ⚠️ INCONSISTENT
datetime.now()           # Local time
datetime.utcnow()        # UTC time
```

**Recommendation:** Use UTC consistently for all database timestamps.

---

### 2. Error Handling - Bare Exception Catches
**Pattern Found:**
```python
try:
    # code
except Exception as e:
    logger.error(f"Error: {e}")
    return None
```

Too broad. Should catch specific exceptions.

---

## Summary Table

| # | Issue | File | Severity | Status |
|---|-------|------|----------|--------|
| 1 | User.query.get() incompatibility | jwt_handler.py:50 | CRITICAL | ⚠️ Needs fix |
| 2 | JWT datetime fields | auth.py, jwt_handler.py, auth_service.py | MINOR | ⚠️ Best practice |
| 3 | DB pattern inconsistency | payment_service.py, maintenance_service.py | HIGH | ⚠️ Needs refactor |
| 4 | SQL named params | push_routes.py | ✅ FALSE POSITIVE | Resolved |
| 5 | JWT import | api.py:5 | ✅ FALSE POSITIVE | Resolved |
| 6 | Timezone inconsistency | Multiple | MEDIUM | ⚠️ Design issue |
| 7 | Bare exception catches | Multiple | LOW | Design issue |

---

## Recommended Fix Order

1. **IMMEDIATE:** Fix User.query.get() in jwt_handler.py (Task #5)
2. **HIGH PRIORITY:** Standardize database access pattern (Tasks #7, #8, #9)
3. **MEDIUM PRIORITY:** Convert JWT datetime fields to Unix timestamps (Tasks #1, #4, #6)
4. **LOW PRIORITY:** Use UTC consistently for timestamps
5. **LOW PRIORITY:** Improve exception handling specificity

---

## Testing Recommendations

After fixes are applied, verify:

- [ ] JWT token generation and refresh flow works
- [ ] User authentication with all methods (password/PIN/pattern)
- [ ] Payment processing doesn't lose transactions
- [ ] Database transactions complete correctly
- [ ] Session management works under concurrent load

---

*End of Error Audit*
