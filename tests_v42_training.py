"""Fast V42 tests: stable benchmark, mixed rotation, holdout and old checkpoint safety."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
from config import Config
from agent.trainer import Trainer
from agent.benchmark import evaluate_brain
from agent.simple_brain import SimpleFlyBrain
from agent.evolution import Evolution


def main():
    cfg = Config(hands_per_generation=24, max_hands_per_session=12)
    with TemporaryDirectory() as directory:
        p = Path(directory)
        t = Trainer(cfg, out_dir=p, train_mode="mixed", bot_fraction=0.5,
                    benchmark_tables=1, progress_every=0, immigrant_every=1)
        assert [t._is_bot_session(i) for i in range(1, 9)] == [False]*4 + [True]*4
        for i in range(1, 9):
            _, mapping = t._agents_for_session(i)
            if t._is_bot_session(i):
                assert mapping.count(None) == 1
            else:
                assert sorted(mapping) == [0, 1, 2, 3]
        # Identical inputs yield identical evaluation; seat rotation is complete.
        b1 = evaluate_brain(t.brains[0], cfg, tables_per_seat=1, seed=980123)
        b2 = evaluate_brain(t.brains[0], cfg, tables_per_seat=1, seed=980123)
        assert b1 == b2, (b1, b2)
        assert b1["tables"] == 4 and b1["hands"] > 0
        assert b1["seed"] == 980123
        result = t.run(generations=2)
        assert len(result) == 2
        for row in result:
            assert row["benchmark_results"] and len(row["benchmark_results"]) == 4
            assert row["validation_result"]["seed"] == 7980123
            assert row["train_mode"] == "mixed"
            assert row["bot_training_tables"] > 0
            assert row["selfplay_training_tables"] > 0
        assert (p/'hall_of_fame'/'benchmark_v1'/'best_ever.npz').exists()
        assert (p/'hall_of_fame'/'balanced'/'best_ever.npz').exists()
        assert (p/'best_brain_gen_0001.npz').exists()
        assert (p/'best_brain_gen_0002.npz').exists()
        lb=json.loads((p/'hall_of_fame'/'benchmark_v1'/'leaderboard.json').read_text())
        assert len(lb["entries"]) >= 1
        assert "selection_benchmark_bb100" in lb["entries"][0]["metrics"]
        # Existing 'best' checkpoint is still loadable.
        ck = SimpleFlyBrain.load(p/'best_brain_gen_0002.npz')
        assert ck.input_size == t.obs_size
        resume=Trainer(cfg,out_dir=p,resume_path=p/'hall_of_fame'/'benchmark_v1'/'best_ever.npz',
                       benchmark_tables=0, progress_every=0)
        assert resume.start_generation == 3
        evolved=Evolution(seed=7)
        fitness=np.array([5,0,0,0])
        idx,champ,children=evolved.next_generation(t.brains,fitness,generation=10,immigrant_every=10)
        assert idx==0 and len(children)==4
        assert all(np.array_equal(getattr(champ,k),getattr(children[0],k))
                   for k in ("w1", "w2", "w_action"))
        assert not np.array_equal(children[3].w1,champ.w1)
    print('V42 MIXED / BENCHMARK / HOLDOUT / IMMIGRANTS / RESUME: OK')


if __name__ == '__main__':
    main()
