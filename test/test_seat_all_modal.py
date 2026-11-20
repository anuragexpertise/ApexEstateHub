"""S4 acceptance: seat-all shows a progress modal while the background job runs."""

import dash
import pytest
from dash import html


def test_seat_all_layout_has_modal_and_progress():
    """The seat-all panel renders a modal with progress bar, store and poll interval."""
    import dash_bootstrap_components as dbc
    from app.dash_apps.pages import onboarding_page as op

    panel = op._seat_all_panel({})
    text = str(panel)
    assert "onb-seat-modal" in text
    assert "onb-seat-bar" in text
    assert "onb-seat-msg" in text
    assert "onb-seat-jobid" in text
    assert "onb-seat-poll" in text
    assert "onb-seat-close" in text


def test_seat_all_callbacks_register():
    """The seat-all start and poll callbacks register on a real Dash app."""
    dash = pytest.importorskip("dash")
    dbc = pytest.importorskip("dash_bootstrap_components")
    from app.dash_apps.callbacks.onboarding_callbacks import register_onboarding_callbacks
    from app.dash_apps.pages import onboarding_page as op
    app = dash.Dash(__name__, suppress_callback_exceptions=True, external_stylesheets=[dbc.themes.BOOTSTRAP])
    app.layout = html.Div(op._seat_all_panel({}))
    register_onboarding_callbacks(app)
    ids = [str(c) for c in app.callback_map.keys()]
    assert any("seat-jobid" in c for c in ids), f"seat-jobid output not found in {ids}"
    assert any("seat-modal" in c for c in ids), f"seat-modal output not found in {ids}"
    assert any("seat-poll" in c for c in ids), f"seat-poll output not found in {ids}"
