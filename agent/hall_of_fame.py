"""Persistent leaderboard of generation champions.

Ranking is based on measured training fitness; it is NOT an out-of-sample
benchmark. The original per-generation checkpoints are never modified.
"""
import json
import shutil
from pathlib import Path


class HallOfFame:
    def __init__(self, checkpoint_dir="checkpoints", reward_mode="balanced", top_k=5):
        self.path = Path(checkpoint_dir) / "hall_of_fame" / reward_mode
        self.path.mkdir(parents=True, exist_ok=True)
        self.json_path = self.path / "leaderboard.json"
        self.best_path = self.path / "best_ever.npz"
        self.top_k = max(1, int(top_k))
        self.mode = reward_mode
        if self.json_path.exists():
            data = json.loads(self.json_path.read_text(encoding="utf-8"))
            self.entries = data.get("entries", [])
        else:
            self.entries = []

    def consider(self, generation, fly, fitness, checkpoint_path, metrics=None):
        name = f"gen_{int(generation):04d}_fly_{int(fly)}.npz"
        item = {
            "generation": int(generation),
            "fly": int(fly),
            "fitness": float(fitness),
            "file": name,
            "metrics": metrics or {},
        }
        # Never prune the per-generation files saved by the Trainer.
        ranked = [x for x in self.entries if x.get("file") != name] + [item]
        ranked.sort(key=lambda x: (-float(x["fitness"]), int(x["generation"]), int(x["fly"])))
        top = ranked[:self.top_k]
        if any(x["file"] == name for x in top):
            shutil.copy2(checkpoint_path, self.path / name)
        self.entries = top
        if self.entries:
            winner = self.path / self.entries[0]["file"]
            if winner.exists():
                shutil.copy2(winner, self.best_path)
        # Update metadata before deleting stale top-5 files.
        tmp = self.json_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"reward_mode": self.mode, "top_k": self.top_k,
                                   "entries": self.entries}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(self.json_path)
        keep = {x["file"] for x in self.entries}
        for path in self.path.glob("gen_*_fly_*.npz"):
            if path.name not in keep:
                path.unlink()
        return bool(self.entries and self.entries[0]["file"] == name)

    def print_ranking(self):
        if not self.entries:
            print(f"Hall of Fame is empty: {self.json_path}")
            return
        print(f"HALL OF FAME ({self.mode}) — best observed generation champions")
        for rank, x in enumerate(self.entries, 1):
            print(f"{rank}. GEN {x['generation']:04d} FLY {x['fly']} | "
                  f"fitness {x['fitness']:+.3f} | {self.path / x['file']}")
