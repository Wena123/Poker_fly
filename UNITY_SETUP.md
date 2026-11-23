# Unity — podłączenie FlyPoker (scena już istnieje)

**Ważne:** ten katalog zawiera skrypty C# do istniejącego projektu Unity. Nie jest samodzielnym projektem Unity: nie zawiera Twoich modeli, scen, animacji ani prefabów. W projekcie Unity używaj `Assets/Script/` (zgodnie z Twoją dotychczasową strukturą).

## Kopiowanie

1. Wyłącz Play Mode w Unity. Zrób kopię projektu lub commit.
2. Skopiuj pliki z katalogu repo `Unity/Assets/Script/` do **lokalnego projektu Unity** pod `Assets/Script/` (podmień pliki o tych samych nazwach).
3. Opcjonalnie skopiuj `Unity/Assets/Editor/FlyPokerFoldAnimatorFix.cs` do `Assets/Editor/` w Unity. Nie kopiuj folderu `Unity/OptionalScripts` na ślepo: to starsze, nieobowiązkowe narzędzia.
4. Upewnij się, że masz `Assets/Resources/cards/` z 52 teksturami kart (`AH.png`, `KD.png` itd.); to **zasoby Unity**, nie `assets/cards/` z repo Pythona.
5. Poczekaj na kompilację, sprawdź Console. Uruchom Unity Play Mode, potem `py main.py --unity --headless --generations 10 --hands 200`.

## Obiekty sceny

- Jedna instancja `PokerReceiver` (nasłuch TCP `127.0.0.1:8765`), jedna instancja `CardManager` i `ChipManager`, jeden `PokerTableHUD` (ręczny `TableHUD` ma pierwszeństwo przed automatycznym).
- Muchy nazwane `Fly1`–`Fly4`, każda z `Animator`, `FlyAnimationController`, `AnchorHold`, `FoldCardController` (receiver/card manager próbują automatycznie przypisać te komponenty do obiektu z Animatorem).
- Każda mucha ma `CardsHeld/Card1` i `CardsHeld/Card2`, zakotwiczenie dłoni `HandAnchor` (może być `HandAnchorn`) lub pazur `tarsal_claw_T1_left`.
- Żetony: `ChipAnchors1..4`, `BetAnchors1..4`, `PotArchorn` (ta stara pisownia jest wspierana) albo `PotAnchor`.
- Karty stołu: `BOARD` z `Card1..Card5`.
- Dla fizycznego rzutu FOLD najlepiej `FoldAnchor1..4` w odpowiednim miejscu przy stole; przy braku kotwicy rzutu istnieje fallback do środka stołu.
- Tekst TMP nad muchą z `FlyLabel`; `seat` = 0..3. Widoczne 2 obrazki kart są tworzone przez `FlyLabel` ze `Resources/cards`.
- `TableHUD` z `PokerTableHUD` dla puli i obrazków kart na stole. **Tylko jeden** HUD puli; kod wybiera główny, ale usuń stare ręcznie dodane napisy `POT: 0`.

## Animator

- Domyślny stan `Fly_idle` (Loop Time ON).
- Stany `Fly_Think`, `Fly_Call`, `Fly_Raise`, `Fly_Fold` z rzeczywistymi klipami; FOLD jest odpalany bezpośrednio przez CrossFade.
- `Fly_Fold`: **Loop Time OFF**; Animation Events: `PickUpCards()`, `ThrowCards()` (po jednym) oraz `AnimationFinished()` (na końcu). Wszystkie te skrypty muszą być na obiekcie z `Animator`.
- THINK/CALL/RAISE: `AnimationFinished()` na końcu klipu. CALL/RAISE opcjonalnie `PickUp()` i `ReleaseToBet()` z `AnchorHold` do animacji żetonów.
- Usuń bezwarunkowe `Any State → Fly_idle`. Opcjonalnie zaznacz `Fly_Fold.anim` i wybierz **Tools → FlyPoker → Fix FOLD Animator**.

## Komunikaty / synchronizacja

Python wysyła JSON przez TCP, osobno w każdym wierszu: `new_hand`, `hole_cards`, `stack`, `bet`, `board`, `pot`, `turn`, `action`, `animation`, `collect_bets`, `award_pot`, `hand_end`.

Unity odpowiada `animation_done` dopiero po animacji (FOLD: również po wylądowaniu kart) oraz `chip_flow_done` po przeliczeniu animacji żetonów. Nie edytuj Pythona po to, by bezwarunkowo odsyłał DONE: źródłem prawdy o stackach i wyniku rozdania jest silnik Pythona.

**ALL-IN vs ELIMINATED:** `0 CHIPS` w trakcie rozdania może oznaczać ALL-IN. `ELIMINATED` wolno pokazać dopiero po końcowym rozliczeniu rozdania i braku żetonów.

## Problemy

- `Fly_Fold` nie uruchamia się: sprawdź stan i klip w Animator, Loop Time OFF, ewentualnie narzędzie Editor.
- Karty wracają do ręki: użyj **pary** `CardManager.cs` V28 + `FoldCardController.cs` V29 i `FlyAnimationController.cs` V28 z tego folderu; nie mieszaj starszych patchy. `PickUpCards` i `ThrowCards` mogą występować tylko raz.
- Karty nie widać: sprawdź `CardManager SEAT X CARDS` w Console, prefab, tekstury w `Resources/cards`, anchory.
- Dwa napisy `POT: 0`: sprawdź czy masz drugą instancję TableHUD lub ręcznie utworzony TextMeshPro; w skrypcie `PokerTableHUD` jest mechanizm wyboru jednego aktywnego HUD.
- Tekst jest odwrócony: w `FlyLabel` ustaw `Flip 180`. Dla puli w `PokerTableHUD` jest osobny `flipHud180`.
- Przełączenie na inną aplikację zatrzymuje animacje: `PokerReceiver` ustawia `Application.runInBackground`; w Unity Editor zweryfikuj dodatkowo ustawienia Play Mode.
- Python pauzuje po wyłączeniu Unity: to poprawne dla `--unity-disconnect pause`; po ponownym Play Mode wznawia. `continue` nie czeka na Unity.

**Szczegóły argumentów uruchomienia:** [COMMANDS.md](COMMANDS.md).
