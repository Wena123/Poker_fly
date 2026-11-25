"""Independent V43 champion store; never mutates historical V41/V42 folders."""
import json
import os
import shutil
from pathlib import Path
from .simple_brain import SimpleFlyBrain


class VerifiedChampion:
    def __init__(self, checkpoint_dir="checkpoints"):
        self.folder = Path(checkpoint_dir) / "hall_of_fame" / "verified_v43"
        self.checkpoint = self.folder / "champion.npz"
        self.metadata = self.folder / "champion.json"
        self.folder.mkdir(parents=True, exist_ok=True)

    def exists(self):
        return self.checkpoint.is_file()

    def load(self, observation_size=None):
        brain = SimpleFlyBrain.load(self.checkpoint)
        if observation_size is not None and brain.input_size != observation_size:
            brain = brain.resize_input(observation_size)
        return brain

    def save(self, brain, *, generation, source, gate=None):
        # Atomic update of checkpoint and metadata. Existing V42 data unchanged.
        tmp = self.checkpoint.with_name(".champion_pending.npz")
        brain.save(tmp)
        os.replace(tmp, self.checkpoint)
        doc = {"generation": int(generation), "source": str(source),
               "gate": gate, "checkpoint": str(self.checkpoint),
               "observation_size": int(brain.input_size)}
        tmp_meta = self.metadata.with_suffix(".json.tmp")
        tmp_meta.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp_meta, self.metadata)

    def describe(self):
        if not self.exists():
            return None
        return json.loads(self.metadata.read_text(encoding="utf-8")) if self.metadata.exists() else {"checkpoint": str(self.checkpoint)}
