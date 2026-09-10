from math import atan, floor, log, pi, sqrt, tan
import numpy as np
from numba import njit

from Solver.Solver import Solver as _Solver
from Solver._random import _randint, _random, _random53, _random_open, _seed_rng


MEMORY_SIZE = 5
P_BEST_RATE = 0.11
ARC_RATE = 1.4



def _cxx_round(value):
    return int(floor(value + 0.5))


@njit(cache=True, nogil=True, error_model="numpy", boundscheck=False, fastmath={"contract"})
def _generate_children(population, fitness, n, archive, arc_n, memory_sf, memory_cr, p_num,
                       seed, children, pop_sf, pop_cr, sf_cdf0, rng_state):
    _seed_rng(rng_state, seed)
    dim = population.shape[1]
    total = n + arc_n
    pbest_indices = np.argpartition(fitness[:n], n - p_num)[n - p_num:]
    for i in range(MEMORY_SIZE):
        sf_cdf0[i] = 0.5 - atan(memory_sf[i] * 10.0) / pi
    has_normal = 0
    spare_normal = 0.0
    for target in range(n):
        period = _randint(rng_state, MEMORY_SIZE)
        mu_sf = memory_sf[period]
        mu_cr = memory_cr[period]
        if mu_cr < 0.0:
            cr = 0.0
        else:
            if has_normal:
                normal = spare_normal
                has_normal = 0
            else:
                radius_sq = 2.0
                while radius_sq >= 1.0 or radius_sq == 0.0:
                    u = 2.0 * _random(rng_state) - 1.0
                    v = 2.0 * _random(rng_state) - 1.0
                    radius_sq = u * u + v * v
                scale = sqrt(-2.0 * log(radius_sq) / radius_sq)
                normal = u * scale
                spare_normal = v * scale
                has_normal = 1
            cr = mu_cr + 0.1 * normal
            if cr > 1.0:
                cr = 1.0
            elif cr < 0.0:
                cr = 0.0

        cdf0 = sf_cdf0[period]
        sf = mu_sf + 0.1 * tan(pi * (cdf0 + (1.0 - cdf0) * _random_open(rng_state) - 0.5))
        if sf > 1.0:
            sf = 1.0

        pbest = pbest_indices[_randint(rng_state, pbest_indices.size)]
        r1 = _randint(rng_state, n - 1)
        r1 += r1 >= target
        lo = min(target, r1)
        hi = max(target, r1)
        r2 = _randint(rng_state, total - 2)
        r2 += r2 >= lo
        r2 += r2 >= hi
        forced = _randint(rng_state, dim)
        cr_threshold = np.uint64(cr * 9007199254740992.0)

        for j in range(dim):
            parent = population[target, j]
            if j == forced or _random53(rng_state) < cr_threshold:
                xr2 = archive[r2 - n, j] if r2 >= n else population[r2, j]
                value = parent + sf * (population[pbest, j] - parent) + sf * (population[r1, j] - xr2)
                if value < 0.0:
                    value = 0.5 * parent
                elif value > 1.0:
                    value = 0.5 * (1.0 + parent)
            else:
                value = parent
            children[target, j] = value
        pop_sf[target] = sf
        pop_cr[target] = cr


@njit(cache=True, nogil=True, error_model="numpy", boundscheck=False, fastmath={"contract"})
def _select_and_adapt(population, fitness, children, child_fitness, n, archive, arc_size,
                      arc_n, pop_sf, pop_cr, memory_sf, memory_cr, memory_pos, seed, rng_state):
    _seed_rng(rng_state, seed)
    sf_num = sf_den = cr_num = cr_den = 0.0
    dim = population.shape[1]
    for i in range(n):
        child_fit = child_fitness[i]
        parent_fit = fitness[i]
        if child_fit >= parent_fit:
            if child_fit > parent_fit:
                if arc_size > 1:
                    if arc_n < arc_size:
                        archive_index = arc_n
                        arc_n += 1
                    else:
                        archive_index = _randint(rng_state, arc_size)
                    for j in range(dim):
                        archive[archive_index, j] = population[i, j]
                diff = child_fit - parent_fit
                sf = pop_sf[i]
                cr = pop_cr[i]
                sf_num += diff * sf * sf
                sf_den += diff * sf
                cr_num += diff * cr * cr
                cr_den += diff * cr
            for j in range(dim):
                population[i, j] = children[i, j]
            fitness[i] = child_fit

    if sf_den > 0.0:
        memory_sf[memory_pos] = sf_num / sf_den
        memory_cr[memory_pos] = cr_num / cr_den if cr_den > 0.0 else -1.0
        memory_pos = (memory_pos + 1) % MEMORY_SIZE
    return arc_n, memory_pos


