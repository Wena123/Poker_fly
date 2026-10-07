from pathlib import Path
import tempfile
import numpy as np

from config import Config
from agent.trainer import Trainer
from agent.simple_brain import SimpleFlyBrain
from agent.checkpoints import default_checkpoint_dir, save_checkpoint_atomic, latest_checkpoint
from poker.env import PokerEnv, ACTION_COUNT


def main():
    root = Path(__file__).resolve().parent
    assert default_checkpoint_dir().resolve() == (root / "checkpoints").resolve()

    cfg = Config()
    env = PokerEnv(cfg, seed=123)
    brain = SimpleFlyBrain(
        env.observation_size, cfg.hidden_1, cfg.hidden_2,
        output_size=ACTION_COUNT, rng=np.random.default_rng(1)
    )

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        saved = save_checkpoint_atomic(brain, td / "best_brain_gen_0042.npz")
        assert saved.exists() and saved.stat().st_size > 0
        assert (td / "LATEST.txt").read_text().strip() == saved.name
        assert latest_checkpoint(td).resolve() == saved.resolve()

        trainer = Trainer(cfg, out_dir=td)
        assert trainer.out_dir.resolve() == td.resolve()

    print("CHECKPOINT PATH TEST: OK")
    print("Default:", default_checkpoint_dir().resolve())

if __name__ == "__main__":
    main()
