"""
profile_architect.py — Manual recoil pattern builder with zoom/pan
==================================================================
Click each bullet hole in order. Zoom in for precision on dense sprays.

Controls:
    Left-click     Place a node on the bullet hole
    +/=            Zoom in
    -              Zoom out
    Arrow keys     Pan around when zoomed
    Scroll wheel   Zoom in/out
    F              Fit (reset zoom to see full image)
    Z              Undo last click
    C              Clear all clicks
    Q / ENTER      Export pattern

Usage:
    python profile_architect.py --weapon AKM --sens 22 --fov 100
"""

import cv2
import numpy as np
import os, sys, glob, argparse

INPUT_DIR  = "./inputs"
OUTPUT_DIR = "./outputs"
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

WEAPON_RATES = {
    "M11": 60, "P90": 70, "XP54": 68, "93R": 64,
    "AKM": 99, "FCAR": 111, "FAMAS": 52, "M60": 100,
    "Lewis": 114, "SH1900": 200, "Pike": 130,
}

# Fixed display size — image zooms/pans inside this, UI doesn't scale
DISP_W = 900
DISP_H = 700
PANEL_H = 32  # info bar height at bottom
VIEW_H = DISP_H - PANEL_H


def get_latest_input():
    files = []
    for ext in ("*.png", "*.jpg", "*.jpeg"):
        files.extend(glob.glob(os.path.join(INPUT_DIR, ext)))
    return max(files, key=os.path.getmtime) if files else None


class ZoomView:
    """Handles zoom, pan, and coordinate mapping between display and image."""

    def __init__(self, img_w, img_h):
        self.img_w = img_w
        self.img_h = img_h
        self.zoom = 1.0
        # Center of view in image coordinates
        self.cx = img_w / 2
        self.cy = img_h / 2

    def fit(self):
        self.zoom = 1.0
        self.cx = self.img_w / 2
        self.cy = self.img_h / 2

    def zoom_in(self, factor=1.3):
        self.zoom = min(self.zoom * factor, 15.0)

    def zoom_out(self, factor=1.3):
        self.zoom = max(self.zoom / factor, 0.5)
        self._clamp_pan()

    def pan(self, dx_screen, dy_screen):
        # Convert screen pixel movement to image pixel movement
        vis_w, vis_h = self._visible_size()
        self.cx += dx_screen * (vis_w / DISP_W)
        self.cy += dy_screen * (vis_h / VIEW_H)
        self._clamp_pan()

    def zoom_at(self, screen_x, screen_y, zoom_in=True):
        """Zoom toward/away from a screen point."""
        # Convert screen pos to image pos before zoom
        img_x, img_y = self.screen_to_img(screen_x, screen_y)
        if zoom_in:
            self.zoom = min(self.zoom * 1.2, 15.0)
        else:
            self.zoom = max(self.zoom / 1.2, 0.5)
        # Re-center so the image point stays under the cursor
        self.cx = img_x
        self.cy = img_y
        self._clamp_pan()

    def _visible_size(self):
        return self.img_w / self.zoom, self.img_h / self.zoom

    def _clamp_pan(self):
        vis_w, vis_h = self._visible_size()
        self.cx = max(vis_w / 2, min(self.img_w - vis_w / 2, self.cx))
        self.cy = max(vis_h / 2, min(self.img_h - vis_h / 2, self.cy))

    def get_crop_box(self):
        """Returns (x1, y1, x2, y2) in image coords for the visible region."""
        vis_w, vis_h = self._visible_size()
        x1 = max(0, int(self.cx - vis_w / 2))
        y1 = max(0, int(self.cy - vis_h / 2))
        x2 = min(self.img_w, int(self.cx + vis_w / 2))
        y2 = min(self.img_h, int(self.cy + vis_h / 2))
        return x1, y1, x2, y2

    def screen_to_img(self, sx, sy):
        """Convert display coordinates to original image coordinates."""
        vis_w, vis_h = self._visible_size()
        x1 = self.cx - vis_w / 2
        y1 = self.cy - vis_h / 2
        img_x = x1 + (sx / DISP_W) * vis_w
        img_y = y1 + (sy / VIEW_H) * vis_h
        return img_x, img_y

    def img_to_screen(self, ix, iy):
        """Convert image coordinates to display coordinates."""
        vis_w, vis_h = self._visible_size()
        x1 = self.cx - vis_w / 2
        y1 = self.cy - vis_h / 2
        sx = ((ix - x1) / vis_w) * DISP_W
        sy = ((iy - y1) / vis_h) * VIEW_H
        return int(sx), int(sy)


