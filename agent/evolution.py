import numpy as np

class Evolution:
    def __init__(self, mutation_strengths=(0.02, 0.05, 0.10), mutation_probability=0.12, seed=1337):
        self.strengths = tuple(mutation_strengths)
        self.probability = mutation_probability
        self.rng = np.random.default_rng(seed)

    def next_generation(self, brains, fitness):
        best_idx = int(np.argmax(fitness))
        champion = brains[best_idx].copy()

        next_brains = [champion.copy()]
        for strength in self.strengths:
            next_brains.append(
                champion.mutate(
                    strength=float(strength),
                    probability=float(self.probability),
                    rng=self.rng,
                )
            )

        if len(next_brains) != 4:
            raise ValueError("Ten projekt zakłada: champion + dokładnie 3 mutacje.")

        return best_idx, champion, next_brains
