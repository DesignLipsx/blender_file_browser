import shutil
from pathlib import Path
from bpy.props import StringProperty, CollectionProperty, IntProperty, BoolProperty, EnumProperty
from bpy.types import PropertyGroup, UIList, Panel, Operator, Menu, AddonPreferences
from send2trash import send2trash

from .icons import load_icons

if "bpy" in locals():
    import importlib
    # Reload the subpackage if it was modified
    importlib.reload(load_icons)
else:
    import bpy


# -------------------------------------------------------------
#                           FUNCTIONS
# -------------------------------------------------------------


move_to_folder_paths: list[Path] = []


def get_addon_root_path(file_path):
    """
    Locate the addon root folder by searching for 'blender_manifest.toml' or '__init__.py'.
    Args:
        file_path (str): Path to the current script file
    Returns:
        str or None: Addon root directory path or None if not found
    """
    if not file_path:
        return None

    current_path = Path(file_path)
    if not current_path.exists():
        return None

    for parent in [current_path.parent] + list(current_path.parent.parents):
        if (parent / "blender_manifest.toml").exists():
            return str(parent)
        if (parent / "__init__.py").exists():
            return str(parent)

    return None


def detect_and_set_root_folder(context):
    """Attempt to automatically detect and set root folder"""
    scene = context.scene
    file_props = scene.file_browser_props
    prefs = bpy.context.preferences.addons[__package__].preferences

    # Auto-detect root folder if enabled and not already set
    if prefs.auto_detect_root:
        # Check current text editor file for addon structure
        text = context.space_data.text if hasattr(
            context.space_data, 'text') else None

        if text and text.filepath:
            file_path = bpy.path.abspath(text.filepath)
            root_path = get_addon_root_path(file_path)
            if root_path:
                file_props.root_path = root_path
                file_props.auto_detection_failed = False
                bpy.ops.file_browser.refresh_list()
                return True

    # If no detection success but default path is set
    if prefs.default_root_dir and Path(prefs.default_root_dir).is_dir():
        file_props.root_path = prefs.default_root_dir
        file_props.auto_detection_failed = False
        bpy.ops.file_browser.refresh_list()
        return True

    file_props.auto_detection_failed = True
    return False


# Operator to search files
def update_file_browser_search(self, context):
    scene = context.scene
    file_props = scene.file_browser_props

    if not file_props.root_path or not Path(file_props.root_path).exists():
        return

    file_props.file_list.clear()

    if file_props.search_term:
        search_term = file_props.search_term.lower()
        try:
            root_path = Path(file_props.root_path)
            for item in root_path.rglob('*'):
                if search_term in item.name.lower():
                    level = len(item.relative_to(root_path).parts) - 1
                    list_item = file_props.file_list.add()
                    list_item.name = str(item.relative_to(root_path))
                    list_item.path = str(item)
                    list_item.is_folder = item.is_dir()
                    list_item.level = level
                    list_item.is_expanded = False
        except PermissionError:
            pass  # Ignore unreadable folders
    else:
        bpy.ops.file_browser.refresh_list()


def create_folder_submenu(folder_path: Path, source_path: Path, menu_id: str):
    class DynamicMoveSubMenu(bpy.types.Menu):
        bl_label = folder_path.name
        bl_idname = menu_id

        def draw(self, context):
            layout = self.layout
            try:
                subfolders = sorted(
                    [p for p in folder_path.iterdir() if p.is_dir()])
            except Exception:
                return  # Skip unreadable folders

            for sub in subfolders:
                try:
                    has_subfolders = any(p.is_dir() for p in sub.iterdir())
                    if has_subfolders:
                        sub_id = f"{menu_id}_{abs(hash(sub))}"
                        submenu_cls = create_folder_submenu(
                            sub, source_path, sub_id)
                        if not hasattr(bpy.types, submenu_cls.__name__):
                            bpy.utils.register_class(submenu_cls)
                        layout.menu(submenu_cls.bl_idname,
                                    text=sub.name, icon='FILE__FOLDER')
                    else:
                        op = layout.operator(
                            "file.move_file_or_folder", text=sub.name, icon='FILE__FOLDER')
                        op.source_path = str(source_path)
                        op.destination_dir = str(sub)
                except Exception:
                    continue  # Skip problematic folders

    DynamicMoveSubMenu.__name__ = f"FILE_BROWSER_MT_move_submenu_{abs(hash(folder_path))}"
    return DynamicMoveSubMenu


def update_root_dir(self, context):
    if self.auto_detect_root:
        detect_and_set_root_folder(context)


_script_template_cache = []
_script_template_cache_dirty = True


def get_script_template_items(context=None):
    global _script_template_cache, _script_template_cache_dirty

    if not _script_template_cache_dirty:
        return _script_template_cache

    items = [("BLANK", "Blank", "Empty script file")]
    prefs = bpy.context.preferences.addons[__package__].preferences
    seen = set()

    paths = []

    try:
        addon_dir = Path(__file__).parent
        paths.append(addon_dir / "templates")
    except:
        pass

    if prefs.template_dir:
        custom_path = Path(bpy.path.abspath(prefs.template_dir))
        if custom_path.exists():
            items.append(None)  # separator
            paths.append(("CUSTOM", custom_path))  # mark as custom

    for path in paths:
        if path is None:
            continue

        is_custom = False
        if isinstance(path, tuple):
            is_custom = True
            path = path[1]

        if not path.exists():
            continue

        for f in path.iterdir():
            if not f.is_file():
                continue
            if is_custom and f.suffix != ".py":
                continue
            if f.name in seen:
                continue

            items.append((f.name, f.stem, f.name))
            seen.add(f.name)

    _script_template_cache = items
    _script_template_cache_dirty = False
    return _script_template_cache


