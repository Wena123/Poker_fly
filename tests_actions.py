import random
from config import Config
from poker.env import PokerEnv, ACTION_COUNT, ACTION_LABELS


class RandomLegalBot:
    def __init__(self, seed):
        self.rng = random.Random(seed)

    def act(self, observation, legal_actions):
        return self.rng.choice(list(legal_actions))


def main():
    cfg = Config()
    env = PokerEnv(cfg, seed=98765)
    bots = [RandomLegalBot(i + 1) for i in range(4)]
    seen = set()
    all_in_hands = 0
    side_pot_hands = 0

    for _ in range(1200):
        result = env.play_hand(bots)
        assert sum(result["profits"]) == 0, result
        assert sum(s.stack for s in env.seats) == cfg.starting_stack * 4
        for s in env.seats:
            if s.last_action >= 0:
                seen.add(s.last_action)
            if s.all_in:
                all_in_hands += 1
        if len(result.get("side_pots", [])) > 1:
            side_pot_hands += 1

    print("ACTION STRESS TEST: OK")
    print("Action count:", ACTION_COUNT)
    print("Seen actions:", [ACTION_LABELS[i] for i in sorted(seen)])
    print("All-in seat occurrences:", all_in_hands)
    print("Hands with side pots:", side_pot_hands)


if __name__ == "__main__":
    main()
