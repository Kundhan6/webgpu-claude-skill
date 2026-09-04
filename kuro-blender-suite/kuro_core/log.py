"""Per-add-on file + console logging.

Ground rule #6: no silent failures. Every operator logs the full traceback
here before reporting a short human-readable message to the UI.
"""

import logging
import os
import sys

import bpy

_loggers = {}


def get_logger(addon_id):
    """Return (creating if needed) a logger for `addon_id` that writes to
    both stdout and a per-add-on log file under the user's Blender config
    directory (so studios can grab logs without hunting for stdout)."""
    if addon_id in _loggers:
        return _loggers[addon_id]

    logger = logging.getLogger(f"kuro.{addon_id}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if not logger.handlers:
        fmt = logging.Formatter(
            "[%(asctime)s] %(name)s %(levelname)s: %(message)s", "%H:%M:%S"
        )

        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        console.setLevel(logging.INFO)
        logger.addHandler(console)

        try:
            log_dir = os.path.join(
                bpy.utils.user_resource("SCRIPTS"), "kuro_logs"
            )
            os.makedirs(log_dir, exist_ok=True)
            file_handler = logging.FileHandler(
                os.path.join(log_dir, f"{addon_id}.log")
            )
            file_handler.setFormatter(fmt)
            file_handler.setLevel(logging.DEBUG)
            logger.addHandler(file_handler)
        except Exception:
            # Logging to disk is best-effort; console logging still works.
            logger.warning("Could not open log file, console-only logging.")

    _loggers[addon_id] = logger
    return logger