def refresh_script_template_cache(self, context):
    global _script_template_cache_dirty
    _script_template_cache_dirty = True


def update_active_root(self, context):
    self.root_path = self.active_root_path
    bpy.ops.file_browser.refresh_list('INVOKE_DEFAULT')


def update_template_names(context):
    props = context.scene.file_browser_props
    props.template_names.clear()

    templates_dir = Path(__file__).parent / "templates"
    for f in templates_dir.glob("*.py"):
        item = props.template_names.add()
        item.name = f.name


def update_filename(self, context):
    if self.selected_template != "BLANK":
        self.filename = self.selected_template
    else:
        self.filename = "new_file.py"


# -------------------------------------------------------------
#                        Property Group
# -------------------------------------------------------------


# Property group for file items
class FILE_BROWSER_PG_item(PropertyGroup):
    name: StringProperty(name="File Name", default="")
    path: StringProperty(name="File Path", default="")
    is_folder: BoolProperty(name="Is Folder", default=False)
    is_expanded: BoolProperty(name="Is Expanded", default=False)
    level: IntProperty(name="Indent Level", default=0)


# Property group for file browser settings
class FILE_BROWSER_PG_properties(PropertyGroup):
    root_path: StringProperty(
        name="Root Path",
        description="Root directory path",
        default="",
        subtype='DIR_PATH'
    )

    file_list: CollectionProperty(type=FILE_BROWSER_PG_item)
    file_list_index: IntProperty(name="File List Index", default=0)
    show_folders_expanded: BoolProperty(
        name="Expand Folders",
        description="Show expanded folder structure",
        default=False
    )

    search_term: StringProperty(
        name="Search",
        description="Search for files and folders",
        default="",
        update=update_file_browser_search,
        options={'TEXTEDIT_UPDATE'}
    )

    auto_detection_failed: BoolProperty(
        name="Auto Detection Failed",
        description="Whether automatic root detection failed",
        default=False
    )

    root_paths: CollectionProperty(type=bpy.types.PropertyGroup)
    active_root_path: EnumProperty(
        name="Active Root Folder",
        description="Switch between root directories",
        items=lambda self, ctx: [
            (p.name, Path(p.name).name, "") for p in self.root_paths
        ],
        update=update_active_root
    )


# -------------------------------------------------------------
#                          UI List
# -------------------------------------------------------------


# UI List for displaying files
class FILE_BROWSER_UL_items(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        scene = context.scene
        file_props = scene.file_browser_props

        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            # Add indentation for nested folders
            row = layout.row(align=True)
            row.ui_units_y = 1.1
            for i in range(item.level):
                row.label(text="", icon='BLANK1')

            # Toggle button for folders
            if item.is_folder:
                toggle_op = row.operator("file_browser.toggle_single_folder", text="",
                                         icon='DOWNARROW_HLT' if item.is_expanded else 'RIGHTARROW_THIN',
                                         emboss=False)
                toggle_op.folder_index = index

            # Icon based on file type
            prefs = context.preferences.addons[__package__].preferences

            display_name = item.name
            file_path = item.path

            text = next((t for t in bpy.data.texts if Path(
                t.filepath).resolve() == Path(file_path).resolve()), None)

            split = row.split(factor=0.85, align=True)
            left = split.row(align=True)
            left.alignment = "LEFT"

            if not item.is_folder:
                file_path = Path(item.path)
                matching_text = None

            if item.is_folder:
                icon_id = 'FILE_FOLDER'
                left.label(text=display_name, icon=icon_id)
            else:
                file_icon_name = self.get_file_icon(item.name)
                custom_icons = load_icons.custom_icons
                if prefs.use_custom_icons and custom_icons and file_icon_name in custom_icons:
                    op = left.operator("file_browser.open_file", text=display_name,
                                       icon_value=custom_icons[file_icon_name].icon_id, emboss=False)
                else:
                    op = left.operator(
                        "file_browser.open_file", text=display_name, icon=file_icon_name, emboss=False)

                op.file_path = item.path

                if text is not None and text.is_dirty:
                    left.alert = True
                    left.label(text="Unsaved")

            # Menu button for active item
            if index == file_props.file_list_index:
                row.operator("wm.call_menu", text="", icon='DOWNARROW_HLT',
                             emboss=False).name = "FILE_BROWSER_MT_file_context_menu"

        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon='FILE_TEXT')

    def get_file_icon(self, filename):
        """Get appropriate icon based on file extension"""
        ext = Path(filename).suffix.lower()

        if ext == '.py':
            return 'FILE_SCRIPT'
        elif ext == '.blend':
            return 'FILE_BLEND'
        elif ext in ['.txt', '.md', '.rst', '.log']:
            return 'TEXT'
        elif ext in ['.png', '.jpg', '.jpeg', '.bmp', '.tga', '.tiff', '.exr', '.hdr']:
            return 'FILE_IMAGE'
        elif ext in ['.obj', '.fbx', '.dae', '.3ds', '.ply', '.stl']:
            return 'FILE_3D'
        elif ext in ['.ttf', '.otf', '.woff', '.woff2']:
            return 'FILE_FONT'
        else:
            return 'TEXT'


