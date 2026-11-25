import numpy as np

class Evolution:
    def __init__(self, mutation_strengths=(0.02, 0.05, 0.10), mutation_probability=0.12, seed=1337):
        self.strengths = tuple(mutation_strengths)
        self.probability = mutation_probability
        self.rng = np.random.default_rng(seed)

    def spawn_from(self, champion, generation=None, immigrant_every=0):
        champion = champion.copy()
        next_brains = [champion.copy()]
        for strength in self.strengths:
            next_brains.append(
                champion.mutate(
                    strength=float(strength),
                    probability=float(self.probability),
                    rng=self.rng,
                )
            )

        if (immigrant_every and generation is not None
                and int(generation) % int(immigrant_every) == 0):
            # Fresh genetic material; elite is NEVER replaced.
            exemplar = champion
            next_brains[-1] = type(exemplar)(
                exemplar.input_size, exemplar.hidden_1, exemplar.hidden_2,
                output_size=exemplar.output_size, rng=self.rng,
            )

        if len(next_brains) != 4:
            raise ValueError("Ten projekt zakłada: champion + dokładnie 3 mutacje.")

        return next_brains

    def next_generation(self, brains, fitness, generation=None, immigrant_every=0):
        best_idx = int(np.argmax(fitness))
        champion = brains[best_idx].copy()
        return best_idx, champion, self.spawn_from(champion, generation, immigrant_every)
