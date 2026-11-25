"""Independent, reproducible evaluation against fixed rule-based bots.

No training, mutations, opponent hidden cards, or live renderer here.
For every trial, the same deck RNG seed is used for all four candidate seats;
StrongPokerBot RNG seeds and evaluation settings stay fixed across generations.
Scores are *estimates*, not guarantees of poker skill or GTO optimality.
"""
from __future__ import annotations

from poker.env import PokerEnv
from .strong_bot import StrongPokerBot

BENCHMARK_VERSION = "strongbot_fixed_seats_v1"


def evaluate_brain(brain, config, *, tables_per_seat=2, seed=980_123,
                   max_session_hands=None):
    tables_per_seat = int(tables_per_seat)
    if tables_per_seat < 1:
        raise ValueError("tables_per_seat must be >= 1")
    cap = max(1, int(max_session_hands or getattr(config, "max_hands_per_session", 500)))
    profit = 0
    hands = 0
    tables = 0
    wins = 0
    capped = 0
    # Explicit pair rotation; avoid grading a candidate on one fortunate seat.
    for trial in range(tables_per_seat):
        for fly_seat in range(4):
            # Same trial's deck seed across all 4 seats, for every generation.
            env = PokerEnv(config, seed=int(seed) + trial * 100_003)
            env.reset_session()
            agents = [StrongPokerBot(config, seed=int(seed) + 1000 + trial * 17 + s)
                      for s in range(4)]
            agents[fly_seat] = brain
            tables += 1
            for _ in range(cap):
                if env.session_over:
                    break
                result = env.play_hand(agents)
                profit += int(result["profits"][fly_seat])
                # An eliminated player is not charged additional hands after busting.
                if result["start_stacks"][fly_seat] > 0:
                    hands += 1
            if env.session_over:
                wins += int(env.session_winner == fly_seat)
            else:
                capped += 1

    bb100 = (float(profit) / float(config.big_blind)) * 100.0 / max(1, hands)
    return {
        "bb100": float(bb100),
        "profit_chips": int(profit),
        "hands": int(hands),
        "tables": int(tables),
        "table_wins": int(wins),
        "capped_tables": int(capped),
        "seed": int(seed),
        "tables_per_seat": int(tables_per_seat),
        "version": BENCHMARK_VERSION,
    }
