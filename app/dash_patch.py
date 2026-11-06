# app/dash_patch.py
"""
Monkey-patch for Dash 2.14.2 IndexError bug in Dash.dispatch().

When callbacks use State with ALL pattern matching and fewer components
match than expected (e.g. dynamically removed DOM elements), the frontend
sends fewer state values than inputs_state_indices expects, causing
IndexError: list index out of range at dash/dash.py:1276.

Fix: pad inputs + state to the expected length before map_grouping and
validate_and_group_input_args are called.
"""

import dash
from dash._grouping import grouping_len

_original_dispatch = dash.Dash.dispatch


def _patched_dispatch(self):
    import flask
    from dash._utils import AttributeDict
    from dash._grouping import map_grouping, update_args_group
    from dash._utils import (
        inputs_to_dict,
        inputs_to_vals,
        split_callback_id,
        convert_to_AttributeDict,
    )
    from contextvars import copy_context
    import functools

    body = flask.request.get_json()

    g = AttributeDict({})

    g.inputs_list = inputs = body.get("inputs", [])
    g.states_list = state = body.get("state", [])
    output = body["output"]
    outputs_list = body.get("outputs") or split_callback_id(output)
    g.outputs_list = outputs_list

    g.input_values = (input_values) = inputs_to_dict(inputs)
    g.state_values = inputs_to_dict(state)
    changed_props = body.get("changedPropIds", [])
    g.triggered_inputs = [
        {"prop_id": x, "value": input_values.get(x)} for x in changed_props
    ]

    response = g.dash_response = flask.Response(mimetype="application/json")

    args = inputs_to_vals(inputs + state)

    try:
        cb = self.callback_map[output]
        func = cb["callback"]
        g.background_callback_manager = (
            cb.get("manager") or self._background_manager
        )
        g.ignore_register_page = cb.get("long", False)

        # Add args_grouping
        inputs_state_indices = cb["inputs_state_indices"]

        # ── PATCH: pad inputs + state to expected length ─────────────
        # When ALL pattern matching matches fewer components than declared
        # (e.g. zero matches for a State dependency), inputs + state is
        # shorter than inputs_state_indices expects. Pad with empty lists
        # so map_grouping() and validate_and_group_input_args() don't
        # raise IndexError / CallbackException. Also pad ctx.states_list
        # (g.states_list) so callbacks that index into it don't raise
        # IndexError: list index out of range.
        expected_len = grouping_len(inputs_state_indices)
        inputs_state = inputs + state
        if len(inputs_state) < expected_len:
            padding = [[] for _ in range(expected_len - len(inputs_state))]
            inputs_state = list(inputs_state) + padding
            state = list(state) + padding
            g.states_list = state
            args = inputs_to_vals(inputs_state)
        # ──────────────────────────────────────────────────────────────

        inputs_state = convert_to_AttributeDict(inputs_state)

        # update args_grouping attributes
        for s in inputs_state:
            # check for pattern matching: list of inputs or state
            if isinstance(s, list):
                for pattern_match_g in s:
                    update_args_group(pattern_match_g, changed_props)
            update_args_group(s, changed_props)

        args_grouping = map_grouping(
            lambda ind: inputs_state[ind], inputs_state_indices
        )

        g.args_grouping = args_grouping
        g.using_args_grouping = (
            not isinstance(inputs_state_indices, int)
            and (
                inputs_state_indices
                != list(range(grouping_len(inputs_state_indices)))
            )
        )

        # Add outputs_grouping
        outputs_indices = cb["outputs_indices"]
        if not isinstance(outputs_list, list):
            flat_outputs = [outputs_list]
        else:
            flat_outputs = outputs_list

        outputs_grouping = map_grouping(
            lambda ind: flat_outputs[ind], outputs_indices
        )
        g.outputs_grouping = outputs_grouping
        g.using_outputs_grouping = (
            not isinstance(outputs_indices, int)
            and outputs_indices != list(range(grouping_len(outputs_indices)))
        )

    except KeyError as missing_callback_function:
        msg = (
            f"Callback function not found for output '{output}', "
            "perhaps you forgot to prepend the '@'?"
        )
        raise KeyError(msg) from missing_callback_function

    ctx = copy_context()
    response.set_data(
        ctx.run(
            functools.partial(
                func,
                *args,
                outputs_list=outputs_list,
                long_callback_manager=self._background_manager,
                callback_context=g,
            )
        )
    )
    return response


dash.Dash.dispatch = _patched_dispatch
