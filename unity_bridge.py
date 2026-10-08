"""Blocking Unity bridge for FlyPoker.

Unity listens on TCP 127.0.0.1:8765 and receives one JSON object per line.
For every poker action Python sends an ``animation`` message and blocks until
Unity replies with ``animation_done`` for the same seat.  This guarantees that
PokerEnv cannot advance to the next actor while the current fly animation is
still playing.
"""

from __future__ import annotations

import json
import socket
from typing import Any

from poker.cards import card_to_str
from poker.env import ACTION_NAMES


class UnityBridge:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        timeout: float = 60.0,
        verbose: bool = True,
    ):
        self.host = str(host)
        self.port = int(port)
        self.timeout = float(timeout)
        self.verbose = bool(verbose)

        self.sock: socket.socket | None = None
        self.reader = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    @property
    def connected(self) -> bool:
        return self.sock is not None

    def connect(self) -> None:
        if self.connected:
            return

        if self.verbose:
            print(f"[UNITY] Connecting to {self.host}:{self.port} ...")

        try:
            sock = socket.create_connection(
                (self.host, self.port),
                timeout=min(10.0, max(1.0, self.timeout)),
            )
        except OSError as exc:
            raise RuntimeError(
                f"Cannot connect to Unity at {self.host}:{self.port}. "
                "Start Unity Play mode first so PokerReceiver is listening."
            ) from exc

        sock.settimeout(self.timeout)
        self.sock = sock
        self.reader = sock.makefile("r", encoding="utf-8", newline="\n")

        if self.verbose:
            print("[UNITY] Connected.")

    def close(self) -> None:
        reader = self.reader
        sock = self.sock
        self.reader = None
        self.sock = None

        if reader is not None:
            try:
                reader.close()
            except OSError:
                pass

        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Raw protocol
    # ------------------------------------------------------------------
    def send(self, payload: dict[str, Any]) -> None:
        if self.sock is None:
            raise RuntimeError("UnityBridge is not connected.")

        line = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        if self.verbose:
            print(f"[PYTHON -> UNITY] {line}")

        try:
            self.sock.sendall((line + "\n").encode("utf-8"))
        except OSError as exc:
            self.close()
            raise ConnectionError("Unity disconnected while Python was sending data.") from exc

    def _read_message(self) -> dict[str, Any]:
        if self.reader is None:
            raise RuntimeError("UnityBridge is not connected.")

        try:
            line = self.reader.readline()
        except (OSError, socket.timeout) as exc:
            raise TimeoutError(
                f"Unity did not answer within {self.timeout:g}s. "
                "Check that AnimationFinished() exists at the end of the clip."
            ) from exc

        if line == "":
            self.close()
            raise ConnectionError("Unity disconnected while Python was waiting for a reply.")

        line = line.strip()
        if self.verbose:
            print(f"[UNITY -> PYTHON] {line}")

        if not line:
            return {}

        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            # Keep compatibility with tiny text replies such as PONG.
            return {"type": line}

        return value if isinstance(value, dict) else {"value": value}

    # ------------------------------------------------------------------
    # Animation handshake
    # ------------------------------------------------------------------
    @staticmethod
    def _unity_action(action: str) -> str:
        value = str(action or "").strip().upper()

        # Unity currently has Think / Call / Raise / Idle.
        # All betting sizes and ALL-IN use Raise for now.
        if value in {"ALL-IN", "ALL_IN", "ALLIN", "ALL IN"}:
            return "RAISE"
        if "RAISE" in value or "POT" in value or "BET" in value:
            return "RAISE"
        if value == "CALL":
            return "CALL"
        if value == "THINK":
            return "THINK"
        if value == "IDLE":
            return "IDLE"

        # CHECK/FOLD do not have their own clips yet.  Sending them is still
        # useful: PokerReceiver immediately returns animation_done.
        return value

    def animate_and_wait(self, seat: int, action: str, amount: int | float = 0) -> None:
        seat = int(seat)
        action = self._unity_action(action)

        self.send(
            {
                "type": "animation",
                "seat": seat,
                "action": action,
                "amount": int(round(float(amount))),
            }
        )

        while True:
            msg = self._read_message()
            msg_type = str(msg.get("type", "")).strip().lower()

            if msg_type != "animation_done":
                continue

            try:
                done_seat = int(msg.get("seat", -1))
            except (TypeError, ValueError):
                continue

            if done_seat == seat:
                return

    # ------------------------------------------------------------------
    # PokerEnv event hooks
    # ------------------------------------------------------------------
    def _send_public_state(self, env) -> None:
        self.send(
            {
                "type": "board",
                "cards": [card_to_str(c) for c in env.board],
                "street": env.street,
            }
        )
        self.send({"type": "pot", "amount": int(env.pot)})

    def _send_seat_state(self, env, seat: int) -> None:
        s = env.seats[int(seat)]
        self.send({"type": "stack", "seat": int(seat), "amount": int(s.stack)})
        self.send({"type": "bet", "seat": int(seat), "amount": int(s.street_contrib)})

    def on_new_hand(self, env, agents) -> None:
        self.send(
            {
                "type": "new_hand",
                "session": int(env.session_no),
                "hand": int(env.session_hand_no),
                "button": int(env.button),
                "small_blind": int(env.small_blind_seat),
                "big_blind": int(env.big_blind_seat),
            }
        )

        for seat, s in enumerate(env.seats):
            self.send(
                {
                    "type": "hole_cards",
                    "seat": int(seat),
                    "cards": [card_to_str(c) for c in s.hole],
                }
            )
            self._send_seat_state(env, seat)

        self._send_public_state(env)

    def before_action(self, env, seat: int, agents) -> None:
        # Board/pot may have changed since the previous action (new street).
        self._send_public_state(env)
        self.send({"type": "turn", "seat": int(seat)})

        # THINK blocks the poker loop until Unity's Think animation ends.
        self.animate_and_wait(int(seat), "THINK", 0)

    def after_action(self, env, seat: int, action: int, amount: int, agents) -> None:
        action_name = ACTION_NAMES.get(int(action), str(action))

        self.send(
            {
                "type": "action",
                "seat": int(seat),
                "action": action_name,
                "amount": int(amount),
            }
        )

        # This is the second blocking point.  The next actor cannot start until
        # Unity says the action clip has finished. CHECK/FOLD return DONE
        # immediately until dedicated clips are added.
        self.animate_and_wait(int(seat), action_name, amount)

        self._send_seat_state(env, seat)
        self._send_public_state(env)

    def on_hand_end(self, env, agents, winners) -> None:
        for seat in range(4):
            self._send_seat_state(env, seat)
        self._send_public_state(env)
        self.send(
            {
                "type": "hand_end",
                "winners": [int(x) for x in winners],
                "session_over": bool(env.session_over),
                "session_winner": (
                    None if env.session_winner is None else int(env.session_winner)
                ),
            }
        )
