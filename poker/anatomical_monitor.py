import time
from pathlib import Path

import cv2
import numpy as np

from .env import ACTION_LABELS, ACTION_COUNT


class PokerAnatomicalMonitor:
    """Four-fly OpenCV activity monitor based directly on FlyIsaac's
    `isaac_v3/neuron_monitor.py` visual language.

    Differences from Isaac:
    - poker currently uses a compact MLP, not the ~166k-neuron MaleCNS runtime;
    - the anatomical base cloud is a fixed XZ reference extracted from the
      user's real FlyIsaac Anatomical Activity Monitor screenshot;
    - live MLP activations are mapped onto local clusters in that reference
      cloud so activity remains spatially stable and does not jump randomly.
    """

    def __init__(
        self,
        title="FlyPoker | 4x Anatomical Activity Monitor",
        width=1920,
        height=1120,
        update_hz=15.0,
        enabled=True,
    ):
        self.title = str(title)
        self.width = int(width)
        self.height = int(height)
        self.update_interval = 1.0 / max(1.0, float(update_hz))
        self.enabled = bool(enabled)
        self._opened = False
        self._last_update = 0.0

        self._anatomy_cache = {}
        self._unit_maps = {}
        self._spike_glow = [None] * 4
        self.positions_uv = self._load_reference_anatomy()

    # ------------------------------------------------------------------
    # Shared FlyIsaac-style drawing helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _label(canvas, text, x, y, scale=0.48, thickness=1, color=(235, 235, 235)):
        cv2.putText(
            canvas,
            str(text),
            (int(x), int(y)),
            cv2.FONT_HERSHEY_SIMPLEX,
            float(scale),
            tuple(int(c) for c in color),
            int(thickness),
            cv2.LINE_AA,
        )

    @staticmethod
    def _panel(canvas, x, y, w, h, title=None, title_scale=0.46):
        cv2.rectangle(canvas, (x, y), (x + w, y + h), (52, 56, 66), 1)
        if title:
            cv2.rectangle(canvas, (x, y - 21), (x + min(w, 300), y - 2), (24, 26, 34), -1)
            PokerAnatomicalMonitor._label(
                canvas, title, x + 7, y - 7, title_scale, 1, (220, 225, 235)
            )

    @staticmethod
    def _bar(canvas, x, y, w, label, value, chosen=False):
        value = float(np.clip(value, 0.0, 1.0))
        cv2.rectangle(canvas, (x, y), (x + w, y + 13), (55, 58, 65), 1)
        fill = int(round((w - 2) * value))
        if fill > 0:
            color = (255, 245, 196) if chosen else (110, 140, 210)
            cv2.rectangle(canvas, (x + 1, y + 1), (x + 1 + fill, y + 12), color, -1)
        PokerAnatomicalMonitor._label(
            canvas,
            f"{label:<8s} {value:4.2f}",
            x + w + 7,
            y + 12,
            0.35,
            1,
            (248, 248, 248) if chosen else (172, 178, 188),
        )

    def open(self):
        if not self.enabled or self._opened:
            return
        cv2.namedWindow(self.title, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.title, self.width, self.height)
        self._opened = True
        blank = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        self._label(blank, "FlyPoker anatomical monitor - waiting for activity", 24, 42, 0.82, 2)
        cv2.imshow(self.title, blank)
        cv2.waitKey(1)

    # ------------------------------------------------------------------
    # Anatomy: fixed reference shape + FlyIsaac density rendering
    # ------------------------------------------------------------------
    def _load_reference_anatomy(self):
        asset = Path(__file__).resolve().parent.parent / "assets" / "malecns_reference_xz.npz"
        if asset.exists():
            try:
                with np.load(asset) as data:
                    uv = np.asarray(data["uv"], dtype=np.float32)
                if uv.ndim == 2 and uv.shape[1] == 2 and len(uv) > 1000:
                    return np.clip(uv, 0.0, 1.0)
            except Exception:
                pass
        return self._fallback_reference(50000)

    @staticmethod
    def _fallback_reference(n):
        """Fallback only. The packaged project normally loads the reference
        projection generated from the user's real FlyIsaac monitor image."""
        rng = np.random.default_rng(3712026)
        chunks = []
        chunks.append(rng.normal((0.50, 0.15), (0.09, 0.075), size=(int(n * 0.18), 2)))
        chunks.append(rng.normal((0.44, 0.34), (0.085, 0.10), size=(int(n * 0.13), 2)))
        chunks.append(rng.normal((0.56, 0.34), (0.085, 0.10), size=(int(n * 0.13), 2)))
        chunks.append(rng.normal((0.50, 0.49), (0.055, 0.09), size=(int(n * 0.09), 2)))
        chunks.append(rng.normal((0.25, 0.79), (0.19, 0.055), size=(int(n * 0.19), 2)))
        chunks.append(rng.normal((0.75, 0.79), (0.19, 0.055), size=(int(n * 0.19), 2)))
        left = n - sum(len(c) for c in chunks)
        chunks.append(rng.normal((0.50, 0.80), (0.16, 0.05), size=(left, 2)))
        return np.clip(np.concatenate(chunks, axis=0), 0.0, 1.0).astype(np.float32)

    def _coords(self, x, y, w, h, indices=None):
        uv = self.positions_uv if indices is None else self.positions_uv[np.asarray(indices, dtype=np.int64)]
        px = x + 8 + uv[:, 0] * max(1, w - 16)
        py = y + 8 + uv[:, 1] * max(1, h - 16)
        return np.column_stack([px, py]).astype(np.int32)

    def _anatomy_background(self, w, h):
        key = (int(w), int(h))
        cached = self._anatomy_cache.get(key)
        if cached is not None:
            return cached.copy()

        # Exact background recipe from the Isaac monitor: dark warm gradient,
        # density histogram, Gaussian blur, BONE map, contour levels and soma dots.
        bg = np.zeros((h, w, 3), dtype=np.uint8)
        yy = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
        xx = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :]
        vign = 1.0 - 0.55 * ((xx - 0.5) ** 2 + (yy - 0.5) ** 2)
        bg[:, :, 0] = np.asarray(18 + 10 * yy + 8 * vign, dtype=np.uint8)
        bg[:, :, 1] = np.asarray(14 + 8 * yy + 6 * vign, dtype=np.uint8)
        bg[:, :, 2] = np.asarray(20 + 16 * yy + 10 * vign, dtype=np.uint8)

        pts = self._coords(0, 0, w, h)
        hist = np.zeros((h, w), dtype=np.float32)
        stride = max(1, len(pts) // 45000)
        for px, py in pts[::stride]:
            if 0 <= px < w and 0 <= py < h:
                hist[py, px] += 1.0
        hist = cv2.GaussianBlur(hist, (0, 0), 8.0)
        if hist.max() > 0:
            hist /= hist.max()

        cloud = cv2.applyColorMap(
            np.asarray(np.clip(hist * 255.0, 0, 255), dtype=np.uint8),
            cv2.COLORMAP_BONE,
        )
        bg = cv2.addWeighted(bg, 0.82, cloud, 0.28, 0.0)

        for lvl, col in [
            (0.15, (60, 72, 96)),
            (0.32, (76, 88, 116)),
            (0.55, (108, 126, 164)),
        ]:
            mask = np.asarray(hist >= lvl, dtype=np.uint8) * 255
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(bg, contours, -1, col, 1, cv2.LINE_AA)

        # Denser, slightly brighter soma field than V7 so the base anatomy is
        # readable even when the MLP is quiet.
        stride = max(1, len(pts) // 38000)
        for px, py in pts[::stride]:
            cv2.circle(bg, (int(px), int(py)), 1, (106, 104, 118), -1, cv2.LINE_AA)

        cv2.rectangle(bg, (0, 0), (w - 1, h - 1), (52, 56, 66), 1)
        self._anatomy_cache[key] = bg
        return bg.copy()

    def _map_units(self, fly_idx, unit_count):
        key = (fly_idx, unit_count)
        if key in self._unit_maps:
            return self._unit_maps[key]

        # Stable mapping: every MLP unit owns a local anatomical patch. This is
        # deterministic, so the same unit always lights up the same region.
        maps = []
        n = len(self.positions_uv)
        for i in range(unit_count):
            anchor = (i * 1297 + fly_idx * 733) % n
            center = self.positions_uv[anchor]
            d = ((self.positions_uv - center) ** 2).sum(axis=1)
            k = min(84, n)
            pool = np.argpartition(d, k - 1)[:k]
            maps.append(np.asarray(pool, dtype=np.int64))
        self._unit_maps[key] = maps
        return maps

    def _activation_to_glow(self, fly_idx, acts):
        acts = np.asarray(acts, dtype=np.float32).reshape(-1)
        if self._spike_glow[fly_idx] is None:
            self._spike_glow[fly_idx] = np.zeros(len(self.positions_uv), dtype=np.float32)
        glow = self._spike_glow[fly_idx]
        glow *= np.float32(0.78)  # same temporal feel as Isaac

        maps = self._map_units(fly_idx, len(acts))
        for i, v in enumerate(acts):
            mag = float(min(1.0, abs(v)))
            if mag < 0.10:
                continue
            glow[maps[i]] = np.maximum(glow[maps[i]], mag)
        return glow

    def _draw_anatomy_activity(self, panel, fly_idx, acts):
        h, w = panel.shape[:2]
        glowvals = self._activation_to_glow(fly_idx, acts)
        active = np.flatnonzero(glowvals >= 0.14)
        if active.size:
            if active.size > 12000:
                order = np.argpartition(glowvals[active], -12000)[-12000:]
                active = active[order]
            pts = self._coords(0, 0, w, h, active)
            vals = glowvals[active]
            glow = np.zeros_like(panel)
            dots = np.zeros_like(panel)
            for (px, py), v in zip(pts, vals):
                radius = 3 if v < 0.45 else (5 if v < 0.8 else 7)
                cv2.circle(glow, (int(px), int(py)), radius, (22, 48, 110), -1, cv2.LINE_AA)
                cv2.circle(
                    dots,
                    (int(px), int(py)),
                    1 + int(v > 0.55),
                    (255, 245, 235),
                    -1,
                    cv2.LINE_AA,
                )
            glow = cv2.GaussianBlur(glow, (0, 0), 5.0)
            panel[:] = cv2.addWeighted(panel, 1.0, glow, 0.70, 0.0)
            panel[:] = cv2.addWeighted(panel, 1.0, dots, 1.0, 0.0)

        return int(np.count_nonzero(np.abs(np.asarray(acts)) >= 0.68)), int(active.size)

    # ------------------------------------------------------------------
    # Poker-specific information panels
    # ------------------------------------------------------------------
    @staticmethod
    def _softmax(out, legal_actions=None):
        out = np.asarray(out, dtype=np.float32).reshape(-1)
        if out.size == 0:
            return np.zeros(ACTION_COUNT, dtype=np.float32)
        if out.size < ACTION_COUNT:
            out = np.pad(out, (0, ACTION_COUNT - out.size), constant_values=-1e9)
        out = out[:ACTION_COUNT]
        if legal_actions is not None:
            legal = [int(a) for a in legal_actions if 0 <= int(a) < ACTION_COUNT]
            masked = np.full(ACTION_COUNT, -1e9, dtype=np.float32)
            for a in legal:
                masked[a] = out[a]
            out = masked
        finite = np.isfinite(out) & (out > -1e8)
        if not np.any(finite):
            return np.zeros(ACTION_COUNT, dtype=np.float32)
        m = float(np.max(out[finite]))
        e = np.zeros(ACTION_COUNT, dtype=np.float32)
        e[finite] = np.exp(out[finite] - m)
        total = float(np.sum(e))
        return e / max(1e-9, total)

    @staticmethod
    def _seat_position(seat, button):
        if seat == button:
            return "BTN"
        if seat == (button + 1) % 4:
            return "SB"
        if seat == (button + 2) % 4:
            return "BB"
        return "UTG"

    def _state_for_fly(self, fly_idx, snapshot):
        if not snapshot:
            return {
                "hole": ["--", "--"], "board": [], "pot": 0, "stack": 0,
                "to_call": 0, "position": "?", "street": "?", "active": 0,
                "current_bet": 0, "last_raise_size": 10, "all_in": False,
                "actions": ["-"] * 4, "legal_actions": [],
            }
        p = snapshot["players"][fly_idx]
        to_call = max(0, int(snapshot.get("current_bet", 0)) - int(p.get("street_contrib", 0)))
        actions = []
        for q in snapshot.get("players", []):
            name = q.get("last_action", "-")
            amt = int(q.get("last_amount", 0) or 0)
            actions.append(f"{name} +{amt}" if amt > 0 else name)
        return {
            "hole": list(p.get("hole", [])),
            "board": list(snapshot.get("board", [])),
            "pot": int(snapshot.get("pot", 0)),
            "stack": int(p.get("stack", 0)),
            "to_call": to_call,
            "position": self._seat_position(fly_idx, int(snapshot.get("button", 0))),
            "street": str(snapshot.get("street", "?")),
            "active": sum(1 for q in snapshot.get("players", []) if not q.get("folded", False)),
            "current_bet": int(snapshot.get("current_bet", 0)),
            "last_raise_size": int(snapshot.get("last_raise_size", 10)),
            "all_in": bool(p.get("all_in", False)),
            "actions": actions,
            "legal_actions": list(p.get("legal_actions", [])),
        }

    @staticmethod
    def _raise_step(state):
        return int(state.get("last_raise_size", 10))

    def _poker_input_panel(self, canvas, rect, state):
        x, y, w, h = rect
        self._panel(canvas, x, y, w, h, title="POKER INPUT")

        hole = " ".join(state["hole"]) if state["hole"] else "-- --"
        board = list(state["board"]) + ["--"] * (5 - len(state["board"]))
        board = " ".join(board[:5])

        left_rows = [
            ("HOLE", hole),
            ("BOARD", board),
            ("STREET", state["street"].upper()),
            ("POSITION", state["position"]),
            ("ACTIVE", f"{state['active']}/4"),
        ]
        right_rows = [
            ("POT", str(state["pot"])),
            ("STACK", str(state["stack"])),
            ("TO CALL", str(state["to_call"])),
            ("CUR BET", str(state["current_bet"])),
            ("MIN RAISE", f"+{self._raise_step(state)}"),
        ]

        split = x + int(w * 0.56)
        yy = y + 23
        for label, value in left_rows:
            self._label(canvas, f"{label:<8}", x + 8, yy, 0.31, 1, (160, 168, 180))
            self._label(canvas, value, x + 69, yy, 0.34, 1, (238, 240, 244))
            yy += 16

        yy = y + 23
        for label, value in right_rows:
            self._label(canvas, f"{label:<9}", split, yy, 0.29, 1, (160, 168, 180))
            self._label(canvas, value, split + 70, yy, 0.33, 1, (238, 240, 244))
            yy += 16

        actions_y = y + 111
        self._label(canvas, "LAST ACTIONS", x + 8, actions_y, 0.33, 1, (220, 225, 235))
        for i, action in enumerate(state["actions"][:4]):
            ax = x + 8 + (i % 2) * max(108, w // 2)
            ay = actions_y + 17 + (i // 2) * 16
            shown = action if len(action) <= 18 else action[:17] + "..."
            self._label(canvas, f"F{i+1}: {shown}", ax, ay, 0.29, 1, (190, 195, 204))

    def _status_panel(self, canvas, rect, fly_idx, acts, out, fitness, state):
        x, y, w, h = rect
        self._panel(canvas, x, y, w, h, title="STATUS / PERFORMANCE")
        probs = self._softmax(out, state.get("legal_actions"))
        choice = int(np.argmax(probs)) if np.any(probs) else -1
        peak = float(np.max(np.abs(acts))) if len(acts) else 0.0
        mean = float(np.mean(np.abs(acts))) if len(acts) else 0.0
        decision = ACTION_LABELS[choice] if 0 <= choice < ACTION_COUNT else "-"
        if state.get("all_in"):
            decision = "ALL-IN / WAIT"
        lines = [
            f"fly: {fly_idx+1}",
            f"fitness: {fitness:+.2f} bb/100",
            f"active units: {int(np.count_nonzero(np.abs(acts) >= .15))}/{len(acts)}",
            f"mean/peak: {mean:.3f} / {peak:.3f}",
            f"decision: {decision}",
        ]
        yy = y + 23
        for line in lines:
            self._label(canvas, line, x + 8, yy, 0.34, 1)
            yy += 17

    def _decoder_panel(self, canvas, rect, out, state):
        x, y, w, h = rect
        self._panel(canvas, x, y, w, h, title="POKER DECODER - 14 ACTIONS")
        legal = set(int(a) for a in state.get("legal_actions", []))
        probs = self._softmax(out, legal)
        choice = int(np.argmax(probs)) if np.any(probs) else -1

        # Two columns x seven actions keeps all bet sizes visible without
        # stealing space from the main anatomical view.
        col_gap = 8
        col_w = max(100, (w - 20 - col_gap) // 2)
        row_h = max(18, min(23, (h - 30) // 7))
        for i, name in enumerate(ACTION_LABELS):
            col = i // 7
            row = i % 7
            xx = x + 8 + col * (col_w + col_gap)
            yy = y + 21 + row * row_h
            is_legal = i in legal
            label = name if is_legal else f"{name} X"
            # Compact inline bar because the original FlyIsaac _bar layout is
            # too wide for 14 actions in a mini monitor.
            self._label(
                canvas, label, xx, yy + 10, 0.28, 1,
                (238,238,238) if is_legal else (90,94,102),
            )
            bar_x = xx + 78
            bar_w = max(18, col_w - 82)
            cv2.rectangle(canvas, (bar_x, yy), (bar_x + bar_w, yy + 10), (55,58,65), 1)
            value = float(probs[i]) if i < len(probs) else 0.0
            fill = int((bar_w - 2) * np.clip(value, 0.0, 1.0))
            if fill > 0:
                color = (255,245,196) if i == choice else (110,140,210)
                cv2.rectangle(canvas, (bar_x+1, yy+1), (bar_x+1+fill, yy+9), color, -1)

    # ------------------------------------------------------------------
    # One mini monitor / four-panel composition
    # ------------------------------------------------------------------
    def _mini_monitor(self, fly_idx, brain, obs, fitness, snapshot, w, h):
        canvas = np.zeros((h, w, 3), dtype=np.uint8)
        canvas[:, :, 0] = 10
        canvas[:, :, 1] = 10
        canvas[:, :, 2] = 14

        try:
            dbg = brain.debug_activations(obs)
        except Exception:
            dbg = {}
        h1 = np.asarray(dbg.get("hidden_1", []), dtype=np.float32)
        h2 = np.asarray(dbg.get("hidden_2", []), dtype=np.float32)
        out = np.asarray(dbg.get("output", []), dtype=np.float32)
        acts = np.concatenate([h1, h2]) if h1.size or h2.size else np.zeros(1, dtype=np.float32)
        state = self._state_for_fly(fly_idx, snapshot)

        self._label(canvas, f"FLY {fly_idx+1} | ANATOMICAL ACTIVITY 2.0", 12, 24, 0.66, 2)
        self._label(
            canvas,
            "FlyIsaac density/glow renderer | fixed XZ anatomy reference | live poker MLP activity",
            12,
            44,
            0.33,
            1,
            (172, 178, 188),
        )

        # No fake 7x14 panel and no activity-over-time raster. The space goes to
        # a much larger main anatomical view and useful poker state.
        ax, ay = 10, 72
        aw = int(w * 0.67)
        right_x = aw + 22
        right_w = w - right_x - 10
        main_h = h - ay - 10

        self._panel(canvas, ax, ay, aw, main_h, title="MAIN VIEW (XZ)")
        anatomy = self._anatomy_background(aw, main_h)
        hot_units, mapped_points = self._draw_anatomy_activity(anatomy, fly_idx, acts)
        canvas[ay:ay + main_h, ax:ax + aw] = anatomy
        self._label(canvas, f"high-activity units: {hot_units}", ax + 10, ay + 22, 0.34, 1, (232, 238, 245))
        self._label(canvas, f"lit anatomy points: {mapped_points}", ax + 175, ay + 22, 0.34, 1, (232, 238, 245))
        self._label(canvas, f"MLP units: {len(acts)}", ax + 365, ay + 22, 0.34, 1, (232, 238, 245))

        # Right column = real state + status + decoder.
        input_h = 165
        status_h = 92
        gap = 24
        input_rect = (right_x, ay, right_w, input_h)
        status_y = ay + input_h + gap
        status_rect = (right_x, status_y, right_w, status_h)
        decoder_y = status_y + status_h + gap
        decoder_h = ay + main_h - decoder_y
        decoder_rect = (right_x, decoder_y, right_w, decoder_h)

        self._poker_input_panel(canvas, input_rect, state)
        self._status_panel(canvas, status_rect, fly_idx, acts, out, fitness, state)
        self._decoder_panel(canvas, decoder_rect, out, state)
        return canvas

    def render(self, brains, observations, fitness=None, generation=0, hand=0, snapshot=None):
        canvas = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        canvas[:, :, 0] = 10
        canvas[:, :, 1] = 10
        canvas[:, :, 2] = 14
        self._label(canvas, "FlyPoker | 4x Anatomical Activity Monitor", 18, 30, 0.90, 2)
        self._label(
            canvas,
            f"generation {generation} | hand {hand} | renderer adapted from FlyIsaac isaac_v3/neuron_monitor.py",
            18,
            55,
            0.45,
            1,
            (172, 178, 188),
        )

        gap = 12
        top = 76
        pw = (self.width - 3 * gap) // 2
        ph = (self.height - top - 3 * gap) // 2
        pos = [
            (gap, top),
            (2 * gap + pw, top),
            (gap, top + gap + ph),
            (2 * gap + pw, top + gap + ph),
        ]
        fit = fitness or [0.0] * 4
        for i, (x, y) in enumerate(pos):
            mini = self._mini_monitor(
                i,
                brains[i],
                observations[i],
                float(fit[i]),
                snapshot,
                pw,
                ph,
            )
            canvas[y:y + ph, x:x + pw] = mini
            cv2.rectangle(canvas, (x, y), (x + pw, y + ph), (52, 56, 66), 1)
        return canvas

    def update(self, brains, observations, fitness=None, generation=0, hand=0, snapshot=None):
        if not self.enabled:
            return
        if not self._opened:
            self.open()
        now = time.perf_counter()
        if now - self._last_update < self.update_interval:
            return
        self._last_update = now
        cv2.imshow(
            self.title,
            self.render(brains, observations, fitness, generation, hand, snapshot=snapshot),
        )
        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            self.close()

    def reset(self):
        for i in range(4):
            if self._spike_glow[i] is not None:
                self._spike_glow[i].fill(0.0)

    def close(self):
        if not self._opened:
            return
        try:
            cv2.destroyWindow(self.title)
            cv2.waitKey(1)
        except Exception:
            pass
        self._opened = False
