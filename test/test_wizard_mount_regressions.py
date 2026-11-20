"""Regression guards for the "Continue to society setup" blank-wizard bug (no DB needed)."""
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGES = ROOT / "app" / "dash_apps"


def test_no_stray_trailing_comma_turns_a_component_into_a_tuple():
    """`x = dbc.Modal(...),` makes x a 1-tuple; Dash then raises 'children is a list of lists'
    and the whole wizard (every step renders up-front) fails to mount."""
    bad = []
    for f in PAGES.rglob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if (isinstance(n, ast.Assign) and isinstance(n.value, ast.Tuple)
                    and len(n.value.elts) == 1 and isinstance(n.value.elts[0], ast.Call)):
                bad.append(f"{f.relative_to(ROOT)}:{n.lineno}")
    assert not bad, f"single-element tuple assignments (stray comma?): {bad}"


def test_every_wizard_step_is_rendered_with_saved_data():
    """Steps other than the opening one are shown by CSS only, never re-rendered, so each must be
    built with is_current=True or it appears blank ('Address is required.')."""
    src = (PAGES / "pages" / "onboarding_page.py").read_text(encoding="utf-8")
    assert "is_current=(i == current_step)" not in src
    assert "render_category_content(cat, society_id, is_current=True)" in src
