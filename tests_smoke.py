from config import Config
from poker.env import PokerEnv, CHECK_CALL

class CallBot:
    def act(self, observation, legal_actions):
        return CHECK_CALL

def main():
    cfg = Config(hands_per_generation=20)
    env = PokerEnv(cfg, seed=123)
    bots = [CallBot(), CallBot(), CallBot(), CallBot()]

    for _ in range(100):
        result = env.play_hand(bots)
        assert sum(result["profits"]) == 0
        all_cards = []
        for s in env.seats:
            all_cards.extend(s.hole)
        all_cards.extend(env.board)
        assert len(all_cards) == len(set(all_cards))

    print("SMOKE TEST: OK")
    print("Observation size:", env.observation_size)

if __name__ == "__main__":
    main()
