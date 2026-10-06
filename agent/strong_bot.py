import math
import numpy as np

from poker.cards import rank, suit
from poker.evaluator import evaluate_best
from poker.env import (
    ACTION_COUNT,
    FOLD, CHECK, CALL,
    MIN_RAISE, POT_1_4, POT_1_3, POT_1_2, POT_2_3, POT_3_4,
    POT_1, POT_1_25, POT_1_5, POT_2, ALL_IN,
)


class StrongPokerBot:
    """Fast rule-based no-limit Hold'em baseline.

    The bot uses ONLY the same observation vector a fly receives: its own hole
    cards, public board, pot/stack/bet state, positions and public actions. It
    never reads opponents' hidden cards.

    It is intentionally lightweight enough to be used inside evolutionary
    training for many hands. It is a strong baseline, not a claim of GTO play.
    """

    display_name = "BOT"
    is_rule_bot = True

    def __init__(self, config, seed=2027):
        self.cfg = config
        self.starting_stack = float(config.starting_stack)
        self.big_blind = float(config.big_blind)
        self.rng = np.random.default_rng(seed)
        self.last_probs = np.zeros(ACTION_COUNT, dtype=np.float32)

    # ------------------------------------------------------------------
    # Observation decoding
    # ------------------------------------------------------------------
    def _decode(self, observation):
        x = np.asarray(observation, dtype=np.float32).reshape(-1)
        hole = np.flatnonzero(x[0:52] > 0.5).astype(int).tolist()
        board = np.flatnonzero(x[52:104] > 0.5).astype(int).tolist()
        street_idx = int(np.argmax(x[104:108]))
        seat_idx = int(np.argmax(x[108:112]))
        rel_button_idx = int(np.argmax(x[112:116]))
        scalars = x[116:122]
        pot = max(0.0, float(scalars[0]) * self.starting_stack)
        to_call = max(0.0, float(scalars[1]) * self.starting_stack)
        stack = max(0.0, float(scalars[2]) * self.starting_stack)
        current_bet = max(0.0, float(scalars[3]) * self.starting_stack)
        active_count = max(1, int(round(float(scalars[4]) * 4.0)))
        min_raise = max(self.big_blind, float(scalars[5]) * self.starting_stack)
        legal_mask = x[-ACTION_COUNT:]
        legal = [i for i, v in enumerate(legal_mask) if v > 0.5]
        return {
            "hole": hole,
            "board": board,
            "street": street_idx,
            "seat": seat_idx,
            "rel_button": rel_button_idx,
            "pot": pot,
            "to_call": to_call,
            "stack": stack,
            "current_bet": current_bet,
            "active_count": active_count,
            "min_raise": min_raise,
            "legal": legal,
        }

    # ------------------------------------------------------------------
    # Fast hand-strength heuristics
    # ------------------------------------------------------------------
    @staticmethod
    def _preflop_strength(hole):
        if len(hole) != 2:
            return 0.35
        r = sorted([rank(c) for c in hole], reverse=True)
        hi, lo = r
        suited = suit(hole[0]) == suit(hole[1])
        gap = hi - lo

        if hi == lo:
            # 22 ~= 0.48, AA ~= 0.99
            return float(np.clip(0.48 + (hi - 2) / 12.0 * 0.51, 0.0, 0.995))

        # High-card value, with broadway/suited/connector bonuses.
        value = 0.20
        value += (hi - 2) / 12.0 * 0.40
        value += (lo - 2) / 12.0 * 0.18
        if suited:
            value += 0.065
        if gap == 1:
            value += 0.055
        elif gap == 2:
            value += 0.025
        elif gap >= 5:
            value -= 0.055
        if hi >= 11 and lo >= 10:
            value += 0.075
        if hi == 14 and lo >= 10:
            value += 0.055
        if hi == 14 and suited and lo <= 5:
            value += 0.035
        return float(np.clip(value, 0.08, 0.94))

    @staticmethod
    def _has_flush_draw(cards):
        counts = [0, 0, 0, 0]
        for c in cards:
            counts[suit(c)] += 1
        return max(counts, default=0) == 4

    @staticmethod
    def _straight_draw_score(cards):
        ranks = set(rank(c) for c in cards)
        if 14 in ranks:
            ranks.add(1)
        best = 0
        for start in range(1, 11):
            hits = sum(1 for r in range(start, start + 5) if r in ranks)
            best = max(best, hits)
        if best >= 4:
            return 0.065
        if best == 3:
            return 0.018
        return 0.0

    def _postflop_strength(self, hole, board):
        cards = list(hole) + list(board)
        if len(cards) < 5:
            return self._preflop_strength(hole)

        score = evaluate_best(cards)
        category = int(score[0])
        category_base = {
            0: 0.18,
            1: 0.43,
            2: 0.62,
            3: 0.72,
            4: 0.80,
            5: 0.84,
            6: 0.93,
            7: 0.985,
            8: 0.997,
        }[category]

        # Tie-break detail adds a little information without pretending this is
        # exact equity.
        kicker = float(score[1]) if len(score) > 1 else 2.0
        strength = category_base + (kicker - 2.0) / 12.0 * (0.035 if category <= 3 else 0.018)

        # Draws are valuable primarily for weak made hands.
        if category < 5 and self._has_flush_draw(cards):
            strength += 0.075
        if category < 4:
            strength += self._straight_draw_score(cards)

        # Top-pair / overpair context.
        if category == 1 and board:
            board_high = max(rank(c) for c in board)
            hole_ranks = [rank(c) for c in hole]
            pair_rank = int(score[1])
            if pair_rank >= board_high:
                strength += 0.055
            if len(hole_ranks) == 2 and hole_ranks[0] == hole_ranks[1] and hole_ranks[0] > board_high:
                strength += 0.07

        return float(np.clip(strength, 0.02, 0.999))

    def _strength(self, s):
        if s["street"] == 0:
            return self._preflop_strength(s["hole"])
        return self._postflop_strength(s["hole"], s["board"])

    # ------------------------------------------------------------------
    # Policy
    # ------------------------------------------------------------------
    @staticmethod
    def _best_available(legal, preferences):
        legal = set(int(a) for a in legal)
        for action in preferences:
            if action in legal:
                return action
        return next(iter(legal)) if legal else CHECK

    def _scores(self, observation, legal_actions):
        s = self._decode(observation)
        legal = sorted(set(int(a) for a in legal_actions))
        strength = self._strength(s)
        pot = max(1.0, s["pot"])
        to_call = s["to_call"]
        stack = max(1.0, s["stack"])
        pot_odds = to_call / max(1.0, pot + to_call)
        spr = stack / max(self.big_blind, pot)

        scores = np.full(ACTION_COUNT, -1e9, dtype=np.float32)
        for a in legal:
            scores[a] = -4.0

        preflop = s["street"] == 0
        position_bonus = {0: 0.05, 1: -0.01, 2: 0.00, 3: -0.025}.get(s["rel_button"], 0.0)
        adjusted = float(np.clip(strength + position_bonus, 0.0, 1.0))

        # Core continue/fold logic.
        if FOLD in legal:
            scores[FOLD] = 1.10 - adjusted * 1.85 + pot_odds * 0.65
        if CHECK in legal:
            scores[CHECK] = 0.62 - adjusted * 0.38
        if CALL in legal:
            # Reward calls when hand strength comfortably clears the price.
            scores[CALL] = 0.35 + adjusted * 1.35 - pot_odds * 1.55

        # Betting / raising. Keep natural sizes more attractive than giant
        # overbets unless the hand is very strong.
        if preflop:
            raise_drive = (adjusted - 0.57) * 3.0
            prefs = [POT_1_2, POT_2_3, POT_3_4, MIN_RAISE, POT_1]
            size_bias = {
                MIN_RAISE: 0.07,
                POT_1_4: -0.18,
                POT_1_3: -0.08,
                POT_1_2: 0.16,
                POT_2_3: 0.14,
                POT_3_4: 0.09,
                POT_1: 0.03,
                POT_1_25: -0.16,
                POT_1_5: -0.30,
                POT_2: -0.45,
            }
        else:
            raise_drive = (adjusted - 0.54) * 3.2
            size_bias = {
                MIN_RAISE: -0.02,
                POT_1_4: 0.02,
                POT_1_3: 0.13,
                POT_1_2: 0.18,
                POT_2_3: 0.16,
                POT_3_4: 0.11,
                POT_1: 0.04,
                POT_1_25: -0.13,
                POT_1_5: -0.28,
                POT_2: -0.48,
            }

        for action, bias in size_bias.items():
            if action in legal:
                scores[action] = raise_drive + bias

        # Strong hands want larger value bets; medium hands prefer smaller sizes.
        if adjusted >= 0.80:
            for action, bonus in ((POT_2_3, 0.22), (POT_3_4, 0.25), (POT_1, 0.20), (POT_1_25, 0.08)):
                if action in legal:
                    scores[action] += bonus
        elif adjusted < 0.66:
            for action in (POT_3_4, POT_1, POT_1_25, POT_1_5, POT_2):
                if action in legal:
                    scores[action] -= 0.22

        # ALL-IN is deliberately hard to trigger. It becomes reasonable with a
        # monster and low SPR or when already facing a huge commitment.
        if ALL_IN in legal:
            shove_score = -5.0
            if adjusted >= 0.965:
                shove_score = 1.15 + (0.965 - pot_odds) + max(0.0, 1.8 - spr) * 0.42
            elif adjusted >= 0.90 and spr <= 1.15:
                shove_score = 0.95 + adjusted - pot_odds
            elif preflop and adjusted >= 0.965 and to_call >= 8 * self.big_blind:
                shove_score = 1.1
            scores[ALL_IN] = shove_score

        # If checking is free, folding must never be selected even if a caller
        # passes a strange legal set.
        if CHECK in legal and FOLD in legal:
            scores[FOLD] = -1e9

        return scores

    @staticmethod
    def _softmax(scores, legal, temperature=0.34):
        probs = np.zeros(ACTION_COUNT, dtype=np.float32)
        legal = [int(a) for a in legal if 0 <= int(a) < ACTION_COUNT]
        if not legal:
            return probs
        vals = np.asarray([scores[a] for a in legal], dtype=np.float64)
        m = float(np.max(vals))
        e = np.exp((vals - m) / max(0.05, float(temperature)))
        e_sum = float(np.sum(e))
        if not math.isfinite(e_sum) or e_sum <= 0:
            probs[legal] = 1.0 / len(legal)
            return probs
        for a, p in zip(legal, e / e_sum):
            probs[a] = float(p)
        return probs

    def decision_probabilities(self, observation, legal_actions):
        scores = self._scores(observation, legal_actions)
        return self._softmax(scores, legal_actions)

    def act(self, observation, legal_actions):
        legal = sorted(set(int(a) for a in legal_actions))
        if not legal:
            raise ValueError("StrongPokerBot received no legal actions")
        scores = self._scores(observation, legal)
        probs = self._softmax(scores, legal)
        self.last_probs = probs.astype(np.float32)

        # 90% disciplined best action, 10% mixed strategy from near-best
        # probabilities to make the bot less trivially exploitable.
        if float(self.rng.random()) < 0.90:
            return int(max(legal, key=lambda a: float(scores[a])))
        p = probs[legal].astype(np.float64)
        p /= max(1e-12, p.sum())
        return int(self.rng.choice(np.asarray(legal, dtype=np.int64), p=p))

    def debug_activations(self, observation):
        legal = self._decode(observation)["legal"]
        probs = self.decision_probabilities(observation, legal)
        # The rule bot has no neural hidden layers. Keep monitor-compatible
        # arrays while making this explicit in the UI.
        return {
            "hidden_1": np.zeros(64, dtype=np.float32),
            "hidden_2": np.zeros(32, dtype=np.float32),
            "output": probs.astype(np.float32),
        }
