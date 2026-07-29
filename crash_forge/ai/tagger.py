"""Claude-powered part tagging.

Sends every uncertain part in ONE batched request and gets structured JSON
back. Uses the official `anthropic` SDK when it is importable, and falls
back to urllib otherwise — Blender ships its own Python and the SDK is not
installed there by default, so the addon cannot assume it is present.
`Install Claude SDK` in the addon preferences pip-installs it into Blender's
interpreter; until then the urllib path keeps the feature working.

Every function here is network-blocking. Call from a worker thread, never
from Blender's main thread.
"""

import json
import urllib.error
import urllib.request

MODEL = "claude-opus-5"
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
MAX_TOKENS = 16000
TIMEOUT_SECONDS = 120

ROLES = ('RIGID', 'DEFORM', 'FRACTURE', 'DETACH', 'PASSIVE')
MATERIAL_CLASSES = (
    'STEEL', 'GLASS', 'RUBBER', 'PLASTIC', 'TRIM_CHROME', 'CONCRETE', 'INTERIOR_FABRIC',
)

SYSTEM_PROMPT = """You tag 3D vehicle parts for a Blender crash-simulation addon.

For each part you are given its object name, bounding-box dimensions in metres, and its material slot names. Assign exactly one role and one material class.

Roles:
- RIGID: solid part that keeps its shape and stays attached (wheels, engine, brakes, seats)
- DEFORM: thin sheet metal that crumples on impact (hood, doors, roof, fenders, quarter panels)
- FRACTURE: brittle, shatters into fragments (windshield, windows, headlight lenses)
- DETACH: breaks free from the vehicle on a hard hit (bumper, mirror, trim, badge, spoiler)
- PASSIVE: structural core that never moves independently (chassis, frame, floor pan)

Material classes: STEEL, GLASS, RUBBER, PLASTIC, TRIM_CHROME, CONCRETE, INTERIOR_FABRIC.

Judge from the name first, then the dimensions. A large flat thin part is almost always a body panel (DEFORM). A small thin part on the outside is usually trim (DETACH). If a name is ambiguous, pick the most common real-world answer for that part on a passenger car. Return every part you were given, exactly once, with its name unchanged."""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "parts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "role": {"type": "string", "enum": list(ROLES)},
                    "material_class": {"type": "string", "enum": list(MATERIAL_CLASSES)},
                },
                "required": ["name", "role", "material_class"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["parts"],
    "additionalProperties": False,
}


def build_part_payload(objects):
    """Serialize Blender objects into the compact form sent to the model."""
    payload = []
    for obj in objects:
        materials = [m.name for m in obj.data.materials if m is not None] if obj.data.materials else []
        payload.append({
            "name": obj.name,
            "dimensions_m": [round(float(d), 4) for d in obj.dimensions],
            "materials": materials,
        })
    return payload


def _request_body(parts):
    return {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": [{
            "role": "user",
            "content": "Tag these vehicle parts:\n\n" + json.dumps(parts, indent=1),
        }],
        "output_config": {
            "effort": "low",
            "format": {"type": "json_schema", "schema": RESPONSE_SCHEMA},
        },
    }


def _parse_tagged(text):
    data = json.loads(text)
    out = {}
    for entry in data.get("parts", []):
        name = entry.get("name")
        role = entry.get("role")
        material_class = entry.get("material_class")
        if name and role in ROLES and material_class in MATERIAL_CLASSES:
            out[name] = (role, material_class)
    return out


def _via_sdk(api_key, parts):
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    body = _request_body(parts)
    response = client.messages.create(
        model=body["model"],
        max_tokens=body["max_tokens"],
        system=body["system"],
        messages=body["messages"],
        output_config=body["output_config"],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to tag these parts.")
    text = next((b.text for b in response.content if b.type == "text"), "")
    if not text:
        raise RuntimeError("Claude returned no tagging output.")
    return _parse_tagged(text)


def _via_urllib(api_key, parts):
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(_request_body(parts)).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Claude API error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach the Claude API: {exc.reason}") from exc

    if payload.get("stop_reason") == "refusal":
        raise RuntimeError("Claude declined to tag these parts.")
    text = next(
        (block.get("text", "") for block in payload.get("content", []) if block.get("type") == "text"),
        "",
    )
    if not text:
        raise RuntimeError("Claude returned no tagging output.")
    return _parse_tagged(text)


def tag_parts(api_key, parts):
    """Tag `parts` via Claude. Returns {object_name: (role, material_class)}.

    Blocking. Raises RuntimeError with a user-readable message on failure.
    """
    if not api_key:
        raise RuntimeError("No Claude API key set in Crash Forge preferences.")
    if not parts:
        return {}

    try:
        import anthropic  # noqa: F401
    except ImportError:
        return _via_urllib(api_key, parts)

    try:
        return _via_sdk(api_key, parts)
    except RuntimeError:
        raise
    except Exception as exc:
        # SDK present but unhappy (version skew, transport). urllib is the
        # same endpoint with no dependency surface — try it before failing.
        try:
            return _via_urllib(api_key, parts)
        except RuntimeError:
            raise RuntimeError(f"Claude tagging failed: {exc}") from exc
