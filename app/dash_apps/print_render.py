"""
Server-side, print-friendly rendering of Dash component trees.

Used by the /print_wizard/<category> route so every Setup Wizard step can be
printed from a clean standalone window (like /print_doc), instead of calling
window.print() on the SPA page, which also prints the wizard modal backdrop.

Only a static snapshot is produced: interactive controls (inputs, buttons,
dropdowns, stores, ...) are dropped, text/tables/alerts/markdown are kept.
"""
from html import escape

import markdown as _markdown

# Dash html.* types that are real tags but need a different name / are void.
_VOID = {"br", "hr", "img", "input", "meta", "link"}
_DROP_HTML = {"Button", "Input", "Select", "Textarea", "Script", "Iframe", "Form"}
# Non-html components that are pure interaction / state and never print.
_DROP_TYPES = {
    "Input", "Button", "Select", "Checkbox", "Switch", "RadioItems", "Checklist",
    "Dropdown", "Store", "Location", "Interval", "Upload", "Textarea", "Tooltip",
    "Popover", "DatePickerSingle", "DatePickerRange", "Slider",
    "ButtonGroup", "Spinner", "Loading", "Download",
}
_ALLOWED_STYLE_PROPS = {
    "color", "background-color", "font-size", "font-weight", "text-align",
    "padding", "margin", "border", "border-radius", "width", "font-style",
}


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
        tag = ctype.lower()
        if tag in _VOID:
            return f"<{tag}{_cls(props)}{_style_attr(style)}>"
        # Anchors become plain text: hrefs/targets are meaningless on paper.
        if tag == "a":
            return f"<span{_cls(props)}{_style_attr(style)}>{_children(kids)}</span>"
        return f"<{tag}{_cls(props)}{_style_attr(style)}>{_children(kids)}</{tag}>"

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
