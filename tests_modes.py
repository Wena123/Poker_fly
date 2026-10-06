from pathlib import Path
import tempfile
import numpy as np

from config import Config
from poker.env import PokerEnv
from agent.simple_brain import SimpleFlyBrain
from agent.strong_bot import StrongPokerBot
from agent.trainer import Trainer
from agent.watcher import Watcher


def main():
    cfg = Config(starting_stack=100, small_blind=5, big_blind=10)
    env = PokerEnv(cfg, seed=91)
    bot = StrongPokerBot(cfg, seed=92)

    brains = [
        SimpleFlyBrain(
            env.observation_size,
            cfg.hidden_1,
            cfg.hidden_2,
            rng=np.random.default_rng(100 + i),
        )
        for i in range(3)
    ] + [bot]

    # Bot must survive normal persistent-stack session play.
    env.reset_session()
    for _ in range(20):
        env.play_hand(brains)
        if env.session_over:
            env.reset_session()

    cfg.hands_per_generation = 12
    with tempfile.TemporaryDirectory() as td:
        trainer = Trainer(cfg, out_dir=td, with_bot=True)
        hist = trainer.run(generations=1)
        row = hist[-1]

        assert row["hands"] >= 12
        assert row["sessions"] >= 1
        assert all(n > 0 for n in row["played_counts"]), row["played_counts"]
        assert all(n > 0 for n in row["sessions_played"]), row["sessions_played"]

        cp = Path(row["checkpoint"])
        assert cp.exists()

        resumed = Trainer(cfg, out_dir=td, resume_path=cp, with_bot=False)
        assert resumed.start_generation == 2

        watcher = Watcher(cfg, cp, renderer=None, with_bot=True)
        result = watcher.run(hands=12)
        assert result["hands"] >= 12
        assert result["sessions"] >= 1

    print("MODE/BOT TEST: OK")
    print("StrongPokerBot: persistent table compatible")
    print("Train with bot: OK")
    print("Resume: OK")
    print("Watch without learning: OK")


if __name__ == "__main__":
    main()