def render(img, clicks, view, weapon, interval_ms, status_msg=""):
    """Render the zoomed view with markers and fixed info panel."""
    x1, y1, x2, y2 = view.get_crop_box()
    crop = img[y1:y2, x1:x2]

    # Scale crop to display size
    disp = cv2.resize(crop, (DISP_W, VIEW_H), interpolation=cv2.INTER_LINEAR)

    # Draw markers
    for i, (ix, iy) in enumerate(clicks):
        sx, sy = view.img_to_screen(ix, iy)
        # Only draw if on screen
        if 0 <= sx < DISP_W and 0 <= sy < VIEW_H:
            if i == 0:
                cv2.circle(disp, (sx, sy), 5, (255, 0, 255), -1)
                cv2.putText(disp, "S", (sx+7, sy+4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 0, 255), 1, cv2.LINE_AA)
            else:
                # Line from previous
                px, py = clicks[i-1]
                psx, psy = view.img_to_screen(px, py)
                cv2.line(disp, (psx, psy), (sx, sy), (0, 255, 255), 1, cv2.LINE_AA)
                cv2.circle(disp, (sx, sy), 3, (0, 0, 255), -1)
                side = 7 if i % 2 == 0 else -14
                cv2.putText(disp, str(i), (sx+side, sy+4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 255, 0), 1, cv2.LINE_AA)

    # Crosshair at center (helps with navigation when zoomed)
    if view.zoom > 1.5:
        cx, cy = DISP_W // 2, VIEW_H // 2
        cv2.line(disp, (cx-10, cy), (cx+10, cy), (80, 80, 80), 1)
        cv2.line(disp, (cx, cy-10), (cx, cy+10), (80, 80, 80), 1)

    # ── Fixed info panel (never scales) ──
    panel = np.zeros((PANEL_H, DISP_W, 3), dtype=np.uint8)
    panel[:] = (20, 20, 25)
    cv2.line(panel, (0, 0), (DISP_W, 0), (40, 40, 50), 1)

    info = f"{len(clicks)} nodes | {weapon} {interval_ms}ms | Zoom: {view.zoom:.1f}x"
    cv2.putText(panel, info, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 190), 1)

    controls = "+/-=zoom  Arrows=pan  F=fit  Z=undo  C=clear  Q=export"
    cv2.putText(panel, controls, (DISP_W - 440, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (100, 100, 110), 1)

    if status_msg:
        cv2.putText(panel, status_msg, (DISP_W // 2 - 60, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 200, 120), 1)

    # Combine
    frame = np.vstack([disp, panel])
    return frame


def run():
    parser = argparse.ArgumentParser(description="Manual recoil pattern builder")
    parser.add_argument("--weapon", default="M11", choices=list(WEAPON_RATES.keys()))
    parser.add_argument("--interval", type=int, default=None, help="Override fire rate ms")
    parser.add_argument("--sens", type=float, default=22.0)
    parser.add_argument("--fov", type=int, default=100)
    parser.add_argument("--ads", action="store_true", help="ADS mode (applies zoom mult)")
    args = parser.parse_args()

    interval_ms = args.interval or WEAPON_RATES.get(args.weapon, 60)
    fov_mod = 90.0 / args.fov
    zoom_mult = 0.75 if args.ads else 1.0
    sens_mod = 22.0 / (args.sens * zoom_mult)
    divisor = interval_ms * fov_mod * sens_mod

    path = get_latest_input()
    if not path:
        print(f"[!] No images in {INPUT_DIR}/")
        return

    name = os.path.basename(path)
    img = cv2.imread(path)
    if img is None:
        print(f"[!] Can't read: {name}")
        return

    img_h, img_w = img.shape[:2]

    print(f"\n[Profile Architect] {name}")
    print(f"  Weapon: {args.weapon} ({interval_ms}ms), Sens: {args.sens}, FOV: {args.fov}")
    print(f"  Divisor: {divisor:.1f}")

    view = ZoomView(img_w, img_h)
    clicks = []  # (img_x, img_y) in original image coordinates
    status = ""

    win = f"Profile Architect [{args.weapon}] - click holes in order"
    cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)

    # Mouse callback
    def on_mouse(event, x, y, flags, param):
        nonlocal status
        if event == cv2.EVENT_LBUTTONDOWN and y < VIEW_H:
            img_x, img_y = view.screen_to_img(x, y)
            img_x = max(0, min(img_w - 1, img_x))
            img_y = max(0, min(img_h - 1, img_y))
            clicks.append((img_x, img_y))
            status = f"#{len(clicks)} placed"
            cv2.imshow(win, render(img, clicks, view, args.weapon, interval_ms, status))
        elif event == cv2.EVENT_MOUSEWHEEL:
            if flags > 0:
                view.zoom_at(x, y, zoom_in=True)
            else:
                view.zoom_at(x, y, zoom_in=False)
            cv2.imshow(win, render(img, clicks, view, args.weapon, interval_ms))

    cv2.setMouseCallback(win, on_mouse)
    cv2.imshow(win, render(img, clicks, view, args.weapon, interval_ms))

    PAN_SPEED = 40

    while True:
        key = cv2.waitKey(30) & 0xFF

        if key == ord('q') or key == 13:  # Q / Enter
            break
        elif key == ord('c'):
            clicks.clear()
            status = "Cleared"
        elif key == ord('z') and clicks:
            clicks.pop()
            status = f"Undo → {len(clicks)}"
        elif key == ord('f'):
            view.fit()
            status = "Fit"
        elif key in (ord('+'), ord('=')):
            view.zoom_in()
        elif key == ord('-'):
            view.zoom_out()
        elif key == 81 or key == 2:  # Left arrow
            view.pan(-PAN_SPEED, 0)
        elif key == 83 or key == 3:  # Right arrow
            view.pan(PAN_SPEED, 0)
        elif key == 82 or key == 0:  # Up arrow
            view.pan(0, -PAN_SPEED)
        elif key == 84 or key == 1:  # Down arrow
            view.pan(0, PAN_SPEED)
        elif key == 255:
            continue  # no key pressed
        else:
            continue

        cv2.imshow(win, render(img, clicks, view, args.weapon, interval_ms, status))
        status = ""

    cv2.destroyAllWindows()

    if len(clicks) < 2:
        print("[!] Need at least 2 clicks")
        return

    # ── Export ──
    out_name = os.path.splitext(name)[0] + f"_{args.weapon}_profile.txt"
    out_path = os.path.join(OUTPUT_DIR, out_name)

    with open(out_path, "w") as f:
        f.write("0.00, 0.00\n")
        for i in range(1, len(clicks)):
            dx_px = clicks[i][0] - clicks[i-1][0]
            dy_px = clicks[i][1] - clicks[i-1][1]
            vx = round(-dx_px / divisor, 4)
            vy = round(-dy_px / divisor, 4)
            f.write(f"{vx}, {vy}\n")

    print(f"\n[Done] {len(clicks)} nodes → {out_path}")
    print(f"  Import → set {args.weapon} preset → Scale 1.0")


if __name__ == "__main__":
    run()