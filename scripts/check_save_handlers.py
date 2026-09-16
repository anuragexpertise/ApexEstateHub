import sys
import os
import re
import ast

# Add app to sys path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.dash_apps.drilldown.schema_introspect import build_entity_meta
from app.dash_apps.drilldown.registry import to_singular, DRILLDOWN_MAP

def extract_get_keys(func_node):
    keys = set()
    for node in ast.walk(func_node):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == 'get':
                if len(node.args) >= 1 and isinstance(node.args[0], ast.Constant):
                    keys.add(node.args[0].value)
        # Also check dict indexing d['...']
        elif isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                # We need to make sure it's the data dict being accessed, but let's just collect all strings for now
                keys.add(node.slice.value)
    return keys

def main():
    app = create_app()
    with app.app_context():
        meta = build_entity_meta()
    
    # parse drilldown_callbacks.py
    with open('app/dash_apps/callbacks/drilldown_callbacks.py', 'r') as f:
        tree = ast.parse(f.read())
        
    save_funcs = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith('_save_'):
            save_funcs[node.name] = extract_get_keys(node)
            
    # Now check for each entity
    for ekey, emeta in meta.items():
        singular = to_singular(ekey)
        form_cols = [f["id"] for f in emeta.get("form_fields", {}).get("new", [])]
        if not form_cols:
            continue
            
        # Try to find corresponding save handler
        handler_name = f"_save_{singular}"
        
        # some exceptions
        if singular == 'transaction':
            continue # maybe handled differently or no edit?
        if handler_name not in save_funcs:
            # check variations
            if handler_name + '_v3' in save_funcs:
                handler_name = handler_name + '_v3'
            elif singular == 'payment': # payables -> payment -> pay_dues?
                handler_name = '_save_pay_dues' # just a guess, we will see
            else:
                print(f"Skipping {ekey}: handler {handler_name} not found")
                continue
                
        keys_used = save_funcs[handler_name]
        missing = [c for c in form_cols if c not in keys_used]
        if missing:
            # Filter out things that are handled in db_manager or db_query or pl/pgsql directly
            # For example, if it's passed as JSON to a postgres function, the python code might not unpack it.
            print(f"{ekey} missing: {missing}")

if __name__ == '__main__':
    main()
