from math import exp, floor, lgamma, log, sqrt
import numpy as np
from numba import njit

from Solver.Solver import Solver as _Solver


def default_population_size(dim):
    return 4 + int(floor(3 * log(dim)))


def _strategy(dim, popsize, dtype):
    weights = np.log((popsize + 1) / 2.0) - np.log(np.arange(1, popsize + 1, dtype=dtype))
    mu = popsize // 2
    weights[:mu] /= weights[:mu].sum()
    negative = weights[mu:]
    negative /= -negative.sum()
    positive = weights[:mu]
    mueff = float(positive.sum() ** 2 / np.square(positive).sum())
    mueffminus = float(negative.sum() ** 2 / np.square(negative).sum())
    cc = (4 + mueff / dim) / (dim + 4 + 2 * mueff / dim)
    cs = (mueff + 2) / (dim + mueff + 3)
    c1 = 2 * min(1.0, popsize / 6.0) / ((dim + 1.3) ** 2 + mueff)
    cmu = min(1 - c1, 2 * (mueff - 1.75 + 1 / mueff) / ((dim + 2) ** 2 + mueff))
    negative *= -(1 + c1 / cmu) / negative.sum()
    for limit in ((1 - c1 - cmu) / cmu / dim, 1 + 2 * mueffminus / (mueff + 2)):
        if negative.sum() < -limit:
            negative *= -limit / negative.sum()
    lam_mirr = int(0.5 + 0.16 * min(popsize, 2 * dim + 2) + 0.29) if popsize < 6 else 0
    mirror = min(1.0, (lam_mirr / (0.159 * popsize) - 1.0) ** 2) / 2.0
    damps = 0.5 + mirror + 2 * max(0.0, sqrt((mueff - 1) / (dim + 1)) - 1.0) + cs
    return (weights, positive, mu, 1 - cs, sqrt(cs * (2 - cs) * mueff), 1 - cc,
            sqrt(cc * (2 - cc) * mueff), cc * (2 - cc), c1, cmu, float(weights.sum()), cs / damps)


@njit(cache=True, nogil=True, error_model="numpy", boundscheck=False)
def _finish_candidates(x, z, mean, sigma, sent, returned, z_norm_sq):
    rows, dim = x.shape
    for row in range(rows):
        norm_sq = 0.0
        for j in range(dim):
            zv = z[row, j]
            norm_sq += zv * zv
            value = mean[j] + sigma * x[row, j]
            x[row, j] = value
            if value < -0.6 or value > 1.6:
                value -= 2.2 * floor((value + 0.6) / 2.2)
            if value > 1.05:
                value -= 2.0 * (value - 1.05)
            elif value < -0.05:
                value += 2.0 * (-0.05 - value)
            if value < 0.05:
                value = (value + 0.05) ** 2 / 0.2
            elif value > 0.95:
                value = 1.0 - (value - 1.05) ** 2 / 0.2
            sent[row, j] = value
            returned[row, j] = value
        z_norm_sq[row] = norm_sq


