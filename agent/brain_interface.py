from abc import ABC, abstractmethod

class BrainInterface(ABC):
    @abstractmethod
    def act(self, observation, legal_actions):
        """Zwróć numer akcji z legal_actions."""
        raise NotImplementedError

    @abstractmethod
    def copy(self):
        raise NotImplementedError

    @abstractmethod
    def mutate(self, strength: float, probability: float, rng):
        raise NotImplementedError

    @abstractmethod
    def save(self, path):
        raise NotImplementedError
