import os, sys, time, json, glob, random, queue, threading, logging, ctypes
import keyboard
import dearpygui.dearpygui as dpg

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
os.environ["PYTHONTIMERRESOLUTION"] = "1"

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR  = os.path.join(SCRIPT_DIR, "configs")
DEVICE_FILE = os.path.join(SCRIPT_DIR, "device.json")
if not os.path.exists(CONFIG_DIR): os.makedirs(CONFIG_DIR)
if SCRIPT_DIR not in sys.path: sys.path.insert(0, SCRIPT_DIR)

# ---------------------------------------------------------------------------
# OPTIONAL HARDWARE MODULE IMPORTS
# ---------------------------------------------------------------------------
try:
    import kmNet as km
    KM_AVAILABLE = True
except ImportError:
    KM_AVAILABLE = False
    logging.warning("kmNet not found — KMBox unavailable.")

# ---------------------------------------------------------------------------
# DEVICE ABSTRACTION LAYER
# All hardware is accessed through DEVICE.move() and DEVICE.is_down().
# Swap in any backend without touching the hot loop.
# ---------------------------------------------------------------------------
def _win_vk(vk_code) -> bool:
    """Read a virtual-key state via Windows API. Works in fullscreen games."""
    if sys.platform.startswith('win'):
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000)
    return False

_BTN_VK = {
    "mouse 5": 0x06, "m5": 0x06,          # VK_XBUTTON2
    "mouse 4": 0x05, "m4": 0x05,          # VK_XBUTTON1
    "left click": 0x01, "left": 0x01,     # VK_LBUTTON
    "right click": 0x02, "right": 0x02,   # VK_RBUTTON
}

class HWDevice:
    def connect(self, **kw) -> bool: return False
    def disconnect(self): pass
    def move(self, x: int, y: int): pass
    def is_down(self, button: str) -> bool: return False
    def is_connected(self) -> bool: return False
    def name(self) -> str: return "Unknown"

class KMBoxDevice(HWDevice):
    def __init__(self):
        self._ok = False
    def connect(self, ip="192.168.2.188", port="8808", device_id="00000000", monitor_port=8888, **kw):
        if not KM_AVAILABLE:
            logging.error("kmNet not installed. Run: pip install kmNet")
            return False
        try:
            km.init(ip, port, device_id)
            km.monitor(int(monitor_port))
            self._ok = True
            logging.info(f"KMBox connected: {ip}:{port}")
            return True
        except Exception as e:
            self._ok = False
            logging.error(f"KMBox connect failed: {e}")
            return False
    def disconnect(self): self._ok = False
    def move(self, x, y):
        if self._ok:
            try: km.move(x, y)
            except: self._ok = False
    def is_down(self, button):
        if not self._ok: return False
        b = button.lower()
        try:
            if b in ("mouse 5", "m5"):      return km.isdown_side2() == 1
            if b in ("mouse 4", "m4"):      return km.isdown_side1() == 1
            if b in ("left click", "left"): return km.isdown_left()  == 1
            if b in ("right click","right"):return km.isdown_right() == 1
        except: self._ok = False
        return False
    def is_connected(self): return self._ok
    def name(self): return "KMBox"

class MakcuDevice(HWDevice):
    """
    Makcu / MAKCU adapter.
    Fill in the two TODO blocks with your makcu library's actual calls.
    Button reads fall back to Windows API (works in fullscreen games).
    """
    def __init__(self):
        self._ok  = False
        self._dev = None
    def connect(self, com_port="COM3", baud_rate=115200, **kw):
        try:
            # ── TODO: replace with your makcu library connect call ──────────
            # Example A (official makcu lib):
            #   from makcu import Makcu
            #   self._dev = Makcu(com_port)
            # Example B (raw serial):
            #   import serial
            #   self._dev = serial.Serial(com_port, int(baud_rate), timeout=0.01)
            # ────────────────────────────────────────────────────────────────
            raise NotImplementedError("Fill in makcu connect — see TODO above")
        except NotImplementedError as e:
            logging.error(f"Makcu: {e}")
            self._ok = False
            return False
        except Exception as e:
            logging.error(f"Makcu connect failed ({com_port}): {e}")
            self._ok = False
            return False
        self._ok = True
        logging.info(f"Makcu connected: {com_port}")
        return True
    def disconnect(self):
        try:
            if self._dev: self._dev.close()
        except: pass
        self._ok = False
    def move(self, x, y):
        if not self._ok or (not x and not y): return
        try:
            # ── TODO: replace with your makcu library move call ─────────────
            # Example A:  self._dev.move(x, y)
            # Example B (serial packet):
            #   import struct
            #   self._dev.write(struct.pack('<bbb', 0x01, x & 0xFF, y & 0xFF))
            # ────────────────────────────────────────────────────────────────
            pass
        except Exception as e:
            logging.error(f"Makcu move failed: {e}")
            self._ok = False
    def is_down(self, button):
        # Makcu doesn't report button state to host; use Windows API fallback.
        b = button.lower()
        vk = _BTN_VK.get(b)
        if vk: return _win_vk(vk)
        return keyboard.is_pressed(b) if b else False
    def is_connected(self): return self._ok
    def name(self): return "Makcu"

class SimDevice(HWDevice):
    """No hardware — keyboard/Win32 fallback for testing."""
    def connect(self, **kw): return True
    def move(self, x, y): pass
    def is_down(self, button):
        b = button.lower()
        vk = _BTN_VK.get(b)
        if vk: return _win_vk(vk)
        return keyboard.is_pressed(b) if b else False
    def is_connected(self): return True
    def name(self): return "Simulation"

# Global device instance — swapped out by connect_device_from_config()
DEVICE: HWDevice = SimDevice()

# ---------------------------------------------------------------------------
# DEVICE CONFIG  (device.json — separate from weapon profiles)
# ---------------------------------------------------------------------------
_DEV_DEFAULTS = {
    "device_type":      "KMBox",
    "kmbox_ip":         "192.168.2.188",
    "kmbox_port":       "8808",
    "kmbox_id":         "00000000",
    "kmbox_monitor":    8888,
    "makcu_com":        "COM3",
    "makcu_baud":       115200,
}

def load_device_config() -> dict:
    if os.path.exists(DEVICE_FILE):
        try:
            with open(DEVICE_FILE) as f:
                return {**_DEV_DEFAULTS, **json.load(f)}
        except Exception as e:
            logging.warning(f"device.json load failed: {e}")
    return _DEV_DEFAULTS.copy()

def save_device_config(cfg: dict):
    try:
        with open(DEVICE_FILE, "w") as f:
            json.dump(cfg, f, indent=4)
    except Exception as e:
        logging.error(f"device.json save failed: {e}")

