from dataclasses import dataclass

@dataclass
class Config:
    players: int = 4
    starting_stack: int = 1000
    small_blind: int = 5
    big_blind: int = 10
    # Safety guard only; normal no-limit betting is stack-limited.
    max_actions_per_street: int = 600

    # Fitness shaping: only a REAL bust (finishing the hand with stack == 0)
    # is penalized. Choosing ALL-IN by itself is never penalized.
    bust_penalty_bb: float = 5.0

    # Ewolucja
    population: int = 4
    hands_per_generation: int = 1500
    generations: int = 200
    mutation_strengths: tuple = (0.02, 0.05, 0.10)
    mutation_probability: float = 0.12

    # Sieć zastępcza. Później można ją podmienić na właściwy brain muchy.
    hidden_1: int = 64
    hidden_2: int = 32

    seed: int = 1337
