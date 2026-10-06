from config import Config
from poker.env import PokerEnv, CHECK, CALL, FOLD, ACTION_COUNT


class PassiveBot:
    def act(self, observation, legal_actions):
        if CHECK in legal_actions:
            return CHECK
        if CALL in legal_actions:
            return CALL
        return FOLD


def main():
    cfg = Config(hands_per_generation=20)
    env = PokerEnv(cfg, seed=123)
    bots = [PassiveBot(), PassiveBot(), PassiveBot(), PassiveBot()]

    assert ACTION_COUNT == 14
    for _ in range(100):
        result = env.play_hand(bots)
        assert sum(result["profits"]) == 0
        assert sum(s.stack for s in env.seats) == cfg.starting_stack * 4
        all_cards = []
        for s in env.seats:
            all_cards.extend(s.hole)
        all_cards.extend(env.board)
        assert len(all_cards) == len(set(all_cards))
        assert env.observation(0).shape[0] == env.observation_size

    print("SMOKE TEST: OK")
    print("Observation size:", env.observation_size)
    print("Action count:", ACTION_COUNT)


if __name__ == "__main__":
    main()
