from pathlib import Path
import time

from .anatomical_monitor import PokerAnatomicalMonitor
from .equity import EquityCalculator


class PygameRenderer:
    """Large polished Pygame game UI + separate OpenCV Anatomical Activity Monitor."""

    BASE_W = 1360
    BASE_H = 920

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
        self.assets = self._load_cards()
        self.card_size = (90, 130)

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

    def set_meta(self, generation, hand_index, fitness=None):
        self.generation = generation
        self.hand_index = hand_index
        self.fitness = fitness

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

        box = pg.Rect(x, y, 322, 210)
        fill = (24, 35, 31) if not p["folded"] else (30, 30, 29)
        outline = (197, 159, 82) if actor else (72, 94, 84)
        self._panel(box, fill=fill, outline=outline, radius=18)

        if actor:
            # Warm outer turn glow.
            pg.draw.rect(self.draw, (238, 194, 92), box.inflate(4, 4), 2, border_radius=20)
            turn = pg.Rect(box.right - 82, box.y + 12, 66, 27)
            pg.draw.rect(self.draw, (151, 104, 36), turn, border_radius=8)
            self._txt("TURN", turn.centerx, turn.centery, tiny=True, color=(255, 245, 218), center=True)

        # Avatar / fly number.
        avatar = (x + 38, y + 39)
        pg.draw.circle(self.draw, (8, 15, 13), avatar, 25)
        pg.draw.circle(self.draw, (107, 137, 119), avatar, 25, 2)
        self._txt(f"F{p['seat']+1}", avatar[0], avatar[1], small=True, color=(229, 235, 229), center=True)

        self._txt(f"FLY {p['seat']+1}", x + 74, y + 17, big=True, color=(244, 238, 225))

        # Equity badge.
        eq_rect = pg.Rect(x + 236, y + 50, 70, 30)
        eq_fill = (37, 76, 57) if not p["folded"] else (55, 48, 48)
        pg.draw.rect(self.draw, eq_fill, eq_rect, border_radius=10)
        pg.draw.rect(self.draw, (90, 123, 101), eq_rect, 1, border_radius=10)
        eq_text = "OUT" if p["folded"] else f"{equity_pct:4.1f}%"
        self._txt(eq_text, eq_rect.centerx, eq_rect.centery, tiny=True, color=(244, 239, 223), center=True)

        # Stack / invested chips.
        self._txt("STACK", x + 20, y + 88, micro=True, color=(126, 145, 135))
        self._txt(f"{p['stack']}", x + 20, y + 105, small=True, color=(235, 224, 202))
        self._txt("IN POT", x + 105, y + 88, micro=True, color=(126, 145, 135))
        self._txt(f"{p['contrib']}", x + 105, y + 105, small=True, color=(235, 224, 202))

        last_txt = p["last_action"]
        if int(p.get("last_amount", 0) or 0) > 0:
            last_txt += f" {p['last_amount']}"
        if p.get("all_in") and not p.get("folded"):
            last_txt += " • ALL-IN"
        if len(last_txt) > 32:
            last_txt = last_txt[:31] + "…"

        action_rect = pg.Rect(x + 18, y + 140, 125, 42)
        pg.draw.rect(self.draw, (17, 25, 23), action_rect, border_radius=10)
        pg.draw.rect(self.draw, (60, 76, 69), action_rect, 1, border_radius=10)
        self._txt("LAST ACTION", action_rect.x + 10, action_rect.y + 6, micro=True, color=(115, 132, 123))
        self._txt(last_txt, action_rect.x + 10, action_rect.y + 21, micro=True, color=(207, 198, 180))

        if p["folded"]:
            fold_rect = pg.Rect(x + 152, y + 142, 78, 31)
            pg.draw.rect(self.draw, (84, 44, 42), fold_rect, border_radius=9)
            self._txt("FOLDED", fold_rect.centerx, fold_rect.centery, tiny=True, color=(255, 220, 190), center=True)

        # Cards on right side.
        card_x = x + 151
        card_y = y + 77
        for j, card in enumerate(p["hole"]):
            self._card(card, card_x + j * 82, card_y)

        # Position chips.
        if p["seat"] == sb:
            self._blind_chip("SB", "SMALL BLIND", x + 45, y + 190, (224, 183, 68))
        elif p["seat"] == bb:
            self._blind_chip("BB", "BIG BLIND", x + 45, y + 190, (194, 74, 64))

        if p["seat"] == dealer:
            self._dealer_chip(x + 91, y + 189)

    # ------------------------------------------------------------------
    # Header / table / equity
    # ------------------------------------------------------------------
    def _draw_header(self, snap):
        pg = self.pg

        # Main header band.
        header = pg.Rect(18, 14, self.BASE_W - 36, 78)
        self._panel(header, fill=(15, 24, 21), outline=(57, 74, 67), radius=15, shadow=False)

        self._txt("FlyPoker", 34, 24, hero=True, color=(246, 240, 226))
        self._txt("SELF-PLAY TRAINER", 36, 65, micro=True, color=(117, 144, 131))

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

        self._pill(f"DEALER F{snap['button']+1}", 995, 30, 145, 38, (36, 40, 39))
        speed = "FAST" if self.fast else f"{self.delay_ms} ms"
        self._pill(speed, 1154, 30, 166, 38, (34, 39, 42), outline=(71, 84, 91))

    def _draw_favorite_banner(self, snap, equity_info):
        pg = self.pg
        equities = equity_info.get("equity", [0.0] * 4)
        favorites = equity_info.get("favorite", [])
        winners = list(snap.get("winners", [])) or equity_info.get("final_winners", [])
        hand_finished = (snap.get("current_actor") is None) and bool(winners)

        banner = pg.Rect(466, 108, 428, 62)

        if hand_finished:
            fill = (86, 64, 25)
            edge = (219, 180, 77)
            if len(winners) == 1:
                headline = f"WINNER — FLY {winners[0] + 1}"
            else:
                headline = "SPLIT POT — " + " / ".join(f"F{i+1}" for i in winners)
            subtitle = "HAND COMPLETE"
        else:
            fill = (21, 49, 39)
            edge = (75, 132, 101)
            if len(favorites) == 1:
                idx = favorites[0]
                headline = f"FAVORITE — FLY {idx + 1}   {equities[idx] * 100:.1f}%"
            elif favorites:
                headline = "TIED FAVORITES — " + " / ".join(f"F{i+1}" for i in favorites)
            else:
                headline = "SHOWDOWN EQUITY"
            subtitle = "spectator-only information • flies cannot see this"

        pg.draw.rect(self.draw, fill, banner, border_radius=15)
        pg.draw.rect(self.draw, edge, banner, 2, border_radius=15)
        self._txt(headline, banner.centerx, banner.y + 23, small=True, color=(250, 242, 218), center=True)
        self._txt(subtitle, banner.centerx, banner.y + 45, micro=True, color=(167, 186, 173), center=True)

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
            self._txt(f"F{i+1}  {txt}", lx, y + 29, tiny=True, color=color)

    def _draw_table(self, snap, equity_info):
        pg = self.pg
        self.draw.fill((8, 20, 17))

        # Subtle background bands.
        pg.draw.rect(self.draw, (10, 24, 20), pg.Rect(0, 0, self.BASE_W, self.BASE_H))
        pg.draw.rect(self.draw, (9, 27, 21), pg.Rect(0, 96, self.BASE_W, 760))

        self._draw_header(snap)
        self._draw_favorite_banner(snap, equity_info)

        # Poker table shadow / rail / felt.
        table = pg.Rect(300, 188, 760, 506)
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

        # Fitness panel on lower felt.
        if self.fitness is not None:
            fit = pg.Rect(table.centerx - 238, table.bottom - 88, 476, 58)
            pg.draw.rect(self.draw, (11, 44, 33), fit, border_radius=13)
            pg.draw.rect(self.draw, (55, 102, 79), fit, 1, border_radius=13)
            self._txt("FITNESS  BB/100", fit.x + 14, fit.y + 8, micro=True, color=(124, 158, 140))
            self._txt(
                "    ".join(f"F{i+1} {v:+.1f}" for i, v in enumerate(self.fitness)),
                fit.centerx,
                fit.y + 37,
                tiny=True,
                color=(206, 220, 211),
                center=True,
            )

        sb = (snap["button"] + 1) % 4
        bb = (snap["button"] + 2) % 4
        dealer = snap["button"]
        equities = equity_info.get("equity", [0.0] * 4)

        # Large symmetric player panels.
        positions = [
            (22, 116),     # Fly 1
            (1016, 116),   # Fly 2
            (1016, 626),   # Fly 3
            (22, 626),     # Fly 4
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

    def _paced_wait(self):
        if self.fast or self.delay_ms <= 0:
            return
        end = time.perf_counter() + self.delay_ms / 1000.0
        while not self.closed and time.perf_counter() < end:
            self._events()
            self.pg.time.wait(min(10, max(1, int((end - time.perf_counter()) * 1000))))

    def render(self, env, snap, agents):
        self._events()
        if self.closed:
            return

        self._current_actor = snap.get("current_actor")
        self._equity_info = self.equity.calculate(env)

        self._draw_table(snap, self._equity_info)
        self._draw_controls()
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
        self._paced_wait()

    def close(self):
        try:
            self.monitor.close()
        except Exception:
            pass
        self.pg.quit()
        self.closed = True
