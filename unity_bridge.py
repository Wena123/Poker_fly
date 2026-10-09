"""Unity bridge for FlyPoker with animation + chip-flow handshakes.

Protocol (one JSON object per line):
- Python -> Unity: animation / state messages / collect_bets / award_pot
- Unity -> Python: animation_done / chip_flow_done

The bridge waits for Unity when an animation or chip-flow is running, but pumps
Pygame/OpenCV while waiting so the debug windows stay responsive.
"""

from __future__ import annotations

import json
import select
import socket
import time
from typing import Any, Callable

from poker.cards import card_to_str
from poker.env import ACTION_NAMES


class UnityBridge:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        timeout: float = 60.0,
        verbose: bool = True,
        poll_interval: float = 0.02,
    ):
        self.host = str(host)
        self.port = int(port)
        self.timeout = float(timeout)
        self.verbose = bool(verbose)
        self.poll_interval = max(0.005, float(poll_interval))

        self.sock: socket.socket | None = None
        self._recv_buffer = bytearray()
        self._wait_pump: Callable[[], None] | None = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    @property
    def connected(self) -> bool:
        return self.sock is not None

    def set_wait_pump(self, callback: Callable[[], None] | None) -> None:
        self._wait_pump = callback

    def _pump_wait_ui(self) -> None:
        cb = self._wait_pump
        if cb is None:
            return
        try:
            cb()
        except Exception as exc:
            if self.verbose:
                print(f"[UNITY] wait-pump warning: {exc}")
            self._wait_pump = None

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

        sock.settimeout(None)
        self.sock = sock
        self._recv_buffer.clear()

        if self.verbose:
            print("[UNITY] Connected.")

    def close(self) -> None:
        sock = self.sock
        self.sock = None
        self._recv_buffer.clear()

        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
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

    def _pop_buffered_line(self) -> str | None:
        try:
            idx = self._recv_buffer.index(10)
        except ValueError:
            return None

        raw = bytes(self._recv_buffer[:idx])
        del self._recv_buffer[: idx + 1]
        return raw.rstrip(b"\r").decode("utf-8", errors="replace")

    def _read_message(self) -> dict[str, Any]:
        sock = self.sock
        if sock is None:
            raise RuntimeError("UnityBridge is not connected.")

        deadline = time.monotonic() + self.timeout

        while True:
            buffered = self._pop_buffered_line()
            if buffered is not None:
                line = buffered.strip()
                break

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"Unity did not answer within {self.timeout:g}s. "
                    "Check Unity Console and the corresponding DONE event."
                )

            self._pump_wait_ui()

            try:
                readable, _, _ = select.select(
                    [sock], [], [], min(self.poll_interval, remaining)
                )
            except (OSError, ValueError) as exc:
                self.close()
                raise ConnectionError(
                    "Unity socket became invalid while Python was waiting."
                ) from exc

            if not readable:
                continue

            try:
                chunk = sock.recv(4096)
            except OSError as exc:
                self.close()
                raise ConnectionError(
                    "Unity disconnected while Python was waiting for a reply."
                ) from exc

            if not chunk:
                self.close()
                raise ConnectionError(
                    "Unity disconnected while Python was waiting for a reply."
                )

            self._recv_buffer.extend(chunk)

        if self.verbose:
            print(f"[UNITY -> PYTHON] {line}")

        if not line:
            return {}

        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            return {"type": line}

        return value if isinstance(value, dict) else {"value": value}

    def _wait_for(self, message_type: str, **expected_fields: Any) -> dict[str, Any]:
        expected_type = str(message_type).strip().lower()

        while True:
            msg = self._read_message()
            msg_type = str(msg.get("type", "")).strip().lower()
            if msg_type != expected_type:
                continue

            matches = True
            for key, expected in expected_fields.items():
                if msg.get(key) != expected:
                    matches = False
                    break

            if matches:
                return msg

    # ------------------------------------------------------------------
    # Animation handshake
    # ------------------------------------------------------------------
    @staticmethod
    def _unity_action(action: str) -> str:
        value = str(action or "").strip().upper()

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

        self._wait_for("animation_done", seat=seat)

    # ------------------------------------------------------------------
    # Chip-flow handshake
    # ------------------------------------------------------------------
    def collect_bets_and_wait(self, street: str = "") -> None:
        self.send({"type": "collect_bets", "street": str(street)})
        self._wait_for("chip_flow_done", flow="collect_bets")

    def award_pot_and_wait(self, winner_seat: int) -> None:
        winner_seat = int(winner_seat)
        self.send({"type": "award_pot", "seat": winner_seat})
        self._wait_for("chip_flow_done", flow="award_pot", seat=winner_seat)

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------
    def _send_public_state(self, env, *, pot_override: int | None = None) -> None:
        self.send(
            {
                "type": "board",
                "cards": [card_to_str(c) for c in env.board],
                "street": env.street,
            }
        )

        pot_value = int(env.pot) if pot_override is None else int(pot_override)
        self.send({"type": "pot", "amount": pot_value})

    def _send_board_only(self, env) -> None:
        self.send(
            {
                "type": "board",
                "cards": [card_to_str(c) for c in env.board],
                "street": env.street,
            }
        )

    def _send_seat_state(self, env, seat: int) -> None:
        s = env.seats[int(seat)]
        self.send({"type": "stack", "seat": int(seat), "amount": int(s.stack)})
        self.send({"type": "bet", "seat": int(seat), "amount": int(s.street_contrib)})

    # ------------------------------------------------------------------
    # PokerEnv hooks
    # ------------------------------------------------------------------
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

        # At the start of a hand the blinds are still physically on BetAnchors.
        # Keep PotAnchor empty until the preflop betting round is collected.
        self._send_public_state(env, pot_override=0)

    def before_action(self, env, seat: int, agents) -> None:
        # Keep board current, but do NOT rebuild PotAnchor while street bets are
        # still sitting on BetAnchors.
        self._send_board_only(env)
        self.send({"type": "turn", "seat": int(seat)})
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

        self.animate_and_wait(int(seat), action_name, amount)

        self._send_seat_state(env, seat)
        self._send_board_only(env)

    def on_betting_round_end(self, env, agents) -> None:
        # If no chips were committed on this street, there is nothing to move.
        if not any(int(s.street_contrib) > 0 for s in env.seats):
            return

        self.collect_bets_and_wait(env.street)

        # After the physical chips reached PotAnchor, reconcile the visual pot
        # with Python's exact cumulative pot value.
        self.send({"type": "pot", "amount": int(env.pot)})

        # The next street starts with no current bets. Clear the BetAnchor UI now
        # rather than waiting for every seat to act again.
        for seat in range(4):
            self.send({"type": "bet", "seat": seat, "amount": 0})

    def on_hand_end(self, env, agents, winners) -> None:
        winners = [int(x) for x in winners]

        # The normal case is one hand winner. Animate PotAnchor -> winner stack
        # before rebuilding the authoritative final stacks.
        if len(winners) == 1:
            self.award_pot_and_wait(winners[0])
        elif len(winners) > 1:
            # Split-pot visual distribution is not implemented yet. Clear pot
            # immediately below and let authoritative stacks show the split.
            if self.verbose:
                print(
                    "[UNITY] split pot: skipping winner-flight animation for "
                    f"winners={winners}"
                )

        for seat in range(4):
            # street_contrib is no longer a visible bet after hand payout.
            s = env.seats[seat]
            self.send({"type": "stack", "seat": seat, "amount": int(s.stack)})
            self.send({"type": "bet", "seat": seat, "amount": 0})

        # env.pot intentionally still contains the hand's historical pot after
        # _award(), so the Unity visual must explicitly be zeroed here.
        self._send_public_state(env, pot_override=0)

        self.send(
            {
                "type": "hand_end",
                "winners": winners,
                "session_over": bool(env.session_over),
                "session_winner": (
                    None if env.session_winner is None else int(env.session_winner)
                ),
            }
        )
