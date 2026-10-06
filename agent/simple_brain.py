import numpy as np
from .brain_interface import BrainInterface


class SimpleFlyBrain(BrainInterface):
    """Mutable MLP with a two-stage poker decision head.

    Stage 1 chooses the *kind* of decision:
        FOLD / CHECK / CALL / BET_RAISE

    Stage 2 is consulted only when BET_RAISE wins and chooses one of the
    available sizing actions:
        MIN, 1/4, 1/3, 1/2, 2/3, 3/4, POT, 1.25x, 1.5x, 2x, ALL-IN

    The environment still exposes the same 14 final action IDs, so the rest of
    the poker engine does not need to know about the internal hierarchy.
    """

    MAIN_FOLD = 0
    MAIN_CHECK = 1
    MAIN_CALL = 2
    MAIN_BET_RAISE = 3
    MAIN_COUNT = 4

    FINAL_ACTION_COUNT = 14
    FIRST_BET_ACTION = 3
    SIZE_COUNT = FINAL_ACTION_COUNT - FIRST_BET_ACTION  # 11

    def __init__(self, input_size, hidden_1=64, hidden_2=32, output_size=14, rng=None):
        self.input_size = int(input_size)
        self.hidden_1 = int(hidden_1)
        self.hidden_2 = int(hidden_2)
        # Kept for compatibility with the environment/monitor. Final actions = 14.
        self.output_size = int(output_size)
        if self.output_size != self.FINAL_ACTION_COUNT:
            raise ValueError("Hierarchical poker brain expects exactly 14 final actions.")

        rng = rng or np.random.default_rng()

        def init(a, b):
            return rng.normal(0.0, 1.0 / np.sqrt(max(1, a)), size=(a, b)).astype(np.float32)

        self.w1 = init(self.input_size, self.hidden_1)
        self.b1 = np.zeros(self.hidden_1, dtype=np.float32)
        self.w2 = init(self.hidden_1, self.hidden_2)
        self.b2 = np.zeros(self.hidden_2, dtype=np.float32)

        # Two separate heads instead of 14 flat competing outputs.
        self.w_action = init(self.hidden_2, self.MAIN_COUNT)
        self.b_action = np.zeros(self.MAIN_COUNT, dtype=np.float32)
        self.w_size = init(self.hidden_2, self.SIZE_COUNT)
        self.b_size = np.zeros(self.SIZE_COUNT, dtype=np.float32)

    @staticmethod
    def _softmax_masked(logits, legal_indices):
        logits = np.asarray(logits, dtype=np.float32).reshape(-1)
        probs = np.zeros_like(logits, dtype=np.float32)
        legal = [int(i) for i in legal_indices if 0 <= int(i) < len(logits)]
        if not legal:
            return probs
        vals = logits[legal]
        m = float(np.max(vals))
        e = np.exp(vals - m).astype(np.float32)
        denom = float(np.sum(e))
        if denom <= 0.0:
            probs[legal] = 1.0 / len(legal)
        else:
            probs[legal] = e / denom
        return probs

    def _heads(self, x):
        x = np.asarray(x, dtype=np.float32)
        h1 = np.tanh(x @ self.w1 + self.b1)
        h2 = np.tanh(h1 @ self.w2 + self.b2)
        action_head = h2 @ self.w_action + self.b_action
        sizing_head = h2 @ self.w_size + self.b_size
        return h1, h2, action_head, sizing_head

    @staticmethod
    def _main_legal_from_final(legal_actions):
        legal = {int(a) for a in legal_actions}
        out = []
        if 0 in legal:
            out.append(SimpleFlyBrain.MAIN_FOLD)
        if 1 in legal:
            out.append(SimpleFlyBrain.MAIN_CHECK)
        if 2 in legal:
            out.append(SimpleFlyBrain.MAIN_CALL)
        if any(a >= SimpleFlyBrain.FIRST_BET_ACTION for a in legal):
            out.append(SimpleFlyBrain.MAIN_BET_RAISE)
        return out

    @staticmethod
    def _legal_size_indices(legal_actions):
        return [
            int(a) - SimpleFlyBrain.FIRST_BET_ACTION
            for a in legal_actions
            if SimpleFlyBrain.FIRST_BET_ACTION <= int(a) < SimpleFlyBrain.FINAL_ACTION_COUNT
        ]

    def decision_probabilities(self, observation, legal_actions):
        """Return probabilities over the 14 final actions using the two heads.

        This is primarily for the monitor. The actual policy remains deterministic
        argmax, matching the previous evolutionary setup.
        """
        _, _, action_head, sizing_head = self._heads(observation)
        legal = {int(a) for a in legal_actions}
        main_legal = self._main_legal_from_final(legal)
        main_probs = self._softmax_masked(action_head, main_legal)

        final = np.zeros(self.FINAL_ACTION_COUNT, dtype=np.float32)
        if 0 in legal:
            final[0] = main_probs[self.MAIN_FOLD]
        if 1 in legal:
            final[1] = main_probs[self.MAIN_CHECK]
        if 2 in legal:
            final[2] = main_probs[self.MAIN_CALL]

        size_legal = self._legal_size_indices(legal)
        if size_legal:
            size_probs = self._softmax_masked(sizing_head, size_legal)
            bet_mass = main_probs[self.MAIN_BET_RAISE]
            for idx in size_legal:
                final[self.FIRST_BET_ACTION + idx] = bet_mass * size_probs[idx]

        total = float(final.sum())
        if total > 0:
            final /= total
        return final

    def forward(self, x, return_debug=False):
        h1, h2, action_head, sizing_head = self._heads(x)

        # A 14-value compatibility vector for older monitor/debug code.
        # Bet-size scores include the BET_RAISE gate score.
        combined = np.empty(self.FINAL_ACTION_COUNT, dtype=np.float32)
        combined[0] = action_head[self.MAIN_FOLD]
        combined[1] = action_head[self.MAIN_CHECK]
        combined[2] = action_head[self.MAIN_CALL]
        combined[3:] = action_head[self.MAIN_BET_RAISE] + sizing_head

        if return_debug:
            return combined, {
                "input": np.asarray(x, dtype=np.float32).copy(),
                "hidden_1": h1.copy(),
                "hidden_2": h2.copy(),
                "action_head": action_head.copy(),
                "sizing_head": sizing_head.copy(),
                "output": combined.copy(),
            }
        return combined

    def act(self, observation, legal_actions):
        legal = sorted({int(a) for a in legal_actions})
        if not legal:
            raise ValueError("act() received no legal poker actions")

        _, _, action_head, sizing_head = self._heads(observation)
        main_legal = self._main_legal_from_final(legal)
        main_masked = np.full(self.MAIN_COUNT, -1e30, dtype=np.float32)
        for idx in main_legal:
            main_masked[idx] = action_head[idx]
        main_choice = int(np.argmax(main_masked))

        if main_choice == self.MAIN_FOLD and 0 in legal:
            return 0
        if main_choice == self.MAIN_CHECK and 1 in legal:
            return 1
        if main_choice == self.MAIN_CALL and 2 in legal:
            return 2

        # BET_RAISE: now and only now choose the amount.
        size_legal = self._legal_size_indices(legal)
        if size_legal:
            size_masked = np.full(self.SIZE_COUNT, -1e30, dtype=np.float32)
            for idx in size_legal:
                size_masked[idx] = sizing_head[idx]
            return self.FIRST_BET_ACTION + int(np.argmax(size_masked))

        # Defensive fallback. Normally impossible because BET_RAISE would not
        # have been legal without at least one legal sizing action.
        if 2 in legal:
            return 2
        if 1 in legal:
            return 1
        return legal[0]

    def debug_activations(self, observation):
        _, dbg = self.forward(observation, return_debug=True)
        return dbg

    def copy(self):
        other = SimpleFlyBrain(
            self.input_size,
            self.hidden_1,
            self.hidden_2,
            output_size=self.output_size,
        )
        for name in (
            "w1", "b1", "w2", "b2",
            "w_action", "b_action", "w_size", "b_size",
        ):
            setattr(other, name, getattr(self, name).copy())
        return other

    def mutate(self, strength: float, probability: float, rng):
        child = self.copy()
        for name in (
            "w1", "b1", "w2", "b2",
            "w_action", "b_action", "w_size", "b_size",
        ):
            arr = getattr(child, name)
            mask = rng.random(arr.shape) < probability
            noise = rng.normal(0.0, strength, size=arr.shape).astype(np.float32)
            arr += mask * noise
        return child

    def save(self, path):
        np.savez_compressed(
            path,
            architecture=np.array("hierarchical_action_size_v1"),
            input_size=self.input_size,
            hidden_1=self.hidden_1,
            hidden_2=self.hidden_2,
            output_size=self.output_size,
            w1=self.w1, b1=self.b1,
            w2=self.w2, b2=self.b2,
            w_action=self.w_action, b_action=self.b_action,
            w_size=self.w_size, b_size=self.b_size,
        )

    @classmethod
    def load(cls, path):
        data = np.load(path)
        output_size = int(data["output_size"]) if "output_size" in data else 14
        brain = cls(
            int(data["input_size"]),
            int(data["hidden_1"]),
            int(data["hidden_2"]),
            output_size=output_size,
        )
        brain.w1 = data["w1"].astype(np.float32)
        brain.b1 = data["b1"].astype(np.float32)
        brain.w2 = data["w2"].astype(np.float32)
        brain.b2 = data["b2"].astype(np.float32)

        if "w_action" in data and "w_size" in data:
            brain.w_action = data["w_action"].astype(np.float32)
            brain.b_action = data["b_action"].astype(np.float32)
            brain.w_size = data["w_size"].astype(np.float32)
            brain.b_size = data["b_size"].astype(np.float32)
            return brain

        # Backward compatibility with V10/V11 flat 14-output checkpoints.
        if "w3" in data:
            old_w = data["w3"].astype(np.float32)
            old_b = data["b3"].astype(np.float32)
            brain.w_action[:, :3] = old_w[:, :3]
            brain.b_action[:3] = old_b[:3]
            brain.w_action[:, 3] = np.mean(old_w[:, 3:14], axis=1)
            brain.b_action[3] = float(np.mean(old_b[3:14]))
            brain.w_size[:, :] = old_w[:, 3:14]
            brain.b_size[:] = old_b[3:14]
            return brain

        raise ValueError("Unsupported checkpoint format")
