# FlyPoker V43 — poprawiona selekcja AI i testy

**Kompatybilny patch na zainstalowane V42.** Nie zawiera `checkpoints/`, Unity ani `.git`.

## Co konkretnie zostało naprawione

1. **Uczciwsza miara** — V43 selekcjonuje na podstawie zysku/straty **BB na pełny turniej** (w `1000/10` zakres wynosi od −100 do +300 BB). Zwykłe `bb/100` dalej może być pokazane, ale nie służy jako podstawa awansu — przy bardzo wczesnych eliminacjach potrafi skrajnie wahać się w obie strony.
2. **Porównanie 1:1 przeciw poprzedniemu championowi** — kandydat i incumbent grają z **trzema StrongPokerBotami**, na czterech miejscach, na tych samych deterministycznych ustawieniach rozdań i botów. V43 wymaga dodatniej różnicy względem championa (oraz marginesu względem błędu standardowego). Gdy brakuje dowodów poprawy, aktualny champion **nie jest zastępowany**.
3. **Różne losowania co generację** — dane selekcyjne i oddzielne dane bramkujące („gate”) zmieniają się dla każdej generacji. Ogranicza to dopasowywanie do kilku niezmiennych turniejów z V42.
4. **7 nowych cech kart** — siła startowa, kategoria układu, flush draw, straight draw, suited/pocket pair i pot odds. Są liczone wyłącznie z **własnych kart** i widocznych kart wspólnych, nie z kart przeciwników. To heurystyki, a nie dokładne equity.
5. **Zgodność z modelami V42/V41** — dawne checkpointy mają 216 wejść; V43 ma 223. Przy wznawianiu wagi są migrowane z siedmioma początkowo zerowymi wierszami, **bez zmiany wcześniejszych decyzji**. Przy treningu mutacje mogą zacząć korzystać z nowych cech.
6. **Opcjonalny teacher warm-up** — `--teacher-hands 200` uczy **jednego kandydata** na obserwowalnych decyzjach StrongPokerBota. Nie nadpisuje bazowego championa: przejście do nowego modelu wymaga testu „gate”.
7. **Bezpieczne archiwum** — zatwierdzony champion znajduje się w `checkpoints/hall_of_fame/verified_v43/champion.npz`. V43 nie modyfikuje dawnych folderów `balanced` i `benchmark_v1`. Wszystkie checkpointy generacji `best_brain_gen_XXXX.npz` dalej powstają, ale w V43 zawierają **przyjętego championa**, niekoniecznie kandydata wybranego z tej generacji.
8. **WATCH z limitem** — zachowano limit długości stołu w trybie oglądania z V41/V42.

## Instalacja na Windows

1. Zakończ trening przez `Ctrl+C`.
2. Zrób kopię całego `checkpoints/` (i najlepiej projektu).
3. Rozpakuj `FlyPoker_V43_ValidatedChampion_PATCH.zip` i skopiuj pliki **do folderu `Poker_fly`**, zachowując podfoldery `agent/` i `poker/` oraz nadpisując tylko te same pliki.
4. **Nie usuwaj** `.git`, checkpointów, innych skryptów Pythona ani Unity. Nie kopiuj ZIP-a do podfolderu `Poker_fly/Poker_fly`.
5. Otwórz PowerShell w folderze projektu.

### Test instalacji

```powershell
py tests_v43_training.py
py main.py --help
```

Pełny zestaw testów (`RUN_TESTS.py`) może także sprawdzać **istnienie plików Unity** w repozytorium. Jeśli lokalnie masz Python i Unity w osobnych projektach, błąd testu struktury folderów Unity nie oznacza błędu AI.

## Polecany pierwszy trening: od starego najlepszego V42

```powershell
py main.py --resume checkpoints/hall_of_fame/balanced/best_ever.npz --headless --selection-v43 --train-mode mixed --bot-fraction 0.5 --generations 20 --hands 5000 --max-session-hands 500 --benchmark-tables 8 --gate-tables 16 --gate-z 0.8 --teacher-hands 200 --immigrant-every 10 --progress-every 1000
```

