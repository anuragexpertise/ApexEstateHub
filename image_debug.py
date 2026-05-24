# image_debug.py
"""
Image Path Debugging Utility
=============================
Helps diagnose image loading issues in profile cards.
"""

from pathlib import Path
import os

def debug_image_path(image_path: str | None, society_id: int | None = None,
                     entity: str = None, pk: int | None = None) -> dict:
    """
    Debug image path resolution and return diagnostic info.
    
    Returns:
        {
            "input_path": original path,
            "entity": entity type,
            "pk": primary key,
            "society_id": society ID,
            "resolved_url": final URL,
            "expected_disk_path": expected file location,
            "file_exists": bool,
            "folder_exists": bool,
            "error": str or None,
        }
    """
    debug_info = {
        "input_path": str(image_path) if image_path else None,
        "entity": entity,
        "pk": pk,
        "society_id": society_id,
        "resolved_url": None,
        "expected_disk_path": None,
        "file_exists": False,
        "folder_exists": False,
        "error": None,
    }
    
    try:
        if not image_path or str(image_path).strip() == "":
            debug_info["error"] = "No image path provided"
            return debug_info
        
        path = str(image_path).strip()
        
        # Already a full URL
        if path.startswith(('http://', 'https://', 'data:image')):
            debug_info["resolved_url"] = path
            debug_info["error"] = "External URL - cannot verify file existence"
            return debug_info
        
        # Already a correct absolute path
        if path.startswith('/assets/'):
            debug_info["resolved_url"] = path
            disk_path = Path("app") / path.lstrip('/')
            debug_info["expected_disk_path"] = str(disk_path)
            debug_info["folder_exists"] = disk_path.parent.exists()
            debug_info["file_exists"] = disk_path.exists()
            return debug_info
        
        # Just a filename - construct path
        if '/' not in path and '\\' not in path:
            if entity == "society":
                if society_id:
                    url = f"/assets/{society_id}/{path}"
                    disk_path = Path("app/assets") / str(society_id) / path
                else:
                    url = f"/assets/default/society/{path}"
                    disk_path = Path("app/assets/default/society") / path
            
            elif entity in ("apartment", "vendor", "security"):
                if society_id and pk:
                    url = f"/assets/{society_id}/{entity}/{pk}/{path}"
                    disk_path = Path("app/assets") / str(society_id) / entity / str(pk) / path
                else:
                    url = f"/assets/default/{entity}/{path}"
                    disk_path = Path("app/assets/default") / entity / path
            
            else:
                if society_id and pk:
                    url = f"/assets/{society_id}/{entity}_{pk}/{path}"
                    disk_path = Path("app/assets") / str(society_id) / f"{entity}_{pk}" / path
                else:
                    url = f"/assets/default/{entity}/{path}"
                    disk_path = Path("app/assets/default") / entity / path
            
            debug_info["resolved_url"] = url
            debug_info["expected_disk_path"] = str(disk_path)
            debug_info["folder_exists"] = disk_path.parent.exists()
            debug_info["file_exists"] = disk_path.exists()
            
            if not disk_path.exists():
                debug_info["error"] = f"File not found at {disk_path}"
            
            return debug_info
        
        # Has path separators - legacy handling
        if '/assets/default/' in path and society_id:
            resolved = path.replace('/assets/default/', f'/assets/{society_id}/')
            debug_info["resolved_url"] = resolved
            disk_path = Path("app") / resolved.lstrip('/')
            debug_info["expected_disk_path"] = str(disk_path)
            debug_info["folder_exists"] = disk_path.parent.exists()
            debug_info["file_exists"] = disk_path.exists()
        else:
            debug_info["resolved_url"] = f"/assets/{path}"
            disk_path = Path("app/assets") / path
            debug_info["expected_disk_path"] = str(disk_path)
            debug_info["folder_exists"] = disk_path.parent.exists()
            debug_info["file_exists"] = disk_path.exists()
        
        return debug_info
    
    except Exception as e:
        debug_info["error"] = f"Exception: {str(e)}"
        return debug_info