def connect_device_from_config(cfg: dict) -> bool:
    global DEVICE
    dtype = cfg.get("device_type", "KMBox")
    if dtype == "KMBox":
        DEVICE = KMBoxDevice()
        return DEVICE.connect(
            ip=cfg["kmbox_ip"], port=cfg["kmbox_port"],
            device_id=cfg["kmbox_id"], monitor_port=cfg["kmbox_monitor"]
        )
    elif dtype == "Makcu":
        DEVICE = MakcuDevice()
        return DEVICE.connect(com_port=cfg["makcu_com"], baud_rate=cfg["makcu_baud"])
    else:
        DEVICE = SimDevice()
        DEVICE.connect()
        return True

def get_available_com_ports() -> list:
    try:
        import serial.tools.list_ports
        ports = [p.device for p in serial.tools.list_ports.comports()]
        return ports if ports else ["No ports found"]
    except ImportError:
        return ["Install pyserial for auto-detect"]

# ---------------------------------------------------------------------------
# GLOBAL QUEUES + LOCK
# maxsize=16 so rapid multi-slider changes don't silently drop each other
# ---------------------------------------------------------------------------
DATA_QUEUE      = queue.Queue(maxsize=16)
STATE_LOCK      = threading.Lock()
UI_UPDATE_QUEUE = queue.Queue(maxsize=32)

KS_KEY_OPTIONS = ["None", "Mouse 5", "Mouse 4", "Left Click", "Right Click"]

# ---------------------------------------------------------------------------
# RUNTIME STATE
# ---------------------------------------------------------------------------
DEFAULT_STATE = {
    "master_active":         True,
    "active_tab":            "Recoil",
    "recoil_module_enabled": True,
    "burst_module_enabled":  True,

    "recoil_trigger_key": "Mouse 5",
    "burst_trigger_key":  "Mouse 4",
    "recoil_require_ads": False,
    "burst_require_ads":  False,
    "recoil_is_toggle":   False,
    "burst_is_toggle":    False,
    "recoil_ks_key":      "None",
    "burst_ks_key":       "None",
    "toggle_key":         "/",

    "local_sens":       22.0,
    "local_zoom_mult":  0.75,
    "local_fov":        100,

    "recoil_nodes":       [[0.0, 0.0, 0.0]],
    "recoil_scale_x":     1.0,
    "recoil_scale_y":     1.0,
    "recoil_jitter":      0.05,
    "time_step_interval": 0.15,
    "overlay_mode":       "None",

    "burst_count":           3,
    "burst_y_pull":          14.0,
    "burst_x_pull":          0.0,
    "burst_intra_delay_ms":  60.0,
    "burst_inter_delay_ms":  275.0,

    "hw_killswitch_enabled": False,
    "hw_killswitch_key":     "Mouse 5",
}

# ---------------------------------------------------------------------------
# DARK TITLEBAR
# ---------------------------------------------------------------------------
def _apply_dark_titlebar_worker():
    if not sys.platform.startswith('win'): return
    time.sleep(0.3)
    for _ in range(30):
        try:
            hwnd = ctypes.windll.user32.FindWindowW(None, "AimASSist Control Workspace")
            if hwnd:
                val = ctypes.c_int(1)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(val), ctypes.sizeof(val))
                ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
                logging.info("Dark title bar applied.")
                return
        except Exception: pass
        time.sleep(0.1)

# ---------------------------------------------------------------------------
# PC KEYBOARD PANIC LISTENER
# ---------------------------------------------------------------------------
def main_pc_keyboard_listener_worker():
    latch = False
    while True:
        try:
            with STATE_LOCK:
                target = DEFAULT_STATE["toggle_key"].lower()
            if keyboard.is_pressed(target):
                if not latch:
                    latch = True
                    with STATE_LOCK:
                        DEFAULT_STATE["master_active"] = not DEFAULT_STATE["master_active"]
                        active = DEFAULT_STATE["master_active"]
                    try: UI_UPDATE_QUEUE.put_nowait(("status", active))
                    except queue.Full: pass
                    logging.info(f"PC panic: {'ONLINE' if active else 'PAUSED'}")
            else:
                latch = False
        except Exception: pass
        time.sleep(0.01)

def callback_update_hotkey(sender, app_data):
    with STATE_LOCK: DEFAULT_STATE["toggle_key"] = app_data
    ui_thread_push_sync(sender, app_data, "toggle_key")

# ---------------------------------------------------------------------------
# INTERPOLATION  (takes a PRE-SORTED list — caller maintains the cache)
# ---------------------------------------------------------------------------
def get_interpolated_velocity(elapsed_time, sorted_nodes):
    sn = sorted_nodes
    if not sn or len(sn) < 2: return 0.0, 0.0
    if elapsed_time >= sn[-1][0]: return 0.0, 0.0
    if elapsed_time <= sn[0][0]:  return sn[0][1], sn[0][2]
    for i in range(len(sn) - 1):
        a, b = sn[i], sn[i + 1]
        if a[0] <= elapsed_time <= b[0]:
            d = b[0] - a[0]
            if d == 0: return a[1], a[2]
            t = (elapsed_time - a[0]) / d
            return a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t
    return 0.0, 0.0

# ---------------------------------------------------------------------------
# CONFIG I/O
# ---------------------------------------------------------------------------
def get_config_files():
    files = [os.path.basename(f) for f in glob.glob(os.path.join(CONFIG_DIR, "*.json"))]
    return files if files else ["No configs found"]

def callback_save_config(sender, app_data):
    filename = dpg.get_value("ui_save_name")
    if not filename: return
    if not filename.endswith(".json"): filename += ".json"
    blob = {
        "recoil_module_enabled":  dpg.get_value("ui_toggle_recoil_mod"),
        "burst_module_enabled":   dpg.get_value("ui_toggle_burst_mod"),
        "recoil_trigger_key":     dpg.get_value("ui_recoil_trigger_combo"),
        "burst_trigger_key":      dpg.get_value("ui_burst_trigger_combo"),
        "recoil_require_ads":     dpg.get_value("ui_recoil_req_ads"),
        "burst_require_ads":      dpg.get_value("ui_burst_req_ads"),
        "recoil_is_toggle":       dpg.get_value("ui_recoil_is_toggle"),
        "burst_is_toggle":        dpg.get_value("ui_burst_is_toggle"),
        "recoil_ks_key":          dpg.get_value("ui_recoil_ks_key"),
        "burst_ks_key":           dpg.get_value("ui_burst_ks_key"),
        "toggle_key":             dpg.get_value("ui_toggle_combo"),
        "local_sens":             dpg.get_value("ui_input_sens"),
        "local_zoom_mult":        dpg.get_value("ui_input_zoom_mult"),
        "local_fov":              dpg.get_value("ui_input_fov"),
        "recoil_scale_x":         dpg.get_value("ui_recoil_scale_x"),
        "recoil_scale_y":         dpg.get_value("ui_recoil_scale_y"),
        "recoil_jitter":          dpg.get_value("ui_recoil_jitter"),
        "time_step_interval":     dpg.get_value("ui_time_interval"),
        "overlay_mode":           dpg.get_value("ui_overlay_combo"),
        "recoil_nodes":           DEFAULT_STATE["recoil_nodes"],
        "burst_count":            dpg.get_value("ui_burst_count"),
        "burst_y_pull":           dpg.get_value("ui_burst_pull"),
        "burst_x_pull":           dpg.get_value("ui_burst_x"),
        "burst_intra_delay_ms":   dpg.get_value("ui_burst_intra_ms"),
        "burst_inter_delay_ms":   dpg.get_value("ui_burst_inter_ms"),
        "hw_killswitch_enabled":  dpg.get_value("ui_hw_ks_enabled"),
        "hw_killswitch_key":      dpg.get_value("ui_hw_ks_key_combo"),
    }
    with open(os.path.join(CONFIG_DIR, filename), "w") as f:
        json.dump(blob, f, indent=4)
    logging.info(f"Saved: {filename}")
    dpg.configure_item("ui_config_selector", items=get_config_files())

