# AimASSist Control Workspace

An independent, low-latency client application built for the mentally retarded and physically disabled with [DearPyGui](https://github.com/hoffstadt/DearPyGui) for Dual-PC (2PC) topologies. This environment executes entirely on a secondary stream/control machine, routing mouse translation coordinates and click sequences directly to a physical KMBox processing unit over UDP.

By offloading the entire execution environment, configuration tables, and input pooling tasks, the script completely isolates execution signatures from the target gaming PC, rendering it **almost** entirely invisible to input heuristics. 

Originally configured for the specific frame pacing and recoil mechanics of *The Finals*, the software layer is built using an open device abstraction layer, allowing seamless adaptability for any competitive first-person shooter environment.

---
### GUI Design
 [![Alt Text](images/GUI.png)]()
 [![m11](images/m11.png)]()m11 @25m

 [![xp54](images/xp54.png)]()xp54 @25m

 [![Alt Text](images/lewis.png)]() lewis @20m


## Prerequisites & Initial Provisioning

- A Kmbox B/Net | Makcu/arduino
- A laptop or miniPC

### Host Environment Requirements

The host environment requires a standard **Python 3.10+** execution shell. Provision the baseline graphic framework and low-level system listener modules before runtime initialization:

```bash
pip install dearpygui keyboard
```

### Module File Layout

To ensure proper workspace linkage, the native target link-layer module corresponding to your network hardware (`kmNet`) must reside directly within the immediate directory structure:

```
|Recoil_processor| priv cuz im mean lol
├── run_extractor.py # AiO tool for generating recoil patterns
├── inputs/image.png
├── outputs/weaponname_profile.txt

|AimASSist|
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

## Disclaimer and Liability

## Disclaimer and Liability

> [!WARNING]
> This software is strictly for educational, research, and personal testing purposes.
> 
> **By downloading, installing, or executing this software, you agree to the following terms:**
> * **Use At Your Own Risk:** The authors and contributors assume absolutely no liability for any account bans, temporary suspensions, or hardware restrictions (such as HWID bans) issued by game developers or anti-cheat providers.
> * **No Guarantees:** While this workspace utilizes hardware emulation and a Dual-PC setup to maximize isolation, no software or hardware automation layer is entirely undetectable. Anti-cheat heuristics change constantly. You are responsible for any outcomes.
> * **Compliance:** You are entirely responsible for reading and understanding the Terms of Service (ToS) of any game you run alongside this tool. 
> 
> This project is provided "as is" without warranty of any kind, express or implied. In no event shall the copyright holders or contributors be liable for any claim, damages, or other liability arising from the use of this software.