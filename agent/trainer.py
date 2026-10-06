from pathlib import Path
import numpy as np

from poker.env import PokerEnv
from .simple_brain import SimpleFlyBrain
from .evolution import Evolution

class Trainer:
    def __init__(self, config, renderer=None, render_every=100, out_dir="checkpoints"):
        self.cfg = config
        self.renderer = renderer
        self.render_every = max(1, int(render_every))
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

        probe = PokerEnv(config, seed=config.seed)
        self.obs_size = probe.observation_size

        rng = np.random.default_rng(config.seed)
        self.brains = [
            SimpleFlyBrain(
                self.obs_size,
                hidden_1=config.hidden_1,
                hidden_2=config.hidden_2,
                rng=rng,
            )
            for _ in range(4)
        ]

        self.evolution = Evolution(
            mutation_strengths=config.mutation_strengths,
            mutation_probability=config.mutation_probability,
            seed=config.seed + 99,
        )

    def evaluate_generation(self, generation):
        env = PokerEnv(self.cfg, seed=self.cfg.seed + generation * 100_003)
        total_profit = np.zeros(4, dtype=np.float64)

        for hand_idx in range(1, self.cfg.hands_per_generation + 1):
            render_this = (
                self.renderer is not None
                and (hand_idx == 1 or hand_idx % self.render_every == 0)
            )

            callback = None
            if render_this:
                current_bb100 = (total_profit / self.cfg.big_blind) / max(1, hand_idx - 1) * 100.0
                self.renderer.set_meta(generation, hand_idx, current_bb100.tolist())
                callback = (lambda env, snap, agents: self.renderer.render(env, snap, agents))

            result = env.play_hand(self.brains, callback=callback)
            total_profit += np.asarray(result["profits"], dtype=np.float64)

            if self.renderer is not None and self.renderer.closed:
                break

        hands_played = hand_idx
        bb100 = (total_profit / self.cfg.big_blind) / max(1, hands_played) * 100.0
        return bb100, hands_played

    def run(self, generations=None):
        generations = int(generations or self.cfg.generations)
        history = []

        for gen in range(1, generations + 1):
            fitness, hands_played = self.evaluate_generation(gen)

            best_idx, champion, next_brains = self.evolution.next_generation(
                self.brains, fitness
            )

            checkpoint = self.out_dir / f"best_brain_gen_{gen:04d}.npz"
            champion.save(checkpoint)

            row = {
                "generation": gen,
                "hands": hands_played,
                "fitness": fitness.tolist(),
                "best_fly": best_idx + 1,
                "best_fitness": float(fitness[best_idx]),
                "checkpoint": str(checkpoint),
            }
            history.append(row)

            print(
                f"GEN {gen:04d} | "
                + " | ".join(f"Fly {i+1}: {v:+7.2f} bb/100" for i, v in enumerate(fitness))
                + f" | BEST: Fly {best_idx+1}"
            )

            self.brains = next_brains

            if self.renderer is not None and self.renderer.closed:
                break

        return history
