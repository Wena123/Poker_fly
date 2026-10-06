from dataclasses import dataclass, field
import random
import numpy as np

from .cards import make_deck, card_to_str
from .evaluator import evaluate_best

# ---------------------------------------------------------------------------
# Discrete no-limit action space
# ---------------------------------------------------------------------------
FOLD = 0
CHECK = 1
CALL = 2
MIN_RAISE = 3
POT_1_4 = 4
POT_1_3 = 5
POT_1_2 = 6
POT_2_3 = 7
POT_3_4 = 8
POT_1 = 9
POT_1_25 = 10
POT_1_5 = 11
POT_2 = 12
ALL_IN = 13
ACTION_COUNT = 14

ACTION_NAMES = {
    FOLD: "FOLD",
    CHECK: "CHECK",
    CALL: "CALL",
    MIN_RAISE: "MIN RAISE",
    POT_1_4: "1/4 POT",
    POT_1_3: "1/3 POT",
    POT_1_2: "1/2 POT",
    POT_2_3: "2/3 POT",
    POT_3_4: "3/4 POT",
    POT_1: "POT",
    POT_1_25: "1.25x POT",
    POT_1_5: "1.5x POT",
    POT_2: "2x POT",
    ALL_IN: "ALL-IN",
}

ACTION_LABELS = tuple(ACTION_NAMES[i] for i in range(ACTION_COUNT))

RAISE_FRACTIONS = {
    POT_1_4: 0.25,
    POT_1_3: 1.0 / 3.0,
    POT_1_2: 0.50,
    POT_2_3: 2.0 / 3.0,
    POT_3_4: 0.75,
    POT_1: 1.00,
    POT_1_25: 1.25,
    POT_1_5: 1.50,
    POT_2: 2.00,
}

BET_ACTIONS = (MIN_RAISE, *RAISE_FRACTIONS.keys(), ALL_IN)
STREETS = ("preflop", "flop", "turn", "river")


@dataclass
class Seat:
    hole: list = field(default_factory=list)
    stack: int = 0
    folded: bool = False
    all_in: bool = False
    eliminated: bool = False
    total_contrib: int = 0
    street_contrib: int = 0
    last_action: int = -1
    last_amount: int = 0