# -------------------------------------------------------------
#                             Menu
# -------------------------------------------------------------


class FILE_BROWSER_MT_move_to_menu(bpy.types.Menu):
    bl_label = "Move To"
    bl_idname = "FILE_BROWSER_MT_move_to_menu"

    def draw(self, context):
        layout = self.layout

        # Get the selected item
        scene = context.scene
        file_props = scene.file_browser_props

        if not file_props.file_list or file_props.file_list_index < 0 or file_props.file_list_index >= len(file_props.file_list):
            layout.label(text="No item selected", icon='ERROR')
            return

        item = file_props.file_list[file_props.file_list_index]
        source_path = Path(item.path)
        root_dir = Path(file_props.root_path)

        global move_to_folder_paths
        print(f"Available folders: {len(move_to_folder_paths)}")

        for folder in move_to_folder_paths:
            try:
                # Skip if it's the same as source folder or source's parent
                if folder.resolve() == source_path.resolve() or folder.resolve() == source_path.parent.resolve():
                    continue

                has_subfolders = any(p.is_dir() for p in folder.iterdir())

                # Create relative path for display
                try:
                    rel_path = folder.relative_to(root_dir)
                    label = str(rel_path) if rel_path.parts else folder.name
                except ValueError:
                    # If folder is not relative to root, use absolute path
                    label = str(folder)

                if has_subfolders:
                    submenu_id = f"FILE_BROWSER_MT_move_submenu_{abs(hash(str(folder)))}"
                    submenu_cls = create_folder_submenu(
                        folder, source_path, submenu_id)
                    if not hasattr(bpy.types, submenu_cls.__name__):
                        bpy.utils.register_class(submenu_cls)
                    layout.menu(submenu_cls.bl_idname, text=label,
                                icon="FILE_BROWSER_FOLDER")
                else:
                    op = layout.operator(
                        "file.move_file_or_folder", text=label, icon='FILE_FOLDER')
                    op.source_path = str(source_path)
                    op.destination_dir = str(folder)
            except Exception as e:
                print(f"Error processing folder {folder}: {e}")
                continue

        # Option to move back to root (if not already at root)
        if source_path.parent.resolve() != root_dir.resolve():
            layout.separator()
            op = layout.operator(
                "file.move_file_or_folder", text=f"../ {root_dir.name}", icon="FILE_PARENT")
            op.source_path = str(source_path)
            op.destination_dir = str(root_dir)


class FILE_BROWSER_MT_file_context_menu(bpy.types.Menu):
    bl_idname = "FILE_BROWSER_MT_file_context_menu"
    bl_label = "File Operations"

    def draw(self, context):
        layout = self.layout
        file_props = context.scene.file_browser_props
        idx = file_props.file_list_index

        if not file_props.file_list or idx < 0 or idx >= len(file_props.file_list):
            return

        item = file_props.file_list[idx]
        is_file = not item.is_folder
        folder_path = item.path if not is_file else str(Path(item.path).parent)

        # --- Basic Operations ---

        layout.operator_context = 'INVOKE_DEFAULT'
        layout.operator("file_browser.rename_item", icon="GREASEPENCIL")
        layout.operator_context = 'EXEC_DEFAULT'

        if is_file:
            layout.operator("file_browser.duplicate_file", icon="DUPLICATE")

        layout.separator()
        layout.operator("file_browser.create_new_file", icon="FILE_NEW")
        layout.operator("file_browser.create_folder", icon="NEWFOLDER")

        layout.separator()

        # --- Move To ---
        src_path = Path(item.path)
        try:
            available_folders = [
                f for f in move_to_folder_paths
                if f.resolve() not in {src_path.resolve(), src_path.parent.resolve()}
            ]
        except Exception:
            available_folders = []

        if available_folders:
            layout.menu("FILE_BROWSER_MT_move_to_menu", icon="FILE_PARENT")

        layout.operator_context = 'INVOKE_DEFAULT'
        layout.operator("file_browser.delete_item", icon="TRASH")
        layout.operator_context = 'EXEC_DEFAULT'

        layout.separator()

        layout.menu("FILE_BROWSER_MT_external", text="External")


class FILE_BROWSER_MT_external(bpy.types.Menu):
    bl_label = "External"
    bl_idname = "FILE_BROWSER_MT_external"

    def draw(self, context):
        file_props = context.scene.file_browser_props
        layout = self.layout
        idx = file_props.file_list_index

        if not file_props.file_list or idx < 0 or idx >= len(file_props.file_list):
            return

        item = file_props.file_list[idx]
        is_file = not item.is_folder
        folder_path = item.path if not is_file else str(Path(item.path).parent)

        if is_file:
            op = layout.operator("file.external_operation", text="Open")
            op.filepath = item.path

        op = layout.operator("file.external_operation", text="Open Folder")
        op.filepath = folder_path

        op = layout.operator("file.external_operation",
                             text="Command Prompt Here")
        op.filepath = folder_path
        op.operation = 'CMD'

        op = layout.operator("file.external_operation", text="Properties")
        op.filepath = item.path
        op.operation = 'PROPERTIES'


