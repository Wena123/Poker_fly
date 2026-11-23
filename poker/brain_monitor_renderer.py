"""OpenCV-only live anatomical brain monitor. Does NOT import pygame."""

from .anatomical_monitor import PokerAnatomicalMonitor


class BrainMonitorRenderer:
    def __init__(self, width=1600, height=940, update_hz=10.):
        self.monitor = PokerAnatomicalMonitor(
            title="FlyPoker | Brain monitor (no pygame)",
            width=width, height=height, update_hz=update_hz,
        )
        self.closed = False
        self.fitness = [0.] * 4
        self.generation = 0
        self.hand_index = 0
        self.mode_text = "BRAIN MONITOR"

    def set_meta(self, generation, hand, fitness, **kwargs):
        self.generation = int(generation)
        self.hand_index = int(hand)
        self.fitness = list(fitness)

    def set_mode_text(self, text):
        self.mode_text = str(text)

    def render(self, env, snap, agents):
        if self.closed:
            return
        obs = [env.observation(i) for i in range(4)]
        self.monitor.update(agents, obs, self.fitness, self.generation,
                            self.hand_index, snapshot=snap)
        self.closed = bool(getattr(self.monitor, "user_closed", False))

    def pump_waiting(self):
        if not self.closed:
            self.monitor.pump_events()
            self.closed = bool(getattr(self.monitor, "user_closed", False))

    def close(self):
        self.monitor.close()
        self.closed = True
