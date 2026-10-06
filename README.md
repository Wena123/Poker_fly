# Poker Fly Trainer — 4 muchy

Starter do self-play w Texas Hold'em:

- 4 niezależne muchy grają przy jednym stole.
- Po każdej generacji wybierana jest najlepsza.
- Najlepsza przechodzi 1:1 do następnej generacji.
- Pozostałe 3 muchy są mutacjami championa:
  - mała mutacja,
  - średnia mutacja,
  - duża mutacja.
- Fitness jest liczony jako `bb/100`.
- Pygame służy tylko do podglądu.
- Logika gry jest oddzielona od renderera.
- `SimpleFlyBrain` jest tymczasowym mózgiem i można go później podmienić
  na właściwy brain z projektu muchy.

## Betting / action space (V10)

Każda mucha zaczyna rozdanie z `1000` żetonów przy blindach `5/10`, czyli **100 BB**.
Stack resetuje się do 100 BB na początku następnego rozdania, dzięki czemu trening
pozostaje cash-game/self-play zamiast turnieju.

Mucha ma teraz **14 wyjść decyzyjnych**:

```text
FOLD
CHECK
CALL
MIN RAISE
1/4 POT
1/3 POT
1/2 POT
2/3 POT
3/4 POT
POT
1.25x POT
1.5x POT
2x POT
ALL-IN
```

Nielegalne akcje są maskowane. Przykładowo `CHECK` znika, gdy trzeba dopłacić,
`CALL` znika, gdy nie ma czego sprawdzać, a sizing niedostępny z powodu za małego
stacka nie konkuruje z `ALL-IN`. Pot-fraction sizing jest liczony na podstawie
puli po dopłaceniu calla i respektuje minimalny legalny raise.

Silnik obsługuje all-iny oraz side poty. Nie ma już starego limitu 3 raise na street;
pozostaje tylko wysoki techniczny safety-limit akcji chroniący przed bugiem/pętlą.

## Instalacja

```bash
python -m venv .venv
source .venv/bin/activate          # macOS / Linux
# Windows:
# .venv\Scripts\activate

pip install -r requirements.txt
```

## Szybki test

```bash
python tests_smoke.py
```

Powinno wyjść:

```text
SMOKE TEST: OK
Observation size: ...
```

## Trening bez grafiki

```bash
python main.py --generations 50 --hands 2000
```

Przykład:

```text
GEN 0001 | Fly 1: +2.15 bb/100 | Fly 2: -1.03 ... | BEST: Fly 1
```

Checkpointy trafiają do:

```text
checkpoints/
best_brain_gen_0001.npz
best_brain_gen_0002.npz
...
```

## Trening z Pygame

```bash
python main.py --render --generations 50 --hands 1500 --render-every 50
```

Sterowanie:

- `SPACE` — pauza
- `F` — szybki / normalny podgląd
- `ESC` — wyjście

## Jak działa generacja

```text
GEN N

Fly 1
Fly 2
Fly 3
Fly 4

   ↓ wiele rozdań

fitness = bb/100

   ↓

BEST FLY
  ├── champion bez zmian
  ├── mutation 0.02
  ├── mutation 0.05
  └── mutation 0.10

   ↓

GEN N+1
```

## Jak podpiąć właściwy mózg muchy

Zaimplementuj klasę zgodną z:

```text
agent/brain_interface.py
```

Potrzebne metody:

```python
act(observation, legal_actions)
copy()
mutate(strength, probability, rng)
save(path)
```

Potem w `agent/trainer.py` zamień `SimpleFlyBrain` na swoją klasę.

## Observation

Mucha NIE widzi kart przeciwników.

Dostaje między innymi:

- własne 2 karty,
- board,
- street,
- swoją pozycję,
- pozycję buttona,
- pot,
- kwotę do call,
- stacki,
- wpłaty graczy,
- kto spasował,
- ostatnie akcje.

Karty przeciwników są używane wyłącznie przez engine przy showdownie.

## Późniejszy vision bridge

`vision_state_adapter.py` jest miejscem na system:

```text
kamera / screenshot
      ↓
Card AI
      ↓
rozpoznany stan
      ↓
adapter
      ↓
ten sam brain muchy
```

