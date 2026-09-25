# app/utils/ux_toasts.py
"""
Shared UX primitives for toasts, confirm dialogs, loading states, and error handling.
"""

from functools import wraps
from dash import html, no_update
import dash_bootstrap_components as dbc


# ──────────────────────────────────────────────────────────────────────────────
# TOAST HELPERS
# ──────────────────────────────────────────────────────────────────────────────

_TOAST_ICONS = {
    "success": "fas fa-check-circle",
    "error": "fas fa-times-circle",
    "warning": "fas fa-exclamation-triangle",
    "info": "fas fa-info-circle",
}

_TOAST_COLORS = {
    "success": "#2ecc71",
    "error": "#e74c3c",
    "warning": "#f39c12",
    "info": "#3498db",
}


def toast(message: str, type: str = "info", reference_id: str | None = None) -> dict:
    """
    Create a standardized toast dict.

    Args:
        message: User-facing message
        type: One of "success", "error", "warning", "info"
        reference_id: Optional internal reference ID for debugging (not shown to user)

    Returns:
        Dict with keys: type, message, reference_id (if provided)
    """
    result = {"type": type, "message": str(message)[:200]}
    if reference_id:
        result["reference_id"] = reference_id
    return result


def error_toast(exc: Exception, fallback: str = "Something went wrong. Please try again.", reference_id: str | None = None) -> dict:
    """
    Map a raw exception to a user-friendly toast.

    Args:
        exc: The caught exception
        fallback: Generic message if exception doesn't match known patterns
        reference_id: Optional internal reference ID for debugging

    Returns:
        Toast dict with type="error"
    """
    msg = str(exc).lower()

    # Map common exception patterns to friendly messages
    if "connection" in msg or "network" in msg or "timeout" in msg:
        friendly = "Database connection error. Please try again shortly."
    elif "duplicate key" in msg or "unique" in msg:
        friendly = "This record already exists."
    elif "foreign key" in msg:
        friendly = "Cannot complete — related record is missing or in use."
    elif "permission" in msg or "forbidden" in msg:
        friendly = "You don't have permission to do that."
    elif "not found" in msg:
        friendly = "Record not found."
    else:
        friendly = fallback

    return toast(friendly, "error", reference_id)


def success_toast(message: str, reference_id: str | None = None) -> dict:
    return toast(message, "success", reference_id)


def warning_toast(message: str, reference_id: str | None = None) -> dict:
    return toast(message, "warning", reference_id)


def info_toast(message: str, reference_id: str | None = None) -> dict:
    return toast(message, "info", reference_id)


# ──────────────────────────────────────────────────────────────────────────────
# CONFIRM MODAL (tiered: undo / modal / type-to-confirm)
# ──────────────────────────────────────────────────────────────────────────────

class ConfirmTier:
    """Confirmation tier levels."""
    UNDO = "undo"           # Toast with undo button (low stakes, reversible)
    MODAL = "modal"         # Standard confirm modal (medium stakes)
    TYPE_TO_CONFIRM = "type_to_confirm"  # Type entity name to confirm (high stakes, irreversible)


def confirm_modal(
    tier: str,
    entity_label: str,
    on_confirm: dict,  # Output spec for confirm action
    on_cancel: dict | None = None,
    type_target: str | None = None,
    modal_id: str = "confirm-modal",
    undo_toast_id: str = "undo-toast",
) -> html.Div:
    """
    Create a tiered confirmation component.

    Args:
        tier: One of ConfirmTier.UNDO, ConfirmTier.MODAL, ConfirmTier.TYPE_TO_CONFIRM
        entity_label: Human-readable label of the entity being deleted
        on_confirm: Dash Output spec for the confirm action
        on_cancel: Optional Dash Output spec for cancel
        type_target: String user must type for TYPE_TO_CONFIRM tier
        modal_id: Base ID for modal component
        undo_toast_id: ID for undo toast component

    Returns:
        html.Div containing the appropriate confirmation UI
    """
    if tier == ConfirmTier.UNDO:
        return _undo_toast(entity_label, on_confirm, undo_toast_id)

    if tier == ConfirmTier.TYPE_TO_CONFIRM:
        return _type_to_confirm_modal(entity_label, type_target, on_confirm, on_cancel, modal_id)

    return _standard_modal(entity_label, on_confirm, on_cancel, modal_id)


