"""Configurable evolutionary fitness in big-blind units per 100 hands.

Only end-of-hand results count as reward. A stack of zero during an
unresolved all-in is NOT an elimination. PokerEnv determines busted after
hand payout. The optional stability penalty is a risk preference, not a
claim to calculate optimal poker strategy.
"""

import numpy as np


class RewardSystem:
    def __init__(self, big_blind=10, mode="balanced", win_bonus_bb=2.0,
                 risk_penalty=0.25, bust_penalty_bb=5.0):
        if mode not in ("classic", "balanced"):
            raise ValueError("reward mode must be classic or balanced")
        self.big_blind = float(big_blind)
        self.mode = mode
        self.win_bonus_bb = float(win_bonus_bb)
        self.risk_penalty = float(risk_penalty)
        self.bust_penalty_bb = float(bust_penalty_bb)

    def calculate(self, total_profit, bust_counts, hands_played, sessions_played,
                  table_wins=None, profit_samples=None):
        profits = np.asarray(total_profit, dtype=np.float64)
        busts = np.asarray(bust_counts, dtype=np.float64)
        hands = np.maximum(1., np.asarray(hands_played, dtype=np.float64))
        sessions = np.maximum(1., np.asarray(sessions_played, dtype=np.float64))
        wins = np.zeros_like(profits) if table_wins is None else np.asarray(table_wins, dtype=np.float64)
        raw_bb100 = profits / self.big_blind / hands * 100.
        bust_rate = busts / sessions
        bust_cost = busts * self.bust_penalty_bb / hands * 100.
        bonus = np.zeros_like(profits)
        risk = np.zeros_like(profits)
        if self.mode == "balanced":
            # Win bonus is per actual table victory, never for temporary all-in.
            bonus = wins * self.win_bonus_bb / hands * 100.
            if profit_samples is not None:
                for i, samples in enumerate(profit_samples):
                    if samples:
                        losses_bb = np.minimum(0., np.asarray(samples, dtype=np.float64) / self.big_blind)
                        # Small downside-deviation preference, not a rule to avoid all-ins.
                        risk[i] = self.risk_penalty * float(np.sqrt(np.mean(losses_bb ** 2)))
        fitness = raw_bb100 + bonus - bust_cost - risk
        return {
            "fitness": fitness,
            "raw_bb100": raw_bb100,
            "bust_rate": bust_rate,
            "bust_cost_bb100": bust_cost,
            "table_win_bonus_bb100": bonus,
            "risk_cost_bb100": risk,
        }
