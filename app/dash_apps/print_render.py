"""
Server-side, print-friendly rendering of Dash component trees.

Used by the /print_wizard/<category> route so every Setup Wizard step can be
printed from a clean standalone window (like /print_doc), instead of calling
window.print() on the SPA page, which also prints the wizard modal backdrop.

Only a static snapshot is produced. Buttons, uploads, stores and other pure-interaction
components are dropped; text/tables/alerts/markdown are kept; and every form control
(inputs, selects, dropdowns, checkboxes, radios, date pickers, data tables) is rendered as
its current value, so a printed form is never blank. Password fields are never printed.
"""
from html import escape

import markdown as _markdown

# Dash html.* types that are real tags but need a different name / are void.
_VOID = {"br", "hr", "img", "input", "meta", "link"}
_DROP_HTML = {"Button", "Script", "Iframe", "Form"}
# Form controls that are printed as their value (see _control_html) instead of being dropped.
_VALUE_HTML = {"Input", "Select", "Textarea"}
_VALUE_TYPES = {
    "Input", "Textarea", "Select", "Dropdown", "Checkbox", "Switch", "RadioItems", "Checklist",
    "DatePickerSingle", "DatePickerRange", "Slider", "DataTable",
}
# Non-html components that are pure interaction / state and never print.
_DROP_TYPES = {
    "Button", "Store", "Location", "Interval", "Upload", "Tooltip",
    "Popover", "ButtonGroup", "Spinner", "Loading", "Download",
}
_ALLOWED_STYLE_PROPS = {
    "color", "background-color", "font-size", "font-weight", "text-align",
    "padding", "margin", "border", "border-radius", "width", "font-style",
}
_NO_VALUE = "\u2014"                       # em dash: an empty field prints as a visible blank, not as nothing
_MASK = "(not printed)"                     # password / secret fields


# ── form controls -> their current value ─────────────────────────────────────────────────────────────────────
def _label_for(options, value):
    """Display label of `value` in a dash `options` list (list of dicts, list of scalars, or {value: label})."""
    if isinstance(options, dict):
        return str(options.get(value, value))
    for o in options or []:
        if isinstance(o, dict):
            if o.get("value") == value:
                lab = o.get("label", value)
                return lab if isinstance(lab, (str, int, float)) else str(value)
        elif o == value:
            return str(o)
    return str(value)


def _as_list(v):
    if v is None or v == "":
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


def _plain(label):
    """A dbc label can be a component tree; reduce it to text."""
    if isinstance(label, (str, int, float)):
        return str(label)
    return ""


def _value_text(ctype, props):
    """Printable text for a form control's current value, or None when the control prints nothing."""
    t = str(props.get("type") or "").lower()
    if ctype in ("Input", "Textarea"):
        if t in ("checkbox", "radio"):                      # raw html.Input: state is `checked`
            return ("\u2611" if (props.get("checked") or props.get("value") is True) else "\u2610")
        if t in ("button", "submit", "reset", "image"):
            return None
        if t in ("password", "hidden", "file"):
            return _MASK if t == "password" and props.get("value") not in (None, "") else None
        v = props.get("value")
        return "" if v is None else str(v)
    if ctype in ("Select", "Dropdown"):
        vals = _as_list(props.get("value"))
        return ", ".join(_label_for(props.get("options"), v) for v in vals)
    if ctype == "RadioItems":
        v = props.get("value")
        return "" if v is None else _label_for(props.get("options"), v)
    if ctype == "Checklist":
        return ", ".join(_label_for(props.get("options"), v) for v in _as_list(props.get("value")))
    if ctype in ("Checkbox", "Switch"):
        return ("\u2611 " if props.get("value") else "\u2610 ") + _plain(props.get("label"))
    if ctype == "DatePickerSingle":
        return str(props.get("date") or "")[:10]
    if ctype == "DatePickerRange":
        a, b = str(props.get("start_date") or "")[:10], str(props.get("end_date") or "")[:10]
        return f"{a} \u2013 {b}" if (a or b) else ""
    if ctype == "Slider":
        v = props.get("value")
        return "" if v is None else str(v)
    return None


def _datatable_html(props):
    cols = props.get("columns") or []
    rows = props.get("data") or []
    head, ids = [], []
    for c in cols:
        if isinstance(c, dict):
            name = c.get("name")
            name = " / ".join(map(str, name)) if isinstance(name, (list, tuple)) else (name if name is not None else c.get("id"))
            head.append(escape(str(name)))
            ids.append(c.get("id"))
    if not ids and rows:                                    # no column spec: use the first row's keys
        ids = list(rows[0].keys())
        head = [escape(str(k)) for k in ids]
    body = "".join(
        "<tr>" + "".join(f"<td>{escape('' if (r or {}).get(i) is None else str((r or {}).get(i)))}</td>" for i in ids) + "</tr>"
        for r in rows)
    if not body:
        body = f"<tr><td colspan='{max(len(ids), 1)}'>{_NO_VALUE}</td></tr>"
    return "<table class='table table-bordered table-sm'><thead><tr>" + "".join(f"<th>{h}</th>" for h in head) + f"</tr></thead><tbody>{body}</tbody></table>"


def _control_html(ctype, props):
    """HTML for a form control, or None if this component is not one."""
    if ctype == "DataTable":
        return _datatable_html(props)
    txt = _value_text(ctype, props)
    if txt is None:
        return ""
    if ctype in ("Checkbox", "Switch") or txt in ("\u2611", "\u2610"):
        return f"<span class='fv fv-check'>{escape(txt)}</span>"
    if txt == _MASK:
        return f"<span class='fv fv-secret'>{_MASK}</span>"
    return f"<span class='fv'>{escape(txt) if txt.strip() else _NO_VALUE}</span>"


