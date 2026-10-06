import numpy as np

from config import Config
from poker.env import PokerEnv, ACTION_COUNT, ALL_IN
from agent.simple_brain import SimpleFlyBrain
from agent.trainer import Trainer


def main():
    cfg = Config(hands_per_generation=40)
    env = PokerEnv(cfg, seed=20261006)
    brain = SimpleFlyBrain(env.observation_size, rng=np.random.default_rng(1))

    # Produce a live legal state.
    env._reset_hand()
    env._post_blinds()
    for seat in range(4):
        legal = env._legal_actions(seat)
        if not legal:
            continue
        obs = env.observation(seat)
        action = brain.act(obs, legal)
        assert action in legal, (seat, action, legal)
        probs = brain.decision_probabilities(obs, legal)
        assert probs.shape == (ACTION_COUNT,)
        assert abs(float(probs.sum()) - 1.0) < 1e-5
        for a in range(ACTION_COUNT):
            if a not in legal:
                assert probs[a] == 0.0

        # No two legal bet-size buttons are allowed to resolve to the same
        # target. Explicit ALL-IN must also remain unique.
        targets = []
        for a in legal:
            if a < 3:
                continue
            target = env._all_in_target(seat) if a == ALL_IN else env._uncapped_raise_target(seat, a)
            targets.append((a, target))
        vals = [t for _, t in targets]
        assert len(vals) == len(set(vals)), targets

    # Check the exact bust-penalty math independently of poker variance.
    trainer = Trainer(cfg, renderer=None)
    total_profit = np.array([100.0, -100.0, 0.0, 0.0])
    busts = np.array([0, 1, 0, 0])
    fit, raw, rate, penalty = trainer._fitness_metrics(total_profit, busts, 100)
    assert np.isclose(raw[0], 10.0)
    assert np.isclose(raw[1], -10.0)
    assert np.isclose(rate[1], 0.01)
    assert np.isclose(penalty[1], 5.0)
    assert np.isclose(fit[1], -15.0)

    print("HIERARCHICAL POLICY TEST: OK")
    print("Final action count:", ACTION_COUNT)
    print("Main head: 4 actions")
    print("Sizing head: 11 sizes")
    print("Bust penalty:", cfg.bust_penalty_bb, "BB per bust")


if __name__ == "__main__":
    main()
