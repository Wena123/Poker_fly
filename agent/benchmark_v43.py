"""V43 matched-seed benchmark: comparable tournament profit, not noisy bb/100.

Each policy is the sole candidate against THREE StrongPokerBots. Candidate
and incumbent see identical seeds and seat rotations; only public/self cards
reach the policy. Profit per tournament is bounded (-100..300 BB at 1000/10).
"""
from __future__ import annotations
import numpy as np

from poker.env import PokerEnv
from .strong_bot import StrongPokerBot

BENCHMARK_VERSION = "paired_profit_per_tournament_v43"


def evaluate_policy(brain, config, *, tables_per_seat=12, seed=230_427,
                    max_session_hands=None):
    n = int(tables_per_seat)
    if n < 1:
        raise ValueError("tables_per_seat must be >= 1")
    cap = max(1, int(max_session_hands or getattr(config, "max_hands_per_session", 500)))
    values = []
    hands = 0
    wins = 0
    capped = 0
    for trial in range(n):
        for seat in range(4):
            # Different trial & seat seeds; matched across candidate/incumbent.
            game_seed = int(seed) + trial * 100_003 + seat * 13_007
            env = PokerEnv(config, seed=game_seed)
            env.reset_session()
            agents = [StrongPokerBot(config, seed=game_seed + 991 + k * 41)
                      for k in range(4)]
            agents[seat] = brain
            profit = 0
            for _ in range(cap):
                if env.session_over:
                    break
                result = env.play_hand(agents)
                profit += int(result["profits"][seat])
                if result["start_stacks"][seat] > 0:
                    hands += 1
            wins += int(env.session_over and env.session_winner == seat)
            capped += int(not env.session_over)
            values.append(profit / float(config.big_blind))
    vals = np.array(values, dtype=np.float64)
    return {
        "profit_bb_per_table": float(np.mean(vals)),
        "bb100": float(np.sum(vals) * 100.0 / max(1, hands)),
        "wins": int(wins), "tables": int(len(vals)),
        "win_rate": float(wins / len(vals)),
        "active_hands": int(hands), "capped": int(capped),
        "seed": int(seed), "tables_per_seat": n,
        "version": BENCHMARK_VERSION,
        # Required for matched comparison; not used in HOF JSON logs.
        "_table_profits_bb": vals.tolist(),
    }


def public_metrics(result):
    """Strip per-table arrays from long-lived JSON files/console output."""
    return {k: v for k, v in result.items() if not k.startswith("_")}


def compare_policies(challenger, incumbent, config, *, tables_per_seat=16,
                     seed=3_450_999, max_session_hands=None, z=0.8,
                     min_delta_bb=1.0):
    challenger_result = evaluate_policy(
        challenger, config, tables_per_seat=tables_per_seat,
        seed=seed, max_session_hands=max_session_hands,
    )
    incumbent_result = evaluate_policy(
        incumbent, config, tables_per_seat=tables_per_seat,
        seed=seed, max_session_hands=max_session_hands,
    )
    differences = np.array(challenger_result["_table_profits_bb"], dtype=np.float64) - np.array(
        incumbent_result["_table_profits_bb"], dtype=np.float64)
    delta = float(differences.mean())
    stderr = float(differences.std(ddof=1) / np.sqrt(len(differences))) if len(differences) > 1 else float("inf")
    lower = float(delta - float(z) * stderr)
    # A modest uncertainty margin, not a formal guarantee of skill.
    accepted = bool(delta >= float(min_delta_bb) and lower > 0.0)
    return {
        "accepted": accepted,
        "delta_profit_bb_per_table": delta,
        "paired_standard_error_bb": stderr,
        "lower_margin_bb": lower,
        "gate_z": float(z),
        "gate_min_delta_bb": float(min_delta_bb),
        "challenger": public_metrics(challenger_result),
        "incumbent": public_metrics(incumbent_result),
    }
