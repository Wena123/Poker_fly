from dataclasses import dataclass, field
import random
import numpy as np

from .cards import make_deck, card_to_str
from .evaluator import evaluate_best

FOLD = 0
CHECK_CALL = 1
RAISE = 2
ACTION_NAMES = {
    FOLD: "FOLD",
    CHECK_CALL: "CHECK/CALL",
    RAISE: "RAISE",
}

STREETS = ("preflop", "flop", "turn", "river")

@dataclass
class Seat:
    hole: list = field(default_factory=list)
    stack: int = 0
    folded: bool = False
    total_contrib: int = 0
    street_contrib: int = 0
    last_action: int = -1

class PokerEnv:
    """
    4-osobowy Texas Hold'em do treningu self-play.

    Dla stabilności treningu starter używa limitowanych podbić:
    - preflop/flop: krok podbicia = 1 BB
    - turn/river: krok podbicia = 2 BB
    - maks. N podbić na street

    Każde rozdanie zaczyna się od równych stacków. Dzięki temu fitness
    mierzy jakość decyzji, a nie efekt wcześniejszego bankructwa.
    """
    def __init__(self, config, seed=None):
        if config.players != 4:
            raise ValueError("Ten starter jest przygotowany pod dokładnie 4 muchy.")
        self.cfg = config
        self.rng = random.Random(config.seed if seed is None else seed)
        self.button = -1
        self.hand_no = 0
        self.seats = [Seat() for _ in range(4)]
        self.board = []
        self.deck = []
        self.pot = 0
        self.street = "preflop"
        self.current_bet = 0
        self.current_actor = None
        self.raises_this_street = 0

        # 52 own-hole + 52 board + 4 street + 4 seat + 4 button-relative
        # + pot,to_call,stack,current_bet,active_count
        # + 4 stacks + 4 street contrib + 4 folded + 4*4 last-action onehot
        self.observation_size = 52 + 52 + 4 + 4 + 4 + 5 + 4 + 4 + 4 + 16

    def _reset_hand(self):
        self.hand_no += 1
        self.button = (self.button + 1) % 4
        self.deck = make_deck(self.rng)
        self.board = []
        self.pot = 0
        self.street = "preflop"
        self.current_bet = 0
        self.current_actor = None
        self.raises_this_street = 0

        for s in self.seats:
            s.hole = [self.deck.pop(), self.deck.pop()]
            s.stack = self.cfg.starting_stack
            s.folded = False
            s.total_contrib = 0
            s.street_contrib = 0
            s.last_action = -1

    def _pay(self, seat_idx, amount):
        s = self.seats[seat_idx]
        amount = min(int(amount), s.stack)
        s.stack -= amount
        s.total_contrib += amount
        s.street_contrib += amount
        self.pot += amount
        return amount

    def _post_blinds(self):
        sb = (self.button + 1) % 4
        bb = (self.button + 2) % 4
        self._pay(sb, self.cfg.small_blind)
        self._pay(bb, self.cfg.big_blind)
        self.current_bet = self.cfg.big_blind
        return sb, bb

    def _active(self):
        return [i for i, s in enumerate(self.seats) if not s.folded]

    def _next_active(self, idx):
        for step in range(1, 5):
            j = (idx + step) % 4
            if not self.seats[j].folded:
                return j
        return idx

    def _legal_actions(self, seat_idx, bet_size):
        s = self.seats[seat_idx]
        to_call = max(0, self.current_bet - s.street_contrib)
        legal = [CHECK_CALL]

        # Fold jest potrzebny głównie gdy trzeba dopłacić.
        if to_call > 0:
            legal.append(FOLD)

        if (
            self.raises_this_street < self.cfg.max_raises_per_street
            and s.stack >= to_call + bet_size
        ):
            legal.append(RAISE)

        return sorted(set(legal))

    def _encode_card_multi_hot(self, cards):
        out = np.zeros(52, dtype=np.float32)
        for c in cards:
            out[c] = 1.0
        return out

    def observation(self, seat_idx):
        s = self.seats[seat_idx]
        to_call = max(0, self.current_bet - s.street_contrib)
        start = float(self.cfg.starting_stack)
        bb = float(self.cfg.big_blind)

        parts = [
            self._encode_card_multi_hot(s.hole),
            self._encode_card_multi_hot(self.board),
        ]

        street_oh = np.zeros(4, dtype=np.float32)
        street_oh[STREETS.index(self.street)] = 1
        parts.append(street_oh)

        seat_oh = np.zeros(4, dtype=np.float32)
        seat_oh[seat_idx] = 1
        parts.append(seat_oh)

        rel_button = np.zeros(4, dtype=np.float32)
        rel_button[(self.button - seat_idx) % 4] = 1
        parts.append(rel_button)

        scalars = np.array([
            self.pot / start,
            to_call / start,
            s.stack / start,
            self.current_bet / start,
            len(self._active()) / 4.0,
        ], dtype=np.float32)
        parts.append(scalars)

        parts.append(np.array([x.stack / start for x in self.seats], dtype=np.float32))
        parts.append(np.array([x.street_contrib / max(bb, start) for x in self.seats], dtype=np.float32))
        parts.append(np.array([1.0 if x.folded else 0.0 for x in self.seats], dtype=np.float32))

        last = np.zeros(16, dtype=np.float32)
        # 4 możliwe "stany": brak akcji, fold, call/check, raise
        for i, x in enumerate(self.seats):
            code = x.last_action + 1
            code = max(0, min(3, code))
            last[i * 4 + code] = 1.0
        parts.append(last)

        obs = np.concatenate(parts)
        assert obs.shape[0] == self.observation_size
        return obs

    def snapshot(self, reveal_all=True):
        return {
            "hand_no": self.hand_no,
            "button": self.button,
            "street": self.street,
            "board": [card_to_str(c) for c in self.board],
            "pot": self.pot,
            "current_bet": self.current_bet,
            "current_actor": self.current_actor,
            "players": [
                {
                    "seat": i,
                    "hole": [card_to_str(c) for c in s.hole] if reveal_all else [],
                    "stack": s.stack,
                    "folded": s.folded,
                    "contrib": s.total_contrib,
                    "street_contrib": s.street_contrib,
                    "last_action": ACTION_NAMES.get(s.last_action, "-"),
                }
                for i, s in enumerate(self.seats)
            ],
        }

    def _betting_round(self, agents, first_to_act, bet_size, callback=None):
        self.raises_this_street = 0
        acted_since_raise = set()
        actor = first_to_act

        while True:
            active = self._active()
            if len(active) <= 1:
                return

            everyone_matched = all(
                self.seats[i].street_contrib == self.current_bet
                for i in active
            )
            if everyone_matched and all(i in acted_since_raise for i in active):
                return

            if self.seats[actor].folded:
                actor = self._next_active(actor)
                continue

            self.current_actor = actor
            legal = self._legal_actions(actor, bet_size)
            obs = self.observation(actor)
            action = int(agents[actor].act(obs, legal))
            if action not in legal:
                action = CHECK_CALL

            s = self.seats[actor]
            to_call = max(0, self.current_bet - s.street_contrib)

            if action == FOLD:
                s.folded = True
                s.last_action = FOLD
                acted_since_raise.add(actor)

            elif action == CHECK_CALL:
                self._pay(actor, to_call)
                s.last_action = CHECK_CALL
                acted_since_raise.add(actor)

            elif action == RAISE:
                self._pay(actor, to_call + bet_size)
                self.current_bet += bet_size
                self.raises_this_street += 1
                s.last_action = RAISE
                acted_since_raise = {actor}

            if callback is not None:
                callback(self, self.snapshot(reveal_all=True), agents)

            active = self._active()
            if len(active) <= 1:
                return

            actor = self._next_active(actor)

    def _new_street(self, street):
        self.street = street
        self.current_bet = 0
        self.raises_this_street = 0
        for s in self.seats:
            s.street_contrib = 0
            s.last_action = -1

    def _deal_board(self, count):
        # Burn card jak w normalnym Hold'em.
        self.deck.pop()
        for _ in range(count):
            self.board.append(self.deck.pop())

    def _award(self):
        active = self._active()
        if len(active) == 1:
            winners = active
        else:
            scores = {
                i: evaluate_best(self.seats[i].hole + self.board)
                for i in active
            }
            best = max(scores.values())
            winners = [i for i, score in scores.items() if score == best]

        share, rem = divmod(self.pot, len(winners))
        for i in winners:
            self.seats[i].stack += share
        for i in sorted(winners)[:rem]:
            self.seats[i].stack += 1

        return winners

    def play_hand(self, agents, callback=None):
        if len(agents) != 4:
            raise ValueError("Potrzeba dokładnie 4 agentów.")

        self._reset_hand()
        sb, bb = self._post_blinds()

        if callback is not None:
            callback(self, self.snapshot(reveal_all=True), agents)

        # Preflop: gracz po lewej od BB.
        self._betting_round(
            agents,
            first_to_act=(bb + 1) % 4,
            bet_size=self.cfg.big_blind,
            callback=callback,
        )

        if len(self._active()) > 1:
            self._new_street("flop")
            self._deal_board(3)
            self._betting_round(
                agents,
                first_to_act=self._next_active(self.button),
                bet_size=self.cfg.big_blind,
                callback=callback,
            )

        if len(self._active()) > 1:
            self._new_street("turn")
            self._deal_board(1)
            self._betting_round(
                agents,
                first_to_act=self._next_active(self.button),
                bet_size=2 * self.cfg.big_blind,
                callback=callback,
            )

        if len(self._active()) > 1:
            self._new_street("river")
            self._deal_board(1)
            self._betting_round(
                agents,
                first_to_act=self._next_active(self.button),
                bet_size=2 * self.cfg.big_blind,
                callback=callback,
            )

        self.current_actor = None
        winners = self._award()

        if callback is not None:
            callback(self, self.snapshot(reveal_all=True), agents)

        profits = [
            s.stack - self.cfg.starting_stack
            for s in self.seats
        ]

        # Zero-sum kontrola (pomijając bugi).
        assert sum(profits) == 0, profits

        return {
            "profits": profits,
            "winners": winners,
            "board": [card_to_str(c) for c in self.board],
            "button": self.button,
        }
