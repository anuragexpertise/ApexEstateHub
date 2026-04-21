from dash import Input, Output, State, no_update
import dash

def register_mobile_callbacks(app):
    
    # Simple sidebar toggle for mobile
    @app.callback(
        Output("main-content", "style"),
        Input("url", "pathname"),
        prevent_initial_call=False
    )
    def reset_margin(pathname):
        # This just ensures the margin is set correctly
        return {'marginLeft': '250px', 'transition': 'all 0.3s ease'}