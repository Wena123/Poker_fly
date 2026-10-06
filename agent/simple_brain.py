import numpy as np
from .brain_interface import BrainInterface


class SimpleFlyBrain(BrainInterface):
    """Small mutable MLP used as the temporary poker brain."""

    def __init__(self, input_size, hidden_1=64, hidden_2=32, output_size=14, rng=None):
        self.input_size = int(input_size)
        self.hidden_1 = int(hidden_1)
        self.hidden_2 = int(hidden_2)
        self.output_size = int(output_size)
        rng = rng or np.random.default_rng()

        def init(a, b):
            return rng.normal(0.0, 1.0 / np.sqrt(max(1, a)), size=(a, b)).astype(np.float32)

        self.w1 = init(self.input_size, self.hidden_1)
        self.b1 = np.zeros(self.hidden_1, dtype=np.float32)
        self.w2 = init(self.hidden_1, self.hidden_2)
        self.b2 = np.zeros(self.hidden_2, dtype=np.float32)
        self.w3 = init(self.hidden_2, self.output_size)
        self.b3 = np.zeros(self.output_size, dtype=np.float32)

    def forward(self, x, return_debug=False):
        x = np.asarray(x, dtype=np.float32)
        h1 = np.tanh(x @ self.w1 + self.b1)
        h2 = np.tanh(h1 @ self.w2 + self.b2)
        out = h2 @ self.w3 + self.b3
        if return_debug:
            return out, {
                "input": x.copy(),
                "hidden_1": h1.copy(),
                "hidden_2": h2.copy(),
                "output": out.copy(),
            }
        return out

    def act(self, observation, legal_actions):
        logits = self.forward(observation)
        masked = np.full(self.output_size, -1e30, dtype=np.float32)
        for a in legal_actions:
            if 0 <= int(a) < self.output_size:
                masked[int(a)] = logits[int(a)]
        return int(np.argmax(masked))

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
        for name in ("w1", "b1", "w2", "b2", "w3", "b3"):
            setattr(other, name, getattr(self, name).copy())
        return other

    def mutate(self, strength: float, probability: float, rng):
        child = self.copy()
        for name in ("w1", "b1", "w2", "b2", "w3", "b3"):
            arr = getattr(child, name)
            mask = rng.random(arr.shape) < probability
            noise = rng.normal(0.0, strength, size=arr.shape).astype(np.float32)
            arr += mask * noise
        return child

    def save(self, path):
        np.savez_compressed(
            path,
            input_size=self.input_size,
            hidden_1=self.hidden_1,
            hidden_2=self.hidden_2,
            output_size=self.output_size,
            w1=self.w1, b1=self.b1,
            w2=self.w2, b2=self.b2,
            w3=self.w3, b3=self.b3,
        )

    @classmethod
    def load(cls, path):
        data = np.load(path)
        output_size = int(data["output_size"]) if "output_size" in data else int(data["w3"].shape[1])
        brain = cls(
            int(data["input_size"]),
            int(data["hidden_1"]),
            int(data["hidden_2"]),
            output_size=output_size,
        )
        for name in ("w1", "b1", "w2", "b2", "w3", "b3"):
            setattr(brain, name, data[name].astype(np.float32))
        return brain
