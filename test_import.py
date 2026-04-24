# test_import.py
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("Testing import of app_shell...")

try:
    from app.dash_apps.app_shell import shell_layout
    print("✓ Successfully imported shell_layout")
    print(f"  Function: {shell_layout}")
    print(f"  Returns: {type(shell_layout())}")
except Exception as e:
    print(f"✗ Failed to import: {e}")
    import traceback
    traceback.print_exc()
