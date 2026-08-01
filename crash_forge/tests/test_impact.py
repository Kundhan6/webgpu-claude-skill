"""Tier A (§13) — pure core, no bpy.

Synthetic speed curves: clean impact, no impact, impact on frame 1,
gradual deceleration with no wall. Assert frame and stop conditions.
"""
from crash_forge.core.impact import detect_impact


def _constant_motion_positions(n_frames, speed_per_frame):
    return [(i * speed_per_frame, 0.0, 0.0) for i in range(n_frames)]


def test_clean_impact_detected_at_the_right_frame():
    fps = 24.0
    per_frame = 20.0 / fps  # 20 units/sec
    positions = _constant_motion_positions(30, per_frame)  # frames 0..29, constant 20 u/s
    # sudden stop at frame 30, then stays stopped through frame 60
    stop_position = (positions[-1][0] + 0.01, 0.0, 0.0)
    positions.append(stop_position)
    positions += [stop_position] * 30  # frames 31..60

    samples = list(enumerate(positions))
    result = detect_impact(samples, fps=fps)

    assert result is not None
    assert result.frame == 30
    assert result.vector == (1.0, 0.0, 0.0)
    assert abs(result.speed - 20.0) < 1e-6


def test_no_impact_when_speed_never_changes():
    fps = 24.0
    positions = _constant_motion_positions(40, 20.0 / fps)
    samples = list(enumerate(positions))

    assert detect_impact(samples, fps=fps) is None


def test_no_impact_when_car_never_moves():
    fps = 24.0
    samples = [(f, (0.0, 0.0, 0.0)) for f in range(30)]

    assert detect_impact(samples, fps=fps) is None


def test_impact_on_frame_1_is_rejected_by_the_boundary_check():
    """V11 (§11): a candidate within 5 frames of either end of the range
    means the collision probably never happened, or happened before the
    bake could capture a clean pre-impact vector — refuse rather than
    report a frame nobody can verify against the viewport."""
    fps = 24.0
    per_frame = 20.0 / fps
    positions = [(0.0, 0.0, 0.0), (per_frame, 0.0, 0.0)]
    stop_position = (positions[-1][0] + 0.01, 0.0, 0.0)
    positions.append(stop_position)
    positions += [stop_position] * 27  # total 30 frames, crash at index 2

    samples = list(enumerate(positions))
    assert detect_impact(samples, fps=fps) is None


def test_gradual_deceleration_with_no_wall_is_not_reported_as_impact():
    """Smooth braking (many frames of similar small decel) must not be
    mistaken for a wall impact (one frame of dramatically larger decel) —
    §8.5's raw argmax can't tell them apart on its own; the spike-ratio
    check in detect_impact is what does."""
    fps = 24.0
    speeds = [max(0.0, 30.0 - i * 0.8) for i in range(40)]  # smooth linear braking to a stop
    positions = [(0.0, 0.0, 0.0)]
    for s in speeds:
        last = positions[-1]
        positions.append((last[0] + s / fps, last[1], last[2]))

    samples = list(enumerate(positions))
    assert detect_impact(samples, fps=fps) is None


def test_too_few_samples_returns_none():
    assert detect_impact([(0, (0, 0, 0)), (1, (1, 0, 0))], fps=24.0) is None


def test_zero_fps_returns_none():
    samples = [(f, (float(f), 0.0, 0.0)) for f in range(30)]
    assert detect_impact(samples, fps=0.0) is None
