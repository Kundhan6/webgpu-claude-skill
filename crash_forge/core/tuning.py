"""Every tuned-not-verified numeric constant used by core/, in one place.

TUNED AGAINST SYNTHETIC FIXTURES, NOT VERIFIED. Each constant below was
picked to make classify.py/impact.py/density.py/pairs.py behave
correctly against this project's own synthetic car fixtures
(tests/car_fixture_builder.py) — none of them come from a real car, and
none of them are given an exact value anywhere in the spec (§12 only
gives qualitative rules: "low Z", "lateral extreme", "a small margin").
When a real car (tools/dump_car.py's output) disagrees with these
values, retune here — one file, not a hunt through five modules.

Constants that ARE given exact values in the spec (§12.2's 15% size
tolerance, §11 V11's 5-frame boundary, §8.5's 0.5×max_speed threshold,
§12.5's ~200k-vert ceiling) are deliberately NOT here — they're spec-given,
not tuned, and belong next to the code quoting the section that gives
them. Retuning those means the spec changed, not that reality disagreed
with a guess.
"""

# --- core/classify.py ------------------------------------------------------

# §12.1 step 4: "low Z" / normalised-Z bands for BUMPER_F/R vs HOOD/BOOT.
CLASSIFY_LOW_Z = 0.35
CLASSIFY_HIGH_Z = 0.6

# §12.1 step 4: "forward extreme" / "lateral extreme (high |x|)" cutoffs.
CLASSIFY_FORWARD_EXTREME = 0.8
CLASSIFY_LATERAL_EXTREME = 0.75

# Not "half the car", the rear *extremity* — a boot lid is a shape fact
# (it sits close to the very back of the car), not a curve fitted to one
# car. §12.1 step 4 only says "rear half, high Z, broad and flat", which
# a real Crown Victoria's roof-mounted light bar also satisfied purely by
# geometric coincidence (high, planar, thin-vertical, and a bare 46.5% of
# the way forward — comfortably inside "rear half"). Requiring the rear
# quarter separates a real boot lid (this car's own glass/interior data
# puts the cabin, let alone the boot behind it, well toward the rear) by
# a wide margin, not a coin flip: every synthetic fixture's own Boot part
# sits at fwd=0.2375 (verified numerically, not assumed), comfortably
# inside 0.25; the light bar's fwd=0.465 is nowhere close.
CLASSIFY_BOOT_REAR_EXTREME = 0.25

# §12.2: score floor a wheel candidate must clear before being considered
# plausible at all (roundness × bottom-third weighting).
CLASSIFY_WHEEL_SCORE_FLOOR = 0.5

# §12.4 priority-3 fallback ("thin planar geometry in the upper half of
# the car bbox"): normalised-Z cutoff, against the *whole car's* bbox.
# Doubly tuned — even "upper half" (0.5) was already an interpretation of
# the spec's qualitative wording, and 0.5 produced false positives
# against hood/boot/door panels in this project's own fixtures (see
# tests/test_classify.py), so it was raised further to 0.75.
CLASSIFY_GLASS_FALLBACK_HIGH_Z = 0.75

# --- core/impact.py ---------------------------------------------------------

# Not in §8.5 at all — added to distinguish a real wall impact (one sharp
# frame of decel) from gradual braking (many frames of similar decel),
# which §13's test plan requires detect_impact to tell apart and the raw
# argmax formula alone cannot.
IMPACT_SPIKE_FACTOR = 3.0

# Relative floor below which a frame's deceleration is treated as
# floating-point noise, not a real event — constant-velocity data (real
# baked or synthetic) accumulates rounding error that can leave a frame's
# decel marginally positive with nothing behind it.
IMPACT_EPSILON_FACTOR = 1e-6

# Absolute floor for max(speed) itself: below this, the chassis is
# treated as never having moved at all, same as exactly zero. Guards
# against tiny positive floating-point noise (not exactly 0.0) letting
# the 0.5×max_speed candidate threshold admit frames and IMPACT_EPSILON_FACTOR
# (which scales *with* max_speed) shrink to the point that noise alone
# clears it.
IMPACT_MIN_MAX_SPEED = 1e-9

# --- core/density.py ---------------------------------------------------------

# Order-of-magnitude estimate only: a voxel remesh's output vertex count
# scales roughly with remeshed surface area ÷ voxel_size², not any exact
# formula Blender documents. ~2 verts per voxel-sized surface patch.
DENSITY_ASSUMED_VERTS_PER_VOXEL_AREA = 2.0

# --- core/pairs.py ------------------------------------------------------

# §9.4 says "a small margin" with no number and no unit. A *fixed*
# distance breaks the moment the car is scaled (a giant truck needs a
# proportionally larger touch-margin than a toy car; one fixed constant
# either misses real neighbours on the truck or falsely merges distant
# parts on the toy) — so this is a fraction of the car's own length,
# computed fresh from whichever parts are passed in.
PAIRS_DEFAULT_MARGIN_FRACTION = 0.01
