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

## V12 — anti all-in spam / hierarchical decisions / bust penalty

V12 changes the temporary MLP policy from one flat 14-way choice to two stages:

1. **ACTION HEAD** — `FOLD`, `CHECK`, `CALL`, `BET/RAISE`
2. **SIZING HEAD** — consulted only after `BET/RAISE` wins:
   `MIN`, `1/4 POT`, `1/3 POT`, `1/2 POT`, `2/3 POT`, `3/4 POT`,
   `POT`, `1.25x POT`, `1.5x POT`, `2x POT`, `ALL-IN`

The environment still exposes the same 14 final actions. This prevents `ALL-IN`
from directly competing as a peer with `CHECK`/`CALL` in one flat argmax.

Sizing deduplication remains active: if a nominal sizing would require all of the
remaining stack, that sizing is masked and only the explicit `ALL-IN` action is
kept. Multiple buttons therefore cannot secretly resolve to the same shove.

### Bust penalty

`Config.bust_penalty_bb = 5.0` by default.

A fly is penalized only when it **finishes a hand with stack == 0**. Merely
choosing `ALL-IN` is not penalized. Raw chip profit is still tracked separately.

Fitness is:

`raw BB/100 - bust penalty BB/100`

With the default setting, one bust per 100 hands subtracts `5 BB/100` from
fitness. Console output shows both raw BB/100 and bust rate, and Pygame shows the
current penalized fitness plus bust percentages.

Old V10/V11 flat-head checkpoints can still be loaded; their old 14-output head
is converted into the new action/sizing heads as a compatibility approximation.

# V13 — Strong BOT + WATCH / RESUME modes

V13 adds a fixed rule-based poker opponent and explicit modes for training and watching checkpoints.

## StrongPokerBot

`agent/strong_bot.py` is a fast no-limit Hold'em baseline intended for millions of training hands.
It uses only the exact observation available to a normal player:

- its own two hole cards,
- public board cards,
- pot and amount to call,
- stack and current bet,
- position,
- public previous actions,
- legal action mask.

It does **not** read opponents' hidden cards.

The bot uses:

- preflop hand quality,
- made-hand strength after the flop,
- flush/straight draw detection,
- pot odds,
- stack-to-pot ratio (SPR),
- position,
- natural bet sizing,
- a small mixed-strategy component so it is less trivial to exploit.

ALL-IN is intentionally difficult for the bot to select unless the hand is extremely strong or the SPR is already low. The bot is a strong fixed baseline/teacher, not a claim of GTO-perfect poker.

## Modes

### 1. Train without BOT

```bash
python main.py --generations 500 --hands 5000
```

Four flies play self-play. No UI, fastest mode.

### 2. Train with BOT

```bash
python main.py --generations 500 --hands 5000 --with-bot
```

One BOT seat rotates every hand. The fly whose normal seat is occupied sits that hand out. Over every four hands each candidate fly plays exactly three hands against the BOT. Fitness is normalized by the number of hands actually played by each fly.

The BOT is never mutated and never becomes champion. The flies learn from it through evolutionary pressure: strategies that perform better against the BOT are more likely to survive.

### 3. Watch checkpoint WITHOUT learning

```bash
python main.py --watch checkpoints/best_brain_gen_0250.npz
```

This automatically enables Pygame + the OpenCV monitor.

- mutation OFF
- evolution OFF
- saving OFF
- checkpoint is copied into four seats
- only observation/playback happens

Limit the watch session with:

```bash
python main.py --watch checkpoints/best_brain_gen_0250.npz --hands 200
```

### 4. Watch checkpoint WITHOUT learning, against BOT

```bash
python main.py --watch checkpoints/best_brain_gen_0250.npz --with-bot
```

Three copies of the checkpoint play against the fixed BOT in seat 4.

### 5. Watch WHILE learning from checkpoint

```bash
python main.py --watch-train checkpoints/best_brain_gen_0250.npz --generations 100 --hands 5000
```

This resumes training and enables the UI. `--watch-train` shows every hand by default.

Against the BOT:

```bash
python main.py --watch-train checkpoints/best_brain_gen_0250.npz --with-bot --generations 100 --hands 5000
```

### 6. Watch WHILE learning from scratch

```bash
python main.py --render --render-every 1 --generations 100 --hands 5000
```

With BOT:

```bash
python main.py --render --render-every 1 --with-bot --generations 100 --hands 5000
```

### 7. Resume training without watching

```bash
python main.py --resume checkpoints/best_brain_gen_0250.npz --generations 500 --hands 5000
```

With BOT:

```bash
python main.py --resume checkpoints/best_brain_gen_0250.npz --with-bot --generations 500 --hands 5000
```

The next checkpoint continues numbering from the loaded file. For example, loading `best_brain_gen_0250.npz` begins at generation 251.

### Latest-checkpoint shortcuts

```bash
python main.py --resume-latest
python main.py --resume-latest --with-bot
python main.py --watch-latest
python main.py --watch-latest --with-bot
python main.py --watch-train-latest
python main.py --watch-train-latest --with-bot
```

