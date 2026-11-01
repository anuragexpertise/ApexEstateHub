"""Plan v5, DPDP: the society's grievance officer is published on the login page (stage 2) and nowhere is a blank shown."""
from app.dash_apps.pages.login_system import grievance_footer, login_layout
from app.services import dpdp_service as dp


def test_no_officer_named_shows_nothing():
    assert grievance_footer(None) is None
    assert "login-grievance-contact" not in str(login_layout("Sunrise"))


def test_named_officer_is_shown_under_the_login_form():
    layout = login_layout("Sunrise", {"name": "Asha Verma", "email": "asha@sunrise.example", "phone": "9876543210"})
    text = str(layout[-1])
    assert layout[-1].id == "login-grievance-contact"
    assert "Asha Verma" in text and "asha@sunrise.example" in text and "9876543210" in text


def test_one_contact_channel_is_enough_and_no_none_is_printed():
    text = str(login_layout("S", {"name": "Asha", "email": None, "phone": "9876543210"})[-1])
    assert "9876543210" in text and "None" not in text


def test_contact_needs_a_name_and_a_way_to_reach_them(monkeypatch):
    rows = {"v": None}
    monkeypatch.setattr(dp, "_row", lambda sql, params=None: rows["v"])
    assert dp.grievance_contact(1) is None
    rows["v"] = {"name": "Asha", "email": None, "phone": None}
    assert dp.grievance_contact(1) is None                       # a name alone is not a contact
    rows["v"] = {"name": "Asha", "email": "a@x.in", "phone": None}
    assert dp.grievance_contact(1) == {"name": "Asha", "email": "a@x.in", "phone": None}
