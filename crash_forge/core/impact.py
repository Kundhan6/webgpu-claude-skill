"""Impact frame + vector from a baked transform track (§8.5). No bpy import.

This replaces v1's per-frame BVH overlap test entirely. Because the
rigid body sim is already baked to keyframes by the time this runs
(§2.1), the whole analysis is offline and exact — there is no tunneling
risk, and it's fully unit-testable against synthetic speed curves with
no Blender involved.

    speed[f]  = |p[f] - p[f-1]| * fps
    decel[f]  = speed[f-1] - speed[f]
    impact_frame = argmax(decel) over frames where speed[f-1] > 0.5 * max(speed)
    impact_vector = normalize(p[impact_frame-1] - p[impact_frame-2])
    impact_speed  = speed[impact_frame-1]

Every exit path is a sentinel (None from detect_impact, or a zero vector
from _impact_vector) — nothing here raises on malformed or edge-case
input. A bad frame index reads through Python's negative-index
wraparound as silently-wrong data, not a crash; sentinels are the only
way to make "nothing to report" distinguishable from "garbage".
"""
import math
from dataclasses import dataclass
from typing import Optional, Sequence

from . import tuning


@dataclass(frozen=True)
class ImpactResult:
    frame: int
    vector: tuple
    speed: float


def _sub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def _length(v):
    return math.sqrt(sum(c * c for c in v))


def _normalize(v):
    length = _length(v)
    if length == 0:
        return (0.0, 0.0, 0.0)
    return tuple(c / length for c in v)


def _impact_vector(positions, impact_index: int) -> tuple:
    """The pre-impact direction vector, or a (0.0, 0.0, 0.0) sentinel if
    there isn't enough history to compute one safely.

    `positions[impact_index - 2]` underflows for impact_index < 2 — not
    with an exception (Python's negative-index wraparound silently reads
    from the *end* of the list instead), which is worse than a crash: it
    returns a plausible-looking but meaningless vector instead of
    signalling anything went wrong. This check is independent of
    detect_impact's V11 boundary rejection (which today happens to
    already exclude impact_index < 2, since its 5-frame margin is wider)
    — deliberately not relying on that: if V11's margin ever changed,
    this still has to hold on its own.
    """
    if impact_index < 2:
        return (0.0, 0.0, 0.0)
    return _normalize(_sub(positions[impact_index - 1], positions[impact_index - 2]))


def detect_impact(samples: Sequence[tuple], fps: float) -> Optional[ImpactResult]:
    """`samples`: chronologically ordered (frame, position) pairs for the
    chassis, one per baked frame, evenly spaced. Returns None if no
    impact is detected (too few samples, the car never really moves, or
    V11's sanity check rejects the candidate frame — see below); callers
    should treat None as "stop and report", never as "assume frame 0".
    """
    samples = list(samples)
    if len(samples) < 3 or fps <= 0:
        return None

    frames = [f for f, _ in samples]
    positions = [p for _, p in samples]

    speed = [0.0]  # speed[0] is undefined (no p[-1]); kept as a placeholder for index alignment
    for i in range(1, len(positions)):
        speed.append(_length(_sub(positions[i], positions[i - 1])) * fps)

    max_speed = max(speed)
    # Not a bare `<= 0`: tiny positive floating-point noise (not exactly
    # 0.0) on an essentially-stationary chassis would otherwise let the
    # 0.5×max_speed candidate threshold admit frames, and the epsilon
    # below — which scales *with* max_speed — shrink to the point that
    # the same noise clears it too. An absolute floor closes both gaps.
    if max_speed <= tuning.IMPACT_MIN_MAX_SPEED:
        return None  # the car never moved at all

    decel = [0.0] * len(speed)
    for i in range(1, len(speed)):
        decel[i] = speed[i - 1] - speed[i]

    threshold = 0.5 * max_speed  # §8.5's literal formula
    candidate_indices = [i for i in range(1, len(speed)) if speed[i - 1] > threshold]
    if not candidate_indices:
        return None

    impact_index = max(candidate_indices, key=lambda i: decel[i])
    epsilon = tuning.IMPACT_EPSILON_FACTOR * max_speed
    if decel[impact_index] <= epsilon:
        return None  # never actually decelerating — no real impact happened

    # §13 requires "gradual deceleration with no wall" to NOT be reported
    # as an impact. §8.5's argmax formula alone can't tell a wall (a sharp
    # 1-2 frame spike) from smooth braking (many frames of similar, small
    # decel) — the argmax picks *some* frame either way. A real wall
    # impact's peak decel is dramatically larger than the surrounding
    # deceleration; gradual braking's isn't.
    other_candidates = [i for i in candidate_indices if i != impact_index]
    if other_candidates:
        mean_other_decel = sum(decel[i] for i in other_candidates) / len(other_candidates)
        if mean_other_decel > 0 and decel[impact_index] < tuning.IMPACT_SPIKE_FACTOR * mean_other_decel:
            return None  # deceleration is too gradual/uniform to be a real wall impact

    # V11 (§11): a candidate within 5 frames of either end of the range
    # means the collision probably never happened, or happened
    # instantly/off-camera — refuse rather than report a frame nobody can
    # verify against the viewport.
    if impact_index < 5 or impact_index > len(speed) - 1 - 5:
        return None

    vector = _impact_vector(positions, impact_index)
    impact_speed = speed[impact_index - 1]

    return ImpactResult(frame=frames[impact_index], vector=vector, speed=impact_speed)
