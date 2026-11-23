"""Basic regression tests for V39 without opening any GUI windows."""
from pathlib import Path
import tempfile
import numpy as np

from config import Config
from agent.trainer import Trainer
from agent.reward import RewardSystem
from agent.hall_of_fame import HallOfFame
from agent.simple_brain import SimpleFlyBrain
from poker.env import PokerEnv


def main():
    cfg = Config(starting_stack=120, small_blind=5, big_blind=10)
    classic = RewardSystem(mode="classic", big_blind=10)
    c = classic.calculate([100, -100, 0, 0], [0, 1, 0, 0], [10] * 4, [1] * 4)
    assert abs(c["fitness"][0] - 100) < 1e-6
    assert abs(c["fitness"][1] + 150) < 1e-6
    balanced = RewardSystem(mode="balanced", big_blind=10)
    b = balanced.calculate([100, -100, 0, 0], [0, 1, 0, 0], [10] * 4,
                           [1] * 4, [1, 0, 0, 0], [[100, -5], [-100], [], []])
    assert b["fitness"][0] > c["fitness"][0]
    assert b["risk_cost_bb100"][1] > 0

    cfg.hands_per_generation = 10
    with tempfile.TemporaryDirectory() as td:
        trainer = Trainer(cfg, out_dir=td, reward_mode="balanced", top_k=2, progress_every=0)
        rows = trainer.run(generations=3)
        assert len(rows) == 3
        hof = HallOfFame(td, reward_mode="balanced", top_k=2)
        assert len(hof.entries) == 2
        assert hof.best_path.exists()
        assert all((hof.path / e["file"]).exists() for e in hof.entries)
        assert len(list(hof.path.glob("gen_*_fly_*.npz"))) == 2
        assert len(list(Path(td).glob("best_brain_gen_*.npz"))) == 3
        assert (Path(td) / "training_history.jsonl").exists()
        checkpoint = str(hof.best_path)
        env = PokerEnv(cfg)
        model = SimpleFlyBrain.load(checkpoint)
        assert model.input_size == env.observation_size
        resumed = Trainer(cfg, out_dir=td, resume_path=checkpoint, progress_every=0)
        assert resumed.start_generation == 4, resumed.start_generation
        assert all("vpip_pct" in r and "pfr_pct" in r and "risk_cost_bb100" in r for r in rows)

    print("V39 HEADLESS/REWARD/HALL OF FAME/RESUME/TELEMETRY TESTS: OK")

    # Render without opening a window: verifies the OpenCV monitor's new panels.
    try:
        from poker.anatomical_monitor import PokerAnatomicalMonitor
    except ImportError:
        print("BRAIN MONITOR: skipped (opencv-python not installed)")
    else:
        env = PokerEnv(cfg)
        env.reset_session()
        brains = [SimpleFlyBrain(env.observation_size, cfg.hidden_1, cfg.hidden_2,
                                 rng=np.random.default_rng(i)) for i in range(4)]
        monitor = PokerAnatomicalMonitor(width=1200, height=850, enabled=False)
        frame = monitor.render(brains, [env.observation(i) for i in range(4)], snapshot=env.snapshot())
        assert frame.shape == (850, 1200, 3)
        print("V39 BRAIN MONITOR OFFSCREEN TEST: OK")


if __name__ == "__main__":
    main()
