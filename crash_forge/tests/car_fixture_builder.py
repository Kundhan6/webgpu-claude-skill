"""Parametric synthetic-car builder for the §13 golden fixtures (sedan,
SUV, van, badly-named). Not a test module itself (no test_ prefix, so
pytest.ini's `python_files = test_*.py` never collects it) — it only
generates the JSON under tests/fixtures/, which test_classify.py and
test_wheels.py then load.

Layout convention: forward axis = X, lateral = Y, vertical = Z, ground =
Z=0. Proportions are tuned by hand against core/classify.py's thresholds
(documented there) so each fixture actually classifies the way a real car
of that shape should — this is deliberately more realistic than a plain
box-with-wheels: hood/boot sit at deck height, well below the roofline,
because that's what keeps them from being mistaken for glass under the
§12.4 priority-3 fallback (see GLASS_FALLBACK_HIGH_Z's docstring).
"""
import json
from pathlib import Path

from crash_forge.core.classify import PartDescriptor

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def make_car(hl_body=2.0, hw_body=0.9, wheel_radius=0.35, name_prefix="", name_fn=None):
    """Build one synthetic car's PartDescriptor list.

    `name_fn(default_suffix: str, index: int) -> str` overrides part
    naming (used for the badly-named fixture, which needs generic
    `Cube.0NN` names instead of semantic ones) while keeping the same
    geometry — proving classification is geometry-driven, not name-driven.
    """
    parts = []
    counter = [0]

    def p(suffix, bmin, bmax, **kw):
        name = name_fn(suffix, counter[0]) if name_fn else f"{name_prefix}{suffix}"
        counter[0] += 1
        c = tuple((bmin[i] + bmax[i]) / 2.0 for i in range(3))
        parts.append(PartDescriptor(
            name=name, bbox_min=bmin, bbox_max=bmax, centroid=c,
            vert_count=kw.get("vert_count", 500),
            material_names=kw.get("material_names", ()),
            max_transmission=kw.get("max_transmission", 0.0),
            is_planar=kw.get("is_planar", False),
        ))

    body_z0, body_z1 = 0.4, 1.6
    p("Body", (-hl_body, -hw_body, body_z0), (hl_body, hw_body, body_z1), vert_count=6000)

    wr = wheel_radius
    wx, wy = hl_body * 0.8, hw_body * 1.05
    wheel_positions = {"Wheel_FL": (wx, -wy), "Wheel_FR": (wx, wy), "Wheel_RL": (-wx, -wy), "Wheel_RR": (-wx, wy)}
    for suffix, (cx, cy) in wheel_positions.items():
        p(suffix, (cx - wr, cy - 0.1, 0.0), (cx + wr, cy + 0.1, wr * 2), vert_count=800)

    # Deck (hood/boot): a thin slab below the cabin roofline, not at it —
    # see module docstring.
    deck_z0, deck_z1 = 1.15, 1.25
    p("Hood", (0.25 * hl_body, -0.95 * hw_body, deck_z0), (0.8 * hl_body, 0.95 * hw_body, deck_z1), is_planar=True)
    p("Boot", (-0.8 * hl_body, -0.95 * hw_body, deck_z0), (-0.25 * hl_body, 0.95 * hw_body, deck_z1), is_planar=True)

    p("Bumper_F", (hl_body * 1.02, -hw_body, 0.3), (hl_body * 1.1, hw_body, 0.5))
    p("Bumper_R", (-hl_body * 1.1, -hw_body, 0.3), (-hl_body * 1.02, hw_body, 0.5))

    door_z0, door_z1 = 0.6, 1.4
    p("Door_L", (-0.5 * hl_body, -1.02 * hw_body, door_z0), (0.5 * hl_body, -0.94 * hw_body, door_z1), is_planar=True)
    p("Door_R", (-0.5 * hl_body, 0.94 * hw_body, door_z0), (0.5 * hl_body, 1.02 * hw_body, door_z1), is_planar=True)

    # Glass: raked, spanning from just above the deck up past the roofline.
    p("Glass_Windshield", (0.78 * hl_body, -0.85 * hw_body, deck_z1), (0.98 * hl_body, 0.85 * hw_body, body_z1 + 0.25),
      max_transmission=0.9, is_planar=True)
    p("Glass_Rear", (-0.98 * hl_body, -0.85 * hw_body, deck_z1), (-0.78 * hl_body, 0.85 * hw_body, body_z1 + 0.2),
      max_transmission=0.9, is_planar=True)

    return parts


def to_json(parts):
    return [
        {
            "name": p.name,
            "bbox_min": list(p.bbox_min),
            "bbox_max": list(p.bbox_max),
            "centroid": list(p.centroid),
            "vert_count": p.vert_count,
            "material_names": list(p.material_names),
            "max_transmission": p.max_transmission,
            "is_planar": p.is_planar,
        }
        for p in parts
    ]


def from_json(data):
    return [
        PartDescriptor(
            name=d["name"], bbox_min=tuple(d["bbox_min"]), bbox_max=tuple(d["bbox_max"]),
            centroid=tuple(d["centroid"]), vert_count=d["vert_count"],
            material_names=tuple(d.get("material_names", ())),
            max_transmission=d.get("max_transmission", 0.0), is_planar=d.get("is_planar", False),
        )
        for d in data
    ]


def load_fixture(name):
    with open(FIXTURES_DIR / f"{name}.json") as f:
        return from_json(json.load(f))


def _write_fixtures():
    FIXTURES_DIR.mkdir(exist_ok=True)

    sedan = make_car(hl_body=2.0, hw_body=0.9, wheel_radius=0.35)
    suv = make_car(hl_body=2.3, hw_body=1.05, wheel_radius=0.42)
    van = make_car(hl_body=2.8, hw_body=0.95, wheel_radius=0.38)

    def cube_name(suffix, index):
        return f"Cube.{index:03d}"

    badly_named = make_car(hl_body=2.0, hw_body=0.9, wheel_radius=0.35, name_fn=cube_name)

    for filename, parts in (
        ("sedan", sedan), ("suv", suv), ("van", van), ("badly_named", badly_named),
    ):
        with open(FIXTURES_DIR / f"{filename}.json", "w") as f:
            json.dump(to_json(parts), f, indent=2)


if __name__ == "__main__":
    _write_fixtures()
    print(f"Wrote fixtures to {FIXTURES_DIR}")
