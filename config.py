from dataclasses import dataclass

@dataclass
class Config:
    players: int = 4
    starting_stack: int = 1000
    small_blind: int = 5
    big_blind: int = 10

    # A TABLE SESSION now keeps stacks between hands and only resets when
    # one seat owns all chips and the other three are eliminated.
    table_session_mode: bool = True

    # Safety guard only; normal no-limit betting is stack-limited.
    max_actions_per_street: int = 600

    # Small extra evolutionary penalty for being eliminated from a table.
    # The lost chips already hurt raw BB/100; this is intentionally small.
    bust_penalty_bb: float = 5.0

    # Evolution.
    # hands_per_generation is now a MINIMUM hand target. If that target is
    # reached in the middle of a table session, the session is completed
    # before the generation ends.
    population: int = 4
    hands_per_generation: int = 1500
    generations: int = 200
    mutation_strengths: tuple = (0.02, 0.05, 0.10)
    mutation_probability: float = 0.12

    hidden_1: int = 64
    hidden_2: int = 32

    seed: int = 1337
