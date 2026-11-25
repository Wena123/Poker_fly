"""Regression: two heads-up players may never eliminate each other."""
from pathlib import Path
from tempfile import TemporaryDirectory
from config import Config
from poker.env import PokerEnv, FOLD, CHECK
from agent.trainer import Trainer

class AlwaysFoldSmallBlind:
    def act(self, obs, legal):
        return CHECK if CHECK in legal else FOLD

def main():
    cfg=Config(hands_per_generation=24, max_hands_per_session=8)
    env=PokerEnv(cfg, seed=111)
    env.reset_session()
    for i,s in enumerate(env.seats):
        if i in (1,3):
            s.eliminated=True; s.folded=True; s.stack=0
        else:
            s.stack=327 if i==0 else 3673
    agents=[AlwaysFoldSmallBlind() for _ in range(4)]
    for i in range(32):
        r=env.play_hand(agents)
        assert not r["session_over"]
    assert [s.stack for s in env.seats]==[327,0,3673,0]
    # Same agents make trainer hang forever WITHOUT the new session cap.
    with TemporaryDirectory() as tmp:
        trainer=Trainer(cfg, out_dir=Path(tmp), progress_every=0)
        trainer.brains=agents
        _, hands, metrics=trainer.evaluate_generation(generation=1)
        assert hands==24, hands
        assert metrics["sessions"]==3, metrics
        assert metrics["capped_sessions"]==3, metrics
        assert sum(metrics["table_wins"])==0
    print("SESSION CAP TEST: OK")

if __name__ == "__main__":
    main()