class FILE_BROWSER_MT_select_root_path(bpy.types.Menu):
    bl_label = "Select Root Path"
    bl_idname = "FILE_BROWSER_MT_select_root_path"

    def draw(self, context):
        file_props = context.scene.file_browser_props
        layout = self.layout

        for path in file_props.root_paths:
            layout.operator("file_browser.set_active_root", text=Path(
                path.name).name, icon='FILE_FOLDER').path = path.name


class FILE_BROWSER_MT_preferences_menu(bpy.types.Menu):
    bl_label = "File Browser Preferences"
    bl_idname = "FILE_BROWSER_MT_preferences_menu"

    def draw(self, context):
        layout = self.layout
        prefs = bpy.context.preferences.addons[__package__].preferences

        layout.prop(prefs, "auto_detect_root")
        layout.prop(prefs, "use_custom_icons")
        layout.prop(prefs, "show_search_bar")
        layout.prop(prefs, "enable_dynamic_popup_height")


# -------------------------------------------------------------
#                          Operators
# -------------------------------------------------------------


# Operator to select root folder
class FILE_BROWSER_OT_set_root_directory(Operator):
    bl_idname = "file_browser.select_root_folder"
    bl_label = "Select Root Folder"
    bl_description = "Select the root folder to browse.\n\nShift+Click: Add new path.\nAlt+Click: Remove active path"
    bl_options = {'REGISTER'}

    directory: StringProperty(subtype="DIR_PATH")

    def execute(self, context):
        file_props = context.scene.file_browser_props
        if self.directory and Path(self.directory).exists():
            abs_path = str(Path(self.directory).resolve())

            if getattr(self, "_event_shift", False):
                # SHIFT: add path
                if not any(p.name == abs_path for p in file_props.root_paths):
                    new_path = file_props.root_paths.add()
                    new_path.name = abs_path
            else:
                # Normal behavior: replace all paths with this one
                file_props.root_paths.clear()
                new_path = file_props.root_paths.add()
                new_path.name = abs_path

            # Set active path and refresh (for SHIFT and normal cases)
            file_props.active_root_path = abs_path
            file_props.root_path = abs_path
            bpy.ops.file_browser.refresh_list()

            # Update global move_to_folder_paths
            global move_to_folder_paths
            root_path = Path(abs_path)
            move_to_folder_paths = [p for p in root_path.rglob(
                "*") if p.is_dir() and not p.name.startswith('.')]

            self.report({'INFO'}, f"Root folder set: {abs_path}")
        else:
            self.report({'ERROR'}, "Invalid directory")
        return {'FINISHED'}

    def invoke(self, context, event):
        self._event_shift = event.shift
        self._event_alt = event.alt
        file_props = context.scene.file_browser_props
        prefs = bpy.context.preferences.addons[__package__].preferences

        if event.alt:
            # ALT: remove currently active root path
            file_props = context.scene.file_browser_props
            if file_props.active_root_path:
                abs_path = file_props.active_root_path
                # Remove the path from root_paths collection
                to_remove = [
                    p for p in file_props.root_paths if p.name == abs_path]
                for p in to_remove:
                    file_props.root_paths.remove(
                        file_props.root_paths.find(p.name))

                # Update active path - set to first remaining path or clear
                if file_props.root_paths:
                    file_props.active_root_path = file_props.root_paths[0].name
                    file_props.root_path = file_props.root_paths[0].name
                else:
                    file_props.active_root_path = ""
                    file_props.root_path = ""

                self.report({'INFO'}, f"Removed root path: {abs_path}")
                bpy.ops.file_browser.refresh_list()
                return {'FINISHED'}
            else:
                self.report({'WARNING'}, "No active root path to remove")
                return {'CANCELLED'}

        # Prefer default_root_dir if no file loaded
        if not file_props.file_list and prefs.default_root_dir:
            self.directory = prefs.default_root_dir
        else:
            # Normal flow: open file browser for directory selection
            text = context.space_data.text
            if text and text.filepath:
                path = Path(bpy.path.abspath(text.filepath)).parent
                if path.is_dir():
                    self.directory = str(path)

        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


