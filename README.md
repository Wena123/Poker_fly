# FlyPoker — Python + Unity (wersja zintegrowana V40)

Projekt gry Texas Hold'em dla czterech much, w którym **Python decyduje o stanie gry i treningu**, a **Unity odpowiada za wizualizację**. Repozytorium zawiera kod Pythona oraz gotowy, scalony zestaw skryptów C#; **nie zawiera kompletnej sceny Unity, modeli ani klipów animacji używanych w Twoim lokalnym projekcie**.

## Szybki start (Windows)

W terminalu, w folderze `Poker_fly`:

```powershell
py -m pip install -r requirements.txt
py main.py --headless --generations 5 --hands 200
```

Ten tryb nie otwiera okien. Dla szybszego treningu można zainstalować tylko `numpy` z `requirements_headless.txt`. Wszystkie pozostałe komendy są w **[COMMANDS.md](COMMANDS.md)**.

## Co jest w projekcie

- **Gra i sesje:** 4 muchy, 14 akcji (w tym różne wielkości zakładów i ALL-IN), żetony oraz blindy, showdown, side poty i kontynuacja stołu do jednego zwycięzcy.
- **Trening ewolucyjny:** champion + trzy mutacje, checkpoint po generacji.
- **V39 AI:** headless, sam monitor OpenCV, telemetria VPIP/PFR, opcjonalne Balanced Reward, ranking TOP 5 oraz `best_ever.npz`.
- **Połączenie Unity:** `127.0.0.1:8765`, komunikaty JSON po TCP, synchronizacja animacji i przepływu żetonów. Obsługa ponownego połączenia w trybie `pause`/`continue`.
- **Unity scripts:** animacje THINK/CALL/RAISE/FOLD, wyrzucanie kart, grafiki PNG nad muchą oraz nad stołem, POT, status ALL-IN/ELIMINATED i przekazywanie żetonów do zwycięzcy.

> **Ważne:** rankingi to ocena na rozgrywkach treningowych, **nie niezależny ranking siły gry ani algorytm GTO**. Monitor pokazuje aktywację tego modelu, nie pełny konektom muchy.

## Struktura

```text
Poker_fly/
├── main.py                    # CLI
├── unity_bridge.py            # Python ↔ Unity TCP
├── config.py
├── agent/                     # brain, training, reward, Hall of Fame
├── poker/                     # engine, evaluator, monitor, renderer
├── Unity/
│   ├── Assets/Script/         # aktywne skrypty C# do skopiowania do Unity
│   ├── Assets/Editor/         # opcjonalny animator FOLD fix
│   └── OptionalScripts/       # starsze narzędzia - nie kopiować w ciemno
├── tests_*.py
├── RUN_TESTS.py
├── requirements*.txt
├── COMMANDS.md
└── UNITY_SETUP.md
```

Karty Pythona pozostają w `assets/cards/` (w istniejącym repo). Karty Unity **muszą już istnieć** w osobnym projekcie Unity pod `Assets/Resources/cards/`. Obrazy nad muchami są ładowane w Unity z tych samych plików PNG — nie są przesyłane jako obrazy przez sieć.

## Podłączenie własnej sceny Unity

Zobacz **[UNITY_SETUP.md](UNITY_SETUP.md)**. Kopiuj pliki z `Unity/Assets/Script/` do `Assets/Script/` lokalnego **projektu Unity**, a nie do folderu Python. Nie nadpisuj własnej sceny, prefabów, materiałów ani animacji. Unity powinno mieć obiekty `Fly1`–`Fly4`, `PokerReceiver`, menedżery kart/żetonów oraz odpowiednie anchory i klip `Fly_Fold`.

## Trening — gdzie są wyniki?

```text
checkpoints/
├── best_brain_gen_XXXX.npz           # checkpoint generacji
├── training_history.jsonl           # historia wyników / VPIP / PFR
└── hall_of_fame/balanced/
    ├── leaderboard.json
    ├── best_ever.npz
    └── gen_XXXX_fly_Y.npz
```

**Nie usuwaj `checkpoints/`**, jeśli chcesz zachować postępy. `.gitignore` blokuje nowe pliki wynikowe, ale nie usuwa checkpointów wcześniej dodanych do Git.

## Kontrola poprawności

```powershell
py RUN_TESTS.py
```

Testy sprawdzają silnik, akcje, turnieje, połączenie TCP z symulowanym Unity i V39. Test struktury skryptów Unity **nie zastępuje** uruchomienia sceny w Unity Editor.

## Wersje i integracja

Ta paczka zastępuje przekazywane wcześniej luźne patche V20–V39. Kod Pythona pochodzi z V39, Unity jest scaleniem: `PokerReceiver` V38 + `FlyLabel` V37 + `PokerTableHUD` V32 + `ChipManager` V21 + `CardManager/FlyAnimationController` V28 + `FoldCardController` V29. Nie kopiuj starszych plików na te nowsze. Zobacz [INTEGRATION_NOTES.md](INTEGRATION_NOTES.md) z ograniczeniami i historią.
