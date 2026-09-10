import numpy as np


class Solver:
    def __init__(self, dim, MAX_EVALS, dtype=np.float64):
        self.dim = int(dim)
        self.MAX_EVALS = int(MAX_EVALS)
        self.dtype = np.dtype(dtype)
        self.lower = np.zeros(self.dim, dtype=self.dtype)
        self.upper = np.ones(self.dim, dtype=self.dtype)
        self.rng = np.random.default_rng()

    def ask(self) -> np.ndarray:
        raise NotImplementedError

    def tell(self, x: np.ndarray, fitness: np.ndarray, sentinel=-1e3):
        """Shared input handling recommended for solver subclasses."""
        return x, np.maximum(sentinel, fitness)