def callback_load_config(sender, app_data):
    filename = dpg.get_value("ui_config_selector")
    if filename in ["No configs found", "Select Profile", None]: return
    try:
        with open(os.path.join(CONFIG_DIR, filename)) as f:
            data = json.load(f)
        dpg.set_value("ui_toggle_recoil_mod",   data.get("recoil_module_enabled", True))
        dpg.set_value("ui_toggle_burst_mod",     data.get("burst_module_enabled",  True))
        dpg.set_value("ui_recoil_trigger_combo", data.get("recoil_trigger_key", "Mouse 5"))
        dpg.set_value("ui_burst_trigger_combo",  data.get("burst_trigger_key",  "Mouse 4"))
        dpg.set_value("ui_recoil_req_ads",       data.get("recoil_require_ads", False))
        dpg.set_value("ui_burst_req_ads",        data.get("burst_require_ads",  False))
        dpg.set_value("ui_recoil_is_toggle",     data.get("recoil_is_toggle",   False))
        dpg.set_value("ui_burst_is_toggle",      data.get("burst_is_toggle",    False))
        dpg.set_value("ui_recoil_ks_key",        data.get("recoil_ks_key",      "None"))
        dpg.set_value("ui_burst_ks_key",         data.get("burst_ks_key",       "None"))
        dpg.set_value("ui_toggle_combo",         data.get("toggle_key",         "/"))
        dpg.set_value("ui_input_sens",           data.get("local_sens",         22.0))
        dpg.set_value("ui_input_zoom_mult",      data.get("local_zoom_mult",    0.75))
        dpg.set_value("ui_input_fov",            data.get("local_fov",          100))
        dpg.set_value("ui_recoil_scale_x",       data.get("recoil_scale_x",     1.0))
        dpg.set_value("ui_recoil_scale_y",       data.get("recoil_scale_y",     1.0))
        dpg.set_value("ui_recoil_jitter",        data.get("recoil_jitter",      0.05))
        dpg.set_value("ui_time_interval",        data.get("time_step_interval", 0.15))
        dpg.set_value("ui_overlay_combo",        data.get("overlay_mode",       "None"))
        dpg.set_value("ui_burst_count",          data.get("burst_count",        3))
        dpg.set_value("ui_burst_pull",           data.get("burst_y_pull",       14.0))
        dpg.set_value("ui_burst_x",              data.get("burst_x_pull",       0.0))
        dpg.set_value("ui_burst_intra_ms",       data.get("burst_intra_delay_ms",  60.0))
        dpg.set_value("ui_burst_inter_ms",       data.get("burst_inter_delay_ms", 275.0))
        dpg.set_value("ui_hw_ks_enabled",        data.get("hw_killswitch_enabled", False))
        dpg.set_value("ui_hw_ks_key_combo",      data.get("hw_killswitch_key",  "Mouse 5"))
        DEFAULT_STATE["recoil_nodes"] = data.get("recoil_nodes", [[0.0, 0.0, 0.0]])
        # Push full blob — maxsize=16 means this won't stomp a simultaneous change
        try: DATA_QUEUE.put_nowait(data)
        except queue.Full: pass
        with STATE_LOCK:
            DEFAULT_STATE["toggle_key"]            = data.get("toggle_key", "/")
            DEFAULT_STATE["hw_killswitch_enabled"] = data.get("hw_killswitch_enabled", False)
            DEFAULT_STATE["hw_killswitch_key"]     = data.get("hw_killswitch_key", "Mouse 5")
        redraw_recoil_canvas()
        redraw_burst_canvas()
        logging.info(f"Loaded: {filename}")
    except Exception as e:
        logging.error(f"Load failed: {e}")

# ---------------------------------------------------------------------------
# SPIN SLEEP — hybrid: OS sleep most of it, spin the last 200µs
# Keeps precision without burning 100% of one core
# ---------------------------------------------------------------------------
def precision_sleep(duration):
    end = time.perf_counter() + duration
    spin_threshold = end - 0.0002
    if spin_threshold > time.perf_counter():
        time.sleep(max(0, spin_threshold - time.perf_counter()))
    while time.perf_counter() < end:
        pass

