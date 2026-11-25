"""Run FlyPoker regression tests (no Unity Editor required)."""
import subprocess
import sys
from pathlib import Path

TESTS = [
    "tests_smoke.py", "tests_actions.py", "tests_hierarchical.py",
    "tests_table_session.py", "tests_modes.py", "tests_winner_labels.py",
    "tests_win_history.py", "test_unity_bridge.py",
    "tests_v39_features.py", "tests_session_cap.py",
    "tests_v42_training.py", "tests_v43_training.py", "tests_unity_api.py",
]


def main() -> int:
    root = Path(__file__).resolve().parent
    for name in TESTS:
        print("\n" + "=" * 66 + "\n" + name, flush=True)
        result = subprocess.run([sys.executable, str(root / name)], cwd=root)
        if result.returncode:
            print(f"FAILED: {name} (exit code {result.returncode})", flush=True)
            return result.returncode
    print("\nALL FLYPOKER REGRESSION TESTS: OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
