from poker.renderer import PygameRenderer

def main():
    snap = {
        "side_pots": [
            {"amount": 101, "winners": [0, 2]},
            {"amount": 60, "winners": [2]},
        ]
    }
    payouts = PygameRenderer._payouts_from_side_pots(snap)
    assert payouts == [51, 0, 110, 0], payouts

    assert PygameRenderer._hand_name((8, 14)) == "ROYAL FLUSH"
    assert PygameRenderer._hand_name((8, 9)) == "STRAIGHT FLUSH"
    assert PygameRenderer._hand_name((4, 9)) == "STRAIGHT"

    print("WIN HISTORY / PAYOUT TEST: OK")

if __name__ == "__main__":
    main()
