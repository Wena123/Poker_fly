import argparse
from pathlib import Path

from config import Config
from agent.trainer import Trainer
from agent.watcher import Watcher
from agent.checkpoints import latest_checkpoint, default_checkpoint_dir


def _resolve_latest(checkpoint_dir=None):
    return latest_checkpoint(checkpoint_dir)


def main():
    parser = argparse.ArgumentParser(description="FlyPoker evolutionary trainer / watcher")

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--resume", type=str, metavar="CHECKPOINT", help="Kontynuuj trening od checkpointu.")
    mode.add_argument("--resume-latest", action="store_true", help="Kontynuuj trening od najnowszego checkpointu.")
    mode.add_argument("--watch", type=str, metavar="CHECKPOINT", help="Oglądaj checkpoint BEZ uczenia/mutacji.")
    mode.add_argument("--watch-latest", action="store_true", help="Oglądaj najnowszy checkpoint BEZ uczenia.")
    mode.add_argument("--watch-train", type=str, metavar="CHECKPOINT", help="Kontynuuj trening od checkpointu i pokazuj go na żywo.")
    mode.add_argument("--watch-train-latest", action="store_true", help="Kontynuuj najnowszy checkpoint z podglądem na żywo.")

    parser.add_argument("--render", action="store_true", help="Włącz Pygame + monitor podczas zwykłego treningu.")
    parser.add_argument("--with-bot", "--bot", dest="with_bot", action="store_true", help="Dodaj stałego StrongPokerBot jako przeciwnika.")
    parser.add_argument("--generations", type=int, default=None, help="Ile nowych generacji wytrenować.")
    parser.add_argument("--hands", type=int, default=None, help="Minimalna liczba rąk. Rozpoczęty stół zawsze jest dogrywany aż zostanie 1 gracz.")
    parser.add_argument("--render-every", type=int, default=None, help="W treningu pokazuj co N-te rozdanie. Watch-train domyślnie pokazuje każde.")
    parser.add_argument("--checkpoint-dir", type=str, default=None, help="Opcjonalny folder checkpointów. Domyślnie: <folder projektu>/checkpoints.")
    parser.add_argument("--unity", action="store_true", help="Wysyłaj prawdziwy stan gry do lokalnego Unity na 127.0.0.1:8765.")
    args = parser.parse_args()

    checkpoint_dir = (
        Path(args.checkpoint_dir).expanduser().resolve()
        if args.checkpoint_dir
        else default_checkpoint_dir().resolve()
    )
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    print(f"CHECKPOINT DIRECTORY -> {checkpoint_dir}", flush=True)

    cfg = Config()
    if args.hands is not None and not (args.watch or args.watch_latest):
        cfg.hands_per_generation = max(1, int(args.hands))

    # Resolve aliases / latest checkpoint.
    watch_path = None
    resume_path = None
    force_render = False

    if args.watch:
        watch_path = Path(args.watch)
    elif args.watch_latest:
        watch_path = _resolve_latest(checkpoint_dir)
    elif args.watch_train:
        resume_path = Path(args.watch_train)
        force_render = True
    elif args.watch_train_latest:
        resume_path = _resolve_latest(checkpoint_dir)
        force_render = True
    elif args.resume:
        resume_path = Path(args.resume)
    elif args.resume_latest:
        resume_path = _resolve_latest(checkpoint_dir)

    if watch_path is not None and not watch_path.exists():
        parser.error(f"Checkpoint does not exist: {watch_path}")
    if resume_path is not None and not resume_path.exists():
        parser.error(f"Checkpoint does not exist: {resume_path}")

    unity_bridge = None
    if args.unity:
        from viewer.unity_bridge import UnityBridge
        unity_bridge = UnityBridge()
        print("UNITY BRIDGE -> 127.0.0.1:8765", flush=True)

    renderer = None
    needs_render = bool(args.render or force_render or watch_path is not None)
    if needs_render:
        from poker.renderer import PygameRenderer
        renderer = PygameRenderer()

    try:
        if watch_path is not None:
            hands = max(1, int(args.hands or 1000))
            print(
                f"WATCH MODE | TABLE SESSION | checkpoint={watch_path} | min_hands={hands} | "
                f"learning=OFF | bot={'ON' if args.with_bot else 'OFF'}"
            )
            watcher = Watcher(
                cfg,
                checkpoint=watch_path,
                renderer=renderer,
                with_bot=args.with_bot,
                unity_bridge=unity_bridge,
            )
            result = watcher.run(hands=hands)
            print(
                "WATCH FINISHED | "
                + f"tables={result.get('sessions', 0)} | "
                + " | ".join(f"Seat {i+1}: {v:+.2f} bb/100" for i, v in enumerate(result["bb100"]))
            )
            return

        if resume_path is not None:
            print(
                f"RESUME TABLE TRAINING | checkpoint={resume_path} | "
                f"bot={'ON' if args.with_bot else 'OFF'} | "
                f"render={'ON' if needs_render else 'OFF'}"
            )
        else:
            print(
                f"TABLE TRAINING FROM SCRATCH | bot={'ON' if args.with_bot else 'OFF'} | "
                f"render={'ON' if needs_render else 'OFF'}"
            )

        render_every = args.render_every if args.render_every is not None else (1 if force_render else 100)
        trainer = Trainer(
            cfg,
            renderer=renderer,
            render_every=render_every,
            out_dir=checkpoint_dir,
            resume_path=resume_path,
            with_bot=args.with_bot,
            unity_bridge=unity_bridge,
        )
        trainer.run(generations=args.generations)

    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        if renderer is not None:
            renderer.close()
        if unity_bridge is not None:
            unity_bridge.close()


if __name__ == "__main__":
    main()