Dzięki temu możesz trenować mózg wyłącznie w symulatorze, a warstwę
rozpoznawania obrazu rozwijać osobno.


## Nowe elementy UI

- Kolory kart:
  - ♥ i ♦ są czerwone,
  - ♠ i ♣ są czarne.
- Grafiki kart: w katalogu `assets/cards/` są gotowe PNG wszystkich 52 kart + rewers.
- Blindy: przy odpowiedniej musze pojawia się żeton `SB` albo `BB`.
- Spowolnienie / przyspieszenie:
  - `S` — przełącznik trybu wolnego,
  - `UP` / `+` — wolniej,
  - `DOWN` / `-` — szybciej,
  - `F` — szybki podgląd.
- Widok neuronów wszystkich much:
  - dla każdej muchy pokazuje pierwsze fragmenty wejścia,
  - aktywacje `hidden_1`, `hidden_2`,
  - 14 wyjść: fold/check/call + min-raise, sizingi potowe i all-in.


## V3 UI update

- Uses the user-provided playing-card PNG graphics.
- Card files are renamed internally to engine codes:
  - `ace_of_hearts.png -> AH.png`
  - `10_of_clubs.png -> TC.png`
  - etc.
- Poker table and neural monitor are separated so the brain display never covers Fly 4.
- Brain monitor is now an anatomical-style point cloud inspired by the Isaac monitor.
- All 4 flies have their own live brain panel.
- Each brain panel includes:
  - live neuron activation cloud,
  - highlighted strongest activations,
  - output/descending nodes,
  - FOLD/CALL/RAISE bars,
  - recent spike raster.
- Blind markers now say `SMALL BLIND` and `BIG BLIND`.
- Clickable speed controls:
  - PAUSE / RESUME
  - SLOWER
  - FASTER
  - NORMAL
  - FAST

Note: while `SimpleFlyBrain` is still being used, the brain point positions are a visualization layout.
When the real MaleCNS brain is connected, those positions can be replaced with real `brain.positions`.


## V4 UI / monitor refresh

- Brain monitor redesigned to look closer to the Isaac anatomical activity monitor screenshot.
- 4 separate fly brain panels (2x2), one for each fly.
- Bigger anatomical-style brain clouds with warm glow / spark effect.
- Better dark UI theme for the whole Pygame window.
- Blind chips are now round chips with `SB` / `BB` in the center and the full label underneath.
- Poker table layout cleaned up so the brain monitor is separate from the game area.


## V5 dual window mode

- The renderer now opens **two separate windows**:
  - `FlyPoker — Game`
  - `FlyPoker — Brain Monitor`
- The poker game and the brain monitor are no longer in the same window.
- The game window keeps the table and player UI.
- The brain monitor window shows the 4 anatomical-style brain panels.
- If the environment does not support `pygame._sdl2` multi-window mode, the secondary monitor window may not open; on your local `pygame-ce` install it should work.


## V6 OpenCV monitor

- The poker **game stays in Pygame**.
- The fly **brain monitor is now rendered in OpenCV (`cv2`)** in a separate window.
- Two windows open when you run with `--render`:
  - `FlyPoker — Game`
  - `FlyPoker - Brain Monitor`
- The monitor uses an Isaac-inspired dark dashboard layout with 4 separate fly panels.
- Each monitor panel shows:
  - large anatomical-style point cloud,
  - tactical input grid,
  - recent spike history,
  - status/performance box,
  - action decoder bars.
- If you close the OpenCV monitor window or press `ESC` in it, the run closes.

### Install

```bash
pip install -r requirements.txt
```

This now installs:
- `numpy`
- `pygame-ce`
- `opencv-python`


## V7 — FlyIsaac Anatomical Activity Monitor port

This version was rebuilt from the actual monitor implementation in the connected GitHub repository:

`Wena123/Flysaac.V2/fly_agent/isaac_v3/neuron_monitor.py`

The poker monitor now reuses the same visual design principles:

- OpenCV window separate from Pygame,
- dark `MaleCNS Anatomical Activity 2.0` dashboard styling,
- density/anatomy background with `COLORMAP_BONE`,
- contour outlines,
- blurred recent-activity glow,
- bright activity points,
- tactical/state panel,
- status/performance panel,
- activity-over-time raster,
- decoder bars.

