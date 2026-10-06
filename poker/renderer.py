from pathlib import Path
from collections import deque
import time

from .anatomical_monitor import PokerAnatomicalMonitor
from .equity import EquityCalculator
from .evaluator import evaluate_best


class PygameRenderer:
    """Large polished Pygame game UI + separate OpenCV Anatomical Activity Monitor."""

    BASE_W = 1600
    BASE_H = 1000

    def __init__(self, width=BASE_W, height=BASE_H, delay_ms=140):
        import pygame
        self.pg = pygame
        pygame.init()

        self.width = int(width)
        self.height = int(height)
        self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
        pygame.display.set_caption("FlyPoker — Game")

        # Draw everything to a fixed logical canvas and scale it to the real window.
        # This keeps the UI proportional when macOS resizes the window slightly.
        self.canvas = pygame.Surface((self.BASE_W, self.BASE_H)).convert()
        self.draw = self.canvas

        self.font = pygame.font.SysFont("Arial", 24)
        self.small = pygame.font.SysFont("Arial", 18)
        self.tiny = pygame.font.SysFont("Arial", 14)
        self.micro = pygame.font.SysFont("Arial", 12)
        self.big = pygame.font.SysFont("Arial", 34, bold=True)
        self.hero = pygame.font.SysFont("Arial", 42, bold=True)
        self.amount_font = pygame.font.SysFont("Arial", 28, bold=True)

        self.delay_ms = int(delay_ms)
        self.default_delay_ms = int(delay_ms)
        self.fast = False
        self.paused = False
        self.closed = False

        self.generation = 0
        self.hand_index = 0
        self.fitness = None
        self.bust_rate = None
        self.session_index = 0
        self.table_wins = [0, 0, 0, 0]
        self._table_chips = 4000
        self.mode_text = "TRAINING • TABLE SESSION • LEARNING ON"
        self.agent_labels = [f"FLY {i+1}" for i in range(4)]
        self.assets = self._load_cards()
        self.card_size = (96, 138)

        self.buttons = {}
        self._current_actor = None

        self.monitor = PokerAnatomicalMonitor()
        self.monitor.open()

        self.equity = EquityCalculator(preflop_samples=3000)
        self._equity_info = {
            "equity": [0.0] * 4,
            "favorite": [],
            "final_winners": [],
        }
        self._winner_hand_names = {}
        self.win_history = deque(maxlen=6)
        self._last_history_key = None
        self._result_popup = None
        self.result_popup_hold_ms = 900

    # ------------------------------------------------------------------
    # Basics
    # ------------------------------------------------------------------
    def _load_cards(self):
        assets = {}
        base = Path(__file__).resolve().parent.parent / "assets" / "cards"
        for path in base.glob("*.png"):
            try:
                assets[path.stem.upper()] = self.pg.image.load(str(path)).convert_alpha()
            except Exception:
                pass
        return assets

    def set_meta(
        self,
        generation,
        hand_index,
        fitness=None,
        bust_rate=None,
        session_index=None,
        table_wins=None,
    ):
        self.generation = generation
        self.hand_index = hand_index
        self.fitness = fitness
        self.bust_rate = bust_rate
        if session_index is not None:
            self.session_index = int(session_index)
        if table_wins is not None:
            self.table_wins = list(table_wins)

    def set_mode_text(self, text):
        self.mode_text = str(text)

    def _agent_label(self, seat):
        if 0 <= int(seat) < len(self.agent_labels):
            return self.agent_labels[int(seat)]
        return f"FLY {int(seat)+1}"

    def _agent_short(self, seat):
        label = self._agent_label(seat)
        return "BOT" if label.upper().startswith("BOT") else f"F{int(seat)+1}"

    def _txt(self, text, x, y, *, big=False, hero=False, small=False, tiny=False, micro=False,
             color=(235, 235, 235), center=False):
        if hero:
            f = self.hero
        elif big:
            f = self.big
        elif small:
            f = self.small
        elif tiny:
            f = self.tiny
        elif micro:
            f = self.micro
        else:
            f = self.font

        surf = f.render(str(text), True, color)
        rect = surf.get_rect()
        if center:
            rect.center = (int(x), int(y))
        else:
            rect.topleft = (int(x), int(y))
        self.draw.blit(surf, rect)
        return rect

    def _panel(self, rect, fill=(22, 31, 28), outline=(87, 102, 92), radius=16, shadow=True):
        pg = self.pg
        if shadow:
            shadow_rect = rect.move(0, 5)
            pg.draw.rect(self.draw, (5, 10, 9), shadow_rect, border_radius=radius)
        pg.draw.rect(self.draw, fill, rect, border_radius=radius)
        pg.draw.rect(self.draw, outline, rect, 1, border_radius=radius)

    def _pill(self, text, x, y, w, h, fill, outline=(110, 120, 113), text_color=(240, 238, 229)):
        pg = self.pg
        rect = pg.Rect(x, y, w, h)
        pg.draw.rect(self.draw, fill, rect, border_radius=h // 2)
        pg.draw.rect(self.draw, outline, rect, 1, border_radius=h // 2)
        self._txt(text, rect.centerx, rect.centery, small=True, color=text_color, center=True)
        return rect

    def _logical_mouse(self, pos):
        if self.width <= 0 or self.height <= 0:
            return pos
        return (
            pos[0] * self.BASE_W / self.width,
            pos[1] * self.BASE_H / self.height,
        )

    # ------------------------------------------------------------------
    # Winner / hand labels
    # ------------------------------------------------------------------
    @staticmethod
    def _hand_name(score):
        """Human-readable Hold'em category for a best-five evaluator score."""
        if not score:
            return "UNKNOWN HAND"
        category = int(score[0])
        if category == 8:
            # An ace-high straight flush is a royal flush.
            return "ROYAL FLUSH" if len(score) > 1 and int(score[1]) == 14 else "STRAIGHT FLUSH"
        return {
            7: "FOUR OF A KIND",
            6: "FULL HOUSE",
            5: "FLUSH",
            4: "STRAIGHT",
            3: "THREE OF A KIND",
            2: "TWO PAIR",
            1: "ONE PAIR",
            0: "HIGH CARD",
        }.get(category, "UNKNOWN HAND")

    def _update_winner_hand_names(self, env, snap):
        """Compute showdown labels for spectator UI only."""
        self._winner_hand_names = {}
        winners = list(snap.get("winners", []))
        if not winners:
            return

        # evaluate_best needs 5+ cards. If a hand ended before enough board
        # cards were dealt, the correct explanation is that everyone folded.
        for seat in winners:
            cards = list(env.seats[seat].hole) + list(env.board)
            if len(cards) >= 5:
                try:
                    self._winner_hand_names[int(seat)] = self._hand_name(evaluate_best(cards))
                except Exception:
                    pass

    @staticmethod
    def _payouts_from_side_pots(snap):
        """Actual chips awarded to each seat from main/side pots."""
        payouts = [0, 0, 0, 0]
        for pot in snap.get("side_pots", []) or []:
            amount = int(pot.get("amount", 0) or 0)
            winners = [int(i) for i in (pot.get("winners", []) or [])]
            if amount <= 0 or not winners:
                continue

            share, rem = divmod(amount, len(winners))
            for seat in winners:
                if 0 <= seat < 4:
                    payouts[seat] += share

            # Match env.py remainder rule exactly.
            for seat in sorted(winners)[:rem]:
                if 0 <= seat < 4:
                    payouts[seat] += 1
        return payouts

    def _capture_finished_hand(self, snap):
        """Store one recent-win entry per completed hand and prepare popup."""
        winners = [int(i) for i in (snap.get("winners", []) or [])]
        hand_finished = snap.get("current_actor") is None and bool(winners)

        if not hand_finished:
            self._result_popup = None
            return False

        payouts = self._payouts_from_side_pots(snap)
        rows = []
        for seat in winners:
            hand_name = self._winner_hand_names.get(seat, "UNCONTESTED")
            rows.append({
                "seat": seat,
                "label": self._agent_label(seat),
                "short": self._agent_short(seat),
                "amount": int(payouts[seat]),
                "hand": hand_name,
            })

        hand_key = (
            int(self.generation),
            int(snap.get("hand_no", self.hand_index) or 0),
        )

        self._result_popup = {
            "key": hand_key,
            "rows": rows,
            "split": len(rows) > 1,
            "session_over": bool(snap.get("session_over", False)),
            "session_winner": snap.get("session_winner"),
            "table_chips": int(snap.get("table_chips", 4000) or 4000),
            "session_no": int(snap.get("session_no", self.session_index) or 0),
        }

        if hand_key != self._last_history_key:
            self._last_history_key = hand_key
            self.win_history.appendleft({
                "hand_no": int(snap.get("hand_no", self.hand_index) or 0),
                "rows": [dict(row) for row in rows],
            })

        return True

    # ------------------------------------------------------------------
    # Speed controls
    # ------------------------------------------------------------------
    def _set_delay(self, value):
        self.delay_ms = max(0, min(2500, int(value)))
        self.fast = False

    def _button_action(self, name):
        if name == "pause":
            self.paused = not self.paused
        elif name == "slower":
            self._set_delay(self.delay_ms + 100)
        elif name == "faster":
            self._set_delay(self.delay_ms - 100)
        elif name == "normal":
            self._set_delay(self.default_delay_ms)
        elif name == "fast":
            self.fast = not self.fast

    def _events(self):
        pg = self.pg
        for event in pg.event.get():
            if event.type == pg.QUIT:
                self.closed = True

            elif event.type == pg.VIDEORESIZE:
                self.width, self.height = event.w, event.h
                self.screen = pg.display.set_mode((event.w, event.h), pg.RESIZABLE)

            elif event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = self._logical_mouse(event.pos)
                for name, rect in self.buttons.items():
                    if rect.collidepoint(mx, my):
                        self._button_action(name)
                        break

            elif event.type == pg.KEYDOWN:
                if event.key == pg.K_SPACE:
                    self._button_action("pause")
                elif event.key == pg.K_f:
                    self._button_action("fast")
                elif event.key in (pg.K_s, pg.K_EQUALS, pg.K_PLUS, pg.K_UP):
                    self._button_action("slower")
                elif event.key in (pg.K_MINUS, pg.K_DOWN):
                    self._button_action("faster")
                elif event.key == pg.K_0:
                    self._button_action("normal")
                elif event.key == pg.K_ESCAPE:
                    self.closed = True

    def _draw_controls(self):
        pg = self.pg
        footer = pg.Rect(18, self.BASE_H - 58, self.BASE_W - 36, 42)
        self._panel(footer, fill=(16, 22, 21), outline=(65, 79, 73), radius=12, shadow=False)

        x = footer.x + 12
        y = footer.y + 7
        specs = [
            ("pause", "PAUSE" if not self.paused else "RESUME", 104),
            ("slower", "SLOWER", 104),
            ("faster", "FASTER", 104),
            ("normal", "NORMAL", 104),
            ("fast", "FAST", 84),
        ]
        self.buttons = {}
        for name, label, w in specs:
            rect = pg.Rect(x, y, w, 28)
            self.buttons[name] = rect
            active = (name == "pause" and self.paused) or (name == "fast" and self.fast)
            fill = (132, 96, 46) if active else (34, 43, 40)
            edge = (178, 136, 72) if active else (83, 100, 93)
            pg.draw.rect(self.draw, fill, rect, border_radius=8)
            pg.draw.rect(self.draw, edge, rect, 1, border_radius=8)
            self._txt(label, rect.centerx, rect.centery, tiny=True, color=(246, 241, 229), center=True)
            x += w + 8

        mode = "FAST" if self.fast else f"{self.delay_ms} ms / decision"
        self._txt(f"Speed: {mode}", x + 12, footer.y + 12, small=True, color=(211, 201, 184))
        self._txt(
            "SPACE pause  •  S / ↑ slower  •  ↓ faster  •  0 normal  •  F fast",
            footer.right - 470,
            footer.y + 14,
            tiny=True,
            color=(137, 151, 143),
        )

    # ------------------------------------------------------------------
    # Cards / chips
    # ------------------------------------------------------------------
    def _card(self, text, x, y):
        pg = self.pg
        shadow = pg.Rect(x + 4, y + 5, *self.card_size)
        pg.draw.rect(self.draw, (4, 8, 7), shadow, border_radius=10)

        img = self.assets.get(text.upper())
        if img is not None:
            scaled = pg.transform.smoothscale(img, self.card_size)
            self.draw.blit(scaled, (x, y))
            return

        rect = pg.Rect(x, y, *self.card_size)
        pg.draw.rect(self.draw, (245, 245, 245), rect, border_radius=10)
        pg.draw.rect(self.draw, (25, 25, 25), rect, 2, border_radius=10)

    def _empty_card(self, x, y):
        pg = self.pg
        rect = pg.Rect(x, y, *self.card_size)
        pg.draw.rect(self.draw, (18, 61, 44), rect, border_radius=10)
        pg.draw.rect(self.draw, (72, 113, 91), rect, 2, border_radius=10)
        inner = rect.inflate(-12, -12)
        pg.draw.rect(self.draw, (15, 50, 37), inner, 1, border_radius=8)

    def _blind_chip(self, short, full, x, y, fill):
        pg = self.pg
        center = (int(x), int(y))
        radius = 27
        pg.draw.circle(self.draw, (4, 7, 6), (center[0] + 3, center[1] + 4), radius)
        pg.draw.circle(self.draw, fill, center, radius)
        pg.draw.circle(self.draw, (248, 241, 222), center, radius, 3)
        pg.draw.circle(self.draw, (248, 241, 222), center, radius - 9, 1)
        self._txt(short, center[0], center[1] - 1, small=True, color=(24, 25, 22), center=True)
        self._txt(full, center[0], center[1] + 37, micro=True, color=(187, 177, 158), center=True)

    def _dealer_chip(self, x, y):
        pg = self.pg
        center = (int(x), int(y))
        pg.draw.circle(self.draw, (4, 7, 6), (center[0] + 2, center[1] + 3), 19)
        pg.draw.circle(self.draw, (232, 229, 220), center, 19)
        pg.draw.circle(self.draw, (55, 58, 54), center, 19, 2)
        self._txt("D", center[0], center[1], tiny=True, color=(25, 28, 25), center=True)

    # ------------------------------------------------------------------
    # Players
    # ------------------------------------------------------------------
    def _draw_player(self, p, x, y, sb, bb, dealer, equity_pct=0.0):
        pg = self.pg
        actor = p["seat"] == self._current_actor
        eliminated = bool(p.get("eliminated", False))

        box = pg.Rect(x, y, 350, 226)
        if eliminated:
            fill = (24, 25, 24)
            outline = (75, 63, 60)
        else:
            fill = (24, 35, 31) if not p["folded"] else (30, 30, 29)
            outline = (197, 159, 82) if actor else (72, 94, 84)

        self._panel(box, fill=fill, outline=outline, radius=18)

        if actor and not eliminated:
            pg.draw.rect(self.draw, (238, 194, 92), box.inflate(4, 4), 2, border_radius=20)
            turn = pg.Rect(box.right - 82, box.y + 12, 66, 27)
            pg.draw.rect(self.draw, (151, 104, 36), turn, border_radius=8)
            self._txt("TURN", turn.centerx, turn.centery, tiny=True,
                      color=(255, 245, 218), center=True)

        avatar = (x + 38, y + 39)
        pg.draw.circle(self.draw, (8, 15, 13), avatar, 25)
        pg.draw.circle(self.draw, (107, 137, 119), avatar, 25, 2)
        self._txt(self._agent_short(p["seat"]), avatar[0], avatar[1],
                  small=True, color=(229, 235, 229), center=True)
        self._txt(self._agent_label(p["seat"]), x + 74, y + 17,
                  big=True, color=(244, 238, 225))

        eq_rect = pg.Rect(x + 260, y + 50, 72, 30)
        eq_fill = (37, 76, 57) if not p["folded"] and not eliminated else (55, 48, 48)
        pg.draw.rect(self.draw, eq_fill, eq_rect, border_radius=10)
        pg.draw.rect(self.draw, (90, 123, 101), eq_rect, 1, border_radius=10)
        eq_text = "BUST" if eliminated else ("OUT" if p["folded"] else f"{equity_pct:4.1f}%")
        self._txt(eq_text, eq_rect.centerx, eq_rect.centery, tiny=True,
                  color=(244, 239, 223), center=True)

        self._txt("STACK", x + 20, y + 88, micro=True, color=(126, 145, 135))
        stack_color = (222, 118, 103) if eliminated else (235, 224, 202)
        self._txt(f"{p['stack']}", x + 20, y + 105, small=True, color=stack_color)

        self._txt("IN POT", x + 105, y + 88, micro=True, color=(126, 145, 135))
        self._txt(f"{p['contrib']}", x + 105, y + 105,
                  small=True, color=(235, 224, 202))

        # Table-bank progress bar: 0..4000.
        bank = float(max(1, self._table_chips))
        ratio = max(0.0, min(1.0, float(p["stack"]) / bank))
        prog = pg.Rect(x + 20, y + 130, 122, 8)
        pg.draw.rect(self.draw, (34, 45, 40), prog, border_radius=4)
        if ratio > 0:
            pg.draw.rect(
                self.draw, (105, 145, 115),
                pg.Rect(prog.x, prog.y, max(2, int(prog.w * ratio)), prog.h),
                border_radius=4,
            )

        last_txt = p["last_action"]
        if int(p.get("last_amount", 0) or 0) > 0:
            last_txt += f" {p['last_amount']}"
        if p.get("all_in") and not p.get("folded"):
            last_txt += " • ALL-IN"
        if len(last_txt) > 33:
            last_txt = last_txt[:32] + "…"

        action_rect = pg.Rect(x + 18, y + 148, 132, 42)
        pg.draw.rect(self.draw, (17, 25, 23), action_rect, border_radius=10)
        pg.draw.rect(self.draw, (60, 76, 69), action_rect, 1, border_radius=10)
        self._txt("LAST ACTION", action_rect.x + 10, action_rect.y + 6,
                  micro=True, color=(115, 132, 123))
        self._txt(last_txt, action_rect.x + 10, action_rect.y + 21,
                  micro=True, color=(207, 198, 180))

        if eliminated:
            bust_rect = pg.Rect(x + 162, y + 151, 112, 33)
            pg.draw.rect(self.draw, (100, 45, 42), bust_rect, border_radius=9)
            self._txt("ELIMINATED", bust_rect.centerx, bust_rect.centery,
                      tiny=True, color=(255, 219, 191), center=True)
        elif p["folded"]:
            fold_rect = pg.Rect(x + 162, y + 151, 82, 31)
            pg.draw.rect(self.draw, (84, 44, 42), fold_rect, border_radius=9)
            self._txt("FOLDED", fold_rect.centerx, fold_rect.centery,
                      tiny=True, color=(255, 220, 190), center=True)

        card_x = x + 158
        card_y = y + 78
        for j, card in enumerate(p["hole"]):
            self._card(card, card_x + j * 86, card_y)

        if not eliminated:
            if p["seat"] == sb:
                self._blind_chip("SB", "SMALL BLIND", x + 45, y + 225, (224, 183, 68))
            elif p["seat"] == bb:
                self._blind_chip("BB", "BIG BLIND", x + 45, y + 225, (194, 74, 64))

            if p["seat"] == dealer:
                self._dealer_chip(x + 91, y + 224)

    # ------------------------------------------------------------------
    # Header / table / equity
    # ------------------------------------------------------------------
    def _draw_header(self, snap):
        pg = self.pg

        # Main header band.
        header = pg.Rect(18, 14, self.BASE_W - 36, 78)
        self._panel(header, fill=(15, 24, 21), outline=(57, 74, 67), radius=15, shadow=False)

        self._txt("FlyPoker", 34, 24, hero=True, color=(246, 240, 226))
        self._txt(self.mode_text, 36, 65, micro=True, color=(117, 144, 131))

        # Status pills.
        self._pill(f"GEN {self.generation}", 255, 30, 112, 38, (27, 46, 39))
        self._pill(f"HAND {self.hand_index}", 378, 30, 130, 38, (27, 46, 39))
        self._pill(snap["street"].upper(), 520, 30, 116, 38, (44, 54, 39), outline=(113, 116, 74))
        self._pill(f"BET {snap.get('current_bet', 0)}", 648, 30, 120, 38, (38, 41, 49), outline=(80, 87, 104))

        # Pot display.
        pot = pg.Rect(788, 24, 190, 50)
        pg.draw.rect(self.draw, (88, 65, 29), pot, border_radius=13)
        pg.draw.rect(self.draw, (184, 141, 67), pot, 2, border_radius=13)
        self._txt("POT", pot.x + 18, pot.y + 10, tiny=True, color=(225, 207, 167))
        # Pot amount uses a dedicated large font.
        value_surf = self.amount_font.render(str(snap["pot"]), True, (255, 238, 198))
        self.draw.blit(value_surf, value_surf.get_rect(midright=(pot.right - 15, pot.centery + 1)))

        self._pill(f"DEALER {self._agent_short(snap['button'])}", 995, 30, 145, 38, (36, 40, 39))
        speed = "FAST" if self.fast else f"{self.delay_ms} ms"
        self._pill(speed, 1154, 30, 146, 38, (34, 39, 42), outline=(71, 84, 91))
        self._pill(
            f"TABLE {snap.get('session_no', self.session_index)}",
            1312, 30, 126, 38, (31, 45, 41)
        )
        self._pill(
            f"ALIVE {len(snap.get('alive_seats', []))}/4",
            1450, 30, 126, 38, (46, 47, 37), outline=(103, 103, 70)
        )

    def _draw_favorite_banner(self, snap, equity_info):
        pg = self.pg
        equities = equity_info.get("equity", [0.0] * 4)
        favorites = equity_info.get("favorite", [])
        winners = list(snap.get("winners", [])) or equity_info.get("final_winners", [])
        hand_finished = (snap.get("current_actor") is None) and bool(winners)

        banner = pg.Rect(466, 108, 428, 62)

        if hand_finished:
            fill = (72, 57, 29)
            edge = (173, 139, 72)
            headline = "HAND COMPLETE"
            subtitle = "result shown in the popup"
        else:
            fill = (21, 49, 39)
            edge = (75, 132, 101)
            if len(favorites) == 1:
                idx = favorites[0]
                headline = f"FAVORITE — {self._agent_label(idx)}   {equities[idx] * 100:.1f}%"
            elif favorites:
                headline = "TIED FAVORITES — " + " / ".join(self._agent_short(i) for i in favorites)
            else:
                headline = "SHOWDOWN EQUITY"
            subtitle = "spectator-only information • flies cannot see this"

        pg.draw.rect(self.draw, fill, banner, border_radius=15)
        pg.draw.rect(self.draw, edge, banner, 2, border_radius=15)
        self._txt(headline, banner.centerx, banner.y + 23, small=True,
                  color=(250, 242, 218), center=True)
        self._txt(subtitle, banner.centerx, banner.y + 45, micro=True,
                  color=(167, 186, 173), center=True)

    def _draw_equity_strip(self, snap, equity_info, table):
        pg = self.pg
        equities = equity_info.get("equity", [0.0] * 4)
        favorites = set(equity_info.get("favorite", []))

        x = table.x + 78
        y = table.y + 68
        total_w = table.w - 156

        # One combined stacked bar.
        bar = pg.Rect(x, y, total_w, 22)
        pg.draw.rect(self.draw, (17, 43, 33), bar, border_radius=8)

        colors = [
            (83, 147, 107),
            (100, 127, 176),
            (169, 124, 76),
            (131, 102, 154),
        ]
        cursor = bar.x
        remaining = bar.w
        for i, eq in enumerate(equities):
            width = remaining if i == 3 else int(round(bar.w * max(0.0, min(1.0, float(eq)))))
            if snap["players"][i]["folded"]:
                width = 0
            if width > 0:
                rect = pg.Rect(cursor, bar.y, width, bar.h)
                pg.draw.rect(self.draw, colors[i], rect)
                cursor += width
                remaining = max(0, bar.right - cursor)

        pg.draw.rect(self.draw, (89, 114, 99), bar, 1, border_radius=8)

        # Labels underneath.
        for i, eq in enumerate(equities):
            lx = x + i * (total_w // 4)
            txt = "OUT" if snap["players"][i]["folded"] else f"{eq * 100:.1f}%"
            color = (247, 214, 137) if i in favorites and not snap["players"][i]["folded"] else (183, 195, 187)
            self._txt(f"{self._agent_short(i)}  {txt}", lx, y + 29, tiny=True, color=color)

    def _draw_table_race(self, snap):
        """Persistent stack race for the current winner-takes-all table."""
        pg = self.pg
        panel = pg.Rect(1368, 112, 214, 346)
        self._panel(panel, fill=(14, 24, 21), outline=(59, 79, 69),
                    radius=14, shadow=False)

        alive = set(int(i) for i in snap.get("alive_seats", []))
        table_chips = max(1, int(snap.get("table_chips", 4000) or 4000))

        self._txt("TABLE RACE", panel.x + 14, panel.y + 12,
                  small=True, color=(235, 229, 214))
        self._txt(
            f"Session {snap.get('session_no', self.session_index)}  •  "
            f"{len(alive)}/4 alive",
            panel.x + 14, panel.y + 39,
            micro=True, color=(129, 150, 138)
        )
        self._txt(
            f"Bank: {table_chips} chips",
            panel.x + 14, panel.y + 57,
            micro=True, color=(157, 145, 113)
        )

        y = panel.y + 88
        for p in sorted(snap["players"], key=lambda row: (-int(row["stack"]), int(row["seat"]))):
            seat = int(p["seat"])
            stack = int(p["stack"])
            label = self._agent_short(seat)
            alive_now = seat in alive
            status = "ALIVE" if alive_now else "OUT"

            self._txt(label, panel.x + 14, y, tiny=True,
                      color=(230, 225, 211) if alive_now else (140, 112, 108))
            self._txt(f"{stack}", panel.right - 58, y, tiny=True,
                      color=(229, 211, 171) if alive_now else (142, 109, 103))
            self._txt(status, panel.right - 12, y + 1, micro=True,
                      color=(119, 161, 132) if alive_now else (165, 92, 83),
                      center=False)

            bar = pg.Rect(panel.x + 14, y + 22, panel.w - 28, 10)
            pg.draw.rect(self.draw, (31, 42, 38), bar, border_radius=5)
            ratio = max(0.0, min(1.0, stack / float(table_chips)))
            if ratio > 0:
                pg.draw.rect(
                    self.draw,
                    (111, 145, 113) if alive_now else (102, 65, 62),
                    pg.Rect(bar.x, bar.y, max(2, int(bar.w * ratio)), bar.h),
                    border_radius=5,
                )
            y += 56

        self._txt("TABLE WINS", panel.x + 14, panel.bottom - 29,
                  micro=True, color=(113, 135, 123))
        wins_text = "  ".join(
            f"{self._agent_short(i)} {int(self.table_wins[i])}"
            for i in range(min(4, len(self.table_wins)))
        )
        self._txt(wins_text, panel.x + 14, panel.bottom - 14,
                  micro=True, color=(198, 190, 171))

    def _draw_win_history(self):
        """Small recent-win history: winner, payout, winning hand."""
        pg = self.pg
        panel = pg.Rect(1368, 478, 214, 370)
        self._panel(panel, fill=(14, 24, 21), outline=(59, 79, 69),
                    radius=14, shadow=False)

        self._txt("RECENT WINS", panel.x + 14, panel.y + 11,
                  small=True, color=(232, 226, 212))
        self._txt("last 6", panel.right - 58, panel.y + 15,
                  micro=True, color=(119, 139, 128))

        if not self.win_history:
            self._txt("No finished hands yet", panel.centerx, panel.centery,
                      tiny=True, color=(110, 128, 118), center=True)
            return

        y = panel.y + 44
        for entry in list(self.win_history)[:6]:
            rows = entry.get("rows", [])
            if not rows:
                continue

            winners = " / ".join(
                f"{row['short']} +{int(row['amount'])}"
                for row in rows
            )
            hand_names = " / ".join(
                str(row.get("hand", ""))
                for row in rows
                if row.get("hand")
            )

            if len(winners) > 20:
                winners = winners[:19] + "…"
            if len(hand_names) > 22:
                hand_names = hand_names[:21] + "…"

            self._txt(f"H{entry['hand_no']}", panel.x + 14, y + 2,
                      micro=True, color=(103, 125, 113))
            self._txt(winners, panel.x + 45, y,
                      tiny=True, color=(226, 215, 191))
            self._txt(hand_names, panel.x + 45, y + 17,
                      micro=True, color=(135, 157, 144))

            y += 48
            if y > panel.bottom - 25:
                break

    def _draw_result_popup(self):
        """Large centered hand result, with an even bigger TABLE WINNER state."""
        if not self._result_popup:
            return

        pg = self.pg
        shade = pg.Surface((self.BASE_W, self.BASE_H), pg.SRCALPHA)
        shade.fill((0, 0, 0, 165))
        self.draw.blit(shade, (0, 0))

        session_over = bool(self._result_popup.get("session_over", False))
        rows = self._result_popup.get("rows", [])

        if session_over:
            popup = pg.Rect(250, 250, 1100, 430)
            pg.draw.rect(self.draw, (12, 20, 16), popup, border_radius=28)
            pg.draw.rect(self.draw, (229, 188, 75), popup, 5, border_radius=28)

            winner = int(self._result_popup.get("session_winner", 0))
            table_chips = int(self._result_popup.get("table_chips", 4000))
            self._txt("TABLE WINNER", popup.centerx, popup.y + 54,
                      big=True, color=(221, 187, 101), center=True)

            headline = f"{self._agent_label(winner)} WON THE TABLE"
            surf = self.hero.render(headline, True, (255, 247, 216))
            self.draw.blit(surf, surf.get_rect(center=(popup.centerx, popup.y + 135)))

            self._txt(f"{table_chips} CHIPS • ALL 3 OPPONENTS ELIMINATED",
                      popup.centerx, popup.y + 205,
                      big=True, color=(237, 224, 190), center=True)

            # Also keep the final hand information the user asked for.
            final_row = next((r for r in rows if int(r["seat"]) == winner), rows[0] if rows else None)
            if final_row:
                hand = final_row.get("hand", "UNCONTESTED")
                if hand == "UNCONTESTED":
                    final_text = "FINAL HAND: EVERYONE ELSE FOLDED"
                else:
                    final_text = f"FINAL HAND: WON WITH {hand}"
                self._txt(final_text, popup.centerx, popup.y + 270,
                          small=True, color=(197, 204, 188), center=True)

            self._txt("new table starts at 1000 / 1000 / 1000 / 1000",
                      popup.centerx, popup.bottom - 58,
                      small=True, color=(135, 157, 144), center=True)
            return

        popup = pg.Rect(290, 300, 1020, 340)
        pg.draw.rect(self.draw, (10, 20, 17), popup, border_radius=26)
        pg.draw.rect(self.draw, (219, 178, 76), popup, 4, border_radius=26)

        self._txt("HAND RESULT", popup.centerx, popup.y + 38,
                  small=True, color=(191, 169, 111), center=True)

        if len(rows) == 1:
            row = rows[0]
            hand = row.get("hand", "UNCONTESTED")
            if hand == "UNCONTESTED":
                headline = f"{row['label']} WON"
                detail = "EVERYONE ELSE FOLDED"
            else:
                headline = f"{row['label']} WON WITH {hand}"
                detail = f"+{int(row['amount'])} CHIPS"

            surf = self.hero.render(headline, True, (255, 245, 211))
            if surf.get_width() > popup.w - 80:
                surf = self.big.render(headline, True, (255, 245, 211))
            self.draw.blit(surf, surf.get_rect(center=(popup.centerx, popup.y + 132)))
            self._txt(detail, popup.centerx, popup.y + 205,
                      big=True, color=(235, 222, 190), center=True)
        else:
            self._txt("MULTIPLE POT WINNERS", popup.centerx, popup.y + 100,
                      big=True, color=(255, 245, 211), center=True)
            y = popup.y + 150
            for row in rows[:4]:
                text = (
                    f"{row['label']}  +{int(row['amount'])} CHIPS"
                    f"  •  {row.get('hand', '')}"
                )
                self._txt(text, popup.centerx, y,
                          small=True, color=(232, 220, 194), center=True)
                y += 36

        self._txt("stacks continue into the next hand",
                  popup.centerx, popup.bottom - 38,
                  micro=True, color=(119, 142, 128), center=True)

    def _draw_table(self, snap, equity_info):
        pg = self.pg
        self._table_chips = int(snap.get("table_chips", 4000) or 4000)
        self.draw.fill((8, 20, 17))

        # Subtle background bands.
        pg.draw.rect(self.draw, (10, 24, 20), pg.Rect(0, 0, self.BASE_W, self.BASE_H))
        pg.draw.rect(self.draw, (9, 27, 21), pg.Rect(0, 96, self.BASE_W, 836))

        self._draw_header(snap)
        self._draw_favorite_banner(snap, equity_info)
        self._draw_table_race(snap)
        self._draw_win_history()

        # Poker table shadow / rail / felt.
        table = pg.Rect(330, 188, 790, 560)
        pg.draw.ellipse(self.draw, (3, 9, 7), table.move(0, 9).inflate(22, 22))
        pg.draw.ellipse(self.draw, (82, 60, 36), table.inflate(22, 22))
        pg.draw.ellipse(self.draw, (148, 104, 55), table.inflate(10, 10), 3)
        pg.draw.ellipse(self.draw, (9, 72, 49), table)
        pg.draw.ellipse(self.draw, (14, 86, 59), table.inflate(-18, -18), 3)

        # Center logo / info.
        self._txt("FLYPOKER", table.centerx, table.centery - 98, big=True, color=(80, 128, 101), center=True)
        self._txt(snap["street"].upper(), table.centerx, table.centery - 63, tiny=True, color=(118, 157, 136), center=True)

        self._draw_equity_strip(snap, equity_info, table)

        # Board label and cards.
        board_y = table.centery - 20
        self._txt("BOARD", table.centerx, board_y - 34, tiny=True, color=(189, 207, 196), center=True)

        board_x = table.centerx - ((5 * self.card_size[0] + 4 * 12) // 2)
        for i in range(5):
            x = board_x + i * (self.card_size[0] + 12)
            if i < len(snap["board"]):
                self._card(snap["board"][i], x, board_y)
            else:
                self._empty_card(x, board_y)

        # Fitness panel on lower felt. Fitness already includes the bust penalty.
        if self.fitness is not None:
            fit = pg.Rect(table.centerx - 252, table.bottom - 98, 504, 74)
            pg.draw.rect(self.draw, (11, 44, 33), fit, border_radius=13)
            pg.draw.rect(self.draw, (55, 102, 79), fit, 1, border_radius=13)
            self._txt("FITNESS BB/100 • PERSISTENT STACKS • BUST PENALTY INCLUDED", fit.x + 14, fit.y + 7, micro=True, color=(124, 158, 140))
            self._txt(
                "    ".join(f"{self._agent_short(i)} {v:+.1f}" for i, v in enumerate(self.fitness)),
                fit.centerx,
                fit.y + 34,
                tiny=True,
                color=(206, 220, 211),
                center=True,
            )
            if self.bust_rate is not None:
                self._txt(
                    "TABLE BUST  " + "    ".join(f"{self._agent_short(i)} {v:.1f}%" for i, v in enumerate(self.bust_rate)),
                    fit.centerx,
                    fit.y + 55,
                    micro=True,
                    color=(173, 183, 176),
                    center=True,
                )

        sb = snap.get("small_blind")
        bb = snap.get("big_blind")
        dealer = snap["button"]
        equities = equity_info.get("equity", [0.0] * 4)

        # Large symmetric player panels.
        positions = [
            (18, 126),     # Fly 1
            (1000, 126),   # Fly 2
            (1000, 650),   # Fly 3
            (18, 650),     # Fly 4
        ]
        for p, pos in zip(snap["players"], positions):
            self._draw_player(
                p,
                pos[0],
                pos[1],
                sb,
                bb,
                dealer,
                equities[p["seat"]] * 100.0,
            )

        # Pot label hovering above board.
        pot_chip = pg.Rect(table.centerx - 84, table.y + 118, 168, 48)
        pg.draw.rect(self.draw, (92, 66, 28), pot_chip, border_radius=16)
        pg.draw.rect(self.draw, (189, 144, 63), pot_chip, 2, border_radius=16)
        self._txt("POT", pot_chip.x + 15, pot_chip.centery, tiny=True, color=(221, 201, 161), center=False)
        psurf = self.amount_font.render(str(snap["pot"]), True, (255, 239, 199))
        self.draw.blit(psurf, psurf.get_rect(midright=(pot_chip.right - 15, pot_chip.centery)))

    # ------------------------------------------------------------------
    # Present / pacing
    # ------------------------------------------------------------------
    def _present(self):
        if self.width == self.BASE_W and self.height == self.BASE_H:
            self.screen.blit(self.canvas, (0, 0))
        else:
            scaled = self.pg.transform.smoothscale(self.canvas, (self.width, self.height))
            self.screen.blit(scaled, (0, 0))
        self.pg.display.flip()

    def _paced_wait(self, result_popup=False):
        # True pause: keep the windows responsive until RESUME/SPACE.
        while self.paused and not self.closed:
            self._events()
            self._draw_controls()
            if result_popup:
                self._draw_result_popup()
            self._present()
            self.pg.time.wait(20)

        # FAST means maximum training speed: do not add a result hold.
        if self.fast:
            return

        wait_ms = int(self.delay_ms)
        if result_popup:
            hold = int(self.result_popup_hold_ms)
            if self._result_popup and self._result_popup.get("session_over"):
                hold = max(hold, 1800)
            wait_ms = max(wait_ms, hold)

        if wait_ms <= 0:
            return

        end = time.perf_counter() + wait_ms / 1000.0
        while not self.closed and time.perf_counter() < end:
            self._events()
            if self.paused:
                while self.paused and not self.closed:
                    self._events()
                    self._draw_controls()
                    if result_popup:
                        self._draw_result_popup()
                    self._present()
                    self.pg.time.wait(20)
                end = time.perf_counter() + wait_ms / 1000.0
            self.pg.time.wait(min(10, max(1, int((end - time.perf_counter()) * 1000))))

    def render(self, env, snap, agents):
        self._events()
        if self.closed:
            return

        self._current_actor = snap.get("current_actor")
        self.agent_labels = [getattr(a, "display_name", f"FLY {i+1}") for i, a in enumerate(agents)]
        self._equity_info = self.equity.calculate(env)
        self._update_winner_hand_names(env, snap)
        hand_finished = self._capture_finished_hand(snap)

        self._draw_table(snap, self._equity_info)
        self._draw_controls()
        if hand_finished:
            self._draw_result_popup()
        self._present()

        observations = [env.observation(i) for i in range(4)]
        self.monitor.update(
            agents,
            observations,
            self.fitness,
            self.generation,
            self.hand_index,
            snapshot=snap,
        )
        self._paced_wait(result_popup=hand_finished)

    def close(self):
        try:
            self.monitor.close()
        except Exception:
            pass
        self.pg.quit()
        self.closed = True
