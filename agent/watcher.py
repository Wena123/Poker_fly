from pathlib import Path
import numpy as np

from poker.env import PokerEnv
from .simple_brain import SimpleFlyBrain
from .strong_bot import StrongPokerBot
from .checkpoints import checkpoint_generation


class Watcher:
    """Watch complete persistent-stack table sessions without learning."""

    def __init__(self, config, checkpoint, renderer=None, with_bot=False, unity_bridge=None):
        self.cfg = config
        self.renderer = renderer
        self.with_bot = bool(with_bot)
        self.unity_bridge = unity_bridge
        self.checkpoint = Path(checkpoint)
        self.brain = SimpleFlyBrain.load(self.checkpoint)

        probe = PokerEnv(config, seed=config.seed)
        if self.brain.input_size != probe.observation_size:
            raise ValueError(
                f"Checkpoint input size {self.brain.input_size} does not match "
                f"current environment {probe.observation_size}."
            )

        self.generation = checkpoint_generation(self.checkpoint)
        self.bot = StrongPokerBot(config, seed=config.seed + 777) if self.with_bot else None

    def _agents(self):
        agents = [self.brain.copy() for _ in range(4)]
        for i, brain in enumerate(agents):
            brain.display_name = f"FLY {i+1}"

        if self.with_bot:
            # Fixed BOT seat in WATCH keeps the visual layout easy to follow.
            self.bot.display_name = "BOT"
            agents[3] = self.bot
        return agents

    def run(self, hands=1000):
        target_hands = max(1, int(hands))
        env = PokerEnv(self.cfg, seed=self.cfg.seed + 900_001 + self.generation)
        agents = self._agents()

        total_profit = np.zeros(4, dtype=np.float64)
        busts = np.zeros(4, dtype=np.int64)
        table_wins = np.zeros(4, dtype=np.int64)

        if self.renderer is not None:
            mode = "WATCH • TABLE SESSION • NO LEARNING"
            if self.with_bot:
                mode += " • VS BOT"
            self.renderer.set_mode_text(mode)

        played = 0
        sessions = 0

        # Watch at least `hands`, but never cut a table in the middle.
        while True:
            sessions += 1
            env.reset_session()

            while not env.session_over:
                played += 1

                if self.renderer is not None:
                    raw = (total_profit / self.cfg.big_blind) / max(1, played) * 100.0
                    # Rough display metric in watch mode.
                    bust_rate = busts / max(1, sessions) * 100.0
                    self.renderer.set_meta(
                        self.generation,
                        played,
                        raw.tolist(),
                        bust_rate=bust_rate.tolist(),
                        session_index=sessions,
                        table_wins=table_wins.tolist(),
                    )
                    callback = lambda e, s, a: self.renderer.render(e, s, a)
                else:
                    callback = None

                result = env.play_hand(agents, callback=callback, event_handler=self.unity_bridge)
                total_profit += np.asarray(result["profits"], dtype=np.float64)
                busts += np.asarray(result.get("busted", [False] * 4), dtype=np.int64)

                if result.get("session_over"):
                    table_wins[int(result["session_winner"])] += 1

                if self.renderer is not None and self.renderer.closed:
                    return {
                        "hands": played,
                        "sessions": sessions,
                        "profits": total_profit.tolist(),
                        "bb100": ((total_profit / self.cfg.big_blind) / max(1, played) * 100.0).tolist(),
                        "bust_rate": (busts / max(1, sessions)).tolist(),
                        "table_wins": table_wins.tolist(),
                    }

            if played >= target_hands:
                break

        return {
            "hands": played,
            "sessions": sessions,
            "profits": total_profit.tolist(),
            "bb100": ((total_profit / self.cfg.big_blind) / max(1, played) * 100.0).tolist(),
            "bust_rate": (busts / max(1, sessions)).tolist(),
            "table_wins": table_wins.tolist(),
        }