## UI changes

- Pygame now displays `BOT` when a bot occupies a seat.
- Winner/favorite/equity labels also use the real seat name.
- Header shows `TRAINING • LEARNING ON`, `WATCH • NO LEARNING`, and BOT status.
- OpenCV monitor marks a bot panel as `RULE BOT` instead of pretending it is a neural fly.
- Pause now actually pauses the live simulation instead of only changing the button text.

## Tests

```bash
python tests_smoke.py
python tests_actions.py
python tests_hierarchical.py
python tests_modes.py
```


## V14 — winner hand banner + chip placement

- SB / BB chips and dealer button were moved lower so they no longer cover LAST ACTION.
- Bottom player panels were moved slightly upward to preserve room above the speed footer.
- End-of-hand banner now shows the winning poker hand, for example:
  - `FLY 1 WON WITH STRAIGHT`
  - `FLY 3 WON WITH FULL HOUSE`
  - `BOT WON WITH ROYAL FLUSH`
- Split/side-pot outcomes show winner labels plus their hand categories when available.
- If the hand ends before a 5-card hand can be evaluated, the banner says that the other players folded.


## V15 — big result popup + recent wins

- The winner message is now a large centered popup.
- Example: `FLY 1 WON WITH STRAIGHT`.
- The popup also shows the actual chips collected from the pot.
- Non-FAST mode holds the popup for ~0.9 seconds.
- FAST mode adds no extra delay.
- Added a compact `RECENT WINS` panel with the latest six hands.
- History includes winner(s), chips collected and winning hand.
- Main/side-pot payouts and split pots are supported.


## V16 — persistent winner-takes-all table sessions

This changes the core game loop.

A table starts:
- F1 = 1000
- F2 = 1000
- F3 = 1000
- F4 = 1000
- total bank = 4000

Stacks now persist between hands. A player that reaches 0 is eliminated:
- receives no more hole cards,
- posts no blinds,
- cannot act,
- remains out until the table is finished.

Dealer and blinds skip eliminated seats. Heads-up blind/action order is handled separately.

The table resets ONLY when exactly one seat remains. Because chips are conserved,
that player must have all 4000 chips. The next hand then starts a new table at
1000 / 1000 / 1000 / 1000.

Training:
- `--hands` is now a minimum hand target per generation.
- if the target is reached during an unfinished table, that table is completed
  before evolution selects the champion.
- table wins and session bust rate are tracked.
- with `--with-bot`, the bot keeps one fixed seat for a whole table session;
  its seat rotates between sessions.

Pygame V16:
- logical canvas increased to 1600×1000,
- larger cards and player panels,
- new TABLE RACE sidebar with live stacks and progress toward all 4000 chips,
- eliminated players are visibly marked,
- table/session number and ALIVE count are in the header,
- the existing recent-win history remains,
- normal hand wins still show the big popup,
- the final survivor gets an even larger `TABLE WINNER` popup,
- table-winner popup remains longer in non-FAST mode.


## V17 — checkpoint path/save fix

- Checkpoints no longer depend on the terminal current working directory.
- Default save folder is always `<project root>/checkpoints`.
- `watch-train`, normal training and resumed training all use the same absolute checkpoint folder.
- Every completed generation prints `CHECKPOINT SAVED -> /absolute/path/...`.
- Checkpoint writes are atomic and verified.
- `checkpoints/LATEST.txt` is updated after every successful generation save.
- Added optional `--checkpoint-dir PATH` for an explicit custom destination.
- `--resume-latest`, `--watch-latest`, and `--watch-train-latest` all search the same resolved checkpoint directory.

## V18: Unity live bridge

V18 can stream the real PokerEnv state to a local Unity viewer. Unity does not
shuffle or simulate poker; it only visualizes the same cards produced by the
Python engine/Pygame.

Start Unity Play Mode first, with `PokerReceiver` listening on `127.0.0.1:8765`,
then add `--unity` to any training/watch command, for example:

```bash
python main.py --watch-train-latest --with-bot --unity --generations 100 --hands 5000
```

or Pygame + Unity together:

```bash
python main.py --resume-latest --with-bot --render --unity --render-every 1 --generations 100 --hands 5000
```

The bridge currently emits `new_hand`, `hole_cards` for seats 0..3 and `board`
for flop/turn/river. A `new_hand` event clears the previous hole cards and board
in the Unity `CardManager`.

## V19 - Unity chips

`--unity` now also streams chip state from the real PokerEnv snapshot:

- `stack`: each seat's persistent table stack
- `bet`: each seat's current-street contribution
- `pot`: chips already settled in the centre (previous streets)

At showdown, Unity receives zero current bets / pot together with updated player stacks. This is intentionally an instant payout for now; movement animation can be added later.

Unity helper scripts are included in `unity_scripts/ChipManager.cs` and `unity_scripts/PokerReceiver.cs`.
