# Najważniejsze komendy V43

**Test:** `py tests_v43_training.py`

**Start (z V42):**

```powershell
py main.py --resume checkpoints/hall_of_fame/balanced/best_ever.npz --headless --selection-v43 --train-mode mixed --generations 20 --hands 5000 --benchmark-tables 8 --gate-tables 16 --teacher-hands 200 --progress-every 1000
```

**Wznowienie (V43):**

```powershell
py main.py --resume-verified-best --headless --selection-v43 --train-mode mixed --generations 20 --hands 5000 --benchmark-tables 8 --gate-tables 16 --progress-every 1000
```

**Porównanie starego i nowego championa na 100 wspólnych turniejach:**

```powershell
py main.py --compare checkpoints/hall_of_fame/verified_v43/champion.npz checkpoints/hall_of_fame/balanced/best_ever.npz --gate-tables 25 --validation-seed 3456789
```

**Lista/metadata zatwierdzonego championa:** `py main.py --list-verified`

**Benchmark jednego championa:**

```powershell
py main.py --benchmark-v43 checkpoints/hall_of_fame/verified_v43/champion.npz --benchmark-tables 25 --validation-seed 3456789
```

**Oglądanie V43 (bez treningu):**

```powershell
py main.py --watch-verified-best --headless --with-bot --hands 5000
```

**Unity:**

```powershell
py main.py --watch-verified-best --headless --with-bot --unity --hands 100
```

**Interpretacja:** `BENCH`=wynik kandydata na turniej; `GATE`=różnica względem poprzedniego championa; `ACCEPTED`=awans; `REJECTED`=kontynuuj od starego. Patrz `README_V43.md`.
