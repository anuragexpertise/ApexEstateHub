#!/usr/bin/env python3
"""
apply_dropdown_fixes.py
=======================
Applies BOTH root-cause fixes for the societies dropdown not working.

Run from project root:
    python3 apply_dropdown_fixes.py

Fixes applied:
  Fix 1 - Creates/replaces app/dash_apps/callbacks/__init__.py
           so register_all_callbacks() calls register_shell_callbacks()
  Fix 2 - Uncomments id="login-society-logo" in app/dash_apps/app_shell.py
           so the update_login_branding callback doesn't crash at runtime
"""

import os
import sys
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent

OK  = "\033[92m✅\033[0m"
ERR = "\033[91m❌\033[0m"
WRN = "\033[93m⚠️ \033[0m"

print("\n" + "="*70)
print("  APPLYING DROPDOWN FIXES")
print("="*70)


# ════════════════════════════════════════════════════════════════════════════
# FIX 1 — callbacks/__init__.py
# ════════════════════════════════════════════════════════════════════════════

print("\n[Fix 1] app/dash_apps/callbacks/__init__.py")
print("-" * 70)

CALLBACKS_INIT = PROJECT_ROOT / "app/dash_apps/callbacks/__init__.py"
CALLBACKS_INIT.parent.mkdir(parents=True, exist_ok=True)

# Back up existing file
if CALLBACKS_INIT.exists():
    backup = CALLBACKS_INIT.with_suffix(".py.bak")
    shutil.copy(CALLBACKS_INIT, backup)
    print(f"{WRN} Backed up existing file to {backup.name}")

