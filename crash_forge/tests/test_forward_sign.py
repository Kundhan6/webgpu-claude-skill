"""Tier A (§13) — pure core, no bpy.

Regression coverage for the diagonal wheel-swap bug found on a real car
(Sketchfab Crown Victoria, M4 verification): every wheel came back
labelled as its diagonally-opposite corner (WHEEL_FL called WHEEL_RR,
etc.) — both front<->back *and* left<->right swapped together.

Root cause (confirmed by hand-tracing, not guessed): "right" is only
meaningful relative to which way the car is facing (right = forward x
up; negate forward and right negates with it). _assign_wheel_roles()
multiplied rel_forward by forward_sign but left rel_lateral's sign as a
fixed, forward_sign-independent "positive = right" convention. That
convention is only correct when forward_sign happens to be +1 — which
every synthetic fixture in this project is, by construction (all built
nose-first along positive forward), so nothing here ever exercised the
negative-sign path before. On a real car whose resolved forward_sign is
-1, the fixed convention is backwards, and because it's backwards for
every wheel simultaneously, front/back and left/right both flip at
once — the diagonal swap.

The fix couples rel_lateral to forward_sign the same way rel_forward
already is. This is provably a no-op for every existing fixture (all
forward_sign=+1, and multiplying by +1 changes nothing) — the tests here
specifically exercise the forward_sign=-1 path those fixtures never
touch.

Note on scope: the fix makes "right" track forward_sign the same way
"front" already does, using the *same baseline convention this codebase
already had* ("positive lateral = right" whenever forward_sign is +1).
That baseline was never itself derived from a strict right-hand
forward-x-up rule — it's the "arbitrary but consistently applied
convention" the code's own docstring already called it — so a rotated
version of the existing X-forward sedan fixture (same physical car,
described with Y as forward instead) is *not* guaranteed to reproduce
the same left/right labels under this fix, and isn't asserted here. What
*is* guaranteed, and is what's tested: (1) every existing forward_sign=+1
fixture is completely unaffected, and (2) for a car whose forward_sign is
correctly known to be -1, front/back and left/right both resolve
correctly and self-consistently — no more diagonal swap.
"""
from crash_forge.core.classify import (
    VERTICAL_AXIS,
    PartDescriptor,
    PartRole,
    _assign_wheel_roles,
    classify,
    detect_forward_axis,
    detect_glass_names,
    resolve_forward_sign,
)
from crash_forge.core.geometry import centroid as bbox_centroid
from crash_forge.core.geometry import union_bbox

from .car_fixture_builder import load_fixture

# --- the glass heuristic itself is degenerate on any car with rear glass --


def test_glass_at_both_ends_gives_a_mathematically_tied_forward_sign_signal():
    """A finding from building this test file, not something the
    reviewer's trace predicted: detect_forward_sign's heuristic averages
    every glass part's forward position. The sedan fixture (like almost
    any real car) has a windshield AND a rear window, roughly symmetric
    about the car's centre — Glass_Windshield sits at +1.76, Glass_Rear
    at -1.76, whole_center at 0.0. Averaging them is 0.0, an *exact* tie
    against whole_center. sign resolves to +1 only because the `>=`
    comparison defaults ties to +1 — not because the signal actually said
    anything. Every synthetic fixture happens to be built nose-first
    along +forward, so this tie-break has always silently agreed with
    the truth; it would silently agree just as often with a car built
    facing the other way. This is exactly why §12.3 step 5 treats the
    heuristic as a coin flip that must be visible and overridable, not a
    signal worth trying to tune harder."""
    parts = load_fixture("sedan")
    forward_axis = detect_forward_axis(parts)

    boxes = [(p.bbox_min, p.bbox_max) for p in parts]
    whole_min, whole_max = union_bbox(boxes)
    whole_center = bbox_centroid(whole_min, whole_max)
    glass_names = detect_glass_names(parts, whole_min, whole_max, VERTICAL_AXIS)
    glass_parts = [p for p in parts if p.name in glass_names]

    avg_glass_forward = sum(p.centroid[forward_axis] for p in glass_parts) / len(glass_parts)
    assert avg_glass_forward == whole_center[forward_axis]  # an exact tie, not a real signal

    sign, _confidence, source = resolve_forward_sign(parts, forward_axis)
    assert sign == 1  # only because the tie-break defaults there
    assert source == "auto"


# --- direct unit coverage of the reviewer's own worked numeric trace ------


def _wheel(name, forward_pos, lateral_pos):
    """A minimal wheel-shaped descriptor at a given (forward_axis=Y,
    lateral_axis=X) position, thin along X (the axle/lateral axis) —
    only the position matters for _assign_wheel_roles, which consumes
    pre-classified wheel_parts directly."""
    wr = 0.35
    return PartDescriptor(
        name=name,
        bbox_min=(lateral_pos - 0.1, forward_pos - wr, 0.0),
        bbox_max=(lateral_pos + 0.1, forward_pos + wr, wr * 2),
        centroid=(lateral_pos, forward_pos, wr),
        vert_count=800,
    )


def test_assign_wheel_roles_matches_the_reviewers_worked_trace():
    """Reproduces the exact scenario from the reviewer's trace: real nose
    at -Y (forward_sign=-1), forward_axis=Y(1), lateral_axis=X(0).
    True corners: FL=(y-,x+), FR=(y-,x-), RL=(y+,x+), RR=(y+,x-)."""

    whole_center = (0.0, 0.0, 0.0)
    fl = _wheel("fl", forward_pos=-5.0, lateral_pos=+1.0)
    fr = _wheel("fr", forward_pos=-5.0, lateral_pos=-1.0)
    rl = _wheel("rl", forward_pos=+5.0, lateral_pos=+1.0)
    rr = _wheel("rr", forward_pos=+5.0, lateral_pos=-1.0)

    roles = _assign_wheel_roles(
        [fl, fr, rl, rr], forward_axis=1, forward_sign=-1, lateral_axis=0, whole_center=whole_center,
    )

    assert roles["fl"] == PartRole.WHEEL_FL
    assert roles["fr"] == PartRole.WHEEL_FR
    assert roles["rl"] == PartRole.WHEEL_RL
    assert roles["rr"] == PartRole.WHEEL_RR


