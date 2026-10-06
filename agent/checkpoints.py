from pathlib import Path
import re


_GEN_RE = re.compile(r"best_brain_gen_(\d+)\.npz$", re.IGNORECASE)


def checkpoint_generation(path):
    m = _GEN_RE.search(Path(path).name)
    return int(m.group(1)) if m else 0


def latest_checkpoint(directory="checkpoints"):
    directory = Path(directory)
    candidates = []
    for p in directory.glob("best_brain_gen_*.npz"):
        gen = checkpoint_generation(p)
        candidates.append((gen, p))
    if not candidates:
        raise FileNotFoundError(f"No checkpoints found in: {directory.resolve()}")
    candidates.sort(key=lambda x: (x[0], x[1].name))
    return candidates[-1][1]