# Operator to refresh file list
class FILE_BROWSER_OT_refresh_list(Operator):
    bl_idname = "file_browser.refresh_list"
    bl_label = "Refresh File List"
    bl_description = "Refresh the file list"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        file_props = scene.file_browser_props

        if not file_props.root_path or not Path(file_props.root_path).exists():
            self.report({'WARNING'}, "No valid root folder selected")
            return {'CANCELLED'}

        root_path = Path(file_props.root_path)

        # --- 1. Store expanded folder paths ---
        expanded_paths = {
            Path(item.path).resolve()
            for item in file_props.file_list
            if item.is_folder and item.is_expanded
        }

        # --- 2. Clear existing list ---
        file_props.file_list.clear()

        # --- 3. Update global move_to_folder_paths ---
        global move_to_folder_paths
        move_to_folder_paths = [
            p for p in root_path.rglob("*")
            if p.is_dir() and not p.name.startswith('.')
        ]
        print(
            f"Refreshed: Found {len(move_to_folder_paths)} folders for move operations")

        # --- 4. Repopulate file list with state restoration ---
        self.populate_file_list(
            root_path, file_props.file_list, 0, expanded_paths)

        return {'FINISHED'}

    def populate_file_list(self, path, file_list, level, expanded_paths):
        try:
            items = sorted(path.iterdir(), key=lambda x: (
                not x.is_dir(), x.name.lower()))
            folders = [item for item in items if item.is_dir()]
            files = [item for item in items if item.is_file()]

            for folder in folders:
                item = file_list.add()
                item.name = folder.name
                item.path = str(folder)
                item.is_folder = True
                item.level = level

                resolved = folder.resolve()
                item.is_expanded = resolved in expanded_paths

                if item.is_expanded:
                    self.populate_file_list(
                        folder, file_list, level + 1, expanded_paths)

            for file in files:
                item = file_list.add()
                item.name = file.name
                item.path = str(file)
                item.is_folder = False
                item.level = level

        except PermissionError:
            pass  # Skip folders without permission


# Operator to toggle single folder expansion
class FILE_BROWSER_OT_toggle_folder(Operator):
    bl_idname = "file_browser.toggle_single_folder"
    bl_label = "Toggle Folder"
    bl_description = "Expand or collapse folder"
    bl_options = {'REGISTER'}

    folder_index: IntProperty(name="Folder Index", default=0)

    def execute(self, context):
        file_props = context.scene.file_browser_props

        # Save the path of the currently selected item (if valid)
        active_path = ""
        if 0 <= file_props.file_list_index < len(file_props.file_list):
            active_path = file_props.file_list[file_props.file_list_index].path

        # Toggle expansion
        if 0 <= self.folder_index < len(file_props.file_list):
            folder = file_props.file_list[self.folder_index]
            if folder.is_folder:
                folder.is_expanded = not folder.is_expanded
                self.rebuild_file_list(context)

        # Restore active index after rebuild
        if active_path:
            for i, item in enumerate(file_props.file_list):
                if item.path == active_path:
                    file_props.file_list_index = i
                    break

        return {'FINISHED'}

    def rebuild_file_list(self, context):
        """Rebuild the file list with current expansion states"""
        scene = context.scene
        file_props = scene.file_browser_props

        if not file_props.root_path or not Path(file_props.root_path).exists():
            return

        # Store expansion states
        expansion_states = {}
        for item in file_props.file_list:
            if item.is_folder:
                expansion_states[item.path] = item.is_expanded

        # Clear and rebuild
        file_props.file_list.clear()
        self.populate_file_list_with_states(
            Path(file_props.root_path), file_props.file_list, 0, expansion_states)

    def populate_file_list_with_states(self, path, file_list, level, expansion_states):
        try:
            items = sorted(path.iterdir(), key=lambda x: (
                not x.is_dir(), x.name.lower()))
            folders = [item for item in items if item.is_dir()]
            files = [item for item in items if item.is_file()]

            # Add folders first
            for folder in folders:
                item = file_list.add()
                item.name = folder.name
                item.path = str(folder)
                item.is_folder = True
                item.level = level
                item.is_expanded = expansion_states.get(str(folder), False)

                # If expanded, add contents recursively
                if item.is_expanded:
                    self.populate_file_list_with_states(
                        folder, file_list, level + 1, expansion_states)

            # Add files
            for file in files:
                item = file_list.add()
                item.name = file.name
                item.path = str(file)
                item.is_folder = False
                item.level = level

        except PermissionError:
            pass  # Skip folders without permission


class FILE_BROWSER_OT_create_new_file(bpy.types.Operator):
    bl_idname = "file_browser.create_new_file"
    bl_label = "Create New File"
    bl_description = "Create a new file from template or blank"

    filename: bpy.props.StringProperty(name="File Name", default="new_file.py")

    selected_template: bpy.props.EnumProperty(
        name="Template",
        description="Select a script template",
        items=lambda self, context: get_script_template_items(context),
        update=update_filename
    )
    open_in_text_editor: bpy.props.BoolProperty(
        name="Open in Text Editor",
        description="Open the newly created file in Blender's Text Editor",
        default=True
    )

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        layout.prop(self, "selected_template")
        layout.prop(self, "filename")
        layout.prop(self, "open_in_text_editor")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        file_props = context.scene.file_browser_props
        prefs = bpy.context.preferences.addons[__package__].preferences
        index = file_props.file_list_index
        items = file_props.file_list

        if 0 <= index < len(items):
            base_path = Path(items[index].path)
            if not items[index].is_folder:
                base_path = base_path.parent
        else:
            base_path = Path(file_props.root_path)

        file_path = base_path / self.filename

        if file_path.exists():
            self.report({'ERROR'}, "File already exists")
            return {'CANCELLED'}

        try:
            template_content = "# New Python file\n"

            if self.selected_template != "BLANK":
                search_paths = [Path(__file__).parent / "templates"]
                if prefs.template_dir:
                    search_paths.insert(
                        0, Path(bpy.path.abspath(prefs.template_dir)))

                for path in search_paths:
                    tpath = path / self.selected_template
                    if tpath.exists():
                        template_content = tpath.read_text(encoding='utf-8')
                        break

            file_path.write_text(template_content)
            if self.open_in_text_editor:
                text_block = bpy.data.texts.load(str(file_path))
                context.space_data.text = text_block
            bpy.ops.file_browser.refresh_list()
            self.report({'INFO'}, f"Created {file_path.name}")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to create file: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}