CALLBACKS_INIT_CONTENT = '''\
# app/dash_apps/callbacks/__init__.py
"""
Callback registration hub — called by create_dash_app().

Registration order matters:
  1. shell_callbacks   — owns auth-store, login-modal, society-dropdown
  2. login_callbacks   — owns password/PIN/pattern login
  3. drilldown_callbacks
  4. card_catalogue_callbacks
  5. navigation_callbacks
  6. debug_callbacks    — last
"""


def register_all_callbacks(app):
    """Register every callback module with the Dash app."""

    print("\\n" + "="*60)
    print("📞 REGISTERING ALL CALLBACKS")
    print("="*60)

    errors = []

    # ── 1. Shell callbacks (MUST be first) ─────────────────────────────
    try:
        from app.dash_apps.callbacks.shell_callbacks import register_shell_callbacks
        register_shell_callbacks(app)
        print("  ✅ shell_callbacks registered (load_societies, router, sidebar)")
    except Exception as e:
        print(f"  ❌ shell_callbacks FAILED: {e}")
        import traceback; traceback.print_exc()
        errors.append(f"shell_callbacks: {e}")

    # ── 2. Login callbacks ──────────────────────────────────────────────
    try:
        from app.dash_apps.callbacks.login_callbacks import register_login_callbacks
        register_login_callbacks(app)
        print("  ✅ login_callbacks registered")
    except Exception as e:
        print(f"  ❌ login_callbacks FAILED: {e}")
        import traceback; traceback.print_exc()
        errors.append(f"login_callbacks: {e}")

    # ── 3. Drilldown callbacks ──────────────────────────────────────────
    try:
        from app.dash_apps.callbacks.drilldown_callbacks import register_drilldown_callbacks
        register_drilldown_callbacks(app)
        print("  ✅ drilldown_callbacks registered")
    except ImportError:
        print("  ⚠️  drilldown_callbacks not found — skipping")
    except Exception as e:
        print(f"  ❌ drilldown_callbacks FAILED: {e}")
        errors.append(f"drilldown_callbacks: {e}")

    # ── 4. Card catalogue callbacks ────────────────────────────────────
    try:
        from app.dash_apps.callbacks.card_catalogue_callbacks import register_card_catalogue_callbacks
        register_card_catalogue_callbacks(app)
        print("  ✅ card_catalogue_callbacks registered (KPI refresh, lists)")
    except ImportError:
        print("  ⚠️  card_catalogue_callbacks not found — skipping")
    except Exception as e:
        print(f"  ❌ card_catalogue_callbacks FAILED: {e}")
        errors.append(f"card_catalogue_callbacks: {e}")

    # ── 5. Navigation callbacks ─────────────────────────────────────────
    try:
        from app.dash_apps.callbacks.navigation_callbacks import register_navigation_callbacks
        register_navigation_callbacks(app)
        print("  ✅ navigation_callbacks registered (stack push/pop/reset)")
    except ImportError:
        print("  ⚠️  navigation_callbacks not found — skipping")
    except Exception as e:
        print(f"  ❌ navigation_callbacks FAILED: {e}")
        errors.append(f"navigation_callbacks: {e}")

    # ── 6. Customize callbacks ──────────────────────────────────────────
    try:
        from app.dash_apps.callbacks.customize_callbacks import register_customize_callbacks
        register_customize_callbacks(app)
        print("  ✅ customize_callbacks registered")
    except ImportError:
        print("  ⚠️  customize_callbacks not found — skipping")
    except Exception as e:
        print(f"  ❌ customize_callbacks FAILED: {e}")
        errors.append(f"customize_callbacks: {e}")

    # ── 7. KPI customize callbacks ──────────────────────────────────────
    try:
        from app.dash_apps.callbacks.customize_kpi_callbacks import register_customize_kpi_callbacks
        register_customize_kpi_callbacks(app)
        print("  ✅ customize_kpi_callbacks registered")
    except ImportError:
        print("  ⚠️  customize_kpi_callbacks not found — skipping")
    except Exception as e:
        print(f"  ❌ customize_kpi_callbacks FAILED: {e}")
        errors.append(f"customize_kpi_callbacks: {e}")

    # ── 8. Camera / QR callbacks ────────────────────────────────────────
    try:
        from app.dash_apps.callbacks.camera_callbacks import register_camera_callbacks
        register_camera_callbacks(app)
        print("  ✅ camera_callbacks registered (QR scanner)")
    except ImportError:
        print("  ⚠️  camera_callbacks not found — skipping")
    except Exception as e:
        print(f"  ❌ camera_callbacks FAILED: {e}")
        errors.append(f"camera_callbacks: {e}")

    # ── 9. Debug callbacks (last) ───────────────────────────────────────
    try:
        from app.dash_apps.callbacks.debug_callbacks import register_debug_callbacks
        register_debug_callbacks(app)
        print("  ✅ debug_callbacks registered (error monitoring)")
    except ImportError:
        print("  ⚠️  debug_callbacks not found — skipping")
    except Exception as e:
        print(f"  ❌ debug_callbacks FAILED: {e}")
        errors.append(f"debug_callbacks: {e}")

    # ── Summary ─────────────────────────────────────────────────────────
    print("="*60)
    if errors:
        print(f"  ⚠️  {len(errors)} callback module(s) failed:")
        for err in errors:
            print(f"     • {err}")
    else:
        print("  ✅ ALL callbacks registered successfully")
    print("="*60 + "\\n")


# Alias — app/__init__.py calls register_callbacks (singular)
register_callbacks = register_all_callbacks
'''

with open(CALLBACKS_INIT, 'w') as f:
    f.write(CALLBACKS_INIT_CONTENT)

print(f"{OK} Written: {CALLBACKS_INIT}")
print(f"   → register_all_callbacks now calls register_shell_callbacks first")
print(f"   → load_societies callback WILL now be registered")


# ════════════════════════════════════════════════════════════════════════════
# FIX 2 — app_shell.py login-society-logo
# ════════════════════════════════════════════════════════════════════════════

print("\n[Fix 2] app/dash_apps/app_shell.py — login-society-logo ID")
print("-" * 70)

APP_SHELL = PROJECT_ROOT / "app/dash_apps/app_shell.py"

