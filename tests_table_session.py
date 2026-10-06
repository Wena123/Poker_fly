from config import Config
from poker.env import PokerEnv, ALL_IN, CALL, CHECK, FOLD


class ShoveBot:
    def act(self, observation, legal_actions):
        if ALL_IN in legal_actions:
            return ALL_IN
        if CALL in legal_actions:
            return CALL
        if CHECK in legal_actions:
            return CHECK
        return FOLD


def main():
    cfg = Config()
    env = PokerEnv(cfg, seed=20261006)
    bots = [ShoveBot() for _ in range(4)]

    env.reset_session()
    session = env.session_no
    assert [s.stack for s in env.seats] == [1000, 1000, 1000, 1000]

    hands = 0
    saw_elimination_before_end = False

    while not env.session_over:
        before = [s.stack for s in env.seats]
        result = env.play_hand(bots)
        hands += 1

        assert result["session_no"] == session
        assert sum(result["end_stacks"]) == 4000
        assert sum(result["profits"]) == 0

        zeroes = sum(1 for x in result["end_stacks"] if x == 0)
        if zeroes and not result["session_over"]:
            saw_elimination_before_end = True
            for i, stack in enumerate(result["end_stacks"]):
                if stack == 0:
                    assert env.seats[i].eliminated
                    assert env.seats[i].hole == [] or env.seats[i].folded

        assert hands < 200, "Session did not finish quickly enough in shove test."

    winner = env.session_winner
    stacks = [s.stack for s in env.seats]
    assert stacks[winner] == 4000, stacks
    assert sum(1 for x in stacks if x > 0) == 1, stacks
    assert sum(1 for x in stacks if x == 0) == 3, stacks

    # Next hand is the ONLY point at which the table resets.
    old_session = env.session_no
    next_result = env.play_hand(bots)
    assert next_result["session_no"] == old_session + 1
    assert next_result["start_stacks"] == [1000, 1000, 1000, 1000]

    print("TABLE SESSION TEST: OK")
    print("Hands to first table winner:", hands)
    print("Winner stack:", 4000)
    print("Reset only after sole survivor: OK")
    print("Intermediate elimination observed:", saw_elimination_before_end)


if __name__ == "__main__":
    main()
