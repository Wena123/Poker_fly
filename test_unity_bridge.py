"""Small local protocol test; does not require Unity."""
import json
import socket
import threading

from unity_bridge import UnityBridge


def main():
    host = "127.0.0.1"
    server = socket.socket()
    server.bind((host, 0))
    server.listen(1)
    port = server.getsockname()[1]
    seen = []

    def fake_unity():
        conn, _ = server.accept()
        reader = conn.makefile("r", encoding="utf-8")
        line = reader.readline()
        msg = json.loads(line)
        seen.append(msg)
        conn.sendall(
            (json.dumps({"type": "animation_done", "seat": msg["seat"]}) + "\n").encode("utf-8")
        )
        conn.close()
        server.close()

    thread = threading.Thread(target=fake_unity, daemon=True)
    thread.start()

    bridge = UnityBridge(host, port, timeout=5, verbose=False)
    bridge.connect()
    bridge.animate_and_wait(2, "ALL-IN", 777)
    bridge.close()
    thread.join(2)

    assert seen[0]["type"] == "animation"
    assert seen[0]["seat"] == 2
    assert seen[0]["action"] == "RAISE"
    assert seen[0]["amount"] == 777
    print("UNITY BRIDGE HANDSHAKE TEST: OK")


if __name__ == "__main__":
    main()
