"""Optional imitation warm-up from observable StrongPokerBot decisions.

This is a teacher-guided *candidate*, not a replacement for evolutionary
selection. The incumbent stays frozen until the candidate passes the gate.
"""
from __future__ import annotations
import numpy as np
from poker.env import PokerEnv
from .strong_bot import StrongPokerBot
from .simple_brain import SimpleFlyBrain


class _CaptureActions:
    def __init__(self, max_samples=5000):
        self.samples = []
        self.pending = {}
        self.max_samples = int(max_samples)

    def before_action(self, env, seat, agents):
        self.pending[int(seat)] = (env.observation(seat).copy(),
                                   env._legal_actions(seat))

    def after_action(self, env, seat, action, amount, agents):
        item = self.pending.pop(int(seat), None)
        if item and len(self.samples) < self.max_samples:
            x, legal = item
            self.samples.append((x, tuple(legal), int(action)))


def collect_teacher_data(config, *, hands=200, seed=1_881_003,
                         max_samples=10000):
    env = PokerEnv(config, seed=seed)
    bots = [StrongPokerBot(config, seed=seed + 13 + i * 97) for i in range(4)]
    capture = _CaptureActions(max_samples=max_samples)
    count = 0
    cap = max(1, int(getattr(config, 'max_hands_per_session', 500)))
    while count < int(hands) and len(capture.samples) < max_samples:
        env.reset_session()
        for _ in range(cap):
            env.play_hand(bots, event_handler=capture)
            count += 1
            if count >= hands or len(capture.samples) >= max_samples or env.session_over:
                break
    return capture.samples


def imitate_teacher(brain, samples, *, epochs=3, learning_rate=0.002, seed=1_982_001):
    if not isinstance(brain, SimpleFlyBrain):
        raise TypeError('Expected SimpleFlyBrain')
    if not samples:
        return {"samples": 0, "epochs": 0, "accuracy_before": None, "accuracy_after": None}
    rng = np.random.default_rng(seed)
    # Preserve the initial network's full V43 dimensions. Only teacher labels
    # and learner observations are used; no opponent cards are read.
    before = float(np.mean([brain.act(x, legal) == act for x, legal, act in samples]))
    weight_names = ('w1', 'b1', 'w2', 'b2', 'w_action', 'b_action', 'w_size', 'b_size')
    # On-policy teacher demos are correlated; mild SGD + shuffled examples.
    for _ in range(max(1, int(epochs))):
        for idx in rng.permutation(len(samples)):
            observation, legal, chosen = samples[int(idx)]
            x = brain._normalize_observation(observation)
            h1, h2, action_logits, size_logits = brain._heads(x)
            main_legal = brain._main_legal_from_final(legal)
            if not main_legal:
                continue
            goal = 3 if chosen >= 3 else chosen
            pm = brain._softmax_masked(action_logits, main_legal)
            dm = np.zeros(brain.MAIN_COUNT, dtype=np.float32)
            dm[main_legal] = pm[main_legal]
            dm[goal] -= 1.0
            ds = np.zeros(brain.SIZE_COUNT, dtype=np.float32)
            if chosen >= 3:
                size_legal = brain._legal_size_indices(legal)
                if size_legal:
                    ps = brain._softmax_masked(size_logits, size_legal)
                    ds[size_legal] = ps[size_legal]
                    ds[chosen - 3] -= 1.0
            dz2 = (brain.w_action @ dm + brain.w_size @ ds) * (1.0 - h2*h2)
            dz1 = (brain.w2 @ dz2) * (1.0 - h1*h1)
            grads = (
                np.outer(x, dz1), dz1, np.outer(h1, dz2), dz2,
                np.outer(h2, dm), dm, np.outer(h2, ds), ds,
            )
            for name, grad in zip(weight_names, grads):
                arr = getattr(brain, name)
                arr -= np.float32(learning_rate) * np.clip(grad, -3.0, 3.0)
    after = float(np.mean([brain.act(x, legal) == act for x, legal, act in samples]))
    return {"samples": int(len(samples)), "epochs": max(1, int(epochs)),
            "accuracy_before": round(before, 4), "accuracy_after": round(after, 4)}