def test_assign_wheel_roles_unchanged_at_forward_sign_positive_one():
    """The fix must be a no-op for forward_sign=+1 — every existing
    synthetic fixture depends on this being true."""

    whole_center = (0.0, 0.0, 0.0)
    fl = _wheel("fl", forward_pos=+5.0, lateral_pos=-1.0)
    fr = _wheel("fr", forward_pos=+5.0, lateral_pos=+1.0)
    rl = _wheel("rl", forward_pos=-5.0, lateral_pos=-1.0)
    rr = _wheel("rr", forward_pos=-5.0, lateral_pos=+1.0)

    roles = _assign_wheel_roles(
        [fl, fr, rl, rr], forward_axis=1, forward_sign=1, lateral_axis=0, whole_center=whole_center,
    )

    assert roles["fl"] == PartRole.WHEEL_FL
    assert roles["fr"] == PartRole.WHEEL_FR
    assert roles["rl"] == PartRole.WHEEL_RL
    assert roles["rr"] == PartRole.WHEEL_RR


# --- resolve_forward_sign() / classify()'s override escape hatch ----------


def test_resolve_forward_sign_auto_matches_detect_forward_sign():
    parts = load_fixture("sedan")
    forward_axis = detect_forward_axis(parts)
    sign, confidence, source = resolve_forward_sign(parts, forward_axis)
    assert sign == 1
    assert source == "auto"
    assert confidence > 0.5


def test_resolve_forward_sign_override_bypasses_the_heuristic_entirely():
    """An override must win even when the glass heuristic would clearly
    disagree — §12.3 step 5's whole point is that a human can correct a
    wrong guess, not merely nudge it."""
    parts = load_fixture("sedan")  # glass heuristic would resolve +1
    forward_axis = detect_forward_axis(parts)

    sign, confidence, source = resolve_forward_sign(parts, forward_axis, override=-1)

    assert sign == -1
    assert confidence == 1.0
    assert source == "override"


def test_classify_forward_sign_override_changes_wheel_roles():
    """classify()'s own override parameter must actually flow through to
    wheel-role assignment, not just be accepted and ignored."""
    parts = load_fixture("sedan")
    forward_axis = detect_forward_axis(parts)

    auto_result = classify(parts, forward_axis)
    overridden_result = classify(parts, forward_axis, forward_sign_override=-1)

    assert auto_result["Wheel_FL"].role == PartRole.WHEEL_FL
    assert overridden_result["Wheel_FL"].role == PartRole.WHEEL_RR
    # An override is stated with full confidence (1.0); the glass
    # heuristic caps forward_conf at 0.8 even when it's used — different
    # numbers are expected here, not a bug.
    assert overridden_result["Wheel_FL"].confidence > auto_result["Wheel_FL"].confidence
    # forcing the "wrong" sign here is deliberately still self-consistent
    # (a clean diagonal remap of all four), not a crash or a partial mix.
    assert overridden_result["Wheel_FR"].role == PartRole.WHEEL_RL
    assert overridden_result["Wheel_RL"].role == PartRole.WHEEL_FR
    assert overridden_result["Wheel_RR"].role == PartRole.WHEEL_FL


# --- DOOR_L/DOOR_R: the identical uncoupled-convention bug, fixed on the
# same pass rather than left for a real car with doors to happen to exist


def test_assign_doors_sides_swap_together_under_a_forced_sign_not_independently():
    """_classify_remaining_part()'s DOOR_L/DOOR_R split had the exact same
    shape as the original wheel bug: `lat` was the raw normalised lateral
    coordinate with no forward_sign coupling at all. Mechanically identical
    fix, same reasoning — right only means anything relative to which way
    the car faces. A real car with doors was never available to catch this
    (M4.5's Crown Victoria has one joined body shell, no separate door
    meshes), but the bug doesn't need a real car to exist: the sedan
    fixture already has doors, and forcing forward_sign=-1 on it exercises
    the identical code path a real car with a wrong-signed forward guess
    would hit. If the sides swapped independently of each other (one
    stays, one flips) that would be the bug; a clean, self-consistent full
    swap of both together is the correct, already-established behaviour
    (matching the wheel fix)."""
    parts = load_fixture("sedan")
    forward_axis = detect_forward_axis(parts)

    auto_result = classify(parts, forward_axis)
    overridden_result = classify(parts, forward_axis, forward_sign_override=-1)

    assert auto_result["Door_L"].role == PartRole.DOOR_L
    assert auto_result["Door_R"].role == PartRole.DOOR_R
    # Both sides flip together under the forced sign — not one, not neither.
    assert overridden_result["Door_L"].role == PartRole.DOOR_R
    assert overridden_result["Door_R"].role == PartRole.DOOR_L


def test_assign_doors_unchanged_at_forward_sign_positive_one():
    """The fix must be a no-op for forward_sign=+1 — every existing
    synthetic fixture (including every one of test_classify.py's door
    assertions) depends on this being true."""
    parts = load_fixture("sedan")
    forward_axis = detect_forward_axis(parts)

    result = classify(parts, forward_axis, forward_sign_override=1)

    assert result["Door_L"].role == PartRole.DOOR_L
    assert result["Door_R"].role == PartRole.DOOR_R