def _undo_toast(entity_label: str, on_confirm: dict, toast_id: str) -> html.Div:
    """Toast with undo button for reversible actions."""
    return html.Div(
        dbc.Toast(
            [
                html.Div(
                    [
                        html.I(className="fas fa-check-circle me-2", style={"color": "#2ecc71"}),
                        html.Span(f"{entity_label} deleted. "),
                        dbc.Button(
                            "Undo",
                            id={"type": "undo-btn", "action": on_confirm.get("id")},
                            color="link",
                            size="sm",
                            style={"padding": "0 8px"},
                        ),
                    ],
                    style={"display": "flex", "alignItems": "center"},
                ),
            ],
            id=toast_id,
            header="Deleted",
            icon="success",
            duration=5000,
            is_open=True,
            dismissable=True,
            style={"minWidth": "300px"},
        ),
        id=f"{toast_id}-container",
    )


def _standard_modal(
    entity_label: str,
    on_confirm: dict,
    on_cancel: dict | None,
    modal_id: str,
) -> html.Div:
    """Standard modal confirmation."""
    confirm_id = f"{modal_id}-confirm"
    cancel_id = f"{modal_id}-cancel"

    return html.Div(
        dbc.Modal(
            [
                dbc.ModalHeader(dbc.ModalTitle(f"Delete {entity_label}?"), close_button=True),
                dbc.ModalBody(
                    f"Are you sure you want to delete {entity_label}? This action cannot be undone."
                ),
                dbc.ModalFooter(
                    [
                        dbc.Button("Cancel", id=cancel_id, color="secondary", outline=True, n_clicks=0),
                        dbc.Button(
                            "Delete",
                            id=confirm_id,
                            color="danger",
                            n_clicks=0,
                        ),
                    ]
                ),
            ],
            id=modal_id,
            is_open=False,
            centered=True,
        ),
        id=f"{modal_id}-container",
    )


def _type_to_confirm_modal(
    entity_label: str,
    type_target: str,
    on_confirm: dict,
    on_cancel: dict | None,
    modal_id: str,
) -> html.Div:
    """Type-to-confirm modal for irreversible actions."""
    confirm_id = f"{modal_id}-confirm"
    cancel_id = f"{modal_id}-cancel"
    input_id = f"{modal_id}-input"

    return html.Div(
        dbc.Modal(
            [
                dbc.ModalHeader(dbc.ModalTitle(f"Delete {entity_label}?"), close_button=True),
                dbc.ModalBody(
                    [
                        html.P(
                            f"This action is irreversible. To confirm, type the entity name exactly:",
                            style={"fontSize": "13px", "color": "#7d8ea3", "marginBottom": "12px"},
                        ),
                        html.Code(type_target, style={"display": "block", "marginBottom": "8px", "fontSize": "14px"}),
                        dbc.Input(
                            id=input_id,
                            placeholder=f"Type '{type_target}' to confirm",
                            style={"fontSize": "13px"},
                        ),
                        html.Small(
                            "Case-sensitive. The confirm button enables only when text matches exactly.",
                            style={"color": "#aaa", "display": "block", "marginTop": "6px"},
                        ),
                    ]
                ),
                dbc.ModalFooter(
                    [
                        dbc.Button("Cancel", id=cancel_id, color="secondary", outline=True, n_clicks=0),
                        dbc.Button(
                            "Delete",
                            id=confirm_id,
                            color="danger",
                            n_clicks=0,
                            disabled=True,
                        ),
                    ]
                ),
            ],
            id=modal_id,
            is_open=False,
            centered=True,
        ),
        id=f"{modal_id}-container",
    )


# ──────────────────────────────────────────────────────────────────────────────
# LOADING / SUBMITTING BUTTON STATE
# ──────────────────────────────────────────────────────────────────────────────

