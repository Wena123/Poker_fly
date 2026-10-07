import json
import socket
import time


class UnityBridge:
    """Stream PokerEnv snapshots to a local Unity viewer.

    PokerEnv stays the single source of truth. Unity only receives visual
    events over newline-delimited JSON on localhost.
    """

    def __init__(self, host="127.0.0.1", port=8765, reconnect_delay=1.0):
        self.host = str(host)
        self.port = int(port)
        self.reconnect_delay = float(reconnect_delay)
        self.sock = None
        self._next_reconnect = 0.0

        self._last_hand_no = None
        self._last_board = None
        self._last_holes = {}
        self._last_stacks = {}
        self._last_bets = {}
        self._last_visual_pot = None
        self._needs_full_sync = True

    @property
    def connected(self):
        return self.sock is not None

    def _disconnect(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None
        self._needs_full_sync = True
        self._next_reconnect = time.monotonic() + self.reconnect_delay

    def connect(self):
        if self.sock is not None:
            return True

        now = time.monotonic()
        if now < self._next_reconnect:
            return False

        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=0.35)
            self.sock.settimeout(None)
            self._needs_full_sync = True
            print(f"[UNITY] Connected -> {self.host}:{self.port}", flush=True)
            return True
        except OSError:
            self.sock = None
            self._next_reconnect = now + self.reconnect_delay
            return False

    def send(self, event_type, **data):
        if not self.connect():
            return False

        payload = {"type": str(event_type), **data}
        try:
            line = json.dumps(payload, separators=(",", ":")) + "\n"
            self.sock.sendall(line.encode("utf-8"))
            return True
        except OSError:
            print("[UNITY] Connection lost; waiting for Unity to come back...", flush=True)
            self._disconnect()
            return False

    @staticmethod
    def _chip_state(snapshot):
        players = snapshot.get("players", [])
        winners = snapshot.get("winners") or []

        stacks = {
            int(p.get("seat", -1)): int(p.get("stack", 0))
            for p in players
            if int(p.get("seat", -1)) >= 0
        }

        # During a betting street, chips in front of players represent their
        # current-street contribution. Previous-street chips are in the centre.
        if winners:
            bets = {seat: 0 for seat in stacks}
            visual_pot = 0
        else:
            bets = {
                int(p.get("seat", -1)): int(p.get("street_contrib", 0))
                for p in players
                if int(p.get("seat", -1)) >= 0
            }
            total_pot = int(snapshot.get("pot", 0))
            visual_pot = max(0, total_pot - sum(bets.values()))

        return stacks, bets, visual_pot

    def _sync_chips(self, snapshot, force=False):
        stacks, bets, visual_pot = self._chip_state(snapshot)

        for seat, amount in sorted(stacks.items()):
            if force or self._last_stacks.get(seat) != amount:
                if not self.send("stack", seat=seat, amount=amount):
                    return False
                self._last_stacks[seat] = amount

        for seat, amount in sorted(bets.items()):
            if force or self._last_bets.get(seat) != amount:
                if not self.send("bet", seat=seat, amount=amount):
                    return False
                self._last_bets[seat] = amount

        if force or self._last_visual_pot != visual_pot:
            if not self.send("pot", amount=visual_pot):
                return False
            self._last_visual_pot = visual_pot

        return True

    def _full_sync(self, snapshot):
        # Clear previous hand visuals first.
        if not self.send("new_hand"):
            return False

        self._last_holes = {}
        self._last_stacks = {}
        self._last_bets = {}
        self._last_visual_pot = None

        for player in snapshot.get("players", []):
            seat = int(player.get("seat", -1))
            hole = tuple(player.get("hole") or [])
            if seat >= 0 and len(hole) == 2:
                if self.send("hole_cards", seat=seat, cards=list(hole)):
                    self._last_holes[seat] = hole
                else:
                    return False

        board = tuple(snapshot.get("board") or [])
        if board:
            if not self.send("board", cards=list(board)):
                return False
        self._last_board = board

        if not self._sync_chips(snapshot, force=True):
            return False

        self._last_hand_no = snapshot.get("hand_no")
        self._needs_full_sync = False
        return True

    def on_snapshot(self, env, snapshot, agents=None):
        """Callback compatible with PokerEnv.play_hand(callback=...)."""
        if snapshot is None:
            return

        hand_no = snapshot.get("hand_no")
        if self._needs_full_sync or self._last_hand_no != hand_no:
            self._full_sync(snapshot)
            return

        for player in snapshot.get("players", []):
            seat = int(player.get("seat", -1))
            hole = tuple(player.get("hole") or [])
            if seat >= 0 and len(hole) == 2 and self._last_holes.get(seat) != hole:
                if self.send("hole_cards", seat=seat, cards=list(hole)):
                    self._last_holes[seat] = hole

        board = tuple(snapshot.get("board") or [])
        if board != self._last_board:
            if self.send("board", cards=list(board)):
                self._last_board = board

        self._sync_chips(snapshot, force=False)

    def close(self):
        self._disconnect()