class FILE_BROWSER_OT_create_folder(bpy.types.Operator):
    bl_idname = "file_browser.create_folder"
    bl_label = "Create New Folder"
    bl_description = "Create a new folder"

    folder_name: bpy.props.StringProperty(
        name="Folder Name", default="NewFolder")

    def execute(self, context):
        file_props = context.scene.file_browser_props
        index = file_props.file_list_index
        items = file_props.file_list

        if 0 <= index < len(items):
            base_path = Path(items[index].path)
            if not items[index].is_folder:
                base_path = base_path.parent
        else:
            base_path = Path(file_props.root_path)

        folder_path = base_path / self.folder_name

        if folder_path.exists():
            self.report({'ERROR'}, "Folder already exists")
            return {'CANCELLED'}

        try:
            folder_path.mkdir(parents=True)
            bpy.ops.file_browser.refresh_list()
            self.report({'INFO'}, f"Created folder: {folder_path.name}")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to create folder: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)


class FILE_BROWSER_OT_open_file(bpy.types.Operator):
    bl_idname = "file_browser.open_file"
    bl_label = "Open File"
    bl_description = "Open selected file in text editor"
    bl_options = {'REGISTER'}

    file_path: bpy.props.StringProperty(name="File Path", subtype="FILE_PATH")

    def execute(self, context):
        abs_path = str(Path(self.file_path).resolve())

        # Check if already opened
        for text in bpy.data.texts:
            if bpy.path.abspath(text.filepath) == abs_path:
                for area in context.window.screen.areas:
                    if area.type == 'TEXT_EDITOR':
                        area.spaces.active.text = text
                        break
                self.report({'INFO'}, f"Switched to: {text.name}")
                return {'FINISHED'}

        # Open file if not already loaded
        try:
            bpy.ops.text.open(filepath=abs_path, internal=False)
            self.report({'INFO'}, f"Opened: {Path(abs_path).name}")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to open file: {e}")
            return {'CANCELLED'}


# Operator to rename file/folder
class FILE_BROWSER_OT_rename_item(Operator):
    bl_idname = "file_browser.rename_item"
    bl_label = "Rename"
    bl_description = "Rename selected file or folder"
    bl_options = {'REGISTER'}

    new_name: StringProperty(name="New Name", default="")

    def execute(self, context):
        scene = context.scene
        file_props = scene.file_browser_props

        if file_props.file_list and 0 <= file_props.file_list_index < len(file_props.file_list):
            item = file_props.file_list[file_props.file_list_index]

            if self.new_name and self.new_name != item.name:
                old_path = Path(item.path)
                new_path = old_path.parent / self.new_name

                try:
                    old_path.rename(new_path)
                    bpy.ops.file_browser.refresh_list()
                    self.report({'INFO'}, f"Renamed to: {self.new_name}")
                except Exception as e:
                    self.report({'ERROR'}, f"Failed to rename: {str(e)}")

        return {'FINISHED'}

    def invoke(self, context, event):
        scene = context.scene
        file_props = scene.file_browser_props

        if file_props.file_list and 0 <= file_props.file_list_index < len(file_props.file_list):
            item = file_props.file_list[file_props.file_list_index]
            self.new_name = item.name

        return context.window_manager.invoke_props_dialog(self)


# Operator to duplicate file
class FILE_BROWSER_OT_duplicate_file(Operator):
    bl_idname = "file_browser.duplicate_file"
    bl_label = "Duplicate"
    bl_description = "Duplicate selected file"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        file_props = scene.file_browser_props

        if file_props.file_list and 0 <= file_props.file_list_index < len(file_props.file_list):
            item = file_props.file_list[file_props.file_list_index]

            if not item.is_folder and Path(item.path).exists():
                try:
                    file_path = Path(item.path)
                    counter = 1
                    new_path = file_path.with_stem(f"{file_path.stem}_copy")

                    while new_path.exists():
                        new_path = file_path.with_stem(
                            f"{file_path.stem}_copy{counter}")
                        counter += 1

                    shutil.copy2(str(file_path), str(new_path))
                    bpy.ops.file_browser.refresh_list()
                    self.report({'INFO'}, f"Duplicated to: {new_path.name}")

                except Exception as e:
                    self.report({'ERROR'}, f"Failed to duplicate: {str(e)}")
            else:
                self.report({'WARNING'}, "Cannot duplicate folders")

        return {'FINISHED'}