def _camel_to_kebab(name):
    out = []
    for ch in name:
        if ch.isupper():
            out.append("-")
            out.append(ch.lower())
        else:
            out.append(ch)
    return "".join(out)


def _style_attr(style):
    if not isinstance(style, dict):
        return ""
    parts = []
    for k, v in style.items():
        prop = _camel_to_kebab(str(k))
        if prop in _ALLOWED_STYLE_PROPS and isinstance(v, (str, int, float)):
            parts.append(f"{prop}:{escape(str(v), quote=True)}")
    return f' style="{";".join(parts)}"' if parts else ""


def _cls(props, extra=""):
    cn = " ".join(x for x in (extra, props.get("className") or "") if x).strip()
    return f' class="{escape(cn, quote=True)}"' if cn else ""


def _children(children):
    if children is None:
        return ""
    if isinstance(children, (list, tuple)):
        return "".join(_children(c) for c in children)
    if isinstance(children, bool):
        return ""
    if isinstance(children, (str, int, float)):
        return escape(str(children))
    return component_to_html(children)


def component_to_html(comp):
    """Convert a Dash component (or str/number/list) into an HTML string."""
    if comp is None or isinstance(comp, bool):
        return ""
    if isinstance(comp, (str, int, float, list, tuple)):
        return _children(comp)

    to_json = getattr(comp, "to_plotly_json", None)
    if not callable(to_json):
        return escape(str(comp))
    data = to_json()
    ctype = data.get("type", "")
    ns = (data.get("namespace") or "").lower()
    props = data.get("props") or {}
    kids = props.get("children")

    # Hidden panes should not print.
    style = props.get("style")
    if isinstance(style, dict) and str(style.get("display", "")).lower() == "none":
        return ""

    if ctype == "Markdown" and "dash_core" in ns:
        return f'<div{_cls(props, "md")}>{_markdown.markdown(str(kids or ""), extensions=["tables", "fenced_code"])}</div>'

    if "dash_html" in ns:
        if ctype in _DROP_HTML:
            return ""
        if ctype in _VALUE_HTML:
            if ctype == "Select":                           # html.Select: value + html.Option children
                opts = [{"label": getattr(o, "children", None), "value": getattr(o, "value", None)} for o in _as_list(kids)]
                return _control_html("Select", {"value": props.get("value"), "options": opts})
            return _control_html("Textarea" if ctype == "Textarea" else "Input", props)
        tag = ctype.lower()
        if tag in _VOID:
            return f"<{tag}{_cls(props)}{_style_attr(style)}>"
        # Anchors become plain text: hrefs/targets are meaningless on paper.
        if tag == "a":
            return f"<span{_cls(props)}{_style_attr(style)}>{_children(kids)}</span>"
        return f"<{tag}{_cls(props)}{_style_attr(style)}>{_children(kids)}</{tag}>"

    if ctype in _VALUE_TYPES:
        return _control_html(ctype, props)
    if ctype in _DROP_TYPES or "dash_core" in ns:
        return ""

    # dash-bootstrap-components (and any other library): best-effort mapping.
    if ctype == "Alert":
        color = props.get("color", "primary")
        return f'<div{_cls(props, "alert alert-" + str(color))}>{_children(kids)}</div>'
    if ctype == "Badge":
        return f'<span{_cls(props, "badge")}>{_children(kids)}</span>'
    if ctype == "Table":
        return f'<table{_cls(props, "table table-bordered table-sm")}>{_children(kids)}</table>'
    if ctype == "Row":
        return f'<div{_cls(props, "row")}>{_children(kids)}</div>'
    if ctype == "Col":
        return f'<div{_cls(props, "col")}>{_children(kids)}</div>'
    if ctype in ("Card", "CardBody", "CardHeader", "CardFooter", "ListGroup", "ListGroupItem", "Container"):
        return f'<div{_cls(props, ctype.lower())}>{_children(kids)}</div>'
    return f"<div{_cls(props)}>{_children(kids)}</div>"


PRINT_PAGE_CSS = """
body { font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; line-height: 1.5;
       padding: 20px; max-width: 900px; margin: 0 auto; color: #212529; font-size: 13px; }
h1,h2,h3,h4,h5 { margin: 14px 0 8px; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; }
th, td { border: 1px solid #999; padding: 4px 6px; text-align: left; vertical-align: top; }
th { background: #eee; }
.alert { border: 1px solid #bbb; border-radius: 4px; padding: 8px 10px; margin: 8px 0; background: #f6f6f6; }
.badge { border: 1px solid #999; border-radius: 3px; padding: 0 4px; }
.row { display: flex; flex-wrap: wrap; gap: 12px; }
.col { flex: 1 1 0; min-width: 160px; }
pre { white-space: pre-wrap; }
.fv { display: inline-block; min-width: 140px; border-bottom: 1px solid #888; padding: 1px 4px; margin: 0 0 6px; font-weight: 600; }
.fv-check, .fv-secret { border-bottom: 0; min-width: 0; }
.fv-secret { color: #777; font-weight: 400; font-style: italic; }
@media print { .no-print { display: none; } body { padding: 0; } }
"""


def render_print_page(title, body_html):
    t = escape(title)
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{t}</title><style>{PRINT_PAGE_CSS}</style></head>"
        "<body onload='window.print()'>"
        "<button class='no-print' onclick='window.print()' "
        "style='padding:10px;margin-bottom:20px;cursor:pointer'>Print</button>"
        f"<h2>{t}</h2>{body_html}</body></html>"
    )
