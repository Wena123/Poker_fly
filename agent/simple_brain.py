import numpy as np
from .brain_interface import BrainInterface

class SimpleFlyBrain(BrainInterface):
    """
    Mały MLP jako zastępczy mózg.
    Później możesz zachować ten sam interfejs i podmienić klasę
    na Twój rzeczywisty model muchy.
    """
    def __init__(self, input_size, hidden_1=64, hidden_2=32, rng=None):
        self.input_size = input_size
        self.hidden_1 = hidden_1
        self.hidden_2 = hidden_2
        rng = rng or np.random.default_rng()

        def init(a, b):
            return rng.normal(0.0, 1.0 / np.sqrt(max(1, a)), size=(a, b)).astype(np.float32)

        self.w1 = init(input_size, hidden_1)
        self.b1 = np.zeros(hidden_1, dtype=np.float32)
        self.w2 = init(hidden_1, hidden_2)
        self.b2 = np.zeros(hidden_2, dtype=np.float32)
        self.w3 = init(hidden_2, 3)
        self.b3 = np.zeros(3, dtype=np.float32)

    def forward(self, x, return_debug=False):
        x = np.asarray(x, dtype=np.float32)
        h1_pre = x @ self.w1 + self.b1
        h1 = np.tanh(h1_pre)
        h2_pre = h1 @ self.w2 + self.b2
        h2 = np.tanh(h2_pre)
        out = h2 @ self.w3 + self.b3
        if return_debug:
            return out, {
                'input': x.copy(),
                'hidden_1': h1.copy(),
                'hidden_2': h2.copy(),
                'output': out.copy(),
            }
        return out

    def act(self, observation, legal_actions):
        logits = self.forward(observation)
        masked = np.full(3, -1e30, dtype=np.float32)
        for a in legal_actions:
            masked[a] = logits[a]
        return int(np.argmax(masked))

    def debug_activations(self, observation):
        _, dbg = self.forward(observation, return_debug=True)
        return dbg

    def copy(self):
        other = SimpleFlyBrain(self.input_size, self.hidden_1, self.hidden_2)
        for name in ('w1', 'b1', 'w2', 'b2', 'w3', 'b3'):
            setattr(other, name, getattr(self, name).copy())
        return other

    def mutate(self, strength: float, probability: float, rng):
        child = self.copy()
        for name in ('w1', 'b1', 'w2', 'b2', 'w3', 'b3'):
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
            w1=self.w1, b1=self.b1,
            w2=self.w2, b2=self.b2,
            w3=self.w3, b3=self.b3,
        )

    @classmethod
    def load(cls, path):
        data = np.load(path)
        brain = cls(
            int(data['input_size']),
            int(data['hidden_1']),
            int(data['hidden_2']),
        )
        for name in ('w1', 'b1', 'w2', 'b2', 'w3', 'b3'):
            setattr(brain, name, data[name].astype(np.float32))
        return brain
