"""Tier B (§13) — stubbed bpy.

Locks in the fix for a real bug confirmed on the first Blender run: the
Stage 0 probe used to run at add-on registration, wrapped in a bare
`try/except Exception: print(...); return` that swallowed whatever it
raised — including `bpy.context._RestrictContext`'s `AttributeError` on
`.scene` access, which happens on every real registration (`bpy.context`
is a restricted proxy at that point). Registration "succeeded" while the
probe had validated nothing at all, and nothing said so.

Fixed by moving the probe off registration entirely
(`crash_forge.register()` no longer calls it) and running it lazily
instead, from `bl/probe.py::ensure_probed()`, called by each stage
operator's own `execute()` where real, unrestricted context is
guaranteed. `ensure_probed()` itself never swallows: an exception from
`run_probe()` propagates unchanged — converting that into a clean,
reported operator failure is each ops/*.py file's job (see
ops/prep.py, ops/rig.py, ops/reset.py), not this module's to hide.
"""


def test_register_does_not_call_the_stage_0_probe(stubbed_bpy):
    """The actual fix: registration used to call the probe at all (then
    swallow whatever it raised, including bpy.context._RestrictContext's
    real AttributeError). A raising fake can't distinguish old from new
    here -- the old code caught exceptions too, that was the bug -- so
    this counts real invocations instead: 0 after register() is only
    possible if run_probe() is genuinely never called during
    registration, not just called-and-its-failure-hidden."""
    crash_forge = stubbed_bpy

    from crash_forge.bl import probe as bl_probe
    from crash_forge.core.report import StageResult

    calls = []

    def _counting_probe():
        calls.append(1)
        return StageResult()

    bl_probe.run_probe = _counting_probe

    try:
        crash_forge.register()
    finally:
        crash_forge.unregister()

    assert calls == [], "register() must never call the Stage 0 probe at all -- it runs lazily, from a stage operator's execute()"


def test_ensure_probed_propagates_a_raised_exception_not_swallow_it(stubbed_bpy):
    stubbed_bpy
    from crash_forge.bl import probe as bl_probe

    def _boom():
        raise RuntimeError("boom")

    bl_probe.run_probe = _boom

    try:
        bl_probe.ensure_probed()
    except RuntimeError as exc:
        assert "boom" in str(exc)
    else:
        raise AssertionError("ensure_probed() must propagate a raised exception, not swallow it")


def test_ensure_probed_caches_across_calls(stubbed_bpy):
    """Only actually runs the probe once per session, no matter how many
    stage operators call ensure_probed() -- confirmed by counting real
    invocations, not just asserting equal results (which a fresh call
    returning an equal-but-different StageResult would also satisfy)."""
    stubbed_bpy
    from crash_forge.bl import probe as bl_probe
    from crash_forge.core.report import StageResult

    calls = []

    def _fake_probe():
        calls.append(1)
        return StageResult()

    bl_probe.run_probe = _fake_probe

    first = bl_probe.ensure_probed()
    second = bl_probe.ensure_probed()

    assert first is second
    assert len(calls) == 1


def test_reset_probe_cache_forces_a_fresh_run(stubbed_bpy):
    stubbed_bpy
    from crash_forge.bl import probe as bl_probe
    from crash_forge.core.report import StageResult

    calls = []

    def _fake_probe():
        calls.append(1)
        return StageResult()

    bl_probe.run_probe = _fake_probe

    bl_probe.ensure_probed()
    bl_probe.reset_probe_cache()
    bl_probe.ensure_probed()

    assert len(calls) == 2