@njit(cache=True, nogil=True, error_model="numpy", boundscheck=False, fastmath={"contract"})
def _tell_update(x, fitness, sent_pheno, sent_geno, sent_norm_sq, mean, B, D, radius,
                 recovered, recovered_norm_sq, used, ranks, ps, pc, C,
                 sigma, generation, strategy, chiN, hsig_limit, y_sorted, work):
    n, dim = x.shape
    direct = True
    for row in range(n):
        for j in range(dim):
            if x[row, j] != sent_pheno[row, j]:
                direct = False
                break
        if not direct:
            break

    if direct:
        x_geno = sent_geno
        mahal_sq = sent_norm_sq
    else:
        for i in range(n):
            used[i] = 0
        sigma_sq = sigma * sigma
        for row in range(n):
            found = -1
            for candidate in range(n):
                if used[candidate] != 0:
                    continue
                same = True
                for j in range(dim):
                    if x[row, j] != sent_pheno[candidate, j]:
                        same = False
                        break
                if same:
                    found = candidate
                    break
            if found >= 0:
                used[found] = 1
                recovered_norm_sq[row] = sent_norm_sq[found]
                for j in range(dim):
                    recovered[row, j] = sent_geno[found, j]
                continue

            for j in range(dim):
                value = x[row, j]
                if value < 0.05:
                    value = -0.05 + 2.0 * sqrt(max(0.05 * value, 0.0))
                elif value >= 0.95:
                    value = 1.05 - 2.0 * sqrt(max(0.05 * (1.0 - value), 0.0))
                recovered[row, j] = value

            norm_sq = 0.0
            for i in range(dim):
                projected = 0.0
                for j in range(dim):
                    projected += B[j, i] * (recovered[row, j] - mean[j])
                projected /= D[i]
                norm_sq += projected * projected
            fac = sqrt(norm_sq) / radius
            if fac > 1.0:
                for j in range(dim):
                    recovered[row, j] = mean[j] + (recovered[row, j] - mean[j]) / fac
                norm_sq = radius * radius
            recovered_norm_sq[row] = norm_sq / sigma_sq
        x_geno = recovered
        mahal_sq = recovered_norm_sq

    for i in range(n):
        ranks[i] = i
    for i in range(1, n):
        index = ranks[i]
        value = fitness[index]
        j = i - 1
        while j >= 0 and fitness[ranks[j]] < value:
            ranks[j + 1] = ranks[j]
            j -= 1
        ranks[j + 1] = index

    weights_all, weights, mu, ps_decay, ps_gain, pc_decay, pc_gain, cc2, c1, cmu, weight_sum, sigma_gain = strategy
    old_mean, shift, tmp = work
    for j in range(dim):
        old_mean[j] = mean[j]
        value = 0.0
        for k in range(mu):
            value += weights[k] * x_geno[ranks[k], j]
        mean[j] = value
        shift[j] = value - old_mean[j]

    for i in range(dim):
        value = 0.0
        for j in range(dim):
            value += B[j, i] * shift[j]
        tmp[i] = value / D[i]

    ps_norm_sq = 0.0
    for i in range(dim):
        value = 0.0
        for j in range(dim):
            value += B[i, j] * tmp[j]
        ps[i] = ps_decay * ps[i] + ps_gain * value / sigma
        ps_norm_sq += ps[i] * ps[i]

    hsig_left = ps_norm_sq / (1.0 - ps_decay ** (2 * (generation + 1))) / dim - 1.0
    hsig = 1.0 if hsig_left < hsig_limit else 0.0
    for i in range(dim):
        pc[i] = pc_decay * pc[i] + hsig * pc_gain * shift[i] / sigma

    for k in range(n):
        index = ranks[k]
        for j in range(dim):
            y_sorted[k, j] = (x_geno[index, j] - old_mean[j]) / sigma

    c1a = c1 * (1.0 - (1.0 - hsig * hsig) * cc2)
    cov_scale = 1.0 - c1a - cmu * weight_sum
    for i in range(dim):
        for j in range(i + 1):
            C[i, j] = cov_scale * C[i, j] + c1 * pc[i] * pc[j]

    for k in range(n):
        wk = weights_all[k]
        if wk < 0.0:
            mah = sqrt(mahal_sq[ranks[k]])
            wk *= dim / ((mah + 1e-9) * (mah + 1e-9))
        scale = cmu * wk
        for i in range(dim):
            yi = y_sorted[k, i]
            for j in range(i + 1):
                C[i, j] += scale * yi * y_sorted[k, j]

    for i in range(dim):
        for j in range(i):
            C[j, i] = C[i, j]

    sigma_step = sigma_gain * (sqrt(ps_norm_sq) / chiN - 1.0)
    if sigma_step > 1.0:
        sigma_step = 1.0
    elif sigma_step < -1.0:
        sigma_step = -1.0
    return sigma * exp(sigma_step)


