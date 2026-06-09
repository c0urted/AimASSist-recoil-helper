# AimASSist Control Workspace

An independent, low-latency client application built with [DearPyGui](https://github.com/hoffstadt/DearPyGui) for Dual-PC (2PC) topologies. This environment executes entirely on a secondary stream/control machine, routing mouse translation coordinates and click sequences directly to a physical KMBox processing unit over UDP.

By offloading the entire execution environment, configuration tables, and input pooling tasks, the script completely isolates execution signatures from the target gaming PC, rendering it almost entirely invisible to input heuristics.

Originally configured for the specific frame pacing and recoil mechanics of *The Finals*, the software layer is built using an open device abstraction layer, allowing seamless adaptability for any competitive first-person shooter environment.

---

## Prerequisites & Initial Provisioning

### Host Environment Requirements

The host environment requires a standard **Python 3.10+** execution shell. Provision the baseline graphic framework and low-level system listener modules before runtime initialization:

```bash
pip install dearpygui keyboard
```

### Module File Layout

To ensure proper workspace linkage, the native target link-layer module corresponding to your network hardware (`kmNet`) must reside directly within the immediate directory structure:

```
├── configs/           # Serialized JSON configuration profiles
├── kmNet.pyd          # Native hardware interface abstraction binary
└── master_control.py  # Primary runtime interface and worker engine
```

---

## Workspace Features

### Vector Recoil Matrix

- **Visual Trajectory Node Canvas** — Plot, test, and dynamically scale custom multi-node movement patterns directly onto the coordinate grid system. ADDING SOON
- **Focal-Length Speed Scaling** — Real-time evaluation coefficients calculate field-of-view (FOV) shifts, normalizing translation speeds instantly the millisecond you transition into aim down sights (ADS).
- **Target Constraint Verification** — Standalone validation toggles enforce strict runtime barriers, preventing macro activation unless target input thresholds are actively verified (e.g., ignoring pull vectors during hip-fire actions).

### Burst & Timing Module

- **High-Precision Loop Tracking** — Leverages monotonic hardware reference counters (`time.perf_counter`) encapsulated inside unthrottled spin-locks to mirror target cycle behaviors perfectly (e.g., maintaining exact 60ms bullet spacing intervals).
- **Flexible Input Activation Filters** — Features an edge-detection state engine allowing the operator to dynamically toggle between standard held-down trigger sequences and strict edge-triggered toggle regimes (Click-to-On / Click-to-Off).

### Calibration & Variable Parameters

1. **Base Hardware Calibration Field** — Assign your absolute engine sensitivity value directly into the structural parameter block.
2. **Focal Multiplier Scale** — Define the corresponding magnification adjustment ratio. For engines utilizing a 75% zoom sensitivity balance, input an absolute parameter of `0.75`.
3. **Sensor Field of View Boundaries** — Match the exact local rendering field-of-view configuration to optimize vector-to-pixel coefficient calculations.
4. **Asynchronous Framework Killswitch** — Map a primary virtual key signature (e.g., `/`) to act as an immediate background safety override, instantly halting or waking all device input translation threads across both machines.