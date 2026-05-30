# app/dash_apps/callbacks/shell_callbacks.py
"""
Shell callbacks - Core authentication and routing logic (FIXED).
CRITICAL: This file owns auth-store, url, login-modal, and society dropdown.
Must be registered FIRST before login_callbacks.

FIXES:
  ✅ Fixed society dropdown SQL query (uses correct plan values: Free, 9Apts, 99Apts, etc.)
  ✅ Added plan validity checking (shows only valid plans)
  ✅ Displays plan type in dropdown options
  ✅ Login modal properly closes when authenticated
  ✅ Modal state is managed in the main router callback
"""
import json
from datetime import datetime, timedelta, date as dt_date
import chime
import dash
from dash import Input, Output, State, html, dcc, no_update, callback, ctx
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
from database.db_manager import db
from app.dash_apps.app_shell import ROLE_CONFIG


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sid(auth):
    """Extract society_id from auth data."""
    return (auth or {}).get("society_id")


def _redirect_for_role(role, society_id):
    """Get default redirect path for a given role."""
    if role == "admin" and society_id is None:
        return "/dashboard/master"
    if role == "admin":
        return "/dashboard/admin-portal"
    if role == "apartment":
        return "/dashboard/owner-portal"
    if role == "vendor":
        return "/dashboard/vendor-portal"
    if role == "security":
        return "/dashboard/pass-evaluation"
    return "/dashboard/"


def _make_nav_items(role, society_id, pathname):
    """Generate sidebar navigation items based on role."""
    is_master = role == "admin" and society_id is None
    key  = "master" if is_master else (role or "admin")
    cfg  = ROLE_CONFIG.get(key, ROLE_CONFIG["admin"])
    color = cfg["color"]
    items = []
    for tab in cfg["tabs"]:
        href      = tab["href"]
        is_active = bool(pathname and href.rstrip("/") in pathname)
        items.append(
            html.Li(
                dcc.Link(
                    [
                        html.I(
                            className=f"fas {tab['icon']} me-2",
                            style={
                                "width": "18px",
                                "color": color if is_active else "rgba(255,255,255,0.55)",
                            },
                        ),
                        html.Span(tab["label"]),
                    ],
                    href=href,
                    className="snav-link" + (" snav-link--active" if is_active else ""),
                    refresh=False,
                ),
                className="snav-item",
            )
        )
    return items


def _breadcrumb(pathname):
    """Generate breadcrumb navigation."""
    path_map = {
        "admin-portal":    "Dashboard",
        "owner-portal":    "Dashboard",
        "vendor-portal":   "Dashboard",
        "master":          "Dashboard",
        "pass-evaluation": "Pass Eval",
        "cashbook":        "Cashbook",
        "owner-cashbook":  "Cashbook",
        "vendor-cashbook": "Cashbook",
        "receipts":        "Receipts",
        "expenses":        "Expenses",
        "enroll":          "Enroll",
        "users":           "Users",
        "events":          "Events",
        "owner-events":    "Events",
        "vendor-events":   "Events",
        "security-events": "Events",
        "evaluate-pass":   "Evaluate Pass",
        "customize":       "Customize",
        "settings":        "Settings",
        "owner-settings":  "Settings",
        "vendor-settings": "Settings",
        "security-settings": "Settings",
        "payments":        "Payments",
        "vendor-payments": "Payments",
        "charges":         "Charges",
        "vendor-charges":  "Charges",
        "attendance":      "Attendance",
        "security-receipt":"New Receipt",
        "security-users":  "Users",
    }

    parts = [p for p in (pathname or "").strip("/").split("/") if p and p != "dashboard"]
    items = [
        html.Li(
            html.Button(
                [html.I(className="fas fa-home me-1"), "Home"],
                id={"type": "breadcrumb-link", "level": -1},
                n_clicks=0,
                className="breadcrumb-btn",
                style={
                    "background": "none", "border": "none", "color": "#667eea",
                    "cursor": "pointer", "padding": "0", "fontSize": "12px",
                }
            ),
            className="bc-item",
        )
    ]
    for i, part in enumerate(parts):
        name   = path_map.get(part, part.replace("-", " ").title())
        active = i == len(parts) - 1
        
        if active:
            elem = name
        else:
            elem = html.Button(
                name,
                id={"type": "breadcrumb-link", "level": i},
                n_clicks=0,
                className="breadcrumb-btn",
                style={
                    "background": "none", "border": "none", "color": "#667eea",
                    "cursor": "pointer", "padding": "0", "fontSize": "12px",
                    "textDecoration": "underline",
                }
            )
        
        items.append(
            html.Li(elem, className="bc-item" + (" bc-item--active" if active else ""))
        )
    return items


