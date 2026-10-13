# Physica motion-candidate guard (optional, dry-run only)

Install Physica 0.3.0+ in the Python environment that executes VERA ARK. The guard is **not** a motor controller. It can veto a MOVE when an uncalibrated world-space swept AABB overlaps a static obstacle. It never authorizes physical contact, path safety, live controller output, or measured game movement.

Invoke `vera-ark demo --motion-guard-config model.json --log-dir demo-guard` or add the same flag to `run`. Example configuration (synthetic assumptions, **not** measured ARK coordinates):

```json
{
  "schema": "VERA_ARK_PHYSICA_GUARD_CONFIG_V1",
  "position_m": [0.0, 0.0],
  "x_axis": [2.0, 0.0],
  "y_axis": [0.0, 2.0],
  "radius_m": 0.1,
  "obstacles": [{"id":"wall","lower":[0.9,-0.2],"upper":[1.1,0.2]}]
}
```

The runtime evaluates an action **before** dry-run controller serialization. Any potential intersection or model error fails closed for MOVE, preserves the existing `SESSION_ERROR` and final neutral-release evidence, and returns a failure. LOOK/NOOP are unchanged. Passing the guard means **no broad-phase candidates for this assumed straight-line path**, not proof of safety. Positions are caller-supplied and not updated from screenshots; world coordinates, terrain, momentum, obstacles, collision shapes, and camera/stick calibration need actual observation before gameplay prediction claims.

Without `--motion-guard-config`, the existing dry-run runtime behavior is unchanged. A failed guard never activates a live controller, USB report, PS Remote Play, or virtual HID device.
