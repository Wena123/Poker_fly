"""Fast observable (no hidden opponents' cards) poker hand descriptors.

The seven signals go immediately BEFORE the final 14 legal-action bits.
They are cheap heuristics, not exact multiway equity or GTO advice.
"""
import numpy as np
from .cards import rank, suit
from .evaluator import evaluate_best

HAND_FEATURE_COUNT = 7


def hand_features(hole, board, pot=0, to_call=0):
    hole = list(hole)
    board = list(board)
    if len(hole) != 2:
        return np.zeros(HAND_FEATURE_COUNT, dtype=np.float32)
    hi, lo = sorted((rank(c) for c in hole), reverse=True)
    suited = int(suit(hole[0]) == suit(hole[1]))
    pocket = int(hi == lo)
    gap = hi - lo
    if pocket:
        preflop = 0.48 + (hi - 2) / 12.0 * 0.51
    else:
        preflop = (0.20 + (hi - 2) / 12 * 0.40 + (lo - 2) / 12 * 0.18
                   + suited * 0.065 + (0.055 if gap == 1 else 0.025 if gap == 2 else -0.055 if gap >= 5 else 0.0)
                   + (0.075 if hi >= 11 and lo >= 10 else 0.0)
                   + (0.055 if hi == 14 and lo >= 10 else 0.0))
    preflop = float(np.clip(preflop, 0.08, 0.995))
    cards = hole + board
    category = int(evaluate_best(cards)[0]) if len(cards) >= 5 else 0
    # Hand category is a basic made-hand signal, not a claim of win probability.
    made = category / 8.0
    counts = [sum(suit(c) == ss for c in cards) for ss in range(4)]
    flush_draw = float(len(board) in (3, 4) and category < 5
                       and any(counts[suit(h)] == 4 for h in hole))
    ranks = {rank(c) for c in cards}
    if 14 in ranks:
        ranks.add(1)
    straight_draw = float(len(board) in (3, 4) and category < 4
                          and any(sum(r in ranks for r in range(st, st + 5)) == 4
                                  and any((rank(h) in range(st, st + 5)
                                           or (rank(h) == 14 and st == 1)) for h in hole)
                                  for st in range(1, 11)))
    pot_odds = float(to_call / max(1.0, float(pot) + float(to_call)))
    return np.array([preflop, made, flush_draw, straight_draw,
                     float(suited), float(pocket), pot_odds], dtype=np.float32)
