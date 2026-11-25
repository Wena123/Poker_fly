"""V43 regression: card features, old checkpoints, matched gate, teacher, archive safety."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
from unittest.mock import patch
import numpy as np

from config import Config
from poker.env import PokerEnv
from poker.hand_features import hand_features, HAND_FEATURE_COUNT
from poker.cards import rank
from agent.simple_brain import SimpleFlyBrain
from agent.benchmark_v43 import evaluate_policy, compare_policies
from agent.verified_champion import VerifiedChampion
from agent.imitation import collect_teacher_data, imitate_teacher
from agent.trainer import Trainer
from agent.watcher import Watcher


def main():
    cfg = Config(hands_per_generation=24, max_hands_per_session=10)
    env = PokerEnv(cfg, seed=8)
    assert env.observation_size == 216 + HAND_FEATURE_COUNT == 223
    env.reset_session()
    env._prepare_hand()
    obs = env.observation(0)
    feat = obs[-14-HAND_FEATURE_COUNT:-14]
    assert len(feat) == HAND_FEATURE_COUNT
    assert 0 <= feat[0] <= 1 and feat[-1] == 0
    # No opponents' private hole cards are required to compute engineered features.
    repeat = hand_features(env.seats[0].hole, env.board, env.pot, env._to_call(0))
    assert np.allclose(feat, repeat)
    aa = hand_features([12, 25], [])  # AC/AD
    seven_two = hand_features([5, 13], [])  # 7C/2D
    assert aa[0] > seven_two[0] and aa[5] == 1

    rng = np.random.default_rng(76)
    old = SimpleFlyBrain(216, rng=rng)
    before_action = old.act(obs, env._legal_actions(0))
    migrated = old.resize_input(223)
    assert migrated.input_size == 223
    assert np.array_equal(old.w1[:-14], migrated.w1[:-14-HAND_FEATURE_COUNT])
    assert np.array_equal(old.w1[-14:], migrated.w1[-14:])
    assert np.count_nonzero(migrated.w1[-14-HAND_FEATURE_COUNT:-14]) == 0
    assert before_action == migrated.act(obs, env._legal_actions(0))
    # New card features can influence model decisions when the evolution changes weights.

    ref = evaluate_policy(migrated, cfg, tables_per_seat=1, seed=5019)
    ref2 = evaluate_policy(migrated, cfg, tables_per_seat=1, seed=5019)
    assert ref == ref2 and ref['tables'] == 4
    assert -100.001 <= ref['profit_bb_per_table'] <= 300.001
    same = compare_policies(migrated, migrated, cfg, tables_per_seat=1, seed=8731)
    assert same['delta_profit_bb_per_table'] == 0
    assert not same['accepted']

    demos = collect_teacher_data(cfg, hands=8, seed=891)
    assert demos
    candidate = migrated.copy()
    imitation = imitate_teacher(candidate, demos, epochs=2, learning_rate=.002)
    assert imitation['samples'] == len(demos)
    assert np.isfinite(candidate.w1).all()

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        old_hof = root / 'hall_of_fame' / 'balanced'
        old_hof.mkdir(parents=True)
        (old_hof / 'leaderboard.json').write_text('{"entries":[],"sentinel":"OLD_V42_SENTINEL"}')
        t = Trainer(cfg, out_dir=root, selection_v43=True, train_mode='mixed',
                    bot_fraction=0.5, benchmark_tables=1, gate_tables=1,
                    teacher_hands=8, progress_every=0)
        assert t.obs_size == 223
        rows = t.run(generations=2)
        assert len(rows) == 2
        assert all(row['v43_gate'] and row['v43_enabled'] for row in rows)
        assert all(row['benchmark_results'] and len(row['benchmark_results']) == 4 for row in rows)
        assert rows[0]['v43_teacher']['samples'] > 0
        assert all(row['v43_gate']['challenger']['tables'] == 4 for row in rows)
        store = VerifiedChampion(root)
        assert store.exists()
        assert store.load(223).input_size == 223
        assert (old_hof / 'leaderboard.json').read_text() == '{"entries":[],"sentinel":"OLD_V42_SENTINEL"}'
        assert not (root / 'hall_of_fame' / 'benchmark_v1').exists()
        assert (root / 'best_brain_gen_0002.npz').exists()
        assert len((root / 'training_history.jsonl').read_text().splitlines()) == 2
        # Resuming with the legacy 216 architecture is supported.
        legacy = root / 'older_model.npz'
        old.save(legacy)
        resumed = Trainer(cfg, out_dir=root, selection_v43=True,
                          resume_path=legacy, benchmark_tables=0, progress_every=0)
        assert resumed.obs_size == 223 and resumed.brains[0].input_size == 223
    # Force the gate's ACCEPT branch without depending on a lucky poker draw.
    with TemporaryDirectory() as tmp2:
        root2 = Path(tmp2)
        trainer = Trainer(cfg, out_dir=root2, selection_v43=True,
                          benchmark_tables=0, gate_tables=1, progress_every=0)
        approved = {
            'accepted': True, 'delta_profit_bb_per_table': 10.0,
            'paired_standard_error_bb': 1.0, 'challenger': {'tables': 4, 'bb100': 0.0},
            'incumbent': {'tables': 4},
        }
        with patch('agent.trainer.compare_policies', return_value=approved):
            accepted = trainer.run(generations=1)
        assert accepted[0]['new_best_benchmark']
        assert VerifiedChampion(root2).describe()['generation'] == 1
        assert VerifiedChampion(root2).load(223).input_size == 223
        # WATCH must also stop capped tournaments instead of looping forever.
        watched = Watcher(cfg, checkpoint=VerifiedChampion(root2).checkpoint,
                          with_bot=True).run(hands=24)
        assert watched['hands'] >= 24 and watched['sessions'] >= 1
    print('V43 MATCHED GATE / CARD FEATURES / OLD CKPT / TEACHER / SAFETY: OK')


if __name__ == '__main__':
    main()
