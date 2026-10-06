import random

RANK_CHARS = "23456789TJQKA"
SUIT_CHARS = "CDHS"

def rank(card: int) -> int:
    return card % 13 + 2

def suit(card: int) -> int:
    return card // 13

def card_to_str(card: int) -> str:
    return RANK_CHARS[rank(card) - 2] + SUIT_CHARS[suit(card)]

def make_deck(rng: random.Random):
    deck = list(range(52))
    rng.shuffle(deck)
    return deck
