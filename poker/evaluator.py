from collections import Counter
from itertools import combinations
from .cards import rank, suit

# Zwracamy krotkę: im większa leksykograficznie, tym lepsza ręka.
# category:
# 8 straight flush
# 7 four of a kind
# 6 full house
# 5 flush
# 4 straight
# 3 three of a kind
# 2 two pair
# 1 pair
# 0 high card

def _straight_high(ranks):
    uniq = sorted(set(ranks), reverse=True)
    if 14 in uniq:
        uniq.append(1)  # wheel A-2-3-4-5
    run = 1
    for i in range(1, len(uniq)):
        if uniq[i - 1] - 1 == uniq[i]:
            run += 1
            if run >= 5:
                return uniq[i - 4]
        else:
            run = 1
    return None

def score_five(cards):
    ranks = [rank(c) for c in cards]
    suits = [suit(c) for c in cards]
    counts = Counter(ranks)
    ordered = sorted(ranks, reverse=True)

    is_flush = len(set(suits)) == 1
    straight_high = _straight_high(ranks)

    if is_flush and straight_high:
        return (8, straight_high)

    by_count = sorted(counts.items(), key=lambda x: (x[1], x[0]), reverse=True)

    if by_count[0][1] == 4:
        quad = by_count[0][0]
        kicker = max(r for r in ranks if r != quad)
        return (7, quad, kicker)

    trips = sorted((r for r, c in counts.items() if c == 3), reverse=True)
    pairs = sorted((r for r, c in counts.items() if c >= 2), reverse=True)
    if trips:
        trip = trips[0]
        remaining_pairs = [r for r in pairs if r != trip]
        if remaining_pairs:
            return (6, trip, remaining_pairs[0])

    if is_flush:
        return (5, *ordered)

    if straight_high:
        return (4, straight_high)

    if trips:
        trip = trips[0]
        kickers = sorted((r for r in ranks if r != trip), reverse=True)[:2]
        return (3, trip, *kickers)

    exact_pairs = sorted((r for r, c in counts.items() if c == 2), reverse=True)
    if len(exact_pairs) >= 2:
        high_pair, low_pair = exact_pairs[:2]
        kicker = max(r for r in ranks if r not in (high_pair, low_pair))
        return (2, high_pair, low_pair, kicker)

    if len(exact_pairs) == 1:
        pair = exact_pairs[0]
        kickers = sorted((r for r in ranks if r != pair), reverse=True)[:3]
        return (1, pair, *kickers)

    return (0, *ordered)

def evaluate_best(cards):
    if len(cards) < 5:
        raise ValueError("Potrzeba co najmniej 5 kart.")
    return max(score_five(combo) for combo in combinations(cards, 5))
