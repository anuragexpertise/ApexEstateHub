from dash import html
import dash_bootstrap_components as dbc

def create_breadcrumb(pathname):
    """Create breadcrumb navigation based on current path"""
    
    # Path mapping for display names
    path_map = {
        'admin-portal': 'Dashboard',
        'owner-portal': 'Dashboard',
        'vendor-portal': 'Dashboard',
        'pass-evaluation': 'Pass Evaluation',
        'cashbook': 'Cashbook',
        'owner-cashbook': 'Cashbook',
        'vendor-cashbook': 'Cashbook',
        'receipts': 'Receipts',
        'expenses': 'Expenses',
        'enroll': 'Enroll',
        'users': 'Users',
        'security-users': 'Users',
        'events': 'Events',
        'owner-events': 'Events',
        'vendor-events': 'Events',
        'security-events': 'Events',
        'evaluate-pass': 'Evaluate Pass',
        'customize': 'Customize',
        'settings': 'Settings',
        'owner-settings': 'Settings',
        'vendor-settings': 'Settings',
        'security-settings': 'Settings',
        'payments': 'Payments',
        'vendor-payments': 'Payments',
        'charges': 'Charges',
        'vendor-charges': 'Charges',
        'attendance': 'Attendance',
        'security-receipt': 'New Receipt'
    }
    
    # Split path and build breadcrumb items
    path_parts = pathname.strip('/').split('/')
    
    # Remove 'dashboard' from the beginning if present
    if path_parts and path_parts[0] == 'dashboard':
        path_parts = path_parts[1:]
    
    breadcrumb_items = [
        dbc.BreadcrumbItem(
            [html.I(className="fas fa-home me-1"), "Home"],
            href="/dashboard",
            active=len(path_parts) == 0
        )
    ]
    
    # Build breadcrumb items
    current_path = ""
    for i, part in enumerate(path_parts):
        if part:
            current_path += f"/{part}"
            display_name = path_map.get(part, part.replace('-', ' ').title())
            is_active = i == len(path_parts) - 1
            
            breadcrumb_items.append(
                dbc.BreadcrumbItem(
                    display_name,
                    href=f"/dashboard{current_path}" if not is_active else None,
                    active=is_active
                )
            )
    
    return dbc.Breadcrumb(
        breadcrumb_items,
        className="glass-breadcrumb",
        style={
            "background": "rgba(255, 255, 255, 0.7)",
            "backdropFilter": "blur(5px)",
            "padding": "8px 15px",
            "borderRadius": "8px",
            "margin": "0",
            "fontSize": "14px"
        }
    )