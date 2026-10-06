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

## Ważne

W tym starterze betting jest celowo uproszczony do limitowanego podbijania,
żeby najpierw stabilnie uruchomić self-play i ewolucję.

- preflop/flop: raise o 1 BB
- turn/river: raise o 2 BB
- max 3 raise na street

Każde rozdanie startuje z równym stackiem, dzięki czemu wynik jednej
generacji nie jest zdominowany przez jedno wcześniejsze bankructwo.

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
  - wyjście `FOLD / CHECK-CALL / RAISE`.
