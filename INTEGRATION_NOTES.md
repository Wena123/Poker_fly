# Integracja V40 — zakres i ograniczenia

## Wybrane źródła (bez dublowania starych klas)

| Moduł | Wersja źródłowa |
|---|---|
| Python CLI, trening, reward, hall of fame, monitor | V39 |
| Python reconnect TCP | V38, zachowany w Pythonie V39 |
| PokerReceiver (Unity) | V38 |
| FlyLabel (karty nad głową + ALL-IN) | V37 |
| PokerTableHUD (jeden POT + 5 kart) | V32 |
| ChipManager (Bet → Pot → Winner) | V21 |
| CardManager (FOLD / karty w świecie) | V28 |
| FoldCardController (brak snap-back) | V29 |
| FlyAnimationController (czekanie na lądowanie kart) | V28 |
| AnchorHold | V20 |
| Edytor klipu Fly_Fold | V27 (opcjonalny) |

Starsze próby i skrypty pomocnicze pozostają w `Unity/OptionalScripts/`; tych klas nie kopiuj do sceny, o ile nie są potrzebne.

## Istotne ograniczenia

- **Unity Editor nie był uruchomiony podczas przygotowania tej paczki.** Test statyczny sprawdza obecność klas, metod i sygnałów, ale nie zastępuje testów wizualnych, animacji, prawdziwego TCP ani prefabów.
- **Repo Pythona nie zawiera kompletnej sceny Unity ani Twojego klipu Fold.** Kod C# jest gotowy do zaimportowania do istniejącego projektu, ale nie można zweryfikować konfiguracji jego obiektów bez sceny.
- GitHub repo zawierało starsze README oraz pliki wynikowe/checkpointy. Nowe README/COMMANDS zastępują instrukcje. `.gitignore` nie usuwa już śledzonych plików.
- Rankingi treningowe nie są niezależnym benchmarkiem siły gry; nie porównuj bezpośrednio wyników uzyskanych z różnymi reward-mode / botami / seedami.
- System FOLD tworzy kopie wizualne kart. Fizyczne zdjęcia kart na stole po FOLD mogą się różnić od zaobserwowanej animacji, jeśli prefab ma niestandardowe materiały albo skale.
- `--headless` + `--unity` nie jest tak szybkie jak czyste `--headless`, bo czeka na animacje.

## Bezpieczne wprowadzenie

1. Zapisz bieżące checkpointy i zrób commit/backup repo.
2. Rozpakuj paczkę **do katalogu głównego repo**, zachowując strukturę folderów. Nie usuwa ona istniejącego `assets`, `checkpoints`, scen ani prefabów.
3. Zainstaluj zależności, uruchom `py RUN_TESTS.py` i sprawdź `py main.py --headless --generations 1 --hands 20`.
4. Przenieś aktywne skrypty C# do osobnego projektu Unity, sprawdź Console i animacje.
5. Dopiero potem wykonaj commit i push.
