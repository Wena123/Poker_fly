# FlyPoker V42 — NOWE KOMENDY (stare komendy poniżej)

**Polecany trening mieszany + benchmark + holdout:**

```powershell
py main.py --resume-latest --headless --train-mode mixed --bot-fraction 0.5 --generations 100 --hands 5000 --max-session-hands 500 --benchmark-tables 2 --benchmark-weight 0.75 --immigrant-every 10 --progress-every 500
```

**Szybki test bez trenowania:**

```powershell
py tests_v42_training.py
py main.py --help
```

**Lista championów wybranych na podstawie holdoutu:**

```powershell
py main.py --list-benchmark
```

**Oglądanie zapisanego championa (bez uczenia, bez Pygame):**

```powershell
py main.py --watch-benchmark-best --headless --with-bot --hands 1000
```

**Kontynuowanie od najlepszego z rankingu holdout:**

```powershell
py main.py --resume-benchmark-best --headless --train-mode mixed --generations 50 --hands 5000
```

**Niezależna ocena dowolnego checkpointu przeciw trzem StrongPokerBotom (nowy seed):**

```powershell
py main.py --benchmark checkpoints/hall_of_fame/benchmark_v1/best_ever.npz --benchmark-tables 10 --validation-seed 3456789
```

**Wyłącznie self-play, ale z benchmarkiem:**

```powershell
py main.py --headless --train-mode self-play --generations 20 --hands 5000 --benchmark-tables 2
```

**Wyłącznie bot, ale z benchmarkiem:**

```powershell
py main.py --headless --train-mode bot --generations 20 --hands 5000 --benchmark-tables 2
```

**Szybciej (ocena co 2 generacje):**

```powershell
py main.py --resume-latest --headless --train-mode mixed --generations 50 --hands 5000 --benchmark-tables 1 --benchmark-every 2
```

> `--resume-latest` kontynuuje od najnowszego ukończonego pokolenia; `--resume-benchmark-best` od najlepszego w rankingu holdout. Stare `--resume-best` wciąż oznacza stary ranking treningowy. `--hands 5000` oznacza minimum 5000 rozdań na generację. `--benchmark-tables 2` oznacza 2 turnieje *na pozycję*, a nie łącznie 2.

---

# FlyPoker — wszystkie komendy

Uruchamiaj je **w katalogu repozytorium** (`Poker_fly`). Windows: `py`; Linux/macOS: zamień `py` na `python3` (lub `python`). Włącz Unity **Play Mode przed komendą z `--unity`**.

## Instalacja i pomoc

```powershell
py --version
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
py -m pip install -r requirements_headless.txt
py -m pip install -r requirements_brain_monitor.txt
py main.py --help
```

Pełny `requirements.txt` zawiera `numpy`, `pygame-ce` i `opencv-python`; headless wymaga tylko `numpy`.

## Trening AI

| Cel | Komenda |
|---|---|
| Szybki trening bez okien, bez Unity | `py main.py --headless --generations 100 --hands 5000` |
| Trening z Pygame (+monitor) | `py main.py --render --render-every 1 --generations 5 --hands 200` |
| Sam monitor mózgu bez Pygame | `py main.py --brain-monitor --generations 5 --hands 200` |
| Unity bez Pygame | `py main.py --unity --headless --generations 10 --hands 200` |
| Unity + Pygame | `py main.py --unity --render --render-every 1 --generations 10 --hands 200` |
| Trening przeciw botowi referencyjnemu | `py main.py --headless --with-bot --generations 50 --hands 1000` |
| Trening ze starym rewardem | `py main.py --headless --reward-mode classic --generations 50 --hands 1000` |
| Reward balanced (domyślnie) | `py main.py --headless --reward-mode balanced --generations 50 --hands 1000` |
| Ograniczenie logów | `py main.py --headless --progress-every 0 --generations 10 --hands 1000` |

`--hands` podaje minimalną liczbę rozdań **na generację**. Stół kończy się po zwycięstwie albo po limicie `--max-session-hands` (domyślnie 500). Gdy stół osiąga limit, zapisujemy wynik w żetonach, ale NIE przyznajemy fikcyjnego zwycięzcy. Rzeczywista liczba rozdań może nieznacznie przekroczyć `--hands`.

## Oglądanie i wznawianie modeli

