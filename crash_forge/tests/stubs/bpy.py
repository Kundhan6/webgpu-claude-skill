"""Minimal, deliberately non-auto-vivifying stub of bpy for Tier B tests (§13).

Implements exactly enough surface for the real add-on package to import
cleanly and for register()/unregister() to run without exceptions. Anything
not explicitly defined here does not exist, on purpose: that is what lets
bl/probe.py correctly report "missing" under this stub instead of lying
about API surface a real Blender build would actually have.

Deep behavioural testing of bpy-dependent logic (does CF_Reset actually
clean a messy scene correctly?) is Tier C's job, run by the user on real
Blender 5.2 — building a second, hand-rolled fake data-layer here to
half-simulate that would risk baking in exactly the kind of unverified
assumption about the real API that this whole spec exists to prevent.
"""


class _RegisteredClasses:
    def __init__(self):
        self.classes = []

    def register(self, cls):
        if cls in self.classes:
            raise ValueError(f"class {cls} already registered")
        self.classes.append(cls)

    def unregister(self, cls):
        if cls not in self.classes:
            raise ValueError(f"class {cls} was never registered")
        self.classes.remove(cls)


_registry = _RegisteredClasses()


def registered_classes():
    """Test-only introspection hook, not part of real bpy."""
    return list(_registry.classes)


class utils:
    @staticmethod
    def register_class(cls):
        _registry.register(cls)

    @staticmethod
    def unregister_class(cls):
        _registry.unregister(cls)


# --- bpy.types ------------------------------------------------------------

class Operator:
    bl_options = set()

    def report(self, level, message):
        pass


class Panel:
    pass


class PropertyGroup:
    pass


class AddonPreferences:
    pass


class Object:
    pass


class Scene:
    pass


class types:
    Operator = Operator
    Panel = Panel
    PropertyGroup = PropertyGroup
    AddonPreferences = AddonPreferences
    Object = Object
    Scene = Scene


# --- bpy.props --------------------------------------------------------
# Real bpy.props functions return an opaque object that Blender's own
# class-registration machinery turns into a working RNA property from the
# class's annotations. The stub only needs the call + annotation-assignment
# to succeed without error, which a plain sentinel object provides.

class _PropDef:
    def __init__(self, kind, **kwargs):
        self.kind = kind
        self.kwargs = kwargs


class props:
    @staticmethod
    def PointerProperty(**kwargs):
        return _PropDef("POINTER", **kwargs)

    @staticmethod
    def FloatProperty(**kwargs):
        return _PropDef("FLOAT", **kwargs)

    @staticmethod
    def IntProperty(**kwargs):
        return _PropDef("INT", **kwargs)

    @staticmethod
    def BoolProperty(**kwargs):
        return _PropDef("BOOL", **kwargs)

    @staticmethod
    def StringProperty(**kwargs):
        return _PropDef("STRING", **kwargs)

    @staticmethod
    def FloatVectorProperty(**kwargs):
        return _PropDef("FLOAT_VECTOR", **kwargs)

    @staticmethod
    def EnumProperty(**kwargs):
        return _PropDef("ENUM", **kwargs)


class _Ops:
    """Deliberately empty: no operator exists under this stub."""


ops = _Ops()


class _Context:
    scene = None
    window = None


context = _Context()


class _Data:
    """Deliberately empty: no datablocks collections exist under this stub."""


data = _Data()


class _App:
    version_string = "stub"


app = _App()
