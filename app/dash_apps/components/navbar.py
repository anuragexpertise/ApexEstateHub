from dash import html
from .header import create_header
from .sidebar import create_sidebar
from .breadcrumb import create_breadcrumb
from .footer import create_footer

def get_navbar_components(session_data, pathname):
    """Get all navbar components for authenticated user"""
    
    if not session_data or not session_data.get('authenticated'):
        return None, None, None, None
    
    role = session_data.get('role')
    society_id = session_data.get('society_id')
    email = session_data.get('email')
    is_master = role == 'admin' and society_id is None
    
    # Get society name
    society_name = "ApexEstateHub"
    if society_id and not is_master:
        try:
            from app.services.society_service import get_society_details
            society = get_society_details(society_id)
            if society:
                society_name = society.get('name', 'ApexEstateHub')
        except Exception as e:
            print(f"Error getting society name: {e}")
    
    # Determine role for display
    display_role = 'master' if is_master else role
    
    # Create components with error handling
    try:
        header = create_header(society_name, display_role, email)
    except Exception as e:
        print(f"Error creating header: {e}")
        header = html.Div("Header Error")
    
    try:
        sidebar = create_sidebar(role, society_id)
    except Exception as e:
        print(f"Error creating sidebar: {e}")
        sidebar = html.Div("Sidebar Error")
    
    try:
        breadcrumb = create_breadcrumb(pathname)
    except Exception as e:
        print(f"Error creating breadcrumb: {e}")
        breadcrumb = html.Div("Breadcrumb Error")
    
    try:
        footer = create_footer()
    except Exception as e:
        print(f"Error creating footer: {e}")
        footer = html.Div("Footer Error")
    
    return header, sidebar, breadcrumb, footer