class PokerEnv:
    """4-seat no-limit Hold'em environment with persistent table sessions.

    A table session starts with 4 x starting_stack chips. Stacks carry between
    hands. A seat with stack == 0 after a hand is eliminated and receives no
    more cards/blinds/actions. The session ends only when one seat remains and
    therefore owns the entire table bank.

    The next call to play_hand() automatically starts a fresh 4-player session.
    """

    def __init__(self, config, seed=None):
        if config.players != 4:
            raise ValueError("Ten projekt jest przygotowany pod dokładnie 4 miejsca przy stole.")

        self.cfg = config
        self.rng = random.Random(config.seed if seed is None else seed)

        self.table_chips = int(config.starting_stack) * 4
        self.button = -1
        self.small_blind_seat = None
        self.big_blind_seat = None

        self.hand_no = 0              # global hand counter inside this env
        self.session_no = 0
        self.session_hand_no = 0
        self.session_over = True
        self.session_winner = None
        self.elimination_order = []

        self.seats = [Seat() for _ in range(4)]
        self.board = []
        self.deck = []
        self.pot = 0
        self.street = "preflop"
        self.current_bet = 0
        self.current_actor = None
        self.last_raise_size = int(config.big_blind)
        self.last_winners = []
        self.side_pots = []

        # Keep the same 216-input observation layout as V15.
        self.observation_size = (
            52 + 52 + 4 + 4 + 4 + 6
            + 4 + 4 + 4 + 4
            + 4 * (ACTION_COUNT + 1)
            + 4
            + ACTION_COUNT
        )

    # ------------------------------------------------------------------
    # Session / hand lifecycle
    # ------------------------------------------------------------------
    def reset_session(self):
        """Start a completely fresh winner-takes-all table."""
        self.session_no += 1
        self.session_hand_no = 0
        self.session_over = False
        self.session_winner = None
        self.elimination_order = []
        self.button = -1
        self.small_blind_seat = None
        self.big_blind_seat = None

        for s in self.seats:
            s.hole = []
            s.stack = int(self.cfg.starting_stack)
            s.folded = False
            s.all_in = False
            s.eliminated = False
            s.total_contrib = 0
            s.street_contrib = 0
            s.last_action = -1
            s.last_amount = 0

        self.board = []
        self.deck = []
        self.pot = 0
        self.street = "preflop"
        self.current_bet = 0
        self.current_actor = None
        self.last_raise_size = int(self.cfg.big_blind)
        self.last_winners = []
        self.side_pots = []

    def _live_session(self):
        return [i for i, s in enumerate(self.seats) if not s.eliminated and s.stack > 0]

    @staticmethod
    def _next_in_set(idx, candidates):
        candidates = set(candidates)
        if not candidates:
            return None
        for step in range(1, 5):
            j = (idx + step) % 4
            if j in candidates:
                return j
        return next(iter(candidates))

    def _reset_hand(self):
        """Backward-compatible helper: prepare the next hand without resetting live stacks."""
        if self.session_over:
            self.reset_session()
        self._prepare_hand()

    def _prepare_hand(self):
        if self.session_over:
            self.reset_session()

        live = self._live_session()
        if len(live) < 2:
            # Defensive recovery. A completed session should have been reset.
            self.reset_session()
            live = self._live_session()

        self.hand_no += 1
        self.session_hand_no += 1
        self.button = self._next_in_set(self.button, live)

        self.deck = make_deck(self.rng)
        self.board = []
        self.pot = 0
        self.street = "preflop"
        self.current_bet = 0
        self.current_actor = None
        self.last_raise_size = int(self.cfg.big_blind)
        self.last_winners = []
        self.side_pots = []
        self.small_blind_seat = None
        self.big_blind_seat = None

        # Clear hand state, but DO NOT reset stacks.
        for s in self.seats:
            s.hole = []
            s.folded = bool(s.eliminated)
            s.all_in = False
            s.total_contrib = 0
            s.street_contrib = 0
            s.last_action = -1
            s.last_amount = 0

        # Deal only to seats still alive in the table session.
        # Round-robin deal makes the deck model closer to a real table.
        for _ in range(2):
            for seat in live:
                self.seats[seat].hole.append(self.deck.pop())

    # ------------------------------------------------------------------
    # Hand / seat helpers
    # ------------------------------------------------------------------
    def _pay(self, seat_idx, amount):
        s = self.seats[seat_idx]
        amount = min(max(0, int(amount)), s.stack)
        s.stack -= amount
        s.total_contrib += amount
        s.street_contrib += amount
        self.pot += amount
        if s.stack == 0 and not s.eliminated:
            s.all_in = True
        return amount

    def _post_blinds(self):
        live = self._live_session()
        if len(live) < 2:
            raise RuntimeError("Cannot post blinds with fewer than two live seats.")

        # Heads-up rule: dealer/button is the small blind.
        if len(live) == 2:
            sb = self.button
            bb = self._next_in_set(sb, live)
        else:
            sb = self._next_in_set(self.button, live)
            bb = self._next_in_set(sb, live)

        self.small_blind_seat = sb
        self.big_blind_seat = bb

        self._pay(sb, self.cfg.small_blind)
        self._pay(bb, self.cfg.big_blind)
        self.current_bet = max(s.street_contrib for s in self.seats)
        self.last_raise_size = int(self.cfg.big_blind)
        return sb, bb

    def _active(self):
        """Seats still owning cards in THIS hand, including all-in seats."""
        return [
            i for i, s in enumerate(self.seats)
            if not s.eliminated and not s.folded
        ]

    def _actionable(self):
        return [
            i for i, s in enumerate(self.seats)
            if not s.eliminated and not s.folded and not s.all_in and s.stack > 0
        ]

    def _next_active(self, idx):
        return self._next_in_set(idx, self._active())

    # ------------------------------------------------------------------
    # No-limit action sizing / legality
    # ------------------------------------------------------------------
    def _to_call(self, seat_idx):
        s = self.seats[seat_idx]
        return max(0, int(self.current_bet - s.street_contrib))

    def _all_in_target(self, seat_idx):
        s = self.seats[seat_idx]
        return int(s.street_contrib + s.stack)

    def _uncapped_raise_target(self, seat_idx, action):
        s = self.seats[seat_idx]
        if action == ALL_IN:
            return self._all_in_target(seat_idx)

        min_target = int(self.current_bet + max(1, self.last_raise_size))
        if action == MIN_RAISE:
            return min_target

        frac = RAISE_FRACTIONS.get(action)
        if frac is None:
            return int(self.current_bet)

        to_call = self._to_call(seat_idx)
        call_paid = min(to_call, s.stack)
        pot_after_call = int(self.pot + call_paid)
        raw_raise_increment = max(1, int(round(pot_after_call * float(frac))))
        raise_increment = max(int(self.last_raise_size), raw_raise_increment)
        return int(self.current_bet + raise_increment)

    def _legal_actions(self, seat_idx):
        s = self.seats[seat_idx]
        if s.eliminated or s.folded or s.all_in or s.stack <= 0:
            return []

        to_call = self._to_call(seat_idx)
        legal = [FOLD, CALL] if to_call > 0 else [CHECK]

        all_in_target = self._all_in_target(seat_idx)
        if all_in_target <= self.current_bet:
            return legal

        # De-duplicate bet buttons that would resolve to the same chip target.
        # Sizing buttons that would be forced to the stack cap are masked;
        # ALL-IN remains the one explicit stack-cap action.
        seen_targets = set()
        for action in (MIN_RAISE, *RAISE_FRACTIONS.keys()):
            target = self._uncapped_raise_target(seat_idx, action)
            if target <= self.current_bet:
                continue
            if target >= all_in_target:
                continue
            if target in seen_targets:
                continue
            seen_targets.add(target)
            legal.append(action)

        legal.append(ALL_IN)
        return sorted(set(legal))

    def _execute_action(self, seat_idx, action):
        s = self.seats[seat_idx]
        legal = self._legal_actions(seat_idx)
        if action not in legal:
            action = CALL if CALL in legal else CHECK if CHECK in legal else FOLD

        s.last_action = int(action)
        s.last_amount = 0
        old_bet = int(self.current_bet)

        if action == FOLD:
            s.folded = True
            return False

        if action == CHECK:
            return False

        if action == CALL:
            paid = self._pay(seat_idx, self._to_call(seat_idx))
            s.last_amount = int(paid)
            return False

        target = self._uncapped_raise_target(seat_idx, action)
        if action != ALL_IN:
            target = min(target, self._all_in_target(seat_idx))

        additional = max(0, int(target - s.street_contrib))
        paid = self._pay(seat_idx, additional)
        s.last_amount = int(paid)

        new_total = int(s.street_contrib)
        if new_total > old_bet:
            raise_size = int(new_total - old_bet)
            self.current_bet = new_total
            if raise_size >= self.last_raise_size:
                self.last_raise_size = raise_size
            return True
        return False

    # ------------------------------------------------------------------
    # Observation / snapshots
    # ------------------------------------------------------------------
    @staticmethod
    def _encode_card_multi_hot(cards):
        out = np.zeros(52, dtype=np.float32)
        for c in cards:
            out[c] = 1.0
        return out

    def observation(self, seat_idx):
        s = self.seats[seat_idx]
        to_call = self._to_call(seat_idx)
        start = float(self.cfg.starting_stack)

        parts = [
            self._encode_card_multi_hot(s.hole),
            self._encode_card_multi_hot(self.board),
        ]

        street_oh = np.zeros(4, dtype=np.float32)
        street_oh[STREETS.index(self.street)] = 1.0
        parts.append(street_oh)

        seat_oh = np.zeros(4, dtype=np.float32)
        seat_oh[seat_idx] = 1.0
        parts.append(seat_oh)

        rel_button = np.zeros(4, dtype=np.float32)
        rel_button[(self.button - seat_idx) % 4] = 1.0
        parts.append(rel_button)

        parts.append(np.array([
            self.pot / start,
            to_call / start,
            s.stack / start,
            self.current_bet / start,
            len(self._active()) / 4.0,
            self.last_raise_size / start,
        ], dtype=np.float32))

        parts.append(np.array([x.stack / start for x in self.seats], dtype=np.float32))
        parts.append(np.array([x.street_contrib / start for x in self.seats], dtype=np.float32))
        parts.append(np.array([1.0 if x.folded else 0.0 for x in self.seats], dtype=np.float32))
        parts.append(np.array([1.0 if x.all_in else 0.0 for x in self.seats], dtype=np.float32))

        last = np.zeros(4 * (ACTION_COUNT + 1), dtype=np.float32)
        for i, x in enumerate(self.seats):
            code = 0 if x.last_action < 0 else x.last_action + 1
            last[i * (ACTION_COUNT + 1) + code] = 1.0
        parts.append(last)

        parts.append(np.array([x.last_amount / start for x in self.seats], dtype=np.float32))

        legal_mask = np.zeros(ACTION_COUNT, dtype=np.float32)
        for a in self._legal_actions(seat_idx):
            legal_mask[a] = 1.0
        parts.append(legal_mask)

        obs = np.concatenate(parts)
        assert obs.shape[0] == self.observation_size, (obs.shape, self.observation_size)
        return obs

    def snapshot(self, reveal_all=True):
        return {
            "hand_no": self.hand_no,
            "session_no": self.session_no,
            "session_hand_no": self.session_hand_no,
            "session_over": bool(self.session_over),
            "session_winner": self.session_winner,
            "table_chips": self.table_chips,
            "alive_seats": self._live_session(),
            "elimination_order": list(self.elimination_order),
            "button": self.button,
            "small_blind": self.small_blind_seat,
            "big_blind": self.big_blind_seat,
            "street": self.street,
            "board": [card_to_str(c) for c in self.board],
            "pot": self.pot,
            "current_bet": self.current_bet,
            "last_raise_size": self.last_raise_size,
            "current_actor": self.current_actor,
            "winners": list(self.last_winners),
            "side_pots": list(self.side_pots),
            "players": [
                {
                    "seat": i,
                    "hole": [card_to_str(c) for c in s.hole] if reveal_all else [],
                    "stack": s.stack,
                    "folded": s.folded,
                    "all_in": s.all_in,
                    "eliminated": s.eliminated,
                    "contrib": s.total_contrib,
                    "street_contrib": s.street_contrib,
                    "last_action_id": s.last_action,
                    "last_action": ACTION_NAMES.get(s.last_action, "-"),
                    "last_amount": s.last_amount,
                    "legal_actions": [] if self.last_winners else self._legal_actions(i),
                }
                for i, s in enumerate(self.seats)
            ],
        }

    # ------------------------------------------------------------------
    # Betting / streets
    # ------------------------------------------------------------------
    def _betting_round(self, agents, first_to_act, callback=None):
        pending = set(self._actionable())
        if not pending:
            return

        actor = first_to_act if first_to_act in pending else self._next_in_set(first_to_act - 1, pending)
        safety = 0
        max_actions = int(getattr(self.cfg, "max_actions_per_street", 600))

        while pending:
            safety += 1
            if safety > max_actions:
                raise RuntimeError("Betting round safety limit exceeded; possible action-loop bug.")

            if len(self._active()) <= 1:
                return

            actionable = set(self._actionable())
            pending &= actionable
            if not pending:
                return

            if actor not in pending:
                actor = self._next_in_set(actor, pending)
                if actor is None:
                    return

            self.current_actor = actor
            legal = self._legal_actions(actor)
            if not legal:
                pending.discard(actor)
                actor = self._next_in_set(actor, pending)
                continue

            obs = self.observation(actor)
            action = int(agents[actor].act(obs, legal))
            if action not in legal:
                action = CALL if CALL in legal else CHECK if CHECK in legal else legal[0]

            raised = self._execute_action(actor, action)
            pending.discard(actor)

            if raised:
                pending = {i for i in self._actionable() if i != actor}

            if callback is not None:
                callback(self, self.snapshot(reveal_all=True), agents)

            if len(self._active()) <= 1:
                return

            actor = self._next_in_set(actor, pending)
            if actor is None:
                return

    def _new_street(self, street):
        self.street = street
        self.current_bet = 0
        self.last_raise_size = int(self.cfg.big_blind)
        self.current_actor = None
        for s in self.seats:
            s.street_contrib = 0
            s.last_action = -1
            s.last_amount = 0

    def _deal_board(self, count):
        self.deck.pop()  # burn
        for _ in range(count):
            self.board.append(self.deck.pop())

    # ------------------------------------------------------------------
    # Side pots / payout
    # ------------------------------------------------------------------
    def _award(self):
        active = self._active()
        self.side_pots = []

        if len(active) == 1:
            winner = active[0]
            self.seats[winner].stack += self.pot
            self.last_winners = [winner]
            self.side_pots = [{
                "amount": self.pot,
                "eligible": [winner],
                "winners": [winner],
            }]
            return [winner]

        scores = {i: evaluate_best(self.seats[i].hole + self.board) for i in active}
        contributions = [int(s.total_contrib) for s in self.seats]
        levels = sorted(set(c for c in contributions if c > 0))
        previous = 0
        overall_winners = set()
        paid_total = 0

        for level in levels:
            contributors = [i for i, c in enumerate(contributions) if c >= level]
            amount = int((level - previous) * len(contributors))
            previous = level
            if amount <= 0:
                continue

            eligible = [
                i for i in contributors
                if not self.seats[i].folded and not self.seats[i].eliminated
            ]
            if not eligible:
                continue

            best = max(scores[i] for i in eligible)
            winners = [i for i in eligible if scores[i] == best]
            share, rem = divmod(amount, len(winners))
            for i in winners:
                self.seats[i].stack += share
            for i in sorted(winners)[:rem]:
                self.seats[i].stack += 1

            paid_total += amount
            overall_winners.update(winners)
            self.side_pots.append({
                "amount": amount,
                "eligible": eligible,
                "winners": winners,
            })

        if paid_total != self.pot:
            missing = self.pot - paid_total
            if missing > 0:
                best = max(scores[i] for i in active)
                winners = [i for i in active if scores[i] == best]
                share, rem = divmod(missing, len(winners))
                for i in winners:
                    self.seats[i].stack += share
                for i in sorted(winners)[:rem]:
                    self.seats[i].stack += 1
                overall_winners.update(winners)

        self.last_winners = sorted(overall_winners)
        return self.last_winners

    # ------------------------------------------------------------------
    # Full hand
    # ------------------------------------------------------------------
    def play_hand(self, agents, callback=None):
        if len(agents) != 4:
            raise ValueError("Potrzeba dokładnie 4 agentów/seats.")

        # A fresh table is created only after the previous table has a sole winner.
        if self.session_over:
            self.reset_session()

        hand_start_stacks = [int(s.stack) for s in self.seats]
        self._prepare_hand()
        sb, bb = self._post_blinds()

        if callback is not None:
            callback(self, self.snapshot(reveal_all=True), agents)

        live_count = len(self._live_session())

        # Heads-up: button/SB acts first preflop. 3/4-handed: first left of BB.
        if live_count == 2:
            first_preflop = sb
        else:
            first_preflop = self._next_in_set(bb, self._actionable())

        if first_preflop is not None:
            self._betting_round(agents, first_to_act=first_preflop, callback=callback)

        if len(self._active()) > 1:
            self._new_street("flop")
            self._deal_board(3)
            first = self._next_in_set(self.button, self._actionable())
            if first is not None:
                self._betting_round(agents, first_to_act=first, callback=callback)

        if len(self._active()) > 1:
            self._new_street("turn")
            self._deal_board(1)
            first = self._next_in_set(self.button, self._actionable())
            if first is not None:
                self._betting_round(agents, first_to_act=first, callback=callback)

        if len(self._active()) > 1:
            self._new_street("river")
            self._deal_board(1)
            first = self._next_in_set(self.button, self._actionable())
            if first is not None:
                self._betting_round(agents, first_to_act=first, callback=callback)

        self.current_actor = None
        winners = self._award()

        hand_end_stacks = [int(s.stack) for s in self.seats]
        profits = [
            int(hand_end_stacks[i] - hand_start_stacks[i])
            for i in range(4)
        ]
        assert sum(profits) == 0, profits
        assert sum(hand_end_stacks) == self.table_chips, hand_end_stacks

        newly_busted = []
        for i, s in enumerate(self.seats):
            if hand_start_stacks[i] > 0 and s.stack == 0 and not s.eliminated:
                s.eliminated = True
                s.folded = True
                s.all_in = False
                newly_busted.append(i)

        # Preserve elimination order for the UI. Multiple busts in one hand
        # are recorded together in seat order; poker hand payouts decide chips.
        for i in newly_busted:
            if i not in self.elimination_order:
                self.elimination_order.append(i)

        live_after = self._live_session()
        self.session_over = len(live_after) == 1
        self.session_winner = live_after[0] if self.session_over else None

        if self.session_over:
            winner = self.session_winner
            # Chip conservation means the last seat must own the full 4000 bank.
            assert self.seats[winner].stack == self.table_chips, [
                s.stack for s in self.seats
            ]

        if callback is not None:
            callback(self, self.snapshot(reveal_all=True), agents)

        return {
            "profits": profits,
            "busted": [i in newly_busted for i in range(4)],
            "winners": winners,
            "board": [card_to_str(c) for c in self.board],
            "button": self.button,
            "small_blind": self.small_blind_seat,
            "big_blind": self.big_blind_seat,
            "pot": self.pot,
            "side_pots": list(self.side_pots),
            "start_stacks": hand_start_stacks,
            "end_stacks": hand_end_stacks,
            "session_no": self.session_no,
            "session_hand_no": self.session_hand_no,
            "session_over": bool(self.session_over),
            "session_winner": self.session_winner,
            "elimination_order": list(self.elimination_order),
        }