def _portal_content(role, society_id, pathname):
    """
    Route pathname → portal page content.
    Uses portal_pages.py — the single source for all portal layouts.
    """
    from app.dash_apps.pages.portal_pages import (
        master_portal_page,
        admin_portal_page,
        owner_portal_page,
        vendor_portal_page,
        security_portal_page,
    )

    is_master = role == "admin" and society_id is None
    p = pathname or ""

    # ── Master admin ──────────────────────────────────────────────────────
    if is_master:
        return master_portal_page()

    # ── Admin portal ──────────────────────────────────────────────────────
    if role == "admin":
        tab = (
            "cashbook"      if "/cashbook"       in p else
            "receipts"      if "/receipts"       in p else
            "expenses"      if "/expenses"       in p else
            "enroll"        if "/enroll"         in p else
            "events"        if "/events"         in p else
            "concerns"      if "/concerns"       in p else
            "evaluate_pass" if "/evaluate-pass"  in p else
            "customize"     if "/customize"      in p else
            "settings"      if "/settings"       in p else
            "dashboard"
        )
        if tab == "customize":
            try:
                from app.dash_apps.pages.customize_layout import customize_layout
                return customize_layout()
            except Exception as e:
                print(f"Customize error: {e}")
        return admin_portal_page(tab)

    # ── Apartment owner ───────────────────────────────────────────────────
    if role == "apartment":
        tab = (
            "cashbook"      if "/owner-cashbook" in p or ("/cashbook" in p) else
            "payments"      if "/payments"       in p else
            "charges"       if "/charges"        in p else
            "events"        if "/owner-events"   in p or ("/events" in p) else
            "concerns"      if "/concerns"       in p else
            "settings"      if "/owner-settings" in p or ("/settings" in p) else
            "dashboard"
        )
        return owner_portal_page(tab)

    # ── Vendor ────────────────────────────────────────────────────────────
    if role == "vendor":
        tab = (
            "cashbook"      if "/vendor-cashbook" in p or ("/cashbook" in p) else
            "payments"      if "/vendor-payments" in p or ("/payments" in p) else
            "charges"       if "/vendor-charges"  in p or ("/charges"  in p) else
            "events"        if "/vendor-events"   in p or ("/events"   in p) else
            "settings"      if "/vendor-settings" in p or ("/settings" in p) else
            "dashboard"
        )
        return vendor_portal_page(tab)

    # ── Security ──────────────────────────────────────────────────────────
    if role == "security":
        tab = (
            "attendance"       if "/attendance"        in p else
            "security_events"  if "/security-events"   in p else
            "security_receipt" if "/security-receipt"  in p else
            "security_users"   if "/security-users"    in p else
            "settings"         if "/security-settings" in p or ("/settings" in p) else
            "pass_evaluation"
        )
        return security_portal_page(tab)

    return html.Div("Page not found", className="text-muted text-center p-5 mt-5")


# ── Register ──────────────────────────────────────────────────────────────────

