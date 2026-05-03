def _portal_content(role: str, pathname: str):
    from app.dash_apps.pages.portal_pages import (
        master_portal_page,
        admin_portal_page,
        owner_portal_page,
        vendor_portal_page,
        security_portal_page,
    )

    # Extract active tab from URL
    # Example:
    # /dashboard/admin-portal → dashboard
    # /dashboard/cashbook → cashbook

    parts = pathname.strip("/").split("/")
    tab = parts[-1] if len(parts) > 1 else "dashboard"

    # Normalize tab names
    tab = tab.replace("-", "_")

    if role == "master":
        return master_portal_page()

    if role == "admin":
        return admin_portal_page(tab)

    if role == "apartment":
        return owner_portal_page(tab)

    if role == "vendor":
        return vendor_portal_page(tab)

    if role == "security":
        return security_portal_page(tab)

    return html.Div("Invalid role")
