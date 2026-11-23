"""Structural integration checks only; cannot compile or run Unity Editor."""
from pathlib import Path
import re

root = Path(__file__).resolve().parent / "Unity" / "Assets" / "Script"
expected = {
    "AnchorHold.cs": ["class AnchorHold", "void PickUp(", "void ReleaseToBet("],
    "CardManager.cs": ["class CardManager", "void NewHand(", "void SetHoleCards(", "void SetBoard(", "void DetachHoleCardsForFold("],
    "ChipManager.cs": ["class ChipManager", "void NewHand(", "void CollectBetsToPot(", "void AwardPotToWinner(", "IsFlowBusy"],
    "FoldCardController.cs": ["class FoldCardController", "void PickUpCards(", "void ThrowCards(", "void ForceLandCards(", "IsThrowInProgress"],
    "FlyAnimationController.cs": ["class FlyAnimationController", 'case "FOLD":', "void AnimationFinished(", "WaitForFoldLanding"],
    "FlyLabel.cs": ["class FlyLabel", "void SetHoleCards(", "void ConfirmHandEnded(", "void SetStack(", "void SetAction("],
    "PokerTableHUD.cs": ["class PokerTableHUD", "GetPrimaryHUD(", "void SetPot(", "void SetBoard("],
    "PokerReceiver.cs": ["class PokerReceiver", 'case "collect_bets":', 'case "award_pot":', 'case "hand_end":', 'case "hole_cards":', 'case "animation":'],
}
for filename, needles in expected.items():
    path = root / filename
    assert path.is_file(), f"Missing Unity source: {path}"
    content = path.read_text(encoding="utf-8")
    assert re.search(r"public\s+class\s+" + re.escape(filename.removesuffix(".cs")), content), filename
    for needle in needles:
        assert needle in content, f"Missing {needle!r} in {filename}"
    # Deliberately do not count braces here: JSON inside C# string literals
    # contains literal braces and is not part of source-code block structure.

assert (root.parent / "Editor" / "FlyPokerFoldAnimatorFix.cs").is_file()
print("UNITY API STRUCTURAL CHECK: OK (no Unity Editor compilation was performed)")
