from pathlib import Path
import os
import re


_GEN_RE = re.compile(r"best_brain_gen_(\d+)\.npz$", re.IGNORECASE)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHECKPOINT_DIR = PROJECT_ROOT / "checkpoints"


def checkpoint_generation(path):
    m = _GEN_RE.search(Path(path).name)
    return int(m.group(1)) if m else 0


def default_checkpoint_dir():
    DEFAULT_CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_CHECKPOINT_DIR


def latest_checkpoint(directory=None):
    directory = default_checkpoint_dir() if directory is None else Path(directory).expanduser().resolve()
    candidates = []
    for p in directory.glob("best_brain_gen_*.npz"):
        gen = checkpoint_generation(p)
        candidates.append((gen, p))
    if not candidates:
        raise FileNotFoundError(f"No checkpoints found in: {directory.resolve()}")
    candidates.sort(key=lambda x: (x[0], x[1].name))
    return candidates[-1][1].resolve()


def save_checkpoint_atomic(brain, path):
    """Save a champion atomically and verify the file really exists."""
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp.npz')
    try:
        if tmp.exists():
            tmp.unlink()
        brain.save(tmp)
        if not tmp.exists() or tmp.stat().st_size <= 0:
            raise IOError(f"Checkpoint temporary file was not created: {tmp}")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()

    if not path.exists() or path.stat().st_size <= 0:
        raise IOError(f"Checkpoint save verification failed: {path}")

    latest_txt = path.parent / 'LATEST.txt'
    latest_txt.write_text(path.name + '\n', encoding='utf-8')
    return path