class CMAES(_Solver):
    def __init__(self, dim, MAX_EVALS, sigma0=0.3, batch_size=None, dtype=np.float64):
        super().__init__(dim, MAX_EVALS, dtype=dtype)
        self.batch_size = int(batch_size or default_population_size(self.dim))
        self.mean = (self.lower + self.upper) * 0.5
        self.sigma = float(sigma0 * np.mean(self.upper - self.lower))
        self.strategy = _strategy(self.dim, self.batch_size, self.dtype)
        self.pc = np.zeros(self.dim, dtype=self.dtype)
        self.ps = np.zeros(self.dim, dtype=self.dtype)
        self.B = np.eye(self.dim, dtype=self.dtype)
        self.D = np.ones(self.dim, dtype=self.dtype)
        self.BD = self.B.copy()
        self.C = self.B.copy()
        self.lazy_update_gap = 1.0 / (self.strategy[8] + self.strategy[9] + 1e-23) / self.dim / 10.0
        self.generation = self.last_update = 0
        self.chiN = sqrt(2.0) * exp(lgamma((self.dim + 1.0) * 0.5) - lgamma(self.dim * 0.5))
        self._hsig_limit = 1.0 + 4.0 / (self.dim + 1.0)
        self._repair_radius = sqrt(self.dim) + 2.0 * self.dim / (self.dim + 2.0)
        shape = (self.batch_size, self.dim)
        self._z = np.empty(shape, dtype=self.dtype)
        self._ask_x_geno = np.empty(shape, dtype=self.dtype)
        self._ask_x_pheno = np.empty(shape, dtype=self.dtype)
        self._return_x = np.empty(shape, dtype=self.dtype)
        self._tell_x_geno = np.empty(shape, dtype=self.dtype)
        self._y_sorted = np.empty(shape, dtype=self.dtype)
        self._z_norm_sq = np.empty(self.batch_size, dtype=self.dtype)
        self._tell_norm_sq = np.empty(self.batch_size, dtype=self.dtype)
        self._ranks = np.empty(self.batch_size, dtype=np.int64)
        self._used = np.empty(self.batch_size, dtype=np.uint8)
        self._work = np.empty((3, self.dim), dtype=self.dtype)

    def _update_bd_if_needed(self):
        if self.generation < self.last_update + self.lazy_update_gap:
            return
        eigvals, eigvecs = np.linalg.eigh(self.C)
        if eigvals[0] <= 0.0:
            diag_add = -float(eigvals[0]) + max(float(np.min(self.D) ** 2), 1e-30)
            self.C.flat[:: self.dim + 1] += diag_add
            eigvals += diag_add
        np.sqrt(eigvals, out=self.D)
        self.B = eigvecs
        np.multiply(self.B, self.D, out=self.BD)
        self.last_update = self.generation

    def ask(self):
        self._update_bd_if_needed()
        self.rng.standard_normal(out=self._z, dtype=self.dtype)
        np.matmul(self._z, self.BD.T, out=self._ask_x_geno)
        _finish_candidates(self._ask_x_geno, self._z, self.mean, self.sigma, self._ask_x_pheno,
                           self._return_x, self._z_norm_sq)
        return self._return_x

    def tell(self, x, fitness):
        # CMA-ES intentionally bypasses the base fitness clamp.
        self.sigma = _tell_update(
            x, fitness, self._ask_x_pheno, self._ask_x_geno, self._z_norm_sq, self.mean, self.B, self.D,
            self._repair_radius, self._tell_x_geno,
            self._tell_norm_sq, self._used, self._ranks, self.ps, self.pc, self.C, self.sigma,
            self.generation, self.strategy, self.chiN, self._hsig_limit, self._y_sorted, self._work,
        )
        self.generation += 1
