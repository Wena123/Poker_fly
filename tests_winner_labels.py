from poker.renderer import PygameRenderer

def main():
    h = PygameRenderer._hand_name
    assert h((8, 14)) == "ROYAL FLUSH"
    assert h((8, 9)) == "STRAIGHT FLUSH"
    assert h((7, 13, 12)) == "FOUR OF A KIND"
    assert h((6, 10, 8)) == "FULL HOUSE"
    assert h((5, 14, 12, 9, 7, 3)) == "FLUSH"
    assert h((4, 11)) == "STRAIGHT"
    assert h((3, 9, 14, 7)) == "THREE OF A KIND"
    assert h((2, 12, 8, 14)) == "TWO PAIR"
    assert h((1, 6, 14, 11, 9)) == "ONE PAIR"
    assert h((0, 14, 12, 10, 8, 5)) == "HIGH CARD"
    print("WINNER LABEL TEST: OK")

if __name__ == "__main__":
    main()
