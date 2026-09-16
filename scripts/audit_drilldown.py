import sys
import os
import json

# Adjust sys.path to be able to import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.dash_apps.drilldown.registry import DRILLDOWN_MAP, ENTITY_MAP, to_singular
from app.dash_apps.drilldown.schema_introspect import build_entity_meta

# Need to run within flask app context for db access if build_entity_meta requires it
from app import create_app
app = create_app()

with app.app_context():
    meta = build_entity_meta()
    
    # KPIs to List
    kpi_map = {}
    for key, val in DRILLDOWN_MAP.items():
        if key.startswith("kpi_"):
            target = val.get("target")
            if target:
                kpi_map.setdefault(target, []).append(key)
    
    # Output Markdown
    print("| KPI / Quicklink | List Name (Action Buttons) | Profile Name (Action Buttons) | Form New (Columns) | Form Edit (Columns) | Save Handler Status |")
    print("| --- | --- | --- | --- | --- | --- |")
    
    for list_key in sorted(kpi_map.keys()):
        if not list_key.startswith("list_"):
            continue
        
        kpis = "<br>".join(kpi_map[list_key])
        entity_plural = list_key.replace("list_", "")
        singular = to_singular(entity_plural)
        profile_key = f"profile_{singular}"
        
        # Profile actions
        profile_info = DRILLDOWN_MAP.get(profile_key, {})
        actions = list(profile_info.get("actions", {}).keys())
        actions_str = ", ".join(actions) if actions else "None"
        
        # Forms
        form_new = f"form_{singular}_new"
        form_edit = f"form_{singular}_edit"
        
        entity_meta = meta.get(entity_plural, {})
        form_fields = entity_meta.get("form_fields", {})
        new_cols = [f["id"] for f in form_fields.get("new", [])]
        edit_cols = [f["id"] for f in form_fields.get("edit", [])]
        
        new_cols_str = ", ".join(new_cols) if new_cols else "None"
        edit_cols_str = ", ".join(edit_cols) if edit_cols else "None"
        
        print(f"| {kpis} | {list_key} | {profile_key} <br> Actions: {actions_str} | {form_new} <br> Cols: {new_cols_str} | {form_edit} <br> Cols: {edit_cols_str} | To Check |")

