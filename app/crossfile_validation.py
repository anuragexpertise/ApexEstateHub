import re, sys

files = {
    "shell_callbacks.py":        "/home/at/Documents/ApexEstateHub/app/dash_apps/callbacks/shell_callbacks.py",
    "login_callbacks.py":        "/home/at/Documents/ApexEstateHub/app/dash_apps/callbacks/login_callbacks.py",
    "card_catalogue_callbacks.py": "/home/at/Documents/ApexEstateHub/app/dash_apps/callbacks/card_catalogue_callbacks.py",
    "app_shell.py":              "/home/at/Documents/ApexEstateHub/app/dash_apps/app_shell.py",
}

all_ok = True

for name, path in files.items():
    with open(path) as f:
        src = f.read()
    lines = src.splitlines()
    print(f"\n{'='*50}")
    print(f"  {name} ({len(lines)} lines)")
    print(f"{'='*50}")

    # Rule 1: allow_duplicate + prevent_initial_call
    blocks = re.split(r'\n    @app\.callback\(', src)
    for block in blocks[1:]:
        has_dup = "allow_duplicate=True" in block
        safe = ("prevent_initial_call=True" in block or
                "initial_duplicate" in block)
        if has_dup and not safe:
            fn = re.search(r'def (\w+)\(', block)
            fn_name = fn.group(1) if fn else "unknown"
            print(f"  ❌ DASH RULE VIOLATION in '{fn_name}': "
                  f"allow_duplicate=True without prevent_initial_call=True/'initial_duplicate'")
            all_ok = False

    # Rule 2: wrong db method names in code (not comments)
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for bad in ["db.execute_query(", ".test_connection()"]:
            if bad in line:
                print(f"  ❌ Line {i}: wrong method '{bad}': {stripped[:70]}")
                all_ok = False

    # Rule 3: non-existent column in code
    for i, line in enumerate(lines, 1):
        if "active = true" in line.lower() or "active=true" in line.lower():
            stripped = line.strip()
            if not stripped.startswith("#") and "WHERE" in line.upper():
                print(f"  ❌ Line {i}: non-existent column: {stripped[:70]}")
                all_ok = False

    # Rule 4: app_shell must have refresh=False on dcc.Location
    if name == "app_shell.py":
        if 'refresh=False' in src and 'dcc.Location' in src:
            print("  ✅ dcc.Location has refresh=False")
        else:
            print("  ❌ dcc.Location missing refresh=False")
            all_ok = False

    # Rule 5: auth-store must be 'local' not 'session'
    if name == "app_shell.py":
        if '"auth-store"' in src and 'storage_type="local"' in src:
            print("  ✅ auth-store uses localStorage")
        else:
            print("  ❌ auth-store not set to localStorage")
            all_ok = False

    # Rule 6: guard_modal must exist in shell_callbacks
    if name == "shell_callbacks.py":
        if "guard_modal" in src and "initial_duplicate" in src:
            print("  ✅ guard_modal callback with initial_duplicate present")
        else:
            print("  ❌ guard_modal / initial_duplicate missing")
            all_ok = False

    # Rule 7: dcc.Link in shell_callbacks (not html.A for nav)
    if name == "shell_callbacks.py":
        if "dcc.Link" in src:
            print("  ✅ dcc.Link used for nav items")
        else:
            print("  ❌ dcc.Link missing — nav still uses html.A")
            all_ok = False

    if all_ok:
        print("  ✅ No violations found")

print(f"\n{'='*50}")
print("OVERALL:", "✅ ALL CLEAN" if all_ok else "❌ VIOLATIONS FOUND — see above")
print(f"{'='*50}")