def register_shell_callbacks(app):
    """Register all shell-level callbacks with the Dash app."""
    
    print("  → Registering shell callbacks...")

    # ══════════════════════════════════════════════════════════════════════════
    # 0. SOCIETY DROPDOWN POPULATION (MUST BE FIRST)
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("society-dropdown", "options"),
        Output("society-dropdown", "disabled"),
        Output("login-db-error", "children"),
        Output("login-db-error", "style"),
        Input("login-modal", "is_open"),
        prevent_initial_call=False,
    )
    def load_societies(is_open):
        """Load societies from database into dropdown when login modal opens.
        
        FIXED: Uses corrected SQL query that:
        1. Handles both Free and Paid plans correctly
        2. Checks plan_validity for Paid plans (9Apts, 99Apts, 999Apts, Unlimited)
        3. Shows only valid societies
        4. Displays plan info in dropdown label
        """
        
        print("\n🔍 Loading societies from database...")
        
        try:
            # Test connection first
            if not db.test_connection():
                print("❌ Database connection failed")
                return (
                    [],
                    True,
                    html.Div(
                        [
                            html.I(className="fas fa-database me-2"),
                            "Cannot connect to database. Please check your connection.",
                        ],
                        style={"color": "#dc3545", "fontSize": "12px", "textAlign": "center"},
                    ),
                    {"display": "block", "marginBottom": "15px", "padding": "8px", 
                     "background": "#f8d7da", "borderRadius": "8px"}
                )
            
            # ✅ FIXED: Corrected SQL query
            # Shows:
            # - All Free plan societies
            # - Paid plan societies with validity >= today
            societies = db._execute(
                """
                SELECT id, name, plan, plan_validity 
                FROM societies 
                WHERE 
                    plan = 'Free' 
                    OR (plan IN ('9Apts', '99Apts', '999Apts', 'Unlimited') 
                        AND plan_validity >= CURRENT_DATE)
                ORDER BY name ASC
                """,
                fetch_all=True
            )
            
            if not societies:
                print("\n⚠️  DEBUG: No societies found")
                print(f"   Possible causes:")
                print(f"   1. No societies in database")
                print(f"   2. All societies have expired plans")
                print(f"   3. Database connection issue")
                print(f"\n   Fix steps:")
                print(f"   • python3 db_query.py --test")
                print(f"   • python3 db_query.py --command 'SELECT * FROM societies'")
                return (
                    [],
                    False,
                    html.Div(
                        [
                            html.I(className="fas fa-exclamation-triangle me-2"),
                            "No valid societies available. Please contact the administrator.",
                        ],
                        style={"color": "#856404", "fontSize": "12px", "textAlign": "center"},
                    ),
                    {"display": "block", "marginBottom": "15px", "padding": "8px", 
                     "background": "#fff3cd", "borderRadius": "8px"}
                )
            
            # Build dropdown options with plan info as subtitle
            options = []
            for s in societies:
                plan = s.get("plan", "Free")
                plan_status = "Free"
                
                if plan != "Free" and s.get("plan_validity"):
                    # Show days remaining for paid plans
                    validity = s.get("plan_validity")
                    if isinstance(validity, str):
                        from datetime import datetime
                        validity = datetime.fromisoformat(validity).date()
                    
                    days_left = (validity - dt_date.today()).days
                    if days_left > 0:
                        plan_status = f"{plan} ({days_left}d left)"
                    elif days_left == 0:
                        plan_status = f"{plan} (expires today)"
                    else:
                        plan_status = f"{plan} (expired)"
                
                options.append({
                    "label": f"{s['name']} [{plan_status}]",
                    "value": s["id"]
                })
            
            print(f"✅ Loaded {len(options)} societies:")
            for opt in options:
                print(f"   • {opt['label']}")
            
            return (
                options,
                False,  # enabled
                "",
                {"display": "none"}
            )
            
        except Exception as e:
            print(f"❌ Error loading societies: {e}")
            import traceback
            traceback.print_exc()
            return (
                [],
                True,
                html.Div(
                    [html.I(className="fas fa-database me-2"), 
                     f"Database error: {str(e)[:80]}"],
                    style={"color": "#dc3545", "fontSize": "12px", "textAlign": "center"},
                ),
                {"display": "block", "marginBottom": "15px", "padding": "8px", 
                 "background": "#f8d7da", "borderRadius": "8px"}
            )

    # ══════════════════════════════════════════════════════════════════════════
    # 1. STAGE 1 → STAGE 2 TRANSITION
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("login-stage-1", "style"),
        Output("login-stage-2", "style"),
        Output("auth-store", "data", allow_duplicate=True),
        Output("cookie-store", "data", allow_duplicate=True),
        Input("society-select-btn", "n_clicks"),
        State("society-dropdown", "value"),
        State("remember-society-checkbox", "value"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def transition_to_stage2(n_clicks, society_id, remember_society, auth_data):
        """Move from society selection to login form."""
        if not n_clicks or not society_id:
            raise PreventUpdate
        
        print(f"\n✅ Society selected: {society_id}, Remember: {remember_society}")
        
        # Update auth-store with society_id
        auth_data = auth_data or {}
        auth_data["society_id"] = society_id
        auth_data["authenticated"] = False
        
        # Update cookie if "remember society" is checked
        cookie_update = no_update
        if remember_society:
            cookie_update = {"society_id": society_id}
        
        return (
            {"display": "none"},  # Hide stage 1
            {"display": "block"},  # Show stage 2
            auth_data,
            cookie_update
        )
    
    # ══════════════════════════════════════════════════════════════════════════
    # 2. BACK BUTTON TO RETURN TO STAGE 1
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("login-stage-1", "style", allow_duplicate=True),
        Output("login-stage-2", "style", allow_duplicate=True),
        Input("back-to-stage1-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def back_to_stage1(n_clicks):
        """Return to society selection."""
        if not n_clicks:
            raise PreventUpdate
        
        print("\n← Returning to society selection")
        return {"display": "block"}, {"display": "none"}

    # ══════════════════════════════════════════════════════════════════════════
    # 3. RESTORE SOCIETY FROM COOKIE (AUTO-ADVANCE IF COOKIE EXISTS)
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("society-dropdown", "value", allow_duplicate=True),
        Output("login-stage-1", "style", allow_duplicate=True),
        Output("login-stage-2", "style", allow_duplicate=True),
        Output("auth-store", "data", allow_duplicate=True),
        Input("cookie-store", "data"),
        State("society-dropdown", "options"),
        prevent_initial_call=True,
    )
    def restore_society_from_cookie(cookie, society_options):
        """If cookie has society_id, auto-advance to stage 2."""
        if not cookie or not cookie.get("society_id"):
            return no_update, no_update, no_update, no_update
        
        society_id = cookie["society_id"]
        
        # Verify society_id exists in options
        if society_options:
            valid = any(opt["value"] == society_id for opt in society_options if isinstance(opt, dict))
            if not valid:
                print(f"⚠️ Cookie society_id {society_id} not found in dropdown options")
                return no_update, no_update, no_update, no_update
        
        print(f"\n✅ Restored society from cookie: {society_id}")
        auth_data = {"society_id": society_id, "authenticated": False}
        
        return (
            society_id,           # Pre-select dropdown
            {"display": "none"},  # Hide stage 1
            {"display": "block"},  # Show stage 2
            auth_data
        )
    
    # ══════════════════════════════════════════════════════════════════════════
    # 4. POPULATE LOGIN STAGE 2 CONTENT
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("login-stage-2", "children"),
        Input("auth-store", "data"),
        State("login-stage-2", "children"),
        State("society-dropdown", "options"),
        prevent_initial_call=True,
    )
    def inject_login_stage2(auth_data, current_children, society_options):
        """Generate the login form with society name.
        Only injects when society changes to avoid spurious re-renders
        that cause dynamically-added button callbacks to fire with n_clicks=0.
        """
        if not auth_data or auth_data.get("authenticated"):
            return no_update

        society_id = auth_data.get("society_id")
        if not society_id:
            return no_update

        # Don't re-inject if form already showing
        if current_children:
            return no_update

        # Find society name from options
        society_name = "Society"
        if society_options:
            for opt in society_options:
                if isinstance(opt, dict) and opt.get("value") == society_id:
                    # Extract just the society name (before the plan info)
                    label = opt.get("label", "Society")
                    society_name = label.split("[")[0].strip()
                    break

        print(f"\n✅ Injecting login form for society: {society_name}")
        
        from app.dash_apps.pages.login_system import login_layout
        return login_layout(society_name)
    
    @app.callback(
        Output("login-modal-header", "style"),
        Output("login-modal-body", "style"),
        Output("login-society-logo", "src"),
        Input("auth-store", "data"),
        State("society-dropdown", "options"),
        prevent_initial_call=True,
    )
    def update_login_branding(auth_data, society_options):
        """Update login modal branding based on selected society."""
        if not auth_data:
            # Stage 1: Default EstateHub branding
            return (
                {
                    'background': 'linear-gradient(135deg,#667eea 0%,#764ba2 100%)',
                    'borderRadius': '15px 15px 0 0',
                },
                {
                    'backgroundImage': 'url(/assets/EH_bk.jpg)',
                    'backgroundSize': 'cover',
                    'backgroundPosition': 'center',
                },
                '/assets/EH_logo.png'
            )
        
        society_id = auth_data.get("society_id")
        if not society_id or auth_data.get("authenticated"):
            return no_update, no_update, no_update
        
        # Stage 2: Load society-specific branding
        try:
            society = db._execute(
                "SELECT logo, login_background FROM societies WHERE id=%s",
                (society_id,),
                fetch_one=True
            )
            
            if society:
                logo = society.get("logo") or "/assets/EH_logo.png"
                background = society.get("login_background") or "/assets/EH_bk.jpg"
                
                header_style = {
                    'background': 'linear-gradient(135deg,#667eea 0%,#764ba2 100%)',
                    'borderRadius': '15px 15px 0 0',
                }
                
                body_style = {
                    'backgroundImage': f'url({background})',
                    'backgroundSize': 'cover',
                    'backgroundPosition': 'center',
                    'position': 'relative',
                }
                # Add overlay for better text readability
                if background != "/assets/EH_bk.jpg":
                    body_style['background'] = f'linear-gradient(rgba(255,255,255,0.92), rgba(255,255,255,0.92)), url({background})'
                
                return header_style, body_style, logo
        except Exception as e:
            print(f"Error loading society branding: {e}")
        
        # Fallback to default
        return (
            {
                'background': 'linear-gradient(135deg,#667eea 0%,#764ba2 100%)',
                'borderRadius': '15px 15px 0 0',
            },
            {
                'backgroundImage': 'url(/assets/EH_bk.jpg)',
                'backgroundSize': 'cover',
                'backgroundPosition': 'center',
            },
            '/assets/EH_logo.png'
        )

    # ══════════════════════════════════════════════════════════════════════════
    # 5. TOGGLE MASTER LOGIN
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("master-login-collapse", "style"),
        Input("toggle-master-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_master(n):
        """Toggle master admin login form visibility."""
        if not n:
            raise PreventUpdate
        return {"display": "block"} if n and n % 2 == 1 else {"display": "none"}

    # ══════════════════════════════════════════════════════════════════════════
    # 6. LOGOUT
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("auth-store", "data", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Output("login-modal", "is_open", allow_duplicate=True),
        Input("sb-logout-btn", "n_clicks"),
        Input("qr-modal-logout-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def logout(n2, n3):
        """Handle logout."""
        if not (n2 or n3):
            raise PreventUpdate
        
        print("\n🚪 User logging out...")
        
        try:
            from flask_login import logout_user
            logout_user()
        except:
            pass
        
        return None, "/dashboard/", {"type": "success", "message": "Signed out"}, True

    # ══════════════════════════════════════════════════════════════════════════
    # 7A. LOGIN MODAL STATE MANAGER (SEPARATE FROM ROUTER)
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("login-modal", "is_open", allow_duplicate=True),
        Input("auth-store", "data"),
        prevent_initial_call='initial_duplicate',
    )
    def manage_login_modal_state(auth):
        """Control login modal based on authentication state.
        Fires on initial load so returning authenticated users never see a flash.
        """
        if not auth or not auth.get("authenticated"):
            print("\n🔓 User not authenticated - opening login modal")
            return True  # Open modal
        else:
            print("\n🔒 User authenticated - closing login modal")
            return False  # Close modal

    # ══════════════════════════════════════════════════════════════════════════
    # 6. MAIN ROUTER (URL → PORTAL CONTENT)
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("portal-content", "children"),
        Output("sb-nav-list", "children"),
        Output("breadcrumb-ol", "children"),
        Output("hdr-portal-label", "children"),
        Output("hdr-portal-label", "style"),
        Output("sb-user-name", "children"),
        Output("sb-user-role", "children"),
        Output("sb-avatar", "children"),
        Output("hdr-entity-name", "children"),
        Output("hdr-avatar", "children"),
        Output("hdr-society-name", "children"),
        Output("hdr-society-logo", "src"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def route_page(pathname, auth):
        """Main router - update all shell components based on current URL."""
        
        if not auth or not auth.get("authenticated"):
            print(f"\n⚠️ Not authenticated for path: {pathname}")
            return (
                html.Div("Please log in", className="text-muted text-center mt-5"),
                [], [], "", {}, "—", "—", "?", "User", "?", "EsateHub",
                "/static/assets/EH_logo.png"
            )
        
        # User is authenticated - show content (modal managed by separate callback)
        print(f"\n✅ Authenticated user routing to: {pathname}")
        
        role = auth.get("role")
        society_id = auth.get("society_id")
        user_id = auth.get("user_id")
        email = auth.get("email", "")
        
        user_name = email.split("@")[0].title()
        
        # Get society details
        society_name = "EsateHub"
        society_logo = "/static/assets/EH_logo.png"
        if society_id:
            try:
                society = db._execute(
                    "SELECT name, logo FROM societies WHERE id = %s",
                    (society_id,),
                    fetch_one=True
                )
                if society:
                    society_name = society["name"]
                    if society.get("logo"):
                        society_logo = f"/assets/{society_id}/{society['logo']}"
            except:
                pass
        
        # Get role config
        is_master = role == "admin" and society_id is None
        key = "master" if is_master else (role or "admin")
        cfg = ROLE_CONFIG.get(key, ROLE_CONFIG["admin"])
        
        portal_label = cfg["label"]
        portal_style = {
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "center",
            "textAlign": "center",
            "fontWeight": "700",
            "fontSize": "24px",
            "minWidth": "180px",
            "padding": "0 2px",
            "color": cfg["color"],
        }
        
        avatar = user_name[0].upper() if user_name else "?"
        
        return (
            _portal_content(role, society_id, pathname),
            _make_nav_items(role, society_id, pathname),
            _breadcrumb(pathname),
            portal_label,
            portal_style,
            user_name,
            role.title(),
            avatar,
            user_name,
            avatar,
            society_name,
            society_logo
        )

    # ══════════════════════════════════════════════════════════════════════════
    # 8. SIDEBAR TOGGLE
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("app-sidebar", "className"),
        Output("sb-overlay", "style"),
        Output("sidebar-open-store", "data"),
        Input("hdr-hamburger-btn", "n_clicks"),
        Input("sb-overlay", "n_clicks"),
        Input("sb-collapse-btn", "n_clicks"),
        State("sidebar-open-store", "data"),
        prevent_initial_call=True,
    )
    def toggle_sidebar(ham_n, over_n, col_n, store):
        """Toggle sidebar."""
        if not ctx.triggered:
            raise PreventUpdate
        
        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
        collapsed = store.get("collapsed", False) if store else False
        
        if trigger_id in ["hdr-hamburger-btn", "sb-overlay"]:
            new_collapsed = not collapsed
            return (
                "app-sidebar" if new_collapsed else "app-sidebar sidebar-open",
                {"display": "none"} if new_collapsed else {"display": "block"},
                {"collapsed": new_collapsed}
            )
        
        if trigger_id == "sb-collapse-btn":
            new_collapsed = not collapsed
            return (
                "app-sidebar sidebar-collapsed" if new_collapsed else "app-sidebar",
                {"display": "none"},
                {"collapsed": new_collapsed}
            )
        
        raise PreventUpdate

    # ══════════════════════════════════════════════════════════════════════════
    # 9. TOAST NOTIFICATIONS
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("toast-container", "children"),
        Input("toast-store", "data"),
        prevent_initial_call=True,
    )
    def show_toast(toast_data):
        """Display toast notification."""
        if not toast_data:
            return []
        
        toast_type = toast_data.get("type", "info")
        message = toast_data.get("message", "")
        
        icon_map = {
            "success": "fa-check-circle",
            "error": "fa-exclamation-circle",
            "warning": "fa-exclamation-triangle",
            "info": "fa-info-circle",
        }
        
        color_map = {
            "success": "#10b981",
            "error": "#ef4444",
            "warning": "#f59e0b",
            "info": "#3b82f6",
        }
        
        # Play sound
        try:
            if toast_type == "success":
                chime.success()
            elif toast_type == "error":
                chime.error()
            elif toast_type == "warning":
                chime.warning()
            else:
                chime.info()
        except:
            pass
        
        return dbc.Toast(
            message,
            id="toast",
            header=html.Div([
                html.I(className=f"fas {icon_map.get(toast_type, 'fa-info-circle')} me-2"),
                toast_type.title()
            ]),
            icon=toast_type,
            duration=4000,
            is_open=True,
            style={"borderLeft": f"4px solid {color_map.get(toast_type, '#3b82f6')}"},
        )

    print("  ✓Shell callbacks registered successfully")
