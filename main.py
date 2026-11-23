import argparse
from pathlib import Path

from config import Config
from agent.trainer import Trainer
from agent.watcher import Watcher
from agent.checkpoints import latest_checkpoint
from agent.hall_of_fame import HallOfFame


def _resolve_latest():
    return latest_checkpoint("checkpoints")


def main():
    parser = argparse.ArgumentParser(description="FlyPoker evolutionary trainer / watcher")

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--resume", type=str, metavar="CHECKPOINT", help="Kontynuuj trening od checkpointu.")
    mode.add_argument("--resume-latest", action="store_true", help="Kontynuuj trening od najnowszego checkpointu.")
    mode.add_argument("--resume-best", action="store_true", help="Wznów trening z best_ever.npz w Hall of Fame.")
    mode.add_argument("--watch", type=str, metavar="CHECKPOINT", help="Oglądaj checkpoint BEZ uczenia/mutacji.")
    mode.add_argument("--watch-latest", action="store_true", help="Oglądaj najnowszy checkpoint BEZ uczenia.")
    mode.add_argument("--watch-best", action="store_true", help="Oglądaj najlepszego championa z Hall of Fame.")
    mode.add_argument("--watch-train", type=str, metavar="CHECKPOINT", help="Kontynuuj trening od checkpointu i pokazuj go na żywo.")
    mode.add_argument("--watch-train-latest", action="store_true", help="Kontynuuj najnowszy checkpoint z podglądem na żywo.")

    visual = parser.add_mutually_exclusive_group()
    visual.add_argument("--render", action="store_true", help="Włącz Pygame + monitor podczas treningu.")
    visual.add_argument("--brain-monitor", action="store_true", help="Monitor mózgu OpenCV bez Pygame.")
    visual.add_argument("--headless", action="store_true", help="Bez Pygame, OpenCV i okien; opcjonalnie z Unity.")
    parser.add_argument("--monitor-hz", type=float, default=10.0, help="Maksymalne odświeżanie brain-monitor.")
    parser.add_argument("--reward-mode", choices=("classic", "balanced"), default="balanced",
                        help="classic: stary bb/100-bust; balanced: +win bonus -downside risk.")
    parser.add_argument("--win-bonus-bb", type=float, default=2.0, help="Bonus w BB za wygranie całego stołu.")
    parser.add_argument("--risk-penalty", type=float, default=0.25, help="Waga niewielkiej kary za dotkliwe przegrane rozdania.")
    parser.add_argument("--top-k", type=int, default=5, help="Ilu championów zachować w Hall of Fame.")
    parser.add_argument("--list-best", action="store_true", help="Wyświetl zapisany ranking i zakończ.")
    parser.add_argument("--progress-every", type=int, default=500, help="Co ile rozdań logować postęp do terminala (0 wyłącza).")
    parser.add_argument("--unity", action="store_true", help="Połącz z Unity i czekaj na zakończenie każdej animacji przed kolejnym ruchem.")
    parser.add_argument("--unity-host", type=str, default="127.0.0.1", help="Adres hosta Unity PokerReceiver.")
    parser.add_argument("--unity-port", type=int, default=8765, help="Port Unity PokerReceiver.")
    parser.add_argument("--unity-timeout", type=float, default=60.0, help="Maksymalny czas oczekiwania na animation_done w sekundach.")
    parser.add_argument(
        "--unity-disconnect", choices=("pause", "continue"), default="pause",
        help="Po utracie Unity: pause=czekaj na Play Mode i wznow animacje (domyslnie); "
             "continue=trenuj bez Unity i polacz ponownie na poczatku rozdania.",
    )
    parser.add_argument("--with-bot", "--bot", dest="with_bot", action="store_true", help="Dodaj stałego StrongPokerBot jako przeciwnika.")
    parser.add_argument("--generations", type=int, default=None, help="Ile nowych generacji wytrenować.")
    parser.add_argument("--hands", type=int, default=None, help="Minimalna liczba rąk. Rozpoczęty stół zawsze jest dogrywany aż zostanie 1 gracz.")
    parser.add_argument("--render-every", type=int, default=None, help="W treningu pokazuj co N-te rozdanie. Watch-train domyślnie pokazuje każde.")
    args = parser.parse_args()

    if args.list_best:
        HallOfFame(reward_mode=args.reward_mode, top_k=args.top_k).print_ranking()
        return

    cfg = Config()
    if args.hands is not None and not (args.watch or args.watch_latest):
        cfg.hands_per_generation = max(1, int(args.hands))

    # Resolve aliases / latest checkpoint.
    watch_path = None
    resume_path = None
    force_render = False

    if args.watch:
        watch_path = Path(args.watch)
    elif args.watch_best:
        watch_path = Path("checkpoints") / "hall_of_fame" / args.reward_mode / "best_ever.npz"
    elif args.resume_best:
        resume_path = Path("checkpoints") / "hall_of_fame" / args.reward_mode / "best_ever.npz"
    elif args.watch_latest:
        watch_path = _resolve_latest()
    elif args.watch_train:
        resume_path = Path(args.watch_train)
        force_render = True
    elif args.watch_train_latest:
        resume_path = _resolve_latest()
        force_render = True
    elif args.resume:
        resume_path = Path(args.resume)
    elif args.resume_latest:
        resume_path = _resolve_latest()

    if watch_path is not None and not watch_path.exists():
        parser.error(f"Checkpoint does not exist: {watch_path}")
    if resume_path is not None and not resume_path.exists():
        parser.error(f"Checkpoint does not exist: {resume_path}")

    renderer = None
    needs_render = bool(args.render or (force_render or watch_path is not None) and not args.headless and not args.brain_monitor)
    if args.headless:
        needs_render = False
    if needs_render:
        from poker.renderer import PygameRenderer
        renderer = PygameRenderer()
    elif args.brain_monitor:
        from poker.brain_monitor_renderer import BrainMonitorRenderer
        renderer = BrainMonitorRenderer(update_hz=max(1., args.monitor_hz))

    unity_bridge = None
    if args.unity:
        from unity_bridge import UnityBridge
        unity_bridge = UnityBridge(
            host=args.unity_host,
            port=args.unity_port,
            timeout=max(1.0, float(args.unity_timeout)),
            verbose=True,
            disconnect_mode=args.unity_disconnect,
        )
        # Pump Pygame even while waiting for the FIRST Unity connection.
        if renderer is not None:
            unity_bridge.set_wait_pump(renderer.pump_waiting)
        unity_bridge.connect()

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

        render_every = args.render_every if args.render_every is not None else (1 if (force_render or args.brain_monitor) else 100)
        trainer = Trainer(
            cfg,
            renderer=renderer,
            render_every=render_every,
            resume_path=resume_path,
            with_bot=args.with_bot,
            unity_bridge=unity_bridge,
            reward_mode=args.reward_mode,
            win_bonus_bb=args.win_bonus_bb,
            risk_penalty=args.risk_penalty,
            top_k=args.top_k,
            progress_every=args.progress_every,
        )
        trainer.run(generations=args.generations)

    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        if unity_bridge is not None:
            unity_bridge.close()
        if renderer is not None:
            renderer.close()


if __name__ == "__main__":
    main()
