from pathlib import Path
import numpy as np

from poker.env import PokerEnv, ACTION_COUNT
from .simple_brain import SimpleFlyBrain
from .strong_bot import StrongPokerBot
from .evolution import Evolution
from .checkpoints import checkpoint_generation
from .reward import RewardSystem
from .hall_of_fame import HallOfFame
from .telemetry import ActionTelemetry, EventFanout
from .benchmark import evaluate_brain, BENCHMARK_VERSION
from .benchmark_v43 import evaluate_policy, compare_policies, public_metrics
from .verified_champion import VerifiedChampion
from .imitation import collect_teacher_data, imitate_teacher
import json


class Trainer:
    def __init__(
        self,
        config,
        renderer=None,
        render_every=100,
        out_dir="checkpoints",
        resume_path=None,
        with_bot=False,
        unity_bridge=None,
        reward_mode="balanced",
        win_bonus_bb=2.0,
        risk_penalty=0.25,
        top_k=5,
        progress_every=500,
        train_mode=None,
        bot_fraction=0.5,
        benchmark_tables=2,
        benchmark_seed=980123,
        validation_seed=7980123,
        benchmark_weight=0.75,
        immigrant_every=10,
        benchmark_every=1,
        selection_v43=False,
        gate_tables=16,
        gate_confidence_z=0.8,
        gate_margin_bb=1.0,
        teacher_hands=0,
    ):
        self.cfg = config
        self.renderer = renderer
        self.render_every = max(1, int(render_every))
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        # Legacy --with-bot stays meaningful for old commands.
        self.train_mode = str(train_mode or ("bot" if with_bot else "self-play"))
        if self.train_mode not in ("self-play", "bot", "mixed"):
            raise ValueError("train_mode must be self-play, bot or mixed")
        self.with_bot = self.train_mode != "self-play"
        self.bot_fraction = float(bot_fraction)
        if not (0.0 <= self.bot_fraction <= 1.0):
            raise ValueError("bot_fraction must be between 0 and 1")
        self.benchmark_tables = max(0, int(benchmark_tables))
        self.benchmark_seed = int(benchmark_seed)
        self.validation_seed = int(validation_seed)
        if self.validation_seed == self.benchmark_seed:
            raise ValueError("validation_seed must differ from benchmark_seed")
        self.benchmark_weight = float(benchmark_weight)
        if not (0.0 <= self.benchmark_weight <= 1.0):
            raise ValueError("benchmark_weight must be between 0 and 1")
        self.immigrant_every = max(0, int(immigrant_every))
        self.benchmark_every = max(1, int(benchmark_every))
        self.selection_v43 = bool(selection_v43)
        self.gate_tables = max(1, int(gate_tables))
        self.gate_confidence_z = max(0.0, float(gate_confidence_z))
        self.gate_margin_bb = max(0.0, float(gate_margin_bb))
        self.teacher_hands = max(0, int(teacher_hands))
        self.teacher_summary = None
        self.verified = VerifiedChampion(self.out_dir) if self.selection_v43 else None
        self.benchmark_hall_of_fame = None
        if self.benchmark_tables and not self.selection_v43:
            self.benchmark_hall_of_fame = HallOfFame(
                self.out_dir, reward_mode="benchmark_v1", top_k=top_k)
        self.unity_bridge = unity_bridge
        self.progress_every = max(0, int(progress_every))
        self.reward_system = RewardSystem(
            big_blind=config.big_blind,
            mode=reward_mode,
            win_bonus_bb=win_bonus_bb,
            risk_penalty=risk_penalty,
            bust_penalty_bb=config.bust_penalty_bb,
        )
        self.hall_of_fame = HallOfFame(self.out_dir, reward_mode=reward_mode, top_k=top_k)
        self._last_reward_components = {}

        probe = PokerEnv(config, seed=config.seed)
        self.obs_size = probe.observation_size

        self.evolution = Evolution(
            mutation_strengths=config.mutation_strengths,
            mutation_probability=config.mutation_probability,
            seed=config.seed + 99,
        )

        if resume_path is not None:
            champion = SimpleFlyBrain.load(resume_path)
            if champion.input_size != self.obs_size:
                champion = champion.resize_input(self.obs_size)
            champion.display_name = "FLY 1"
            rng = self.evolution.rng
            self.brains = [champion.copy()]
            for strength in config.mutation_strengths:
                self.brains.append(
                    champion.mutate(
                        strength=float(strength),
                        probability=float(config.mutation_probability),
                        rng=rng,
                    )
                )
            resume_generation = checkpoint_generation(resume_path)
            if resume_generation == 0 and Path(resume_path).name == "best_ever.npz":
                metadata = Path(resume_path).parent / "leaderboard.json"
                if metadata.exists():
                    entries = json.loads(metadata.read_text(encoding="utf-8")).get("entries", [])
                    if entries:
                        resume_generation = int(entries[0]["generation"])
            # Resuming an earlier best must never overwrite newer generation
            # checkpoint files already in the user's checkpoints folder.
            existing = [checkpoint_generation(x) for x in self.out_dir.glob("best_brain_gen_*.npz")]
            self.start_generation = max([resume_generation] + existing) + 1
            self.resume_path = str(resume_path)
        else:
            rng = np.random.default_rng(config.seed)
            self.brains = [
                SimpleFlyBrain(
                    self.obs_size,
                    hidden_1=config.hidden_1,
                    hidden_2=config.hidden_2,
                    output_size=ACTION_COUNT,
                    rng=rng,
                )
                for _ in range(4)
            ]
            self.start_generation = 1
            self.resume_path = None

        for i, brain in enumerate(self.brains):
            brain.display_name = f"FLY {i+1}"

        self.bot = StrongPokerBot(config, seed=config.seed + 707) if self.with_bot else None

        if self.renderer is not None:
            mode = "TRAINING • TABLE SESSION • LEARNING ON"
            if self.with_bot:
                mode += " • " + self.train_mode.upper()
            if self.resume_path:
                mode += " • RESUMED"
            self.renderer.set_mode_text(mode)

    def _fitness_metrics(self, total_profit, bust_counts, hands_played,
                         sessions_played=None, table_wins=None, profit_samples=None):
        if sessions_played is None:
            sessions_played = hands_played
        calculated = self.reward_system.calculate(
            total_profit, bust_counts, hands_played, sessions_played,
            table_wins=table_wins, profit_samples=profit_samples,
        )
        self._last_reward_components = calculated
        return (
            calculated["fitness"],
            calculated["raw_bb100"],
            calculated["bust_rate"],
            calculated["bust_cost_bb100"],
        )

    def _is_bot_session(self, session_idx):
        if self.train_mode == "self-play":
            return False
        if self.train_mode == "bot":
            return True
        # Bresenham-style distribution, deterministic and balanced over blocks.
        # At 50%, every pair of 4-table blocks contains both modes.
        block = (int(session_idx) - 1) // 4
        return (int((block + 1) * self.bot_fraction)
                > int(block * self.bot_fraction))

    def _agents_for_session(self, session_idx):
        """Rotate seats between sessions; never swap players in mid-tournament."""
        if not self._is_bot_session(session_idx):
            rotation = (int(session_idx) - 1) % 4
            indices = [(i + rotation) % 4 for i in range(4)]
            agents = [self.brains[i] for i in indices]
            for seat, brain in enumerate(agents):
                brain.display_name = f"FLY {indices[seat] + 1}"
            return agents, indices

        bot_seat = (int(session_idx) - 1) % 4
        rotation = (int(session_idx) - 1) // 4 % 4
        agents, seat_to_fly = [], []
        for seat in range(4):
            if seat == bot_seat:
                self.bot.display_name = "BOT"
                agents.append(self.bot)
                seat_to_fly.append(None)
            else:
                candidate = (seat + rotation) % 4
                brain = self.brains[candidate]
                brain.display_name = f"FLY {candidate + 1}"
                agents.append(brain)
                seat_to_fly.append(candidate)
        return agents, seat_to_fly

    @staticmethod
    def _seat_values(candidate_values, seat_to_fly, bot_value=0.0):
        out = []
        for fly_idx in seat_to_fly:
            out.append(float(bot_value) if fly_idx is None else float(candidate_values[fly_idx]))
        return out

    def evaluate_generation(self, generation):
        env = PokerEnv(self.cfg, seed=self.cfg.seed + generation * 100_003)

        total_profit = np.zeros(4, dtype=np.float64)
        bust_counts = np.zeros(4, dtype=np.int64)
        played_counts = np.zeros(4, dtype=np.int64)
        sessions_played = np.zeros(4, dtype=np.int64)
        table_wins = np.zeros(4, dtype=np.int64)
        profit_samples = [[] for _ in range(4)]
        telemetry = ActionTelemetry()

        bot_profit = 0.0
        bot_hands = 0
        bot_sessions = 0
        bot_table_wins = 0

        hand_idx = 0
        session_idx = 0
        target_hands = max(1, int(self.cfg.hands_per_generation))
        session_cap = max(1, int(getattr(self.cfg, "max_hands_per_session", 500)))
        capped_sessions = 0
        bot_sessions_count = 0
        selfplay_sessions_count = 0
        stopped = False

        # Normally finish a tournament; cap sessions that cannot eliminate
        # the last players (e.g. deterministic FOLD/FOLD heads-up loops).
        # A capped table records chip profits but awards no table victory.
        while True:
            session_idx += 1
            if self._is_bot_session(session_idx):
                bot_sessions_count += 1
            else:
                selfplay_sessions_count += 1
            agents, seat_to_fly = self._agents_for_session(session_idx)
            telemetry.set_mapping(seat_to_fly)
            events = EventFanout(self.unity_bridge, telemetry)
            env.reset_session()

            for seat, fly_idx in enumerate(seat_to_fly):
                if fly_idx is None:
                    bot_sessions += 1
                else:
                    sessions_played[fly_idx] += 1

            while not env.session_over and env.session_hand_no < session_cap:
                hand_idx += 1

                render_this = (
                    self.renderer is not None
                    and (
                        hand_idx == 1
                        or hand_idx % self.render_every == 0
                        or len(env._live_session()) <= 2
                    )
                )

                callback = None
                if render_this:
                    current_fit, _, current_bust_rate, _ = self._fitness_metrics(
                        total_profit,
                        bust_counts,
                        played_counts,
                        sessions_played,
                        table_wins=table_wins,
                        profit_samples=profit_samples,
                    )
                    seat_fit = self._seat_values(current_fit, seat_to_fly, bot_value=0.0)
                    seat_bust = self._seat_values(
                        current_bust_rate * 100.0,
                        seat_to_fly,
                        bot_value=0.0,
                    )
                    seat_wins = self._seat_values(
                        table_wins,
                        seat_to_fly,
                        bot_value=bot_table_wins,
                    )
                    self.renderer.set_meta(
                        generation,
                        hand_idx,
                        seat_fit,
                        bust_rate=seat_bust,
                        session_index=session_idx,
                        table_wins=seat_wins,
                    )
                    callback = lambda e, s, a: self.renderer.render(e, s, a)

                result = env.play_hand(agents, callback=callback, event_handler=events)
                profits = np.asarray(result["profits"], dtype=np.float64)
                busted = np.asarray(result.get("busted", [False] * 4), dtype=np.int64)

                for seat, fly_idx in enumerate(seat_to_fly):
                    if fly_idx is None:
                        bot_profit += float(profits[seat])
                        bot_hands += 1
                    else:
                        total_profit[fly_idx] += profits[seat]
                        bust_counts[fly_idx] += busted[seat]
                        played_counts[fly_idx] += 1
                        profit_samples[fly_idx].append(float(profits[seat]))

                if result.get("session_over"):
                    winner_seat = int(result["session_winner"])
                    winner_fly = seat_to_fly[winner_seat]
                    if winner_fly is None:
                        bot_table_wins += 1
                    else:
                        table_wins[winner_fly] += 1

                if self.progress_every and hand_idx % self.progress_every == 0:
                    print(f"  GEN {generation:04d} | {hand_idx} hands | "
                          f"{session_idx} tables | stacks {[s.stack for s in env.seats]}", flush=True)

                if self.renderer is not None and self.renderer.closed:
                    stopped = True
                    break

            if stopped:
                break
            if not env.session_over:
                capped_sessions += 1
                print(
                    f"  GEN {generation:04d} | TABLE {session_idx} capped after "
                    f"{session_cap} hands (no tournament winner); "
                    f"final stacks {[seat.stack for seat in env.seats]}",
                    flush=True,
                )

            # End only BETWEEN finished or capped table sessions.
            # Finish whole blocks: bot seats rotate every 4 sessions.
            if hand_idx >= target_hands:
                block_size = 8 if self.train_mode == "mixed" else 4 if self.with_bot else 1
                if session_idx % block_size == 0:
                    break

        fitness, raw_bb100, bust_rate, bust_penalty_bb100 = self._fitness_metrics(
            total_profit,
            bust_counts,
            played_counts,
            sessions_played,
            table_wins=table_wins,
            profit_samples=profit_samples,
        )

        metrics = {
            "raw_bb100": raw_bb100,
            "table_win_bonus_bb100": self._last_reward_components["table_win_bonus_bb100"],
            "risk_cost_bb100": self._last_reward_components["risk_cost_bb100"],
            "bust_rate": bust_rate,
            "bust_counts": bust_counts,
            "bust_penalty_bb100": bust_penalty_bb100,
            "played_counts": played_counts,
            "sessions_played": sessions_played,
            "table_wins": table_wins,
            "table_win_rate": table_wins / np.maximum(1, sessions_played),
            "sessions": int(session_idx),
            "bot_training_tables": int(bot_sessions_count),
            "selfplay_training_tables": int(selfplay_sessions_count),
            "capped_sessions": int(capped_sessions),
            **telemetry.summary(),
            "bot_profit": float(bot_profit),
            "bot_hands": int(bot_hands),
            "bot_sessions": int(bot_sessions),
            "bot_table_wins": int(bot_table_wins),
            "bot_bb100": (
                (bot_profit / self.cfg.big_blind) / max(1, bot_hands) * 100.0
            ) if self.with_bot else 0.0,
        }
        return fitness, int(hand_idx), metrics

    def run(self, generations=None):
        generations = int(generations or self.cfg.generations)
        history = []
        incumbent = None
        if self.selection_v43:
            if self.verified.exists():
                incumbent = self.verified.load(self.obs_size)
                print(f"V43 | verified champion loaded: {self.verified.checkpoint}", flush=True)
            else:
                incumbent = self.brains[0].copy()
                self.verified.save(incumbent, generation=self.start_generation - 1,
                                   source=self.resume_path or "random_initial_champion")
                print(f"V43 | initial champion baseline saved: {self.verified.checkpoint}", flush=True)

        if self.selection_v43 and self.teacher_hands:
            samples = collect_teacher_data(
                self.cfg, hands=self.teacher_hands,
                seed=self.cfg.seed + self.start_generation * 7919,
            )
            # One diversified candidate learns from a rule bot. The baseline
            # incumbent is untouched and must still pass an objective gate.
            self.teacher_summary = imitate_teacher(self.brains[-1], samples)
            print(f"V43 | teacher candidate: {self.teacher_summary}", flush=True)

        first_gen = int(self.start_generation)
        last_gen = first_gen + generations - 1

        for gen in range(first_gen, last_gen + 1):
            fitness, hands_played, metrics = self.evaluate_generation(gen)

            # V43: choose candidate on changing, seat-balanced data; accept it
            # ONLY if it improves over the incumbent on a separate matched gate.
            # Old V42 behavior is unchanged without --selection-v43.
            benchmark_results = None
            gate_result = None
            validation_result = None
            is_new_verified = False
            is_new_best = False
            selected_scores = np.asarray(fitness, dtype=np.float64).copy()
            if self.selection_v43:
                if self.benchmark_tables and gen % self.benchmark_every == 0:
                    generation_seed = self.benchmark_seed + gen * 100_003
                    benchmark_results = [
                        public_metrics(evaluate_policy(
                            brain, self.cfg, tables_per_seat=self.benchmark_tables,
                            seed=generation_seed,
                        )) for brain in self.brains
                    ]
                    bench_scores = np.array([r["profit_bb_per_table"] for r in benchmark_results])
                    # Rank aggregation avoids mixing incomparable bb/100 and
                    # per-tournament units. High rank wins; no fixed seed reuse.
                    # Equal benchmark values receive equal ranks (no arbitrary
                    # promotion based on array order when every fly loses).
                    def tied_ranks(values):
                        values = np.asarray(values, dtype=np.float64)
                        return np.array([
                            float(np.sum(values < v)) + 0.5 * (np.sum(values == v) - 1)
                            for v in values
                        ])
                    bench_rank = tied_ranks(bench_scores)
                    train_rank = tied_ranks(fitness)
                    selected_scores = (self.benchmark_weight * bench_rank
                                       + (1.0 - self.benchmark_weight) * train_rank)
                best_idx = int(np.argmax(selected_scores))
                candidate = self.brains[best_idx].copy()
                gate_seed = self.validation_seed + gen * 104_729
                gate_result = compare_policies(
                    candidate, incumbent, self.cfg,
                    tables_per_seat=self.gate_tables,
                    seed=gate_seed, z=self.gate_confidence_z,
                    min_delta_bb=self.gate_margin_bb,
                )
                is_new_verified = bool(gate_result["accepted"])
                if is_new_verified:
                    incumbent = candidate.copy()
                    self.verified.save(incumbent, generation=gen,
                                       source=f"generation_{gen:04d}_fly_{best_idx+1}",
                                       gate=gate_result)
                champion = incumbent.copy()
                next_brains = self.evolution.spawn_from(
                    champion, generation=gen, immigrant_every=self.immigrant_every)
                # Never modify V42's Hall of Fame directories in V43 mode.
                validation_result = gate_result["challenger"]
            else:
                if self.benchmark_tables and gen % self.benchmark_every == 0:
                    benchmark_results = [
                        evaluate_brain(brain, self.cfg,
                            tables_per_seat=self.benchmark_tables,
                            seed=self.benchmark_seed,
                            max_session_hands=getattr(self.cfg, "max_hands_per_session", 500),
                        ) for brain in self.brains
                    ]
                    bench_scores = np.array([x["bb100"] for x in benchmark_results], dtype=np.float64)
                    selected_scores = (self.benchmark_weight * bench_scores
                        + (1.0 - self.benchmark_weight) * np.asarray(fitness, dtype=np.float64))
                best_idx, champion, next_brains = self.evolution.next_generation(
                    self.brains, selected_scores, generation=gen,
                    immigrant_every=self.immigrant_every,
                )

            checkpoint = self.out_dir / f"best_brain_gen_{gen:04d}.npz"
            champion.save(checkpoint)

            if not self.selection_v43:
                if benchmark_results is not None:
                    validation_result = evaluate_brain(
                        champion, self.cfg, tables_per_seat=self.benchmark_tables,
                        seed=self.validation_seed,
                        max_session_hands=getattr(self.cfg, "max_hands_per_session", 500),
                    )
                    is_new_verified = self.benchmark_hall_of_fame.consider(
                        generation=gen, fly=best_idx + 1,
                        fitness=float(validation_result["bb100"]),
                        checkpoint_path=checkpoint,
                        metrics={**validation_result,
                                 "selection_benchmark_bb100": float(benchmark_results[best_idx]["bb100"]),
                                 "train_mode": self.train_mode,
                                 "selection_score": float(selected_scores[best_idx])},
                    )
                is_new_best = self.hall_of_fame.consider(
                    generation=gen,
                    fly=best_idx + 1,
                    fitness=float(fitness[best_idx]),
                    checkpoint_path=checkpoint,
                    metrics={
                        "raw_bb100": float(metrics["raw_bb100"][best_idx]),
                        "bust_rate": float(metrics["bust_rate"][best_idx]),
                        "table_wins": int(metrics["table_wins"][best_idx]),
                        "hands": int(hands_played),
                        "reward_mode": self.reward_system.mode,
                        "win_bonus_bb": self.reward_system.win_bonus_bb,
                        "risk_penalty": self.reward_system.risk_penalty,
                    },
                )

            row = {
                "generation": gen,
                "hands": hands_played,
                "sessions": metrics["sessions"],
                "capped_sessions": metrics["capped_sessions"],
                "fitness": fitness.tolist(),
                "raw_bb100": metrics["raw_bb100"].tolist(),
                "table_win_bonus_bb100": metrics["table_win_bonus_bb100"].tolist(),
                "risk_cost_bb100": metrics["risk_cost_bb100"].tolist(),
                "bust_rate": metrics["bust_rate"].tolist(),
                "bust_counts": metrics["bust_counts"].tolist(),
                "bust_penalty_bb100": metrics["bust_penalty_bb100"].tolist(),
                "played_counts": metrics["played_counts"].tolist(),
                "sessions_played": metrics["sessions_played"].tolist(),
                "table_wins": metrics["table_wins"].tolist(),
                "table_win_rate": metrics["table_win_rate"].tolist(),
                "best_fly": best_idx + 1,
                "best_fitness": float(fitness[best_idx]),
                "selection_scores": selected_scores.tolist(),
                "benchmark_results": benchmark_results,
                "validation_result": validation_result,
                "new_best_benchmark": bool(is_new_verified),
                "v43_enabled": bool(self.selection_v43),
                "v43_gate": gate_result,
                "v43_teacher": self.teacher_summary if gen == first_gen else None,
                "v43_verified_checkpoint": str(self.verified.checkpoint) if self.selection_v43 else None,
                "train_mode": self.train_mode,
                "bot_training_tables": metrics["bot_training_tables"],
                "selfplay_training_tables": metrics["selfplay_training_tables"],
                "checkpoint": str(checkpoint),
                "new_best_ever": bool(is_new_best),
                "reward_mode": self.reward_system.mode,
                "action_counts": metrics["action_counts"],
                "vpip_pct": metrics["vpip_pct"],
                "pfr_pct": metrics["pfr_pct"],
                "with_bot": self.with_bot,
                "bot_bb100": float(metrics["bot_bb100"]),
                "bot_table_wins": int(metrics["bot_table_wins"]),
            }
            history.append(row)
            with (self.out_dir / "training_history.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

            pieces = []
            for i in range(4):
                pieces.append(
                    f"Fly {i+1}: {fitness[i]:+7.2f} fit "
                    f"[raw {metrics['raw_bb100'][i]:+7.2f} | "
                    f"tables {int(metrics['table_wins'][i])}/{int(metrics['sessions_played'][i])} | "
                    f"bust {metrics['bust_rate'][i]*100:4.1f}% | "
                    f"hands {int(metrics['played_counts'][i])} | "
                    f"VPIP {metrics['vpip_pct'][i]:4.1f}% / PFR {metrics['pfr_pct'][i]:4.1f}%]"
                )

            bot_piece = ""
            if self.with_bot:
                bot_piece = (
                    f" | BOT {metrics['bot_bb100']:+7.2f} bb/100 "
                    f"| BOT tables {metrics['bot_table_wins']}/{metrics['bot_sessions']}"
                )

            print(
                f"GEN {gen:04d} | {metrics['sessions']} TABLES "
                f"({metrics['capped_sessions']} capped) | "
                + " | ".join(pieces)
                + f"{bot_piece} | SELECTED: Fly {best_idx+1}" +
                ((f" | V43 BENCH {benchmark_results[best_idx]['profit_bb_per_table']:+.2f} BB/table"
                  if benchmark_results is not None else "") +
                 f" | GATE {gate_result['delta_profit_bb_per_table']:+.2f} BB/table"
                 f" (SE {gate_result['paired_standard_error_bb']:.2f})"
                 + (" | ACCEPTED" if is_new_verified else " | REJECTED - incumbent kept")
                 if self.selection_v43 else
                 ((f" | BENCH {benchmark_results[best_idx]['bb100']:+.2f} bb/100"
                   f" | HOLDOUT {validation_result['bb100']:+.2f} bb/100"
                   if benchmark_results is not None else "") +
                  (" | NEW BENCHMARK #1" if is_new_verified else "") +
                  (" | NEW TRAINING HOF #1" if is_new_best else "")))
            )

            self.brains = next_brains
            for i, brain in enumerate(self.brains):
                brain.display_name = f"FLY {i+1}"

            if self.renderer is not None and self.renderer.closed:
                break

        return history