# ---------------------------------------------------------------------------
# HARDWARE ENGINE
# ---------------------------------------------------------------------------
def hardware_consumer_engine(data_mailbox):
    rs = DEFAULT_STATE.copy()

    recoil_trigger_latch = False
    start_burst_time     = 0.0
    in_burst_sequence    = False
    burst_seq_start      = 0.0
    shots_in_seq         = 0
    last_burst_finish    = 0.0
    accum_x = accum_y    = 0.0
    prev_r_phys          = False
    recoil_toggled_on    = False
    prev_b_phys          = False
    burst_toggled_on     = False
    r_ks_prev            = False
    b_ks_prev            = False
    hw_ks_prev           = False

    # Pre-sorted nodes cache — only re-sorts when the list object changes
    _nodes_sorted   = []
    _nodes_list_ref = None

    def key(k: str) -> bool:
        if not k or k == "None": return False
        return DEVICE.is_down(k)

    def ui_post(tag, value):
        try: UI_UPDATE_QUEUE.put_nowait(("set_value", tag, value))
        except queue.Full: pass

    while True:
        try:
            # Drain config updates (maxsize=16 — no silent drops on rapid changes)
            while True:
                try: rs.update(data_mailbox.get_nowait())
                except queue.Empty: break

            with STATE_LOCK:
                is_active = DEFAULT_STATE["master_active"]
                hw_ks_on  = DEFAULT_STATE["hw_killswitch_enabled"]
                hw_ks_key = DEFAULT_STATE["hw_killswitch_key"]
                if is_active:
                    raw_nodes = DEFAULT_STATE["recoil_nodes"]

            # Pre-sorted nodes cache — re-sort only when list object changes
            if is_active and raw_nodes is not _nodes_list_ref:
                _nodes_sorted   = sorted(raw_nodes, key=lambda n: n[0])
                _nodes_list_ref = raw_nodes

            # -- PER-TAB MODULE KILLSWITCHES (run even when paused) --
            r_ks = rs["recoil_ks_key"]
            if r_ks != "None":
                r_ks_c = key(r_ks)
                if r_ks_c and not r_ks_prev:
                    new = not rs["recoil_module_enabled"]
                    rs["recoil_module_enabled"] = new
                    with STATE_LOCK: DEFAULT_STATE["recoil_module_enabled"] = new
                    if not new:
                        recoil_trigger_latch = False
                        recoil_toggled_on    = False
                    ui_post("ui_toggle_recoil_mod", new)
                    logging.info(f"Recoil: {'ON' if new else 'OFF'}")
                r_ks_prev = r_ks_c
            else:
                r_ks_prev = False

            b_ks = rs["burst_ks_key"]
            if b_ks != "None":
                b_ks_c = key(b_ks)
                if b_ks_c and not b_ks_prev:
                    new = not rs["burst_module_enabled"]
                    rs["burst_module_enabled"] = new
                    with STATE_LOCK: DEFAULT_STATE["burst_module_enabled"] = new
                    if not new:
                        in_burst_sequence = False
                        burst_toggled_on  = False
                    ui_post("ui_toggle_burst_mod", new)
                    logging.info(f"Burst: {'ON' if new else 'OFF'}")
                b_ks_prev = b_ks_c
            else:
                b_ks_prev = False

            # -- GLOBAL HW KILLSWITCH --
            if hw_ks_on:
                hw_c = key(hw_ks_key)
                if hw_c and not hw_ks_prev:
                    with STATE_LOCK:
                        DEFAULT_STATE["master_active"] = not DEFAULT_STATE["master_active"]
                        is_active = DEFAULT_STATE["master_active"]
                    try: UI_UPDATE_QUEUE.put_nowait(("status", is_active))
                    except queue.Full: pass
                hw_ks_prev = hw_c
            else:
                hw_ks_prev = False

            if not is_active:
                in_burst_sequence    = False
                recoil_trigger_latch = False
                recoil_toggled_on    = False
                burst_toggled_on     = False
                time.sleep(0.01)
                continue

            # -- HOT PATH --
            now     = time.perf_counter()
            fov_mod = 90.0 / rs["local_fov"]
            ads     = key("right click")

            r_phys = key(rs["recoil_trigger_key"])
            if rs["recoil_is_toggle"]:
                if r_phys and not prev_r_phys: recoil_toggled_on = not recoil_toggled_on
                raw_r = recoil_toggled_on
            else:
                raw_r = r_phys; recoil_toggled_on = False
            prev_r_phys = r_phys

            b_phys = key(rs["burst_trigger_key"])
            if rs["burst_is_toggle"]:
                if b_phys and not prev_b_phys: burst_toggled_on = not burst_toggled_on
                raw_b = burst_toggled_on
            else:
                raw_b = b_phys; burst_toggled_on = False
            prev_b_phys = b_phys

            is_firing   = False
            active_mode = "None"
            tab         = rs["active_tab"]

            if tab == "Recoil" and rs["recoil_module_enabled"]:
                active_mode = "Recoil"
                if raw_r and (not rs["recoil_require_ads"] or ads): is_firing = True
            elif tab == "Burst" and rs["burst_module_enabled"]:
                active_mode = "Burst"
                if raw_b and (not rs["burst_require_ads"] or ads): is_firing = True

            if in_burst_sequence and rs["burst_require_ads"] and not ads:
                in_burst_sequence = False; last_burst_finish = now
            if in_burst_sequence and active_mode != "Burst":
                in_burst_sequence = False; last_burst_finish = now

            if is_firing or in_burst_sequence:
                zm       = rs["local_zoom_mult"] if ads else 1.0
                sens_mod = 22.0 / (rs["local_sens"] * zm)

                if active_mode == "Recoil":
                    if not recoil_trigger_latch:
                        recoil_trigger_latch = True
                        start_burst_time     = now
                    vx, vy = get_interpolated_velocity(now - start_burst_time, _nodes_sorted)
                    fx = vx * rs["recoil_scale_x"] * fov_mod * sens_mod
                    fy = vy * rs["recoil_scale_y"] * fov_mod * sens_mod
                    if rs["recoil_jitter"] > 0:
                        fx += random.uniform(-rs["recoil_jitter"], rs["recoil_jitter"]) * 5
                    accum_x += fx; accum_y += fy
                    if abs(accum_x) >= 1.0 or abs(accum_y) >= 1.0:
                        mx, my = int(accum_x), int(accum_y)
                        if mx or my: DEVICE.move(mx, my)
                        accum_x -= mx; accum_y -= my

                elif active_mode == "Burst":
                    if is_firing and not in_burst_sequence:
                        if (now - last_burst_finish) >= rs["burst_inter_delay_ms"] / 1000.0:
                            in_burst_sequence = True
                            burst_seq_start   = now
                            shots_in_seq      = 0
                    if in_burst_sequence:
                        t_ms        = (now - burst_seq_start) * 1000.0
                        target_shot = min(int(t_ms // rs["burst_intra_delay_ms"]) + 1, rs["burst_count"])
                        if target_shot > shots_in_seq:
                            DEVICE.move(int(rs["burst_x_pull"] * fov_mod * sens_mod),
                                        int(rs["burst_y_pull"] * fov_mod * sens_mod))
                            shots_in_seq = target_shot
                        if shots_in_seq >= rs["burst_count"]:
                            in_burst_sequence = False
                            last_burst_finish = time.perf_counter()
            else:
                recoil_trigger_latch = False

            precision_sleep(0.001)
        except Exception as exc:
            logging.debug(f"HW thread exception: {exc}")

# ---------------------------------------------------------------------------
# CANVAS  — node placement, drag, right-click delete
# ---------------------------------------------------------------------------
CANVAS_W, CANVAS_H = 580, 235
CANVAS_CX, CANVAS_CY = CANVAS_W // 2, 35   # origin crosshair position
NODE_HIT_RADIUS = 12   # px

_drag = {"active": False, "idx": -1, "last": None}

def _node_screen_pts():
    """Compute canvas screen positions for all nodes (cumulative offsets)."""
    nodes = DEFAULT_STATE["recoil_nodes"]
    pts = []; cx, cy = CANVAS_CX, CANVAS_CY
    for n in nodes:
        cx = max(5, min(CANVAS_W - 5, cx + int(n[1] * 5.0)))
        cy = max(5, min(CANVAS_H - 5, cy + int(n[2] * 5.0)))
        pts.append((cx, cy))
    return pts

def _find_node_near(canvas_pos):
    mx, my = canvas_pos
    for i, (px, py) in enumerate(_node_screen_pts()):
        if (mx - px) ** 2 + (my - py) ** 2 < NODE_HIT_RADIUS ** 2:
            return i
    return -1

def _recalc_node_times():
    iv = dpg.get_value("ui_time_interval")
    for i, n in enumerate(DEFAULT_STATE["recoil_nodes"]):
        n[0] = i * iv

def callback_canvas_left_click(sender, app_data):
    pos = dpg.get_drawing_mouse_pos()
    idx = _find_node_near(pos)
    if idx >= 0:
        _drag.update({"active": True, "idx": idx, "last": pos})
        return
    # No node hit — add new node
    rx = float(pos[0] - CANVAS_CX) / 5.0
    ry = float(pos[1] - CANVAS_CY) / 5.0
    n  = DEFAULT_STATE["recoil_nodes"]
    iv = dpg.get_value("ui_time_interval")
    if len(n) == 1 and n[0][1] == 0.0 and n[0][2] == 0.0:
        DEFAULT_STATE["recoil_nodes"] = [[0.0, rx, ry]]
    else:
        DEFAULT_STATE["recoil_nodes"].append([len(n) * iv, rx, ry])
    redraw_recoil_canvas()
    dpg.set_value("ui_node_count_text", f"Registered Profile Nodes: {len(DEFAULT_STATE['recoil_nodes'])}")

def callback_canvas_right_click(sender, app_data):
    """Right-click a node to delete it."""
    pos = dpg.get_drawing_mouse_pos()
    idx = _find_node_near(pos)
    if idx < 0 or len(DEFAULT_STATE["recoil_nodes"]) <= 1: return
    DEFAULT_STATE["recoil_nodes"].pop(idx)
    _recalc_node_times()
    redraw_recoil_canvas()
    dpg.set_value("ui_node_count_text", f"Registered Profile Nodes: {len(DEFAULT_STATE['recoil_nodes'])}")

def callback_global_mouse_move(sender, app_data):
    """Viewport-level handler — drives node drag without needing mouse on canvas."""
    if not _drag["active"]: return
    if not dpg.is_mouse_button_down(0):
        _drag.update({"active": False, "idx": -1, "last": None})
        return
    curr = dpg.get_mouse_pos(local=False)
    last = _drag["last"]
    if last is None:
        _drag["last"] = curr; return
    # Delta in screen pixels → node space (divide by 5, same ratio used when placing)
    dx = (curr[0] - last[0]) / 5.0
    dy = (curr[1] - last[1]) / 5.0
    if abs(dx) > 0.01 or abs(dy) > 0.01:
        idx   = _drag["idx"]
        nodes = DEFAULT_STATE["recoil_nodes"]
        if 0 <= idx < len(nodes):
            nodes[idx][1] += dx
            nodes[idx][2] += dy
            redraw_recoil_canvas()
    _drag["last"] = curr

def callback_global_mouse_release(sender, app_data):
    _drag.update({"active": False, "idx": -1, "last": None})

def callback_clear_nodes(sender, app_data):
    DEFAULT_STATE["recoil_nodes"] = [[0.0, 0.0, 0.0]]
    redraw_recoil_canvas()
    dpg.set_value("ui_node_count_text", "Registered Profile Nodes: 1 (Baseline)")

def callback_toggle_overlay(sender, app_data):
    redraw_recoil_canvas()

def redraw_recoil_canvas():
    if not dpg.does_item_exist("recoil_canvas"): return
    dpg.delete_item("recoil_canvas", children_only=True)
    w, h = CANVAS_W, 360
    if dpg.get_value("ui_overlay_combo") == "Load recoil_bg.png" and dpg.does_item_exist("texture_recoil_background"):
        dpg.draw_image("texture_recoil_background", (0, 0), (w, h), parent="recoil_canvas")
    dpg.draw_line((CANVAS_CX, 0), (CANVAS_CX, h), color=(50, 50, 65, 255), thickness=1, parent="recoil_canvas")
    dpg.draw_line((0, CANVAS_CY), (w, CANVAS_CY), color=(50, 50, 65, 255), thickness=1, parent="recoil_canvas")
    nodes = DEFAULT_STATE["recoil_nodes"]
    if len(nodes) <= 1 and nodes[0][1] == 0.0 and nodes[0][2] == 0.0: return
    pts = _node_screen_pts()
    for i in range(len(pts) - 1):
        dpg.draw_line(pts[i], pts[i+1], color=(147, 51, 234, 255), thickness=3, parent="recoil_canvas")
        dpg.draw_circle(pts[i], 5, color=(0, 191, 255, 255), fill=(0, 191, 255, 255), parent="recoil_canvas")
        dpg.draw_text((pts[i][0]+8, pts[i][1]-8), f"#{i+1}", size=13, color=(200, 200, 200), parent="recoil_canvas")
    dpg.draw_circle(pts[-1], 5, color=(0, 191, 255, 255), fill=(0, 191, 255, 255), parent="recoil_canvas")
    dpg.draw_text((pts[-1][0]+8, pts[-1][1]-8), f"#{len(pts)}", size=13, color=(200, 200, 200), parent="recoil_canvas")

def redraw_burst_canvas():
    if not dpg.does_item_exist("burst_canvas"): return
    count = dpg.get_value("ui_burst_count")
    yp    = dpg.get_value("ui_burst_pull")
    xp    = dpg.get_value("ui_burst_x")
    if None in (count, yp, xp): return
    dpg.delete_item("burst_canvas", children_only=True)
    w, h = 580, 160
    for i in range(1, 6):
        dpg.draw_line(((w/6)*i, 0), ((w/6)*i, h), color=(35, 35, 42, 255), parent="burst_canvas")
    pts = []; cx, cy = w // 2, 20
    for _ in range(min(count, 15)):
        pts.append((cx, cy))
        cx = max(5, min(w-5, cx + int(xp * 1.5)))
        cy = max(5, min(h-5, cy + int(yp * 1.5)))
    for i in range(len(pts) - 1):
        dpg.draw_line(pts[i], pts[i+1], color=(0, 191, 255, 255), thickness=2, parent="burst_canvas")
        dpg.draw_circle(pts[i], 4, color=(147, 51, 234, 255), fill=(147, 51, 234, 255), parent="burst_canvas")
    dpg.draw_circle(pts[-1], 4, color=(147, 51, 234, 255), fill=(147, 51, 234, 255), parent="burst_canvas")

def ui_thread_push_sync(sender, app_data, user_data):
    try: DATA_QUEUE.put_nowait({user_data: app_data})
    except queue.Full: pass
    if user_data in ["burst_count", "burst_y_pull", "burst_x_pull"]:
        redraw_burst_canvas()

# ---------------------------------------------------------------------------
# DEVICE UI CALLBACKS
# ---------------------------------------------------------------------------
def callback_device_type_changed(sender, app_data):
    t = app_data if app_data else dpg.get_value("ui_device_type")
    dpg.show_item("grp_kmbox") if t == "KMBox" else dpg.hide_item("grp_kmbox")
    dpg.show_item("grp_makcu") if t == "Makcu" else dpg.hide_item("grp_makcu")

def callback_device_connect(sender, app_data):
    cfg = {
        "device_type":   dpg.get_value("ui_device_type"),
        "kmbox_ip":      dpg.get_value("ui_kmbox_ip"),
        "kmbox_port":    dpg.get_value("ui_kmbox_port"),
        "kmbox_id":      dpg.get_value("ui_kmbox_id"),
        "kmbox_monitor": dpg.get_value("ui_kmbox_monitor"),
        "makcu_com":     dpg.get_value("ui_makcu_com"),
        "makcu_baud":    dpg.get_value("ui_makcu_baud"),
    }
    success = connect_device_from_config(cfg)
    save_device_config(cfg)
    _update_device_status_ui(success)

def callback_refresh_com_ports(sender, app_data):
    ports = get_available_com_ports()
    dpg.configure_item("ui_makcu_com", items=ports)
    if ports: dpg.set_value("ui_makcu_com", ports[0])

def _update_device_status_ui(connected: bool):
    txt = "CONNECTED" if connected else "OFFLINE"
    col = (0, 255, 120) if connected else (239, 68, 68)
    dpg.set_value("ui_device_status", txt)
    dpg.configure_item("ui_device_status", color=col)
    dpg.set_value("ui_device_sidebar", f"  {DEVICE.name()}")
    dpg.configure_item("ui_device_sidebar", color=(0, 191, 255) if connected else (140, 140, 150))

def callback_hw_ks_toggle(sender, app_data):
    with STATE_LOCK: DEFAULT_STATE["hw_killswitch_enabled"] = app_data

def callback_hw_ks_key(sender, app_data):
    with STATE_LOCK: DEFAULT_STATE["hw_killswitch_key"] = app_data

# ---------------------------------------------------------------------------
# MISC UI CALLBACKS
# ---------------------------------------------------------------------------
def ui_tab_navigation(sender, app_data, user_data):
    for t in ["panel_recoil", "panel_burst", "panel_settings"]: dpg.hide_item(t)
    dpg.show_item(user_data)
    name = {"panel_recoil": "Recoil", "panel_burst": "Burst", "panel_settings": "Settings"}[user_data]
    ui_thread_push_sync(None, name, "active_tab")

def callback_viewport_resize(sender, app_data):
    if dpg.does_item_exist("shell"):
        dpg.configure_item("shell", width=app_data[0]-15, height=app_data[1]-35)

# ---------------------------------------------------------------------------
# UI BUILD
# ---------------------------------------------------------------------------
def build_tactical_surface():
    # Connect device from saved config before building UI
    dev_cfg = load_device_config()
    connect_device_from_config(dev_cfg)

    dpg.create_context()

    if os.path.exists("recoil_bg.png"):
        try:
            w, h, _, data = dpg.load_image("recoil_bg.png")
            with dpg.texture_registry():
                dpg.add_static_texture(width=w, height=h, default_value=data, tag="texture_recoil_background")
        except Exception as e:
            logging.warning(f"overlay image: {e}")

    with dpg.theme() as gtheme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg,      (10, 10, 12, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg,       (16, 16, 20, 255))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg,       (24, 24, 30, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (130, 40, 210, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (155, 60, 240, 255))
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding,  4.0)
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 0.0)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing,    12.0, 10.0)
    dpg.bind_theme(gtheme)

    dpg.create_viewport(title="AimASSist Control Workspace", width=820, height=620, resizable=True)

    with dpg.window(tag="shell", width=805, height=580, no_title_bar=True, no_scrollbar=True):
        with dpg.group(horizontal=True):

            # ── SIDEBAR ─────────────────────────────────────────────────
            with dpg.child_window(width=160, height=-1, border=False):
                dpg.add_spacer(height=15)
                dpg.add_text("  AimASSist", color=(145, 55, 240))
                dpg.add_spacer(height=20)
                dpg.add_button(label="  [x]  Recoil Workspace", width=145, height=35, callback=ui_tab_navigation, user_data="panel_recoil")
                dpg.add_button(label="  [*]  Burst Mode (93R)", width=145, height=35, callback=ui_tab_navigation, user_data="panel_burst")
                dpg.add_button(label="  [o]  Settings Panel",   width=145, height=35, callback=ui_tab_navigation, user_data="panel_settings")
                dpg.add_spacer(height=100)
                dpg.add_separator()
                dpg.add_text(" Mod links:")
                dpg.add_checkbox(label="Recoil", default_value=True, tag="ui_toggle_recoil_mod",
                                 callback=ui_thread_push_sync, user_data="recoil_module_enabled")
                dpg.add_checkbox(label="Burst",  default_value=True, tag="ui_toggle_burst_mod",
                                 callback=ui_thread_push_sync, user_data="burst_module_enabled")
                dpg.add_spacer(height=20)
                dpg.add_separator()
                dpg.add_text("  Master:")
                dpg.add_text("  ONLINE", tag="ui_status_text", color=(0, 255, 120))
                dpg.add_spacer(height=6)
                dpg.add_text("  Device:")
                _dev_name  = DEVICE.name()
                _dev_color = (0, 191, 255) if DEVICE.is_connected() else (140, 140, 150)
                dpg.add_text(f"  {_dev_name}", tag="ui_device_sidebar", color=_dev_color)

            # ── MAIN PANELS ──────────────────────────────────────────────
            with dpg.group():

                # Profile bar
                with dpg.child_window(width=-1, height=50, border=False):
                    with dpg.group(horizontal=True):
                        dpg.add_text(" Profiles:", color=(140, 140, 150))
                        dpg.add_combo(get_config_files(), tag="ui_config_selector", width=160, default_value="Select Profile")
                        dpg.add_button(label="Load", width=70, callback=callback_load_config)
                        dpg.add_spacer(width=6)
                        dpg.add_input_text(hint="name", tag="ui_save_name", width=130)
                        dpg.add_button(label="Save", width=70, callback=callback_save_config)

                # ── RECOIL TAB ──────────────────────────────────────────
                with dpg.child_window(tag="panel_recoil", width=-1, height=-1, border=False):
                    dpg.add_text("Visual Profile Tracking & Vector Canvas Engine", color=(145, 55, 240))
                    dpg.add_separator()

                    with dpg.group(horizontal=True):
                        with dpg.group():
                            dpg.add_text("Trigger Key:", color=(140, 140, 150))
                            dpg.add_combo(["Mouse 5", "Mouse 4", "Left Click"],
                                          default_value="Mouse 5", tag="ui_recoil_trigger_combo", width=120,
                                          callback=ui_thread_push_sync, user_data="recoil_trigger_key")
                            dpg.add_checkbox(label="Latch Mode — arm once, fire until pressed again",
                                             tag="ui_recoil_is_toggle",
                                             callback=ui_thread_push_sync, user_data="recoil_is_toggle")
                        dpg.add_spacer(width=30)
                        with dpg.group():
                            dpg.add_text("Module KS Key:", color=(140, 140, 150))
                            dpg.add_combo(KS_KEY_OPTIONS, default_value="None",
                                          tag="ui_recoil_ks_key", width=120,
                                          callback=ui_thread_push_sync, user_data="recoil_ks_key")
                            dpg.add_text("Press to toggle Recoil ON/OFF", color=(100, 100, 110))
                            dpg.add_spacer(height=4)
                            dpg.add_checkbox(label="Require ADS (Right Click) to Fire",
                                             tag="ui_recoil_req_ads",
                                             callback=ui_thread_push_sync, user_data="recoil_require_ads")

                    dpg.add_spacer(height=8)
                    dpg.add_text("Left-click canvas to add nodes  •  Left-drag to reposition  •  Right-click to delete",
                                 color=(80, 80, 95))
                    with dpg.group(horizontal=True):
                        dpg.add_slider_float(label="Shot Interval (s)", default_value=0.15,
                                             min_value=0.04, max_value=0.40,
                                             tag="ui_time_interval", width=130,
                                             callback=ui_thread_push_sync, user_data="time_step_interval")
                        dpg.add_button(label="Reset Grid Trace", callback=callback_clear_nodes)

                    dpg.add_spacer(height=5)
                    with dpg.child_window(width=595, height=250, border=True):
                        dpg.add_drawlist(width=580, height=235, tag="recoil_canvas")
                        with dpg.item_handler_registry(tag="canvas_handler"):
                            dpg.add_item_clicked_handler(button=0, callback=callback_canvas_left_click)
                            dpg.add_item_clicked_handler(button=1, callback=callback_canvas_right_click)
                        dpg.bind_item_handler_registry("recoil_canvas", "canvas_handler")

                    with dpg.group(horizontal=True):
                        dpg.add_text("Registered Profile Nodes: 1 (Baseline)", tag="ui_node_count_text", color=(0, 191, 255))
                        dpg.add_spacer(width=10)
                        dpg.add_combo(["None", "Load recoil_bg.png"], default_value="None",
                                      label="Background", tag="ui_overlay_combo", width=160,
                                      callback=callback_toggle_overlay)

                    dpg.add_spacer(height=5)
                    with dpg.group(horizontal=True):
                        with dpg.group():
                            dpg.add_slider_float(label="Scale (X)", default_value=1.0, min_value=0.0, max_value=5.0,
                                                 tag="ui_recoil_scale_x", width=160,
                                                 callback=ui_thread_push_sync, user_data="recoil_scale_x")
                            dpg.add_slider_float(label="Scale (Y)", default_value=1.0, min_value=0.0, max_value=5.0,
                                                 tag="ui_recoil_scale_y", width=160,
                                                 callback=ui_thread_push_sync, user_data="recoil_scale_y")
                        with dpg.group():
                            dpg.add_slider_float(label="Gaussian Jitter", default_value=0.05, min_value=0.0, max_value=2.0,
                                                 tag="ui_recoil_jitter", width=160,
                                                 callback=ui_thread_push_sync, user_data="recoil_jitter")

                # ── BURST TAB ───────────────────────────────────────────
                with dpg.child_window(tag="panel_burst", width=-1, height=-1, border=False):
                    dpg.hide_item("panel_burst")
                    dpg.add_text("Stepped Burst Mechanical Calibration Matrix (93R)", color=(145, 55, 240))
                    dpg.add_separator()

                    with dpg.group(horizontal=True):
                        with dpg.group():
                            dpg.add_text("Trigger Key:", color=(140, 140, 150))
                            dpg.add_combo(["Mouse 5", "Mouse 4", "Left Click"],
                                          default_value="Mouse 4", tag="ui_burst_trigger_combo", width=140,
                                          callback=ui_thread_push_sync, user_data="burst_trigger_key")
                            dpg.add_checkbox(label="Latch Mode — arm once, fire until pressed again",
                                             tag="ui_burst_is_toggle",
                                             callback=ui_thread_push_sync, user_data="burst_is_toggle")
                        dpg.add_spacer(width=30)
                        with dpg.group():
                            dpg.add_text("Module KS Key:", color=(140, 140, 150))
                            dpg.add_combo(KS_KEY_OPTIONS, default_value="None",
                                          tag="ui_burst_ks_key", width=140,
                                          callback=ui_thread_push_sync, user_data="burst_ks_key")
                            dpg.add_text("Press to toggle Burst ON/OFF", color=(100, 100, 110))
                            dpg.add_spacer(height=4)
                            dpg.add_checkbox(label="Require ADS (Right Click) to Fire",
                                             tag="ui_burst_req_ads",
                                             callback=ui_thread_push_sync, user_data="burst_require_ads")

                    dpg.add_spacer(height=10)
                    dpg.add_slider_int(label="Rounds Per Burst Cycle", default_value=3, min_value=2, max_value=5,
                                       tag="ui_burst_count", width=180,
                                       callback=ui_thread_push_sync, user_data="burst_count")
                    dpg.add_slider_float(label="Vertical Pull Drop (Y)", default_value=14.0, min_value=0.0, max_value=40.0,
                                         tag="ui_burst_pull", width=180,
                                         callback=ui_thread_push_sync, user_data="burst_y_pull")
                    dpg.add_slider_float(label="Horizontal Corrections (X)", default_value=0.0, min_value=-10.0, max_value=10.0,
                                         tag="ui_burst_x", width=180,
                                         callback=ui_thread_push_sync, user_data="burst_x_pull")
                    dpg.add_spacer(height=10)
                    dpg.add_text("The Finals Timing Constraints:", color=(145, 55, 240))
                    dpg.add_slider_float(label="Intra-Burst Pacing (ms)  [60.0]",
                                         default_value=60.0, min_value=10.0, max_value=120.0,
                                         tag="ui_burst_intra_ms", width=180,
                                         callback=ui_thread_push_sync, user_data="burst_intra_delay_ms")
                    dpg.add_slider_float(label="Inter-Burst Recovery (ms)  [275.0]",
                                         default_value=275.0, min_value=100.0, max_value=400.0,
                                         tag="ui_burst_inter_ms", width=180,
                                         callback=ui_thread_push_sync, user_data="burst_inter_delay_ms")
                    dpg.add_spacer(height=10)
                    with dpg.group(horizontal=True):
                        with dpg.group():
                            dpg.add_text("Visual Vector Map:", color=(110, 110, 120))
                            dpg.add_text("Stabilizes burst climb.", color=(110, 110, 120))
                        with dpg.child_window(width=350, height=180, border=True):
                            dpg.add_drawlist(width=335, height=160, tag="burst_canvas")

                # ── SETTINGS TAB ────────────────────────────────────────
                with dpg.child_window(tag="panel_settings", width=-1, height=-1, border=False):
                    dpg.hide_item("panel_settings")
                    dpg.add_text("AimASSist Configuration", color=(145, 55, 240))
                    dpg.add_separator()

                    # ── DEVICE CONNECTION ────────────────────────────────
                    dpg.add_spacer(height=10)
                    dpg.add_text("Device Connection", color=(0, 191, 255))

                    with dpg.group(horizontal=True):
                        dpg.add_text("Device type:", color=(140, 140, 150))
                        dpg.add_combo(["KMBox", "Makcu", "Simulation"],
                                      default_value=dev_cfg.get("device_type", "KMBox"),
                                      tag="ui_device_type", width=130,
                                      callback=callback_device_type_changed)

                    dpg.add_spacer(height=6)

                    # KMBox fields
                    with dpg.group(tag="grp_kmbox"):
                        with dpg.group(horizontal=True):
                            dpg.add_text("IP:", color=(140, 140, 150))
                            dpg.add_input_text(default_value=dev_cfg["kmbox_ip"],
                                               tag="ui_kmbox_ip", width=130)
                            dpg.add_text("  Port:", color=(140, 140, 150))
                            dpg.add_input_text(default_value=dev_cfg["kmbox_port"],
                                               tag="ui_kmbox_port", width=70)
                        with dpg.group(horizontal=True):
                            dpg.add_text("Device ID:", color=(140, 140, 150))
                            dpg.add_input_text(default_value=dev_cfg["kmbox_id"],
                                               tag="ui_kmbox_id", width=130)
                            dpg.add_text("  Monitor:", color=(140, 140, 150))
                            dpg.add_input_int(default_value=dev_cfg["kmbox_monitor"],
                                              tag="ui_kmbox_monitor", width=80)

                    # Makcu fields (hidden by default unless config says Makcu)
                    with dpg.group(tag="grp_makcu"):
                        dpg.add_text("Fill in the TODO blocks in MakcuDevice before connecting.",
                                     color=(100, 100, 110))
                        with dpg.group(horizontal=True):
                            dpg.add_text("COM Port:", color=(140, 140, 150))
                            _com_ports = get_available_com_ports()
                            dpg.add_combo(_com_ports,
                                          default_value=dev_cfg.get("makcu_com", _com_ports[0]),
                                          tag="ui_makcu_com", width=120)
                            dpg.add_button(label="↺", width=28, callback=callback_refresh_com_ports)
                            dpg.add_text("  Baud:", color=(140, 140, 150))
                            dpg.add_input_int(default_value=dev_cfg.get("makcu_baud", 115200),
                                              tag="ui_makcu_baud", width=90)

                    # Hide whichever group shouldn't show
                    callback_device_type_changed(None, dev_cfg.get("device_type", "KMBox"))

                    dpg.add_spacer(height=8)
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Connect / Reconnect", width=160, callback=callback_device_connect)
                        dpg.add_spacer(width=10)
                        _conn_txt = "CONNECTED" if DEVICE.is_connected() else "OFFLINE"
                        _conn_col = (0, 255, 120) if DEVICE.is_connected() else (239, 68, 68)
                        dpg.add_text(_conn_txt, tag="ui_device_status", color=_conn_col)

                    dpg.add_spacer(height=15)
                    dpg.add_separator()

                    # ── SENSITIVITY ──────────────────────────────────────
                    dpg.add_spacer(height=10)
                    dpg.add_text("Step 1: Hip-fire sensitivity", color=(0, 191, 255))
                    dpg.add_input_float(label="", default_value=22.0, tag="ui_input_sens",
                                        width=160, callback=ui_thread_push_sync, user_data="local_sens")

                    dpg.add_spacer(height=12)
                    dpg.add_text("Step 2: ADS zoom multiplier", color=(0, 191, 255))
                    dpg.add_text("75% zoom = 0.75", color=(120, 120, 130))
                    dpg.add_input_float(label="", default_value=0.75, tag="ui_input_zoom_mult",
                                        width=160, callback=ui_thread_push_sync, user_data="local_zoom_mult")

                    dpg.add_spacer(height=12)
                    dpg.add_text("Step 3: FOV", color=(0, 191, 255))
                    dpg.add_input_int(label="", default_value=100, tag="ui_input_fov",
                                      width=160, callback=ui_thread_push_sync, user_data="local_fov")

                    dpg.add_spacer(height=12)
                    dpg.add_text("Step 4: Local Panic Button  (keyboard key)", color=(239, 68, 68))
                    dpg.add_combo(["/", "F4", "Insert", "Home"], default_value="/",
                                  tag="ui_toggle_combo", label="", width=160,
                                  callback=callback_update_hotkey)

                    dpg.add_spacer(height=16)
                    dpg.add_separator()
                    dpg.add_spacer(height=8)
                    dpg.add_text("Step 5: Global Hardware Killswitch  (optional)", color=(239, 68, 68))
                    dpg.add_text("Per-tab KS Keys are the main way — this is a backup.", color=(100, 100, 110))
                    dpg.add_checkbox(label="Enable", default_value=False,
                                     tag="ui_hw_ks_enabled", callback=callback_hw_ks_toggle)
                    dpg.add_combo(KS_KEY_OPTIONS[1:], default_value="Mouse 5",
                                  tag="ui_hw_ks_key_combo", width=160, callback=callback_hw_ks_key)

    # -- GLOBAL MOUSE HANDLERS for canvas drag
    with dpg.handler_registry():
        dpg.add_mouse_move_handler(callback=callback_global_mouse_move)
        dpg.add_mouse_release_handler(button=0, callback=callback_global_mouse_release)

    dpg.setup_dearpygui()
    dpg.show_viewport()

    if sys.platform.startswith('win'):
        threading.Thread(target=_apply_dark_titlebar_worker, daemon=True).start()

    dpg.set_viewport_resize_callback(callback_viewport_resize)
    threading.Thread(target=main_pc_keyboard_listener_worker, daemon=True).start()
    threading.Thread(target=hardware_consumer_engine, args=(DATA_QUEUE,), daemon=True).start()

    redraw_recoil_canvas()
    redraw_burst_canvas()

    while dpg.is_dearpygui_running():
        dpg.render_dearpygui_frame()
        # Drain deferred UI updates — all DPG writes from background threads land here
        while True:
            try:
                msg = UI_UPDATE_QUEUE.get_nowait()
                if msg[0] == "set_value":
                    dpg.set_value(msg[1], msg[2])
                elif msg[0] == "status":
                    ok = msg[1]
                    dpg.set_value("ui_status_text", "ONLINE" if ok else "PAUSED")
                    dpg.configure_item("ui_status_text", color=(0, 255, 120) if ok else (239, 68, 68))
            except queue.Empty:
                break

    dpg.destroy_context()


if __name__ == "__main__":
    build_tactical_surface()