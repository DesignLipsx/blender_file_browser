import bpy
import rna_keymap_ui


# Define your custom keymap layout grouped by functionality
KEYMAP_GROUP = [
    {
        "label": "Quick Save & Load",
        "items": [
            {
                "operator": "wm.save_mainfile",
                "type": "S", "value": "PRESS",
                "ctrl": True, "shift": False, "alt": False
            },
            {
                "operator": "wm.open_mainfile",
                "type": "O", "value": "PRESS",
                "ctrl": True, "shift": False, "alt": False
            },
        ]
    },
    {
        "label": "Pie Menu Access",
        "items": [
            {
                "operator": "wm.call_menu_pie",
                "type": "P",
                "value": "PRESS",
                "ctrl": False,
                "shift": True,
                "alt": False,
                "properties": {"name": "MYADDON_MT_custom_pie_menu"}
            }
        ]
    },
]


# Stores all added keymap entries for cleanup during unregister
keys = []


# Find and return a specific keymap item matching the operator (and prop if set)
def get_hotkey_entry_item(km, item):
    kmi_name = item["operator"]

    for i, km_item in enumerate(km.keymap_items):
        if km.keymap_items.keys()[i] == kmi_name:
            if "prop_name" in item:
                kmi_value = item["prop_name"]
                if km.keymap_items[i].properties.name == kmi_value:
                    return km_item
            return km_item
    return None


# Draw keymap items visually in the addon preferences
def draw_keymap_ui(layout, context):
    col = layout.column()
    kc = context.window_manager.keyconfigs.user

    for group in KEYMAP_GROUP:
        col.separator(factor=0.4)
        col.label(text=group["label"])
        col.separator(factor=0.2)

        km = kc.keymaps.get("Text")
        if not km:
            continue

        for item in group["items"]:
            kmi = get_hotkey_entry_item(km, item)
            if kmi:
                col.context_pointer_set("keymap", km)
                rna_keymap_ui.draw_kmi([], kc, km, kmi, col, 0)


# Register and bind all keymap entries defined in KEYMAP_GROUP
def register_keymap():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return

    for group in KEYMAP_GROUP:
        km = kc.keymaps.get("Text")
        if not km:
            km = kc.keymaps.new(name="Text", space_type='TEXT_EDITOR')

        for item in group["items"]:
            kmi = km.keymap_items.new(
                idname=item["operator"],
                type=item["type"],
                value=item["value"],
                ctrl=item.get("ctrl", False),
                shift=item.get("shift", False),
                alt=item.get("alt", False)
            )

            # Assign any additional properties, e.g., for menu operators
            if "properties" in item:
                for prop_name, prop_value in item["properties"].items():
                    setattr(kmi.properties, prop_name, prop_value)

            kmi.active = True
            keys.append((km, kmi))


# Unregister and remove all custom keymap entries
def unregister_keymap():
    for km, kmi in keys:
        km.keymap_items.remove(kmi)
    keys.clear()


def register:
    register_keymap()


def unregister:
    unregister_keymap()


# ---------------------------
# HOW TO USE THIS TEMPLATE:
# ---------------------------
# 1. Place this script in your addon folder (e.g., main root directory).
# 2. Import this script in your main `__init__.py` or related module:
#       from . import keymap
#
# 3. Call its `register()` and `unregister()` inside your addon's main register/unregister functions:
#       keymap.register()
#       keymap.unregister()
#
# 4. Modify `KEYMAP_GROUPS` to define your own hotkeys.
#
# 5. In your addon's preferences class, call:
#       draw_keymap_ui(layout, context)
#    to show the hotkey UI in the Addon Preferences panel.