if not APP_SHELL.exists():
    print(f"{ERR} {APP_SHELL} not found — skipping")
else:
    with open(APP_SHELL) as f:
        content = f.read()

    # Try multiple possible comment patterns
    patterns = [
        (
            '    # id="login-society-logo",  # Dynamic logo\n',
            '    id="login-society-logo",\n'
        ),
        (
            "    # id='login-society-logo',  # Dynamic logo\n",
            "    id='login-society-logo',\n"
        ),
        (
            '                    # id="login-society-logo",  # Dynamic logo\n',
            '                    id="login-society-logo",\n'
        ),
        (
            "                    # id='login-society-logo',  # Dynamic logo\n",
            "                    id='login-society-logo',\n"
        ),
        # Variant without the comment text
        (
            '    # id="login-society-logo",\n',
            '    id="login-society-logo",\n'
        ),
    ]

    fixed = False
    for old, new in patterns:
        if old in content:
            backup = APP_SHELL.with_suffix(".py.bak")
            shutil.copy(APP_SHELL, backup)
            content = content.replace(old, new)
            with open(APP_SHELL, 'w') as f:
                f.write(content)
            print(f"{OK} Fixed: commented-out id= now uncommented")
            print(f"   → update_login_branding callback won't crash")
            fixed = True
            break

    if not fixed:
        if 'id="login-society-logo"' in content and '# id="login-society-logo"' not in content:
            print(f"{OK} login-society-logo ID already uncommented — no change needed")
        else:
            print(f"{WRN} Could not auto-fix — apply manually:")
            print()
            print('   Find in _login_modal():')
            print('       # id="login-society-logo",  # Dynamic logo')
            print('   Change to:')
            print('       id="login-society-logo",')
            print()
            # Show context around the logo in the file
            for i, line in enumerate(content.split('\n'), 1):
                if 'login-society-logo' in line or 'EH_logo.png' in line:
                    print(f"   Line {i:4d}: {line}")


# ════════════════════════════════════════════════════════════════════════════
# VERIFY
# ════════════════════════════════════════════════════════════════════════════

print("\n[Verify] Checking fixes...")
print("-" * 70)

# Check callbacks/__init__.py has the critical call
with open(CALLBACKS_INIT) as f:
    cb_content = f.read()

if 'register_shell_callbacks' in cb_content:
    print(f"{OK} callbacks/__init__.py calls register_shell_callbacks")
else:
    print(f"{ERR} callbacks/__init__.py missing register_shell_callbacks!")

if 'register_login_callbacks' in cb_content:
    print(f"{OK} callbacks/__init__.py calls register_login_callbacks")

# Check app_shell.py for logo ID
if APP_SHELL.exists():
    with open(APP_SHELL) as f:
        shell_content = f.read()
    
    if '# id="login-society-logo"' in shell_content:
        print(f"{ERR} login-society-logo ID still commented out! Fix manually.")
    elif 'id="login-society-logo"' in shell_content:
        print(f"{OK} login-society-logo ID is active in app_shell.py")
    else:
        print(f"{WRN} login-society-logo ID not found in app_shell.py")


# ════════════════════════════════════════════════════════════════════════════
# NEXT STEPS
# ════════════════════════════════════════════════════════════════════════════

print("\n" + "="*70)
print("  NEXT STEPS")
print("="*70)
print("""
1. Restart the application:
   python3 run.py

2. Open browser and go to:
   http://127.0.0.1:8050/dashboard/

3. The login modal should appear.

4. The society dropdown should now show: "Sunrise Residency [Free]"

5. If still empty, check the terminal for this log:
   🔍 Loading societies from database...
   ✅ Loaded 1 societies:
      • Sunrise Residency [Free]

6. If that log DOESN'T appear, shell_callbacks registration failed.
   Check for "shell_callbacks FAILED" in startup output.
""")

print("="*70 + "\n")
