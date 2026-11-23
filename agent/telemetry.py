"""Action statistics without exposing opponents' hidden cards to the agents."""
from poker.env import FOLD, CHECK, CALL, ALL_IN


class ActionTelemetry:
    def __init__(self):
        self.counts = [{key: 0 for key in ("fold", "check", "call", "raise", "all_in")} for _ in range(4)]
        self.vpip = [0] * 4
        self.pfr = [0] * 4
        self.hands_seen = [0] * 4
        self.mapping = [0, 1, 2, 3]
        self._voluntary = set()
        self._raised = set()

    def set_mapping(self, seat_to_fly):
        self.mapping = list(seat_to_fly)

    def on_new_hand(self, env, agents):
        self._voluntary.clear()
        self._raised.clear()
        for i, fly in enumerate(self.mapping):
            if fly is not None and env.seats[i].stack + env.seats[i].street_contrib > 0:
                self.hands_seen[fly] += 1

    def after_action(self, env, seat, action, amount, agents):
        fly = self.mapping[int(seat)]
        if fly is None:
            return
        action = int(action)
        bucket = "fold" if action == FOLD else "check" if action == CHECK else "call" if action == CALL else "all_in" if action == ALL_IN else "raise"
        self.counts[fly][bucket] += 1
        if env.street == "preflop" and amount > 0 and (action == CALL or action >= 3):
            self._voluntary.add(fly)
        if env.street == "preflop" and action >= 3:
            self._raised.add(fly)

    def on_hand_end(self, env, agents, winners):
        for fly in self._voluntary:
            self.vpip[fly] += 1
        for fly in self._raised:
            self.pfr[fly] += 1

    def summary(self):
        return {
            "action_counts": [dict(x) for x in self.counts],
            "vpip_pct": [round(100. * self.vpip[i] / max(1, self.hands_seen[i]), 1) for i in range(4)],
            "pfr_pct": [round(100. * self.pfr[i] / max(1, self.hands_seen[i]), 1) for i in range(4)],
        }


class EventFanout:
    """Preserves UnityBridge and adds passive telemetry on the same events."""
    def __init__(self, *handlers):
        self.handlers = [h for h in handlers if h is not None]

    def __getattr__(self, name):
        def dispatch(*args, **kwargs):
            for handler in self.handlers:
                method = getattr(handler, name, None)
                if method is not None:
                    method(*args, **kwargs)
        return dispatch