class FILE_BROWSER_OT_delete_item(Operator):
    bl_idname = "file_browser.delete_item"
    bl_label = "Delete"
    bl_description = "Move selected file or folder to trash/recycle bin. Shift+Click: Permanently delete"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        file_props = scene.file_browser_props
        if file_props.file_list and 0 <= file_props.file_list_index < len(file_props.file_list):
            item = file_props.file_list[file_props.file_list_index]
            try:
                item_path = Path(item.path)

                # Check if permanent delete was requested (Shift+Click)
                if getattr(self, "_permanent_delete", False):
                    # Permanent deletion
                    if item.is_folder:
                        shutil.rmtree(str(item_path),
                                      onerror=self.handle_remove_readonly)
                    else:
                        item_path.chmod(0o666)  # Make writable just in case
                        item_path.unlink()
                    self.report({'INFO'}, f"Permanently deleted: {item.name}")
                else:
                    # Move to trash using send2trash
                    try:
                        send2trash(str(item_path))
                        self.report({'INFO'}, f"Moved to trash: {item.name}")
                    except Exception as e:
                        self.report(
                            {'WARNING'}, f"Failed to move to trash, permanently deleted instead: {e}")
                        if item.is_folder:
                            shutil.rmtree(str(item_path),
                                          onerror=self.handle_remove_readonly)
                        else:
                            item_path.chmod(0o666)
                            item_path.unlink()

                bpy.ops.file_browser.refresh_list()

            except Exception as e:
                self.report({'ERROR'}, f"Failed to delete: {str(e)}")
        return {'FINISHED'}

    def invoke(self, context, event):
        self._permanent_delete = event.shift

        if event.shift:
            return context.window_manager.invoke_confirm(
                self, event,
                message="Permanently delete? This cannot be undone!"
            )
        else:
            return context.window_manager.invoke_confirm(self, event)

    @staticmethod
    def handle_remove_readonly(func, path, exc):
        import stat
        path = Path(path)
        try:
            path.chmod(stat.S_IWRITE)
            func(str(path))
        except Exception as e:
            print(f"Failed to forcibly delete {path}: {e}")


class FILE_BROWSER_OT_move_item(bpy.types.Operator):
    bl_idname = "file.move_file_or_folder"
    bl_label = "Move File or Folder"
    bl_description = "Move the selected file or folder to the chosen directory"

    source_path: bpy.props.StringProperty(subtype="FILE_PATH")
    destination_dir: bpy.props.StringProperty(subtype="DIR_PATH")

    def execute(self, context):
        import shutil

        src = Path(self.source_path)
        dst_dir = Path(self.destination_dir)

        if not src.exists():
            self.report({'ERROR'}, "Source path does not exist")
            return {'CANCELLED'}

        if not dst_dir.exists():
            self.report({'ERROR'}, "Destination folder does not exist")
            return {'CANCELLED'}

        dst = dst_dir / src.name
        if dst.exists():
            self.report({'ERROR'}, f"Destination already contains: {dst.name}")
            return {'CANCELLED'}

        try:
            shutil.move(str(src), str(dst))
            self.report({'INFO'}, f"Moved to {dst}")
            bpy.ops.file_browser.refresh_list()  # Refresh the file list
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Move failed: {e}")
            return {'CANCELLED'}


class FILE_BROWSER_OT_set_active_root(bpy.types.Operator):
    bl_idname = "file_browser.set_active_root"
    bl_label = "Set Active Root Directory"
    bl_description = "Set the active root directory from the available paths"

    path: StringProperty()

    def execute(self, context):
        file_props = context.scene.file_browser_props
        file_props.active_root_path = self.path
        file_props.root_path = self.path
        bpy.ops.file_browser.refresh_list('INVOKE_DEFAULT')
        return {'FINISHED'}


# -------------------------------------------------------------
#                            UI
# -------------------------------------------------------------


# Main draw method
def draw_file_browser(layout, context):
    file_props = context.scene.file_browser_props
    prefs = bpy.context.preferences.addons[__package__].preferences

    header = layout.row(align=True)

    show_select_button = not prefs.auto_detect_root or file_props.auto_detection_failed

    if show_select_button:
        folder_name = Path(
            file_props.root_path).name if file_props.root_path else "Select Root"
        sub = header.row(align=True)
        sub.operator("file_browser.select_root_folder",
                     text=folder_name, icon='FILE_FOLDER')
        if len(file_props.root_paths) > 1:
            sub.menu("FILE_BROWSER_MT_select_root_path",
                     icon='DOWNARROW_HLT', text="")
    else:
        if file_props.root_path:
            folder_name = Path(file_props.root_path).name
            header.label(text=folder_name, icon='FILE_FOLDER_LARGE')
        else:
            header.label(text="No root detected", icon='ERROR')

    layout.separator(factor=0.1)

    if prefs.show_search_bar:
        # Search bar
        search_row = layout.row(align=True)
        search_row.prop(file_props, "search_term", text="", icon='VIEWZOOM')
        layout.separator(factor=0.1)

    # Determine dynamic row count based on file count
    if file_props.root_path and Path(file_props.root_path).is_dir() and prefs.enable_dynamic_popup_height:
        try:
            entries = list(Path(file_props.root_path).iterdir())
            file_count = len(
                [f for f in entries if not f.name.startswith('.')])
            dynamic_rows = max(8, min(file_count, 20))
        except Exception:
            dynamic_rows = 8
    else:
        dynamic_rows = 8

    # File list
    if file_props.file_list:
        row = layout.row()
        row.template_list("FILE_BROWSER_UL_items", "", file_props, "file_list",
                          file_props, "file_list_index", rows=dynamic_rows)
        col = row.column(align=True)
        col.operator("file_browser.create_new_file",
                     text="", icon="FILE_NEW")
        col.operator("file_browser.create_folder", text="", icon="NEWFOLDER")
        col.separator()
        col.operator("file_browser.refresh_list", text="", icon='FILE_REFRESH')
        col.separator()
        col.menu("FILE_BROWSER_MT_preferences_menu",
                 icon='DOWNARROW_HLT', text="")

    else:
        if prefs.auto_detect_root and file_props.auto_detection_failed:
            layout.label(
                text="Auto-detection failed. Select root folder manually.", icon='ERROR')
        else:
            layout.label(
                text="No files found. Select a root folder first.", icon='INFO')


