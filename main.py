import argparse
from pathlib import Path

from config import Config
from agent.trainer import Trainer
from agent.watcher import Watcher
from agent.checkpoints import latest_checkpoint
from agent.hall_of_fame import HallOfFame
from agent.benchmark import evaluate_brain
from agent.benchmark_v43 import evaluate_policy, compare_policies
from agent.verified_champion import VerifiedChampion
from agent.simple_brain import SimpleFlyBrain


def _resolve_latest():
    return latest_checkpoint("checkpoints")


def main():
    parser = argparse.ArgumentParser(description="FlyPoker evolutionary trainer / watcher")

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--resume", type=str, metavar="CHECKPOINT", help="Kontynuuj trening od checkpointu.")
    mode.add_argument("--resume-latest", action="store_true", help="Kontynuuj trening od najnowszego checkpointu.")
    mode.add_argument("--resume-benchmark-best", action="store_true", help="Wznow od championa zweryfikowanego przeciw botowi.")
    mode.add_argument("--watch-benchmark-best", action="store_true", help="Ogladaj najlepszego wg benchmarku (bez nauki).")
    mode.add_argument("--benchmark", type=str, metavar="CHECKPOINT", help="V42 legacy benchmark (bb/100).")
    mode.add_argument("--benchmark-v43", type=str, metavar="CHECKPOINT", help="V43 benchmark: BB per tournament, balanced seats.")
    mode.add_argument("--compare", nargs=2, metavar=("CHALLENGER", "INCUMBENT"),
                      help="V43: porownaj dwa checkpointy na tych samych rozgrywkach.")
    mode.add_argument("--watch-verified-best", action="store_true", help="Ogladaj zatwierdzonego championa V43.")
    mode.add_argument("--resume-verified-best", action="store_true", help="Trenuj od zatwierdzonego championa V43.")
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
    parser.add_argument("--list-benchmark", action="store_true", help="Stary ranking V42 (bez zmian).")
    parser.add_argument("--list-verified", action="store_true", help="Pokaz zatwierdzonego championa V43.")
    parser.add_argument("--selection-v43", action="store_true",
                        help="V43: zmienne testy, selekcja przeciw poprzedniemu championowi, osobny katalog.")
    parser.add_argument("--gate-tables", type=int, default=16,
                        help="Turnieje na miejsce w porownaniu nowy vs aktualny champion (V43).")
    parser.add_argument("--gate-z", type=float, default=0.8,
                        help="Margines niepewnosci, mnoznik standard error (V43).")
    parser.add_argument("--gate-margin-bb", type=float, default=1.0,
                        help="Minimalna poprawa BB na turniej (V43).")
    parser.add_argument("--teacher-hands", type=int, default=0,
                        help="V43: opcjonalny pretraining jednego mutanta od StrongPokerBot.")
    parser.add_argument("--train-mode", choices=("self-play", "bot", "mixed"), default=None,
                        help="Tryb treningu: self-play / bot / mixed. --with-bot = legacy bot.")
    parser.add_argument("--bot-fraction", type=float, default=0.5, help="Proporcja stolow z botem w mixed (0..1).")
    parser.add_argument("--benchmark-tables", type=int, default=2,
                        help="Liczba turniejow na pozycje (razem x4) na test jednego mozgu. 0 = bez benchmarku.")
    parser.add_argument("--benchmark-seed", type=int, default=980123, help="Stale ziarno porownywalnych turniejow.")
    parser.add_argument("--validation-seed", type=int, default=7980123,
                        help="Osobne ziarno benchmarku holdout do rankingu.")
    parser.add_argument("--benchmark-weight", type=float, default=0.75,
                        help="Waga wyniku benchmarku (0..1) przy wyborze championa.")
    parser.add_argument("--benchmark-every", type=int, default=1, help="Testuj co N-ta generacje.")
    parser.add_argument("--immigrant-every", type=int, default=10,
                        help="Co N generacji dodawaj jeden nowy losowy mozg; 0 wylacza.")
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
    parser.add_argument("--max-session-hands", type=int, default=None, help="Maksymalna liczba rozdan w jednym turnieju; po limicie nowy stol bez fikcyjnego zwyciezcy (domyslnie 500).")
    args = parser.parse_args()

    if args.list_benchmark:
        HallOfFame(reward_mode="benchmark_v1", top_k=args.top_k).print_ranking()
        return
    if args.list_verified:
        import json
        info = VerifiedChampion().describe()
        print(json.dumps(info, indent=2, ensure_ascii=False) if info else "No V43 champion yet")
        return
    if args.list_best:
        HallOfFame(reward_mode=args.reward_mode, top_k=args.top_k).print_ranking()
        return

    if not 0 <= args.bot_fraction <= 1:
        parser.error("--bot-fraction must be between 0 and 1")
    if not 0 <= args.benchmark_weight <= 1:
        parser.error("--benchmark-weight must be between 0 and 1")
    if args.benchmark_tables < 0 or args.benchmark_every < 1 or args.immigrant_every < 0:
        parser.error("invalid benchmark/immigrant parameters")
    if args.gate_tables < 1 or args.gate_z < 0 or args.gate_margin_bb < 0 or args.teacher_hands < 0:
        parser.error("invalid V43 gate parameters")
    cfg = Config()
    if args.max_session_hands is not None:
        if args.max_session_hands < 1:
            parser.error("--max-session-hands must be >= 1")
        cfg.max_hands_per_session = int(args.max_session_hands)
    if args.hands is not None and not (args.watch or args.watch_latest):
        cfg.hands_per_generation = max(1, int(args.hands))

    # Resolve aliases / latest checkpoint.
    watch_path = None
    resume_path = None
    force_render = False

    if args.compare:
        new, old = map(Path, args.compare)
        for ckpt in (new, old):
            if not ckpt.is_file():
                parser.error(f"Checkpoint does not exist: {ckpt}")
        result = compare_policies(SimpleFlyBrain.load(new), SimpleFlyBrain.load(old), cfg,
                                  tables_per_seat=max(1, args.gate_tables),
                                  seed=args.validation_seed, z=args.gate_z,
                                  min_delta_bb=args.gate_margin_bb)
        print(f"V43 COMPARISON | NEW {new} | {result['challenger']['profit_bb_per_table']:+.2f} BB/table"
              f" | OLD {old} | {result['incumbent']['profit_bb_per_table']:+.2f} BB/table")
        print(f"MATCHED DELTA {result['delta_profit_bb_per_table']:+.2f} BB/table"
              f" | SE {result['paired_standard_error_bb']:.2f}"
              f" | {'BETTER (gate passed)' if result['accepted'] else 'NOT PROVEN BETTER'}"
              f" | {result['challenger']['tables']} tables per model")
        return
    if args.benchmark_v43:
        ckpt = Path(args.benchmark_v43)
        if not ckpt.is_file():
            parser.error(f"Checkpoint does not exist: {ckpt}")
        result = evaluate_policy(SimpleFlyBrain.load(ckpt), cfg,
                                 tables_per_seat=max(1, args.benchmark_tables),
                                 seed=args.validation_seed)
        print(f"V43 BENCHMARK | {ckpt} | {result['profit_bb_per_table']:+.2f} BB/table"
              f" | {result['bb100']:+.2f} bb/100 (secondary)"
              f" | {result['wins']}/{result['tables']} tables won"
              f" | {result['active_hands']} active hands | {result['capped']} capped")
        return
    if args.benchmark:
        ckpt = Path(args.benchmark)
        if not ckpt.exists():
            parser.error(f"Checkpoint does not exist: {ckpt}")
        result = evaluate_brain(
            SimpleFlyBrain.load(ckpt), cfg,
            tables_per_seat=max(1, args.benchmark_tables),
            seed=args.validation_seed,
        )
        print(f"BENCHMARK | {ckpt} | vs 3 StrongPokerBot | "
              f"{result['bb100']:+.2f} bb/100 | {result['table_wins']}/{result['tables']} "
              f"tables won | {result['hands']} active hands | "
              f"{result['capped_tables']} capped")
        return
    if args.resume_verified_best:
        resume_path = VerifiedChampion().checkpoint
    elif args.watch_verified_best:
        watch_path = VerifiedChampion().checkpoint
    elif args.resume_benchmark_best:
        resume_path = Path("checkpoints/hall_of_fame/benchmark_v1/best_ever.npz")
    elif args.watch_benchmark_best:
        watch_path = Path("checkpoints/hall_of_fame/benchmark_v1/best_ever.npz")
    elif args.watch:
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

        actual_train_mode = args.train_mode or ("bot" if args.with_bot else "self-play")
        if resume_path is not None:
            print(
                f"RESUME TABLE TRAINING | checkpoint={resume_path} | "
                f"mode={actual_train_mode} | "
                f"render={'ON' if needs_render else 'OFF'}"
            )
        else:
            print(
                f"TABLE TRAINING FROM SCRATCH | mode={actual_train_mode} | "
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
            train_mode=args.train_mode,
            bot_fraction=args.bot_fraction,
            benchmark_tables=args.benchmark_tables,
            benchmark_seed=args.benchmark_seed,
            validation_seed=args.validation_seed,
            benchmark_weight=args.benchmark_weight,
            benchmark_every=args.benchmark_every,
            immigrant_every=args.immigrant_every,
            selection_v43=args.selection_v43,
            gate_tables=args.gate_tables,
            gate_confidence_z=args.gate_z,
            gate_margin_bb=args.gate_margin_bb,
            teacher_hands=args.teacher_hands,
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
