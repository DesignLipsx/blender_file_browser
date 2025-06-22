import bpy
import bpy.utils.previews
from pathlib import Path


custom_icons = None


def load_custom_icons():
    global custom_icons
    if custom_icons is None:
        custom_icons = bpy.utils.previews.new()

        icon_dir = Path("D:/Add-on/Scripting/script_browser/icons")
        if icon_dir.exists():
            for icon_file in icon_dir.glob("*.png"):
                icon_name = icon_file.stem  # Get filename without extension
                custom_icons.load(icon_name, str(icon_file), 'IMAGE')


def unload_custom_icons():
    global custom_icons
    if custom_icons is not None:
        bpy.utils.previews.remove(custom_icons)
        custom_icons = None
