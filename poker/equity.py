from itertools import combinations
import random

from .evaluator import evaluate_best


class EquityCalculator:
    """Spectator-only Hold'em showdown equity calculator.

    Uses all four known hole-card pairs from the simulator, but the result is
    never fed into an agent observation. Folded players receive 0% equity.

    - preflop: deterministic Monte Carlo for speed
    - flop/turn/river: exact enumeration
    """

    def __init__(self, preflop_samples=3000, seed=0xF17E):
        self.preflop_samples = max(250, int(preflop_samples))
        self.seed = int(seed)
        self._cache = {}

    def _key(self, env):
        return (
            tuple(tuple(int(c) for c in s.hole) for s in env.seats),
            tuple(int(c) for c in env.board),
            tuple(bool(s.folded) for s in env.seats),
        )

    @staticmethod
    def _award_equity(scores, active):
        best = max(scores[i] for i in active)
        winners = [i for i in active if scores[i] == best]
        share = 1.0 / len(winners)
        return winners, share

    def calculate(self, env):
        key = self._key(env)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        active = [i for i, s in enumerate(env.seats) if not s.folded]
        equity = [0.0, 0.0, 0.0, 0.0]

        if not active:
            result = {"equity": equity, "favorite": [], "final_winners": []}
            self._cache[key] = result
            return result

        if len(active) == 1:
            equity[active[0]] = 1.0
            result = {
                "equity": equity,
                "favorite": active[:],
                "final_winners": active[:],
            }
            self._cache[key] = result
            return result

        board = list(env.board)
        missing = max(0, 5 - len(board))
        known = set(board)
        for s in env.seats:
            known.update(s.hole)
        remaining = [c for c in range(52) if c not in known]

        totals = [0.0, 0.0, 0.0, 0.0]
        trials = 0

        def score_board(full_board):
            nonlocal trials
            scores = {
                i: evaluate_best(list(env.seats[i].hole) + list(full_board))
                for i in active
            }
            winners, share = self._award_equity(scores, active)
            for i in winners:
                totals[i] += share
            trials += 1

        if missing == 0:
            score_board(board)
        elif missing <= 2:
            for extra in combinations(remaining, missing):
                score_board(board + list(extra))
        else:
            # Stable result for the same state: deterministic seed based on cards/folds.
            state_seed = self.seed
            for part in key[0]:
                for c in part:
                    state_seed = (state_seed * 1315423911 + c + 17) & 0xFFFFFFFF
            for c in key[1]:
                state_seed = (state_seed * 2654435761 + c + 31) & 0xFFFFFFFF
            for f in key[2]:
                state_seed = (state_seed * 33 + int(f)) & 0xFFFFFFFF
            rng = random.Random(state_seed)
            for _ in range(self.preflop_samples):
                extra = rng.sample(remaining, missing)
                score_board(board + extra)

        if trials:
            equity = [v / trials for v in totals]

        best = max(equity[i] for i in active)
        favorite = [i for i in active if abs(equity[i] - best) < 1e-12]

        final_winners = []
        if len(active) == 1:
            final_winners = active[:]
        elif len(board) == 5:
            scores = {
                i: evaluate_best(list(env.seats[i].hole) + board)
                for i in active
            }
            final_winners, _ = self._award_equity(scores, active)

        result = {
            "equity": equity,
            "favorite": favorite,
            "final_winners": final_winners,
        }
        self._cache[key] = result
        # Keep cache bounded across long training runs.
        if len(self._cache) > 512:
            self._cache.clear()
            self._cache[key] = result
        return result