Alternatywnie użyj `--resume-latest`, jeśli wolisz bazować na najnowszej ukończonej generacji. **Nie uruchamiaj 500 generacji bez pierwszego porównania!** 8 turniejów na miejsce to 32 turnieje *na kandydata*; test gate dodaje 64 turnieje na kandydata i 64 na incumbenta. To więcej pracy na generację, ale pomiar jest bardziej wiarygodny niż 2 turnieje na miejsce w V42.

Przy pierwszym uruchomieniu V43 skopiuje punkt startowy do `verified_v43/champion.npz`. Przy kolejnych wywołaniach używaj:

```powershell
py main.py --resume-verified-best --headless --selection-v43 --train-mode mixed --bot-fraction 0.5 --generations 20 --hands 5000 --benchmark-tables 8 --gate-tables 16 --progress-every 1000
```

`--teacher-hands` zwykle używaj jednorazowo (pierwszy start V43). W kolejnych startach pomiń flagę: nie trzeba ciągle imitować nauczyciela.

## Sprawdzanie postępów na niezależnych losowaniach

Po 20 generacjach **bez trenowania**, wykonaj testy na osobnym, nowym seedzie (nie tym z treningu):

```powershell
py main.py --list-verified
py main.py --compare checkpoints/hall_of_fame/verified_v43/champion.npz checkpoints/hall_of_fame/balanced/best_ever.npz --gate-tables 25 --validation-seed 3456789
```

To porównanie daje **100 turniejów na każdą politykę** (25 × 4 pozycje). `MATCHED DELTA` powyżej zera oznacza przewagę nowego modelu na tych testach; komunikat `NOT PROVEN BETTER` znaczy, że zabrakło dowodów, **nie że oba modele są identyczne**.

Pojedyncze porównanie nowej sieci przeciw 3 StrongPokerBotom:

```powershell
py main.py --benchmark-v43 checkpoints/hall_of_fame/verified_v43/champion.npz --benchmark-tables 25 --validation-seed 3456789
```

Oglądanie nowego championa tak jak dawniej (3 kopie muchy + 1 bot, inny eksperyment niż benchmark V43):

```powershell
py main.py --watch-verified-best --headless --with-bot --hands 5000
```

Stare polecenia `--watch-best`, `--resume-best`, `--list-benchmark`, `--benchmark`, `--unity`, `--brain-monitor`, `--headless` działają nadal. **V43 włącza się dopiero po dodaniu flagi `--selection-v43`.**

## Co znaczą logi

- `SELECTED: Fly 3` — kandydat z danej generacji wybrany do porównania.
- `V43 BENCH -35.0 BB/table` — średni zysk na turniej w rozgrywkach selekcyjnych.
- `GATE +4.1 BB/table (SE 2.4)` — przewaga nad poprzednim championem w **oddzielnym** teście na tych samych losowaniach.
- `ACCEPTED` — incumbent został zastąpiony nowym modelem.
- `REJECTED - incumbent kept` — bezpieczna odmowa; następna generacja powstanie z poprzedniego championa.

## Ograniczenia

- Bramka i margines błędu **nie są matematyczną gwarancją** poprawy. Przez wielokrotne porównania w wielu generacjach może pojawić się przeuczenie i szczęście. Finalna ocena wymaga nowego seeda, dłuższych prób i ewentualnie różnych przeciwników.
- Silniejszy bot stanowi punkt odniesienia, nie nieomylnego nauczyciela; imitacja jego decyzji **nie gwarantuje** przewagi nad nim.
- Testy uruchomione bez Unity Editora weryfikują Python i strukturę plików Unity; **nie są kompilacją ani testem Play Mode Unity**.
- Nie ma szkolenia gradientowego z wygranych rozdań: główne uczenie to nadal **ewolucja**. Opcjonalny teacher warm-up wykorzystuje osobny nadzorowany etap.
