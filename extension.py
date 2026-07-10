import bpy
import re

# --- Configuration ----------------------------------------------------

GODOT_BASE_KEY = "godot_base"
GODOT_UID_KEY = "godot_uid"
GODOT_SUFFIX_KEY = "godot_suffix"

# Matches Blender's automatic duplicate suffix: .001, .002, .010, etc.
DUP_SUFFIX_RE = re.compile(r"^(.+)\.(\d{3,})$")


# --- Core logic ---------------------------------------------------------

def extract_base_name(name):
    """Strip Blender's auto-added duplicate suffix (e.g. '.001')."""
    match = DUP_SUFFIX_RE.match(name)
    if match:
        return match.group(1)
    return name


def compute_name(base, uid, suffix):
    return f"{base}_{uid}{suffix}"


def sync_all_objects(context):
    """
    Walk every object in the file, make sure it has valid
    godot_base / godot_uid / godot_suffix custom properties, resolve
    any uid collisions (duplicated objects, appended files, manual
    property edits, etc.), and rename objects to match.

    Returns the number of objects that were renamed.
    """
    objects = list(bpy.data.objects)

    # Pass 1: collect objects that already have a uid, detect collisions.
    registry = {}       # uid -> object that "owns" it
    needs_uid = []      # objects that need a (re)assigned uid
    max_uid = 0

    for obj in objects:
        if GODOT_BASE_KEY not in obj:
            obj[GODOT_BASE_KEY] = extract_base_name(obj.name)
        if GODOT_SUFFIX_KEY not in obj:
            obj[GODOT_SUFFIX_KEY] = ""

        if GODOT_UID_KEY in obj:
            uid = obj[GODOT_UID_KEY]
            max_uid = max(max_uid, uid)
            if uid in registry:
                # Collision: two different objects share this uid.
                # This happens most often when an already-tagged object
                # gets duplicated, since custom properties are copied
                # along with it. Keep whichever object we saw first,
                # reassign a fresh uid to the rest.
                needs_uid.append(obj)
            else:
                registry[uid] = obj
        else:
            needs_uid.append(obj)

    # Pass 2: hand out fresh uids to anything that needs one.
    # Computed fresh from the current data every time, so there is no
    # stored counter that can go stale after appending another file.
    next_uid = max_uid + 1
    for obj in needs_uid:
        obj[GODOT_UID_KEY] = next_uid
        registry[next_uid] = obj
        next_uid += 1

    # Pass 3: apply the resulting name to every object.
    renamed = 0
    for obj in objects:
        base = obj[GODOT_BASE_KEY]
        uid = obj[GODOT_UID_KEY]
        suffix = obj[GODOT_SUFFIX_KEY]
        new_name = compute_name(base, uid, suffix)
        if obj.name != new_name:
            obj.name = new_name
            renamed += 1

    return renamed


def set_suffix_on_selected(context, suffix):
    """Sync the whole file, then apply `suffix` to the selected objects."""
    sync_all_objects(context)
    for obj in context.selected_objects:
        obj[GODOT_SUFFIX_KEY] = suffix
    return sync_all_objects(context)


# --- Operators -----------------------------------------------------------

class OBJECT_OT_godot_sync_all(bpy.types.Operator):
    bl_idname = "object.godot_sync_all"
    bl_label = "Sync All Godot Names"
    bl_description = (
        "Re-check every object in the file for missing or duplicated "
        "Godot IDs and rename accordingly. Run this after appending or "
        "linking objects from another file, or after duplicating "
        "already-tagged objects"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        count = sync_all_objects(context)
        self.report({'INFO'}, f"Renamed {count} object(s)")
        return {'FINISHED'}


def make_suffix_operator(idname, label, suffix):
    """Factory: build one operator class per suffix option."""

    class _Op(bpy.types.Operator):
        bl_idname = idname
        bl_label = label
        bl_options = {'REGISTER', 'UNDO'}

        def execute(self, context):
            count = set_suffix_on_selected(context, suffix)
            self.report({'INFO'}, f"Updated {count} object(s)")
            return {'FINISHED'}

    return _Op


OBJECT_OT_godot_convcolonly = make_suffix_operator(
    "object.godot_convcolonly", "Convex, hidden (-convcolonly)", "-convcolonly")
OBJECT_OT_godot_colonly = make_suffix_operator(
    "object.godot_colonly", "Trimesh, hidden (-colonly)", "-colonly")
OBJECT_OT_godot_convcol = make_suffix_operator(
    "object.godot_convcol", "Convex (-convcol)", "-convcol")
OBJECT_OT_godot_col = make_suffix_operator(
    "object.godot_col", "Trimesh (-col)", "-col")
OBJECT_OT_godot_clear_suffix = make_suffix_operator(
    "object.godot_clear_suffix", "No collision suffix", "")

SUFFIX_OPS = (
    OBJECT_OT_godot_convcolonly,
    OBJECT_OT_godot_colonly,
    OBJECT_OT_godot_convcol,
    OBJECT_OT_godot_col,
    OBJECT_OT_godot_clear_suffix,
)

CLASSES = (OBJECT_OT_godot_sync_all,) + SUFFIX_OPS


# --- UI: N-panel tab in the 3D viewport -----------------------------------

class VIEW3D_PT_godot_naming(bpy.types.Panel):
    bl_idname = "VIEW3D_PT_godot_naming"
    bl_label = "Godot Naming"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Godot"

    def draw(self, context):
        layout = self.layout
        obj = context.object

        col = layout.column(align=True)
        col.operator(OBJECT_OT_godot_sync_all.bl_idname, icon='FILE_REFRESH')

        layout.separator()
        layout.label(text="Set Collision Suffix:")
        col = layout.column(align=True)
        for cls in SUFFIX_OPS:
            col.operator(cls.bl_idname)

        layout.separator()
        box = layout.box()
        box.label(text="Active Object")
        if obj is None:
            box.label(text="No active object")
        elif GODOT_BASE_KEY not in obj:
            box.label(text="Not synced yet")
        else:
            box.label(text=f"Base: {obj[GODOT_BASE_KEY]}")
            box.label(text=f"UID: {obj[GODOT_UID_KEY]}")
            suffix = obj.get(GODOT_SUFFIX_KEY, "")
            box.label(text=f"Suffix: {suffix if suffix else '(none)'}")


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.utils.register_class(VIEW3D_PT_godot_naming)


def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_godot_naming)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
