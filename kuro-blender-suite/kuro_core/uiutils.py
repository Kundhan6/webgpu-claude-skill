"""Panel helpers, icon management, and error dialogs shared across add-ons."""

import traceback

import bpy


KURO_TAB = "KURO"


def kuro_panel_base(idname_suffix, label, category=None):
    """Return a Panel base class pre-wired for the shared "KURO" N-panel tab.

    Usage:
        class MATFORGE_PT_main(kuro_panel_base("matforge_main", "MatForge")):
            def draw(self, context):
                ...
    """

    class _Base(bpy.types.Panel):
        bl_space_type = "VIEW_3D"
        bl_region_type = "UI"
        bl_category = category or KURO_TAB
        bl_label = label
        bl_idname = f"KURO_PT_{idname_suffix}"

    return _Base


def report_exception(operator, logger, addon_id, user_message=None):
    """Call from an operator's `except Exception as e:` block.

    Logs the full traceback (never lost, per ground rule #6) and reports a
    short, human-readable message to the Blender UI — never a raw
    exception. Returns {'CANCELLED'} so callers can `return
    report_exception(...)` directly.
    """
    tb = traceback.format_exc()
    logger.error(f"[{addon_id}] {tb}")
    message = user_message or "Something went wrong — see the log for details."
    operator.report({"ERROR"}, message)
    return {"CANCELLED"}


def draw_error_box(layout, message, icon="ERROR"):
    """Draw a wrapped warning/error box inline in a panel (for persistent,
    non-modal error states like 'N materials could not be processed')."""
    box = layout.box()
    col = box.column(align=True)
    for i, line in enumerate(message.split("\n")):
        col.label(text=line, icon=icon if i == 0 else "NONE")


def confirm_popup(context, title, message, execute_op_idname, **op_props):
    """Show a confirmation popup before a destructive-feeling action (e.g.
    'Remove All StormKit Data'). The operator named by `execute_op_idname`
    is invoked with `op_props` when the user confirms."""

    def draw(self, _context):
        for line in message.split("\n"):
            self.layout.label(text=line)

    context.window_manager.popup_menu(draw, title=title, icon="QUESTION")
