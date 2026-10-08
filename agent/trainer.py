from pathlib import Path
import numpy as np

from poker.env import PokerEnv, ACTION_COUNT
from .simple_brain import SimpleFlyBrain
from .strong_bot import StrongPokerBot
from .evolution import Evolution
from .checkpoints import checkpoint_generation


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
    ):
        self.cfg = config
        self.renderer = renderer
        self.render_every = max(1, int(render_every))
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.with_bot = bool(with_bot)
        self.unity_bridge = unity_bridge

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
                raise ValueError(
                    f"Checkpoint input size {champion.input_size} does not match "
                    f"current environment {self.obs_size}."
                )
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
            self.start_generation = checkpoint_generation(resume_path) + 1
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
                mode += " • BOT OPPONENT"
            if self.resume_path:
                mode += " • RESUMED"
            self.renderer.set_mode_text(mode)

    def _fitness_metrics(
        self,
        total_profit,
        bust_counts,
        hands_played,
        sessions_played=None,
    ):
        total_profit = np.asarray(total_profit, dtype=np.float64)
        bust_counts = np.asarray(bust_counts, dtype=np.float64)
        hands = np.maximum(1.0, np.asarray(hands_played, dtype=np.float64))
        if hands.ndim == 0:
            hands = np.full(4, float(hands), dtype=np.float64)

        if sessions_played is None:
            sessions = hands
        else:
            sessions = np.maximum(1.0, np.asarray(sessions_played, dtype=np.float64))
            if sessions.ndim == 0:
                sessions = np.full(4, float(sessions), dtype=np.float64)

        raw_bb100 = (total_profit / self.cfg.big_blind) / hands * 100.0

        # Displayed bust rate = percentage of table sessions in which a fly
        # was eliminated. The penalty itself is still normalized per 100 hands.
        bust_rate = bust_counts / sessions
        bust_penalty_bb100 = (
            bust_counts * float(self.cfg.bust_penalty_bb) / hands * 100.0
        )
        fitness = raw_bb100 - bust_penalty_bb100
        return fitness, raw_bb100, bust_rate, bust_penalty_bb100

    def _agents_for_session(self, session_idx):
        """Return fixed seat agents for one complete table session.

        Without BOT: candidates occupy seats 0..3 for the whole table.
        With BOT: the BOT occupies one fixed seat for the whole session and
        rotates seat each NEW session. That seat's candidate sits out until
        the table has a winner. This keeps persistent stacks valid.
        """
        if not self.with_bot:
            agents = list(self.brains)
            for i, brain in enumerate(agents):
                brain.display_name = f"FLY {i+1}"
            return agents, [0, 1, 2, 3]

        bot_seat = (int(session_idx) - 1) % 4
        agents = []
        seat_to_fly = []
        for seat in range(4):
            if seat == bot_seat:
                self.bot.display_name = "BOT"
                agents.append(self.bot)
                seat_to_fly.append(None)
            else:
                brain = self.brains[seat]
                brain.display_name = f"FLY {seat+1}"
                agents.append(brain)
                seat_to_fly.append(seat)
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

        bot_profit = 0.0
        bot_hands = 0
        bot_sessions = 0
        bot_table_wins = 0

        hand_idx = 0
        session_idx = 0
        target_hands = max(1, int(self.cfg.hands_per_generation))
        stopped = False

        # Important: once a table session starts, it is ALWAYS completed.
        # Therefore a generation can contain slightly more than target_hands.
        while True:
            session_idx += 1
            agents, seat_to_fly = self._agents_for_session(session_idx)
            env.reset_session()

            for seat, fly_idx in enumerate(seat_to_fly):
                if fly_idx is None:
                    bot_sessions += 1
                else:
                    sessions_played[fly_idx] += 1

            while not env.session_over:
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

                result = env.play_hand(agents, callback=callback, event_handler=self.unity_bridge)
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

                if result.get("session_over"):
                    winner_seat = int(result["session_winner"])
                    winner_fly = seat_to_fly[winner_seat]
                    if winner_fly is None:
                        bot_table_wins += 1
                    else:
                        table_wins[winner_fly] += 1

                if self.renderer is not None and self.renderer.closed:
                    stopped = True
                    break

            if stopped:
                break

            # Only end a generation BETWEEN completed table sessions.
            # With BOT, finish a full 4-session seat-rotation block so every
            # candidate sits out exactly once and plays the other 3 tables.
            if hand_idx >= target_hands:
                if (not self.with_bot) or (session_idx % 4 == 0):
                    break

        fitness, raw_bb100, bust_rate, bust_penalty_bb100 = self._fitness_metrics(
            total_profit,
            bust_counts,
            played_counts,
            sessions_played,
        )

        metrics = {
            "raw_bb100": raw_bb100,
            "bust_rate": bust_rate,
            "bust_counts": bust_counts,
            "bust_penalty_bb100": bust_penalty_bb100,
            "played_counts": played_counts,
            "sessions_played": sessions_played,
            "table_wins": table_wins,
            "table_win_rate": table_wins / np.maximum(1, sessions_played),
            "sessions": int(session_idx),
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

        first_gen = int(self.start_generation)
        last_gen = first_gen + generations - 1

        for gen in range(first_gen, last_gen + 1):
            fitness, hands_played, metrics = self.evaluate_generation(gen)

            best_idx, champion, next_brains = self.evolution.next_generation(
                self.brains, fitness
            )

            checkpoint = self.out_dir / f"best_brain_gen_{gen:04d}.npz"
            champion.save(checkpoint)

            row = {
                "generation": gen,
                "hands": hands_played,
                "sessions": metrics["sessions"],
                "fitness": fitness.tolist(),
                "raw_bb100": metrics["raw_bb100"].tolist(),
                "bust_rate": metrics["bust_rate"].tolist(),
                "bust_counts": metrics["bust_counts"].tolist(),
                "bust_penalty_bb100": metrics["bust_penalty_bb100"].tolist(),
                "played_counts": metrics["played_counts"].tolist(),
                "sessions_played": metrics["sessions_played"].tolist(),
                "table_wins": metrics["table_wins"].tolist(),
                "table_win_rate": metrics["table_win_rate"].tolist(),
                "best_fly": best_idx + 1,
                "best_fitness": float(fitness[best_idx]),
                "checkpoint": str(checkpoint),
                "with_bot": self.with_bot,
                "bot_bb100": float(metrics["bot_bb100"]),
                "bot_table_wins": int(metrics["bot_table_wins"]),
            }
            history.append(row)

            pieces = []
            for i in range(4):
                pieces.append(
                    f"Fly {i+1}: {fitness[i]:+7.2f} fit "
                    f"[raw {metrics['raw_bb100'][i]:+7.2f} | "
                    f"tables {int(metrics['table_wins'][i])}/{int(metrics['sessions_played'][i])} | "
                    f"bust {metrics['bust_rate'][i]*100:4.1f}% | "
                    f"hands {int(metrics['played_counts'][i])}]"
                )

            bot_piece = ""
            if self.with_bot:
                bot_piece = (
                    f" | BOT {metrics['bot_bb100']:+7.2f} bb/100 "
                    f"| BOT tables {metrics['bot_table_wins']}/{metrics['bot_sessions']}"
                )

            print(
                f"GEN {gen:04d} | {metrics['sessions']} TABLES | "
                + " | ".join(pieces)
                + f"{bot_piece} | BEST: Fly {best_idx+1}"
            )

            self.brains = next_brains
            for i, brain in enumerate(self.brains):
                brain.display_name = f"FLY {i+1}"

            if self.renderer is not None and self.renderer.closed:
                break

        return history