def submitting_button(
    button_id: str,
    label: str,
    submitting: bool = False,
    color: str = "primary",
    **kwargs,
) -> dbc.Button:
    """
    Button that shows spinner and disables while submitting.

    Args:
        button_id: Dash ID for the button
        label: Button text
        submitting: Whether a submission is in progress
        color: Bootstrap color
        **kwargs: Additional dbc.Button props

    Returns:
        dbc.Button with loading state
    """
    children = []
    if submitting:
        children.append(html.I(className="fas fa-spinner fa-spin me-2"))
    children.append(label)

    return dbc.Button(
        children,
        id=button_id,
        disabled=submitting,
        color=color,
        **kwargs,
    )


def make_loading_output(button_id: str, loading: bool) -> dict:
    """Generate Output dict for updating button loading state."""
    return {
        "component_id": button_id,
        "component_property": "disabled",
        "value": loading,
    }


# ──────────────────────────────────────────────────────────────────────────────
# CALLBACK DECORATOR FOR ERROR HANDLING
# ──────────────────────────────────────────────────────────────────────────────

def with_toast(app, output_toast: dict, output_loading: dict | None = None):
    """
    Decorator that wraps a callback to catch exceptions, log them, and return a user-friendly toast.

    Usage:
        @app.callback(Output(...), Input(...))
        @with_toast(app, Output("toast-store", "data"))
        def my_callback(...):
            ...

    Args:
        app: Dash app instance
        output_toast: Output spec for the toast store (e.g., Output("toast-store", "data"))
        output_loading: Optional Output spec for a loading indicator

    Returns:
        Decorated callback function
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                # If the callback returns a tuple with a toast, pass it through
                if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], dict) and "type" in result[1]:
                    return result
                return result, no_update
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception("Callback error")
                toast_data = error_toast(e)
                if output_loading:
                    return no_update, toast_data, {"loading": False}
                return no_update, toast_data
        return wrapper
    return decorator


# ──────────────────────────────────────────────────────────────────────────────
# EMPTY STATE HELPER (extended)
# ──────────────────────────────────────────────────────────────────────────────

def empty_state(
    message: str,
    icon: str = "fa-compass",
    action: dict | None = None,
) -> html.Div:
    """
    Create an empty state component with optional CTA.

    Args:
        message: Message to display
        icon: FontAwesome icon class (without 'fas fa-' prefix)
        action: Optional dict with keys 'label', 'href' or 'id' (for callback)

    Returns:
        html.Div with centered empty state
    """
    children = [
        html.I(
            className=f"fas {icon} fa-3x mb-3",
            style={"color": "rgba(29,116,216,0.2)"},
        ),
        html.P(message, className="text-muted", style={"fontSize": "13px"}),
    ]

    if action:
        if action.get("href"):
            children.append(
                html.A(
                    action["label"],
                    href=action["href"],
                    className="btn btn-primary btn-sm mt-2",
                    style={"textDecoration": "none"},
                )
            )
        elif action.get("id"):
            children.append(
                dbc.Button(
                    action["label"],
                    id=action["id"],
                    color="primary",
                    size="sm",
                    className="mt-2",
                )
            )

    return html.Div(
        children,
        className="text-center",
        style={"padding": "60px 20px"},
    )


# ──────────────────────────────────────────────────────────────────────────────
# HELP TOOLTIP WRAPPER
# ──────────────────────────────────────────────────────────────────────────────

def help_tooltip(label: str, tooltip_text: str, tooltip_id: str | None = None) -> html.Span:
    """
    Wrapper for a label with a help tooltip.

    Args:
        label: Label text
        tooltip_text: Tooltip content
        tooltip_id: Optional ID for the tooltip (auto-generated if not provided)

    Returns:
        html.Span with label and tooltip
    """
    if not tooltip_id:
        import uuid
        tooltip_id = f"tooltip-{uuid.uuid4().hex[:8]}"

    return html.Span(
        [
            label,
            dbc.Tooltip(
                tooltip_text,
                target=tooltip_id,
                placement="top",
            ),
            html.I(
                className="fas fa-question-circle ms-1",
                id=tooltip_id,
                style={"cursor": "help", "fontSize": "12px", "color": "#999", "verticalAlign": "middle"},
            ),
        ],
        style={"display": "inline-flex", "alignItems": "center"},
    )