@njit(cache=True, nogil=True, error_model="numpy", boundscheck=False, fastmath={"contract"})
def _reduce_population(population, fitness, n, target, keep):
    for i in range(n):
        keep[i] = 1.0
    remove = n - target
    if remove > 4:
        worst = np.argpartition(fitness[:n], remove)[:remove]
        for i in range(remove):
            keep[worst[i]] = 0.0
    else:
        for _ in range(remove):
            worst = -1
            worst_fit = 0.0
            for i in range(n):
                if keep[i] != 0.0 and (worst < 0 or fitness[i] < worst_fit):
                    worst = i
                    worst_fit = fitness[i]
            keep[worst] = 0.0

    dst = 0
    dim = population.shape[1]
    for src in range(n):
        if keep[src] != 0.0:
            if dst != src:
                fitness[dst] = fitness[src]
                for j in range(dim):
                    population[dst, j] = population[src, j]
            dst += 1
    return dst



class LSHADE(_Solver):
    def __init__(self, dim, MAX_EVALS):
        super().__init__(dim, MAX_EVALS)
        self.max_pop_size = _cxx_round(self.dim * 18.0)
        self.population_size = self.max_pop_size
        self.min_pop_size = 4
        shape = (self.max_pop_size, self.dim)
        self.population = np.empty(shape, dtype=self.dtype)
        self.rng.random(shape, dtype=self.dtype, out=self.population)
        self.fitness = np.empty(self.max_pop_size, dtype=self.dtype)
        self.arc_size = max(1, _cxx_round(self.max_pop_size * ARC_RATE))
        self.archive = np.empty((self.arc_size, self.dim), dtype=self.dtype)
        self.arc_ind_count = 0
        self.memory_sf = np.full(MEMORY_SIZE, 0.5, dtype=self.dtype)
        self.memory_cr = np.full(MEMORY_SIZE, 0.5, dtype=self.dtype)
        self.memory_pos = self.eval_count = 0
        self.initial = True
        self._children = np.empty(shape, dtype=self.dtype)
        self._pop_sf = np.empty(self.max_pop_size, dtype=self.dtype)
        self._pop_cr = np.empty(self.max_pop_size, dtype=self.dtype)
        self._sf_cdf0 = np.empty(MEMORY_SIZE, dtype=self.dtype)
        self._rng_state = np.empty(4, dtype=np.uint64)

    def ask(self):
        n = self.population_size
        if self.initial:
            return self.population[:n]
        p_num = max(2, _cxx_round(n * P_BEST_RATE))
        _generate_children(
            self.population, self.fitness, n, self.archive, self.arc_ind_count, self.memory_sf, self.memory_cr,
            p_num, self.rng.bit_generator.random_raw() >> 1, self._children, self._pop_sf, self._pop_cr, self._sf_cdf0, self._rng_state,
        )
        return self._children[:n]

    def tell(self, x, fitness):
        x, fitness = super().tell(x, fitness)
        n = self.population_size
        if self.initial:
            self.population[:n] = x
            self.fitness[:n] = fitness
            self.eval_count = n
            self.initial = False
            return

        self.arc_ind_count, self.memory_pos = _select_and_adapt(
            self.population, self.fitness, x, fitness, n, self.archive, self.arc_size,
            self.arc_ind_count, self._pop_sf, self._pop_cr, self.memory_sf, self.memory_cr,
            self.memory_pos, self.rng.bit_generator.random_raw() >> 1, self._rng_state,
        )
        self.eval_count += n
        target = max(self.min_pop_size, _cxx_round(
            (self.min_pop_size - self.max_pop_size) * self.eval_count / self.MAX_EVALS + self.max_pop_size
        ))
        if n > target:
            self.population_size = _reduce_population(self.population, self.fitness, n, target, self._pop_cr)
            self.arc_size = int(self.population_size * ARC_RATE)
            if self.arc_ind_count > self.arc_size:
                self.arc_ind_count = self.arc_size
