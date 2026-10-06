from pathlib import Path
import numpy as np

from poker.env import PokerEnv, ACTION_COUNT
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
                output_size=ACTION_COUNT,
                rng=rng,
            )
            for _ in range(4)
        ]

        self.evolution = Evolution(
            mutation_strengths=config.mutation_strengths,
            mutation_probability=config.mutation_probability,
            seed=config.seed + 99,
        )

    def _fitness_metrics(self, total_profit, bust_counts, hands_played):
        hands = max(1, int(hands_played))
        raw_bb100 = (np.asarray(total_profit, dtype=np.float64) / self.cfg.big_blind) / hands * 100.0
        bust_rate = np.asarray(bust_counts, dtype=np.float64) / hands

        # Each bust costs N BB in total fitness. After normalizing to BB/100:
        # 1 bust per 100 hands with bust_penalty_bb=5 => -5 BB/100.
        bust_penalty_bb100 = (
            np.asarray(bust_counts, dtype=np.float64)
            * float(self.cfg.bust_penalty_bb)
            / hands
            * 100.0
        )
        fitness = raw_bb100 - bust_penalty_bb100
        return fitness, raw_bb100, bust_rate, bust_penalty_bb100

    def evaluate_generation(self, generation):
        env = PokerEnv(self.cfg, seed=self.cfg.seed + generation * 100_003)
        total_profit = np.zeros(4, dtype=np.float64)
        bust_counts = np.zeros(4, dtype=np.int64)

        hand_idx = 0
        for hand_idx in range(1, self.cfg.hands_per_generation + 1):
            render_this = (
                self.renderer is not None
                and (hand_idx == 1 or hand_idx % self.render_every == 0)
            )

            callback = None
            if render_this:
                current_fit, _, current_bust_rate, _ = self._fitness_metrics(
                    total_profit, bust_counts, max(1, hand_idx - 1)
                )
                self.renderer.set_meta(
                    generation,
                    hand_idx,
                    current_fit.tolist(),
                    bust_rate=(current_bust_rate * 100.0).tolist(),
                )
                callback = (lambda env, snap, agents: self.renderer.render(env, snap, agents))

            result = env.play_hand(self.brains, callback=callback)
            total_profit += np.asarray(result["profits"], dtype=np.float64)
            bust_counts += np.asarray(result.get("busted", [False] * 4), dtype=np.int64)

            if self.renderer is not None and self.renderer.closed:
                break

        hands_played = max(1, hand_idx)
        fitness, raw_bb100, bust_rate, bust_penalty_bb100 = self._fitness_metrics(
            total_profit, bust_counts, hands_played
        )
        metrics = {
            "raw_bb100": raw_bb100,
            "bust_rate": bust_rate,
            "bust_counts": bust_counts,
            "bust_penalty_bb100": bust_penalty_bb100,
        }
        return fitness, hands_played, metrics

    def run(self, generations=None):
        generations = int(generations or self.cfg.generations)
        history = []

        for gen in range(1, generations + 1):
            fitness, hands_played, metrics = self.evaluate_generation(gen)

            best_idx, champion, next_brains = self.evolution.next_generation(
                self.brains, fitness
            )

            checkpoint = self.out_dir / f"best_brain_gen_{gen:04d}.npz"
            champion.save(checkpoint)

            row = {
                "generation": gen,
                "hands": hands_played,
                "fitness": fitness.tolist(),
                "raw_bb100": metrics["raw_bb100"].tolist(),
                "bust_rate": metrics["bust_rate"].tolist(),
                "bust_counts": metrics["bust_counts"].tolist(),
                "bust_penalty_bb100": metrics["bust_penalty_bb100"].tolist(),
                "best_fly": best_idx + 1,
                "best_fitness": float(fitness[best_idx]),
                "checkpoint": str(checkpoint),
            }
            history.append(row)

            pieces = []
            for i in range(4):
                pieces.append(
                    f"Fly {i+1}: {fitness[i]:+7.2f} fit "
                    f"[raw {metrics['raw_bb100'][i]:+7.2f} | "
                    f"bust {metrics['bust_rate'][i]*100:4.1f}%]"
                )
            print(
                f"GEN {gen:04d} | "
                + " | ".join(pieces)
                + f" | BEST: Fly {best_idx+1}"
            )

            self.brains = next_brains

            if self.renderer is not None and self.renderer.closed:
                break

        return history
