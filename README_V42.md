# FlyPoker V42 — trening, który mierzy jakość gry przeciw botom

Ta aktualizacja **zmienia tylko Pythona**. Zachowuje V41 (limit długości turnieju), V38 (reconnect Unity), V39 (monitor, headless, nagrody, checkpointy). Nie kasuj `checkpoints/` i nie zmieniaj skryptów Unity.

## Instalacja

1. Zamknij bieżący trening Pythona (`Ctrl+C`). Zrób kopię `checkpoints/`.
2. Rozpakuj **FlyPoker_V42_AI_Benchmark_PATCH.zip** i skopiuj pliki do **głównego katalogu** `Poker_fly`, zachowując podfolder `agent/` i nadpisując pliki o tych samych nazwach.
3. Nie usuwaj pozostałych plików projektu i nie wklejaj folderu `checkpoints/` z żadnych starych ZIP-ów.
4. W terminalu, z katalogu `Poker_fly`, uruchom `py tests_v42_training.py` i `py main.py --help`.

## Co się zmieniło?

- **Trening mieszany**: `--train-mode mixed` przeplata stoły **4 much** (self-play) i stoły **3 muchy + StrongPokerBot**. Bot rotuje po miejscach, a na self-play muchy też zmieniają pozycje. `--bot-fraction 0.5` to domyślna proporcja, zbalansowana w blokach po 4 stoły.
- **Benchmark porównywalny między generacjami**: każdy z czterech kandydatów gra osobno przeciw **3 StrongPokerBotom** na wszystkich 4 pozycjach. Taki sam seed talii i botów we wszystkich generacjach. Wynik jest w `bb/100`; nie używa zapisanych wyników treningu ani ukrytych kart innych graczy.
- **Selekcja**: `--benchmark-weight 0.75` łączy 75% wyniku benchmarku i 25% dotychczasowego fitness; tylko wybrany champion jest kopiowany do następnej generacji.
- **Holdout**: wybrany model jest ponownie testowany na **innym seedzie** (`--validation-seed`); te rozdania nie wpływają na wybór muchy w bieżącej generacji. Najlepszy wynik holdout trafia do *oddzielnego rankingu* `checkpoints/hall_of_fame/benchmark_v1/`.
- **Większa różnorodność**: champion + 2 mutanty + 3. mutant; co 10 generacji trzeci mutant jest zastępowany świeżą losową siecią (`--immigrant-every 10`). **Champion nie jest zastępowany**.
- **Wszystkie dotychczasowe checkpointy** (`best_brain_gen_XXXX.npz`, `hall_of_fame/balanced/`) pozostają dostępne.

### Ważne ograniczenia

1. Nie ma gwarancji, że sieci zaczną wygrywać. Jest to ewolucja, nie uczenie gradientowe.
2. Benchmark jest *bardziej uczciwy niż bieżący self-play*, ale wynik opiera się na ograniczonej liczbie stołów, jednej klasie bota i powtarzanym zbiorze losowań. Możliwe są szum i przeuczenie do bota/seeda. Ocena holdout jest również wielokrotnie wykorzystywana do prowadzenia rankingu, więc do ostatecznego porównania użyj **nowego seeda**.
3. `--benchmark-tables 2` oznacza **2 stoły na pozycję dla każdego mózgu**, czyli 8 stołów na muchę i 32 stoły oceny czterech much + 8 stołów holdout. To wydłuża generację. Zmniejsz do `1` albo ustaw `--benchmark-every 2`, jeśli to za wolne.
4. `--hands` nadal jest *minimum* rozdań na generację. `--max-session-hands` ogranicza każdy stół do 500; po capie nie jest ogłaszany fikcyjny zwycięzca.
5. Stare `--resume-best` korzysta z rankingu treningowego `balanced`. Nowe `--resume-benchmark-best` używa rankingu holdout. Stare `--with-bot` działa jak `--train-mode bot`.

## Start — polecana komenda

```powershell
py main.py --resume-latest --headless --train-mode mixed --bot-fraction 0.5 --generations 100 --hands 5000 --max-session-hands 500 --benchmark-tables 2 --benchmark-weight 0.75 --immigrant-every 10 --progress-every 500
```

Po pierwszej generacji:

```powershell
py main.py --list-benchmark
py main.py --benchmark checkpoints/hall_of_fame/benchmark_v1/best_ever.npz --benchmark-tables 10 --validation-seed 3456789
```

Dodatkowe komendy są w `COMMANDS.md`.

## Interpretacja wyniku

W logu generacji zobaczysz `SELECTED: Fly N | BENCH -150.2 bb/100 | HOLDOUT -135.7 bb/100`. `BENCH` służy do selekcji; `HOLDOUT` jest oddzielną oceną. **Wzrost `HOLDOUT` (w kierunku zera lub wartości dodatnich) jest zachęcający, ale sprawdzaj go na nowym seedzie**, bo nawet ten ranking może się przeuczyć.

W `checkpoints/training_history.jsonl` zapisywane są `benchmark_results`, `validation_result`, `selection_scores`, `train_mode`, a także stare VPIP/PFR, fitness i wygrane stoły.
