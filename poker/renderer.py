from pathlib import Path
import math

class PygameRenderer:
    def __init__(self, width=1400, height=860, delay_ms=140):
        import pygame
        self.pg = pygame
        pygame.init()
        pygame.display.set_caption('Poker Fly Trainer - 4 flies')
        self.screen = pygame.display.set_mode((width, height))
        self.width = width
        self.height = height
        self.font = pygame.font.SysFont('Arial', 22)
        self.small = pygame.font.SysFont('Arial', 16)
        self.tiny = pygame.font.SysFont('Arial', 12)
        self.big = pygame.font.SysFont('Arial', 30, bold=True)
        self.delay_ms = delay_ms
        self.default_delay_ms = delay_ms
        self.slow_delay_ms = 500
        self.fast = False
        self.paused = False
        self.closed = False
        self.generation = 0
        self.hand_index = 0
        self.fitness = None
        self.assets = self._load_cards()

    def _load_cards(self):
        assets = {}
        base = Path(__file__).resolve().parent.parent / 'assets' / 'cards'
        if not base.exists():
            return assets
        for path in base.glob('*.png'):
            img = self.pg.image.load(str(path)).convert_alpha()
            assets[path.stem.upper()] = self.pg.transform.smoothscale(img, (60, 82))
        return assets

    def set_meta(self, generation, hand_index, fitness=None):
        self.generation = generation
        self.hand_index = hand_index
        self.fitness = fitness

    def _events(self):
        pg = self.pg
        for event in pg.event.get():
            if event.type == pg.QUIT:
                self.closed = True
            elif event.type == pg.KEYDOWN:
                if event.key == pg.K_SPACE:
                    self.paused = not self.paused
                elif event.key == pg.K_f:
                    self.fast = not self.fast
                elif event.key == pg.K_s:
                    self.delay_ms = self.slow_delay_ms if self.delay_ms != self.slow_delay_ms else self.default_delay_ms
                elif event.key in (pg.K_EQUALS, pg.K_PLUS, pg.K_UP):
                    self.delay_ms = min(2000, self.delay_ms + 50)
                elif event.key in (pg.K_MINUS, pg.K_DOWN):
                    self.delay_ms = max(0, self.delay_ms - 50)
                elif event.key == pg.K_ESCAPE:
                    self.closed = True

        while self.paused and not self.closed:
            for event in pg.event.get():
                if event.type == pg.QUIT:
                    self.closed = True
                elif event.type == pg.KEYDOWN and event.key == pg.K_SPACE:
                    self.paused = False
                elif event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE:
                    self.closed = True
            pg.time.wait(20)

    def _txt(self, text, x, y, big=False, small=False, color=(235,235,235)):
        f = self.big if big else self.small if small else self.font
        surf = f.render(str(text), True, color)
        self.screen.blit(surf, (x, y))

    def _card_colors(self, card_text):
        suit = card_text[-1].upper()
        return (190, 30, 30) if suit in ('H','D') else (20, 20, 20)

    def _suit_symbol(self, s):
        return {'C':'♣','D':'♦','H':'♥','S':'♠'}.get(s.upper(), s)

    def _card(self, text, x, y):
        code = text.upper()
        if code in self.assets:
            self.screen.blit(self.assets[code], (x, y))
            return

        pg = self.pg
        rect = pg.Rect(x, y, 60, 82)
        pg.draw.rect(self.screen, (245, 245, 245), rect, border_radius=7)
        pg.draw.rect(self.screen, (30, 30, 30), rect, 2, border_radius=7)
        rank = code[:-1]
        suit = code[-1]
        color = self._card_colors(code)
        suit_symbol = self._suit_symbol(suit)
        self.screen.blit(self.big.render(rank, True, color), (x + 7, y + 8))
        self.screen.blit(self.big.render(suit_symbol, True, color), (x + 16, y + 36))

    def _chip(self, label, x, y, color):
        pg = self.pg
        pg.draw.circle(self.screen, color, (x, y), 22)
        pg.draw.circle(self.screen, (245,245,245), (x, y), 22, 3)
        pg.draw.circle(self.screen, (245,245,245), (x, y), 15, 1)
        text = self.small.render(label, True, (20,20,20) if sum(color) > 300 else (250,250,250))
        rect = text.get_rect(center=(x, y))
        self.screen.blit(text, rect)

    def _bars(self, values, x, y, w, h, title, cap=24, bipolar=True):
        pg = self.pg
        self._txt(title, x, y-18, small=True)
        vals = list(values[:cap])
        if not vals:
            return
        n = len(vals)
        bar_w = max(2, (w - (n-1)) // n)
        max_abs = max(1e-6, max(abs(float(v)) for v in vals))
        zero_y = y + h//2 if bipolar else y + h
        # frame
        pg.draw.rect(self.screen, (55,55,55), pg.Rect(x-1, y-1, w+2, h+2), 1)
        if bipolar:
            pg.draw.line(self.screen, (90,90,90), (x, zero_y), (x+w, zero_y), 1)
        for i, v in enumerate(vals):
            v = float(v)
            norm = v / max_abs
            bx = x + i * (bar_w + 1)
            if bipolar:
                bh = int((h//2 - 2) * abs(norm))
                by = zero_y - bh if v >= 0 else zero_y
                color = (70, 190, 120) if v >= 0 else (210, 80, 80)
                pg.draw.rect(self.screen, color, pg.Rect(bx, by, bar_w, max(1,bh)))
            else:
                bh = int((h - 2) * max(0.0, min(1.0, norm)))
                by = y + h - bh
                pg.draw.rect(self.screen, (80, 160, 230), pg.Rect(bx, by, bar_w, max(1,bh)))

    def _neuron_panel(self, fly_idx, brain, obs, x, y, w=300, h=165):
        pg = self.pg
        panel = pg.Rect(x, y, w, h)
        pg.draw.rect(self.screen, (30, 30, 35), panel, border_radius=8)
        pg.draw.rect(self.screen, (80, 80, 90), panel, 1, border_radius=8)
        self._txt(f'Fly {fly_idx+1} neurons', x + 10, y + 8, small=True)
        dbg = None
        if hasattr(brain, 'debug_activations'):
            try:
                dbg = brain.debug_activations(obs)
            except Exception:
                dbg = None
        if not dbg:
            self._txt('No debug activations', x + 10, y + 32, small=True)
            return
        self._bars(dbg['input'], x + 10, y + 34, w - 20, 24, 'Input (first 24)', cap=24, bipolar=False)
        self._bars(dbg['hidden_1'], x + 10, y + 70, w - 20, 28, 'Hidden 1 (first 24)', cap=24, bipolar=True)
        self._bars(dbg['hidden_2'], x + 10, y + 106, w - 20, 24, 'Hidden 2 (first 24)', cap=24, bipolar=True)
        self._bars(dbg['output'], x + 10, y + 138, w - 20, 18, 'Output F/C/R', cap=3, bipolar=True)

    def render(self, env, snap, agents):
        self._events()
        if self.closed:
            return

        pg = self.pg
        self.screen.fill((18, 70, 48))

        self._txt(f'GEN {self.generation}', 20, 16, big=True)
        self._txt(f'HAND {self.hand_index}', 20, 50)
        self._txt(f"Street: {snap['street']}   Pot: {snap['pot']}   Button: Fly {snap['button']+1}", 230, 20)
        self._txt(f"Delay: {self.delay_ms} ms   {'FAST' if self.fast else 'NORMAL'}", 230, 48, small=True)

        board = snap['board']
        bx = 420
        by = 205
        self._txt('BOARD', bx + 100, by - 32, big=True)
        for i in range(5):
            if i < len(board):
                self._card(board[i], bx + i * 72, by)
            else:
                pg.draw.rect(self.screen, (50, 90, 70), pg.Rect(bx + i * 72, by, 60, 82), 2, border_radius=7)

        positions = [
            (50, 105),
            (790, 105),
            (790, 480),
            (50, 480),
        ]
        sb = (snap['button'] + 1) % 4
        bb = (snap['button'] + 2) % 4

        for p, (x, y) in zip(snap['players'], positions):
            actor = snap['current_actor'] == p['seat']
            name = f"FLY {p['seat']+1}"
            if actor:
                name += '  < TURN'

            self._txt(name, x, y, big=True)
            self._txt(f"Stack: {p['stack']}   In pot: {p['contrib']}", x, y + 36)
            self._txt(f"Last: {p['last_action']}", x, y + 60, small=True)
            if p['folded']:
                self._txt('FOLDED', x, y + 80, small=True, color=(255,220,120))

            if p['seat'] == sb:
                self._chip('SB', x + 18, y + 118, (235, 190, 70))
            if p['seat'] == bb:
                self._chip('BB', x + 18, y + 118, (210, 70, 70))

            for j, card in enumerate(p['hole']):
                self._card(card, x + 38 + j * 68, y + 100)

        if self.fitness is not None:
            self._txt('Current fitness (bb/100):', 390, 740)
            self._txt('   '.join(f"F{i+1}: {v:+.2f}" for i, v in enumerate(self.fitness)), 360, 770)

        # Neuron panels 2x2 grid
        panel_positions = [(380, 360), (700, 360), (380, 540), (700, 540)]
        for i, (px, py) in enumerate(panel_positions):
            obs = env.observation(i)
            self._neuron_panel(i, agents[i], obs, px, py)

        self._txt('SPACE pause | F fast | S slow toggle | UP slower | DOWN faster | ESC exit', 260, 830, small=True)
        pg.display.flip()

        if not self.fast:
            pg.time.wait(self.delay_ms)

    def close(self):
        if not self.closed:
            self.pg.quit()
        self.closed = True
