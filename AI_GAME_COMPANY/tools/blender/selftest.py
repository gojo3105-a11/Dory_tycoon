"""Blender background self-test (master prompt sections 11, 40).

Run headless:
    blender --background --factory-startup --python selftest.py -- <out.txt>

Writes a real file so the runner can verify output existence, not just the
exit code.
"""
import sys


def out_path() -> str:
    argv = sys.argv
    if "--" in argv:
        rest = argv[argv.index("--") + 1:]
        if rest:
            return rest[0]
    return "blender_selftest.txt"


def main() -> int:
    target = out_path()
    try:
        import bpy  # available only inside Blender
    except ImportError:
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("FAIL not running inside Blender (bpy unavailable)\n")
        return 1

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    obj = bpy.context.active_object
    mesh = obj.data
    lines = [
        f"blender_version={bpy.app.version_string}",
        f"object={obj.name}",
        f"vertices={len(mesh.vertices)}",
        f"polygons={len(mesh.polygons)}",
        "status=OK",
    ]
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("[blender selftest] wrote", target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