The window contains four complete fly panels in a 2x2 layout.

Important: the current poker agent is `SimpleFlyBrain` (96 hidden units), not the 166k-neuron MaleCNS runtime. Therefore V7 creates a dense deterministic anatomical display cloud and maps the real MLP activations onto that cloud. It no longer displays random standalone circles. If a real MaleCNS brain is connected later, this display can use its real `brain.positions` exactly like FlyIsaac.


## V8 — meaningful poker input + accurate main view

- Removed the fake `POKER STATE / 7x14` panel completely.
- Removed `ACTIVITY OVER TIME` completely.
- Added a real `POKER INPUT` panel per fly showing:
  - hole cards, board, street, position, pot, stack, to-call, current bet, active players, raise step and last actions.
- `CHECK/CALL` is displayed contextually as `CHECK` when to-call is 0 and `CALL` otherwise.
- The MAIN VIEW now uses a fixed XZ anatomical reference derived from the user's actual FlyIsaac Anatomical Activity Monitor screenshot, then rendered using the same density/BONE/contour/glow recipe as `isaac_v3/neuron_monitor.py`.
- Live MLP units map to stable local anatomical clusters instead of random standalone circles.
- Pygame default height reduced to 960 to fit macOS displays better.
- Delay is now responsive in small slices rather than one long blocking wait.
- Ctrl+C exits cleanly with `Stopped by user.` rather than a traceback.


## V8.1 — final monitor cleanup

- `POKER STATE / 7x14` is gone.
- `ACTIVITY OVER TIME` is gone.
- `POKER INPUT` now shows actual per-fly information from the current hand.
- `CHECK/CALL` is shown as `CHECK` or `CALL` depending on `to_call`.
- The main view is larger and uses a packaged XZ reference point cloud derived from the user's real FlyIsaac Anatomical Activity Monitor screenshot.
- The density background, BONE colormap, contours and temporal glow follow the same rendering approach as `Wena123/Flysaac.V2/fly_agent/isaac_v3/neuron_monitor.py`.
- The Pygame window defaults to 940×960 so macOS does not have to shrink a requested 1040px-tall window.
- Pacing is responsive instead of one long blocking `pygame.time.wait()`.
- Ctrl+C exits cleanly without a traceback.

## V9 — showdown equity UI

The Pygame game window now includes spectator-only win probabilities:

- `FAVORITE: FLY X — NN.N%` banner during a hand.
- A showdown-equity percentage badge on every fly panel.
- Four compact equity bars on the poker table.
- Folded flies show `OUT` / 0%.
- At the end of a hand the banner switches to `WINNER: FLY X` or `SPLIT POT`.

The percentages are **not** included in agent observations and therefore do not
help the flies make decisions.

Calculation:

- preflop: deterministic Monte Carlo (3000 boards) for responsive UI,
- flop: exact enumeration of every possible turn+river,
- turn: exact enumeration of every possible river,
- river: exact showdown.

Tie equity is split between tied players, so displayed equities sum to about 100%.


## V10 — no-limit bet sizing

- 14 discrete actions instead of 3.
- Separate `CHECK` and `CALL`.
- Pot sizes from `1/4 POT` through `2x POT`.
- Explicit `ALL-IN`.
- Dynamic legal-action masking.
- Minimum-raise tracking.
- Proper all-in state and side-pot payout.
- Opponent last-action sizing is included in the observation.
- Anatomical monitor decoder now displays all 14 outputs in two columns.
- Observation size in this version: `216`.


## V11 — Larger polished Pygame UI

The game window was redesigned around a 1360×920 logical canvas.

Changes:
- much larger game window,
- responsive scaling when macOS changes the requested window size,
- larger 90×130 card graphics,
- larger player panels,
- cleaner table / felt / rail styling,
- larger central board and pot display,
- improved favorite / winner banner,
- combined showdown-equity strip,
- clearer TURN highlight,
- circular SB / BB chips plus dealer chip,
- better action, stack and contribution presentation,
- cleaner footer speed controls.

The separate OpenCV Anatomical Activity Monitor is unchanged.