def scan_asset_folders(society_id: int | None = None) -> dict:
    """
    Scan asset folders and return inventory.
    
    Returns:
        {
            "default_folders": {entity: [files]},
            "society_folders": {society_id: {entity: [files]}},
        }
    """
    inventory = {
        "default_folders": {},
        "society_folders": {},
    }
    
    # Scan default folders
    default_base = Path("app/assets/default")
    if default_base.exists():
        for entity_dir in default_base.iterdir():
            if entity_dir.is_dir():
                files = [f.name for f in entity_dir.iterdir() if f.is_file()]
                inventory["default_folders"][entity_dir.name] = files
    
    # Scan society folders
    assets_base = Path("app/assets")
    if assets_base.exists():
        for item in assets_base.iterdir():
            if item.is_dir() and item.name != "default":
                try:
                    sid = int(item.name)
                    inventory["society_folders"][sid] = {}
                    
                    # Root level files (society images)
                    root_files = [f.name for f in item.iterdir() if f.is_file()]
                    if root_files:
                        inventory["society_folders"][sid]["_root"] = root_files
                    
                    # Entity subfolders
                    for entity_dir in item.iterdir():
                        if entity_dir.is_dir():
                            # Check for entity/pk structure
                            entity_name = entity_dir.name
                            inventory["society_folders"][sid][entity_name] = {}
                            
                            for pk_dir in entity_dir.iterdir():
                                if pk_dir.is_dir():
                                    files = [f.name for f in pk_dir.iterdir() if f.is_file()]
                                    inventory["society_folders"][sid][entity_name][pk_dir.name] = files
                except ValueError:
                    pass
    
    return inventory


def print_debug_report(image_path: str | None, society_id: int | None = None,
                       entity: str = None, pk: int | None = None):
    """Print a formatted debug report for an image path."""
    print("\n" + "="*70)
    print("IMAGE PATH DEBUG REPORT")
    print("="*70)
    
    info = debug_image_path(image_path, society_id, entity, pk)
    
    print(f"\n📥 INPUT:")
    print(f"   Path:       {info['input_path']}")
    print(f"   Entity:     {info['entity']}")
    print(f"   PK:         {info['pk']}")
    print(f"   Society ID: {info['society_id']}")
    
    print(f"\n🔄 RESOLUTION:")
    print(f"   URL:        {info['resolved_url']}")
    print(f"   Disk Path:  {info['expected_disk_path']}")
    
    print(f"\n✅ VERIFICATION:")
    print(f"   Folder Exists: {info['folder_exists']}")
    print(f"   File Exists:   {info['file_exists']}")
    
    if info['error']:
        print(f"\n❌ ERROR: {info['error']}")
    else:
        print(f"\n✅ No errors detected")
    
    print("="*70 + "\n")
    
    return info


if __name__ == "__main__":
    # Test cases
    print("\n🧪 RUNNING TEST CASES...\n")
    
    # Test 1: Society logo (filename only)
    print_debug_report("logo.png", society_id=1, entity="society", pk=1)
    
    # Test 2: Apartment image (filename only)
    print_debug_report("photo.jpg", society_id=1, entity="apartment", pk=42)
    
    # Test 3: Vendor image (filename only)
    print_debug_report("vendor_logo.png", society_id=1, entity="vendor", pk=5)
    
    # Test 4: Full path
    print_debug_report("/assets/1/society/logo.png", society_id=1, entity="society", pk=1)
    
    # Test 5: Default temp path
    print_debug_report("temp_image.png", society_id=None, entity="apartment", pk=None)
    
    # Scan folders
    print("\n📂 ASSET FOLDER INVENTORY:")
    print("="*70)
    inventory = scan_asset_folders()
    
    print("\n📁 Default Folders:")
    for entity, files in inventory["default_folders"].items():
        print(f"   {entity}/: {len(files)} files")
        if files:
            print(f"      {files[:3]}{'...' if len(files) > 3 else ''}")
    
    print("\n📁 Society Folders:")
    for sid, entities in inventory["society_folders"].items():
        print(f"\n   Society {sid}:")
        for entity, data in entities.items():
            if entity == "_root":
                print(f"      Root files: {data}")
            else:
                print(f"      {entity}/:")
                for pk, files in data.items():
                    print(f"         {pk}/: {files}")
    
    print("\n" + "="*70)