# Panel for displaying in properties
class FILE_BROWSER_PT_browser_panel(Panel):
    bl_label = "File Browser"
    bl_idname = "FILE_BROWSER_PT_browser_panel"
    bl_space_type = 'TEXT_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Files"

    def draw(self, context):
        draw_file_browser(self.layout, context)


# Operator to show popup
class FILE_BROWSER_OT_show_popup(Operator):
    bl_idname = "file_browser.show_popup"
    bl_label = "File Browser"
    bl_description = "Show file browser popup"
    bl_options = {'REGISTER'}

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        detect_and_set_root_folder(context)

        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context):
        draw_file_browser(self.layout, context)


# -------------------------------------------------------------
#                             PREFERENCES
# -------------------------------------------------------------


# Addon Preferences
class FILE_BROWSER_AddonPreferences(AddonPreferences):
    bl_idname = __package__

    auto_detect_root: BoolProperty(
        name="Auto Detect Root Folder",
        description="Automatically detect addon/project root folder based on current text file",
        default=False,
        update=update_root_dir
    )

    use_custom_icons: BoolProperty(
        name="Use Custom Icons",
        description="Enable custom icons for file types in the browser",
        default=False,
    )

    show_search_bar: BoolProperty(
        name="Show Search Bar",
        description="Show or hide the file browser search bar",
        default=True,
    )
    default_root_dir: StringProperty(
        name="Default Root Folder",
        description="Fallback root folder if auto-detection is disabled or fails",
        subtype='DIR_PATH',
        default=""
    )
    enable_dynamic_popup_height: BoolProperty(
        name="Dynamic Popup Height",
        description="Adjust file list height dynamically based on file count",
        default=True,
    )

    template_dir: StringProperty(
        name="Custom Template Directory",
        subtype='DIR_PATH',
        description="Optional path to custom script templates",
        update=refresh_script_template_cache
    )

    def draw(self, context):
        layout = self.layout

        # General Settings
        box_general = layout.box()
        box_general.label(text="General Settings")
        box_general.prop(self, "auto_detect_root")
        box_general.prop(self, "default_root_dir")

        # Appearance Settings
        box_ui = layout.box()
        box_ui.label(text="Appearance")
        box_ui.prop(self, "use_custom_icons")
        box_ui.prop(self, "show_search_bar")
        box_ui.prop(self, "enable_dynamic_popup_height")

        # Template Settings
        box_templates = layout.box()
        box_templates.label(text="Script Templates")
        box_templates.prop(self, "template_dir")


# Registration
classes = (
    FILE_BROWSER_PG_item,
    FILE_BROWSER_PG_properties,
    FILE_BROWSER_UL_items,
    FILE_BROWSER_MT_move_to_menu,
    FILE_BROWSER_MT_file_context_menu,
    FILE_BROWSER_MT_external,
    FILE_BROWSER_MT_select_root_path,
    FILE_BROWSER_MT_preferences_menu,
    FILE_BROWSER_OT_set_root_directory,
    FILE_BROWSER_OT_refresh_list,
    FILE_BROWSER_OT_toggle_folder,
    FILE_BROWSER_OT_create_new_file,
    FILE_BROWSER_OT_create_folder,
    FILE_BROWSER_OT_open_file,
    FILE_BROWSER_OT_rename_item,
    FILE_BROWSER_OT_duplicate_file,
    FILE_BROWSER_OT_delete_item,
    FILE_BROWSER_OT_move_item,
    FILE_BROWSER_OT_set_active_root,
    FILE_BROWSER_PT_browser_panel,
    FILE_BROWSER_OT_show_popup,
    FILE_BROWSER_AddonPreferences,
)

# Keymap storage
addon_keymaps = []


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.file_browser_props = bpy.props.PointerProperty(
        type=FILE_BROWSER_PG_properties)

    # Add keymap
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name='Text', space_type='TEXT_EDITOR')
        kmi = km.keymap_items.new(
            "file_browser.show_popup", type='F', value='PRESS', alt=True)
        addon_keymaps.append((km, kmi))

    load_icons.load_custom_icons()


def unregister():
    load_icons.unload_custom_icons()

    # Remove keymap
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.file_browser_props


if __name__ == "__main__":
    register()
