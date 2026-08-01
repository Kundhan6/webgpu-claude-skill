"""CF_ naming convention and the cf_generated tag contract (§7.1). No bpy import.

Deliberately minimal for now: only what CF_Reset (M2) needs. The full
name-generator/parser set for every constraint kind (hinge, motor, break,
no-collide pair — §7.1's full table) is M3 scope, once core/pairs.py and
core/classify.py exist to feed it from real part data. Building it now
would be exactly the "jump ahead to the interesting physics" the working
rules say not to do.
"""

CF_PREFIX = "CF_"
CF_GENERATED_KEY = "cf_generated"
CF_STAGE_KEY = "cf_stage"


def is_cf_name(name: str) -> bool:
    return name.startswith(CF_PREFIX)


def cf_name(suffix: str) -> str:
    return f"{CF_PREFIX}{suffix}"