| Cel | Komenda |
|---|---|
| Lista najlepszych much | `py main.py --list-best` |
| Lista najlepiej ocenionych w klasycznym rewardzie | `py main.py --list-best --reward-mode classic` |
| Oglądaj najlepszy model w Pygame | `py main.py --watch-best --hands 100` |
| Oglądaj najlepszy model z monitorem mózgu | `py main.py --watch-best --brain-monitor --hands 100` |
| Oglądaj w Unity bez Pygame | `py main.py --watch-best --unity --headless --hands 100` |
| Kontynuuj naukę z najlepszego | `py main.py --resume-best --headless --generations 50 --hands 5000` |
| Kontynuuj z najnowszej generacji | `py main.py --resume-latest --headless --generations 25 --hands 1000` |
| Oglądaj najnowszą generację | `py main.py --watch-latest --hands 100` |
| Oglądaj wybrany checkpoint | `py main.py --watch checkpoints/best_brain_gen_0001.npz --hands 100` |
| Wznów z wybranego checkpointu | `py main.py --resume checkpoints/best_brain_gen_0001.npz --headless --generations 50 --hands 1000` |
| Trenuj z podglądem z najnowszego | `py main.py --watch-train-latest --generations 10 --hands 200` |
| Trenuj z podglądem z wybranego | `py main.py --watch-train checkpoints/best_brain_gen_0001.npz --generations 10 --hands 200` |

**Uwaga:** `--watch-best` i `--resume-best` wymagają wcześniejszego zapisu `checkpoints/hall_of_fame/<reward-mode>/best_ever.npz`. Bez niego rozpocznij od zwykłego treningu.

## Unity: połączenie i rozłączenie

```powershell
# Play Mode w Unity przed startem Pythona
py main.py --unity --headless --generations 10 --hands 200

# Domyślnie pauzuj Pythona po zamknięciu Play Mode, spróbuj połączyć ponownie
py main.py --unity --headless --unity-disconnect pause --generations 10 --hands 200

# Nie zatrzymuj treningu, gdy Unity się rozłączy
py main.py --unity --headless --unity-disconnect continue --generations 10 --hands 200

# Niestandardowy adres/port/timeout
py main.py --unity --headless --unity-host 127.0.0.1 --unity-port 8765 --unity-timeout 60 --generations 10 --hands 200
```

Jeśli Python zgłasza `Cannot connect to Unity at 127.0.0.1:8765`, włącz Play Mode, sprawdź `PokerReceiver`, port i zaporę sieciową. Nie należy odpalać dwóch instancji Pythona do jednego `PokerReceiver`.

## Parametry dodatkowe

| Flaga | Znaczenie |
|---|---|
| `--generations N` | liczba generacji |
| `--hands N` | minimum rozdań na generację / sesję oglądania |
| `--render-every N` | co N-te rozdanie odświeżać podgląd treningowy |
| `--monitor-hz N` | limit odświeżania OpenCV |
| `--win-bonus-bb N` | premia w BB za wygraną całego stołu (balanced) |
| `--risk-penalty N` | waga kary za duże straty (balanced) |
| `--top-k N` | liczba championów w Hall of Fame |
| `--progress-every N` | co ile rozdań informacja w terminalu, `0` = wyłączona |
| `--with-bot` | gracz referencyjny zamiast jednej uczącej się muchy |
| `--max-session-hands N` | bezpieczny limit rozdań na pojedynczy stół; domyślnie 500. Chroni przed nieskończonym heads-up |

## Testy

```powershell
py RUN_TESTS.py
py tests_v39_features.py
py test_unity_bridge.py
py tests_unity_api.py
```

## Aktualizacja repozytorium na GitHubie

```powershell
git status
git add .
git commit -m "Consolidate FlyPoker V40: Unity scripts, V39 AI, docs and tests"
git push origin main
```

Jeśli masz niezapisane własne zmiany, zrób najpierw backup lub osobny branch: `git switch -c integration/flypoker-v40` i po `git push -u origin integration/flypoker-v40` otwórz Pull Request.

## Dlaczego `--hands 5000` może oznaczać więcej rozdań?

`--hands` jest **minimum na generację**, a nie limitem na pojedynczy stół. Trening liczy pełne/capowane sesje i kończy generację po przekroczeniu celu. `--max-session-hands` ogranicza pojedynczy stół, jeżeli dwie muchy np. zawsze pasują na small blind i nigdy nie eliminują się nawzajem.

```powershell
py main.py --resume-latest --headless --generations 500 --hands 5000 --max-session-hands 500 --progress-every 500
```

Niedokończony stół nie daje bonusu za zwycięstwo; zyski i straty z rozegranych rozdań zostają uwzględnione.
