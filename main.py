import argparse

from config import Config
from agent.trainer import Trainer

def main():
    parser = argparse.ArgumentParser(description="4-fly Poker self-play trainer")
    parser.add_argument("--render", action="store_true", help="Włącz podgląd Pygame.")
    parser.add_argument("--generations", type=int, default=None)
    parser.add_argument("--hands", type=int, default=None, help="Rozdań na generację.")
    parser.add_argument("--render-every", type=int, default=100, help="Pokazuj co N-te rozdanie.")
    args = parser.parse_args()

    cfg = Config()
    if args.hands is not None:
        cfg.hands_per_generation = args.hands

    renderer = None
    if args.render:
        from poker.renderer import PygameRenderer
        renderer = PygameRenderer()

    trainer = Trainer(
        cfg,
        renderer=renderer,
        render_every=args.render_every,
    )

    try:
        trainer.run(generations=args.generations)
    finally:
        if renderer is not None:
            renderer.close()

if __name__ == "__main__":
    main()
