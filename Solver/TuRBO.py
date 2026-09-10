import numpy as np
import torch
from numba import njit
from gpytorch.constraints import Interval
from gpytorch.distributions import MultivariateNormal
from gpytorch.kernels import MaternKernel, ScaleKernel
from gpytorch.likelihoods import GaussianLikelihood
from gpytorch.means import ConstantMean
from gpytorch.mlls import ExactMarginalLogLikelihood
from gpytorch.models import ExactGP
from torch.quasirandom import SobolEngine

from Solver.Solver import Solver as _Solver
from Solver._random import _randint, _random, _random53, _seed_rng


DEFAULT_TR_COUNT = 5
DEFAULT_BATCH_SIZE = 64
L_INIT = 0.8
L_MIN = 0.5**7
L_MAX = 1.6
TAU_SUCC = 3
NOISE_CONSTRAINT = Interval(5e-4, 0.2)
LENGTHSCALE_CONSTRAINT = Interval(0.005, 2.0)
OUTPUTSCALE_CONSTRAINT = Interval(0.05, 20.0)
N_TRAINING_STEPS = 50
DTYPE = torch.float64
DEVICE = torch.device("cpu")


@njit(cache=True, nogil=True, error_model="numpy", boundscheck=False, fastmath={"contract"})
def _lhs(out, perm, lower, upper, seed, rng_state):
    _seed_rng(rng_state, seed)
    n, dim = out.shape
    for j in range(dim):
        for i in range(n):
            perm[i] = i
        for i in range(n - 1, 0, -1):
            k = _randint(rng_state, i + 1)
            perm[i], perm[k] = perm[k], perm[i]
        scale = (upper[j] - lower[j]) / n
        for i in range(n):
            out[i, j] = lower[j] + (perm[i] + _random(rng_state)) * scale


@njit(cache=True, nogil=True, error_model="numpy", boundscheck=False, fastmath={"contract"})
def _tr_bounds(lengthscale, best_x, length, lower, upper, low, span):
    dim = best_x.size
    log_sum = 0.0
    for j in range(dim):
        log_sum += np.log(lengthscale[j])
    geometric_mean = np.exp(log_sum / dim)
    for j in range(dim):
        half = lengthscale[j] / geometric_mean * length * 0.5
        lo = best_x[j] - half
        hi = best_x[j] + half
        lo = lower[j] if lo < lower[j] else lo
        hi = upper[j] if hi > upper[j] else hi
        low[j] = lo
        span[j] = hi - lo


@njit(cache=True, nogil=True, error_model="numpy", boundscheck=False, fastmath={"contract"})
def _fill_candidates(best_x, sobol, low, span, probability, seed, out, rng_state):
    _seed_rng(rng_state, seed)
    rows, dim = out.shape
    threshold = np.uint64(probability * 9007199254740992.0)
    for i in range(rows):
        changed = 0
        for j in range(dim):
            if _random53(rng_state) <= threshold:
                out[i, j] = low[j] + sobol[i, j] * span[j]
                changed += 1
            else:
                out[i, j] = best_x[j]
        if changed == 0:
            j = _randint(rng_state, dim)
            out[i, j] = low[j] + sobol[i, j] * span[j]


@njit(cache=True, nogil=True, error_model="numpy", boundscheck=False, fastmath={"contract"})
def _select_candidates(samples, candidates, candidate_count, medians, stds, selected, selected_tr):
    batch_size, total = samples.shape
    dim = candidates.shape[1]
    tr_count = total // candidate_count
    for k in range(batch_size):
        best = 0
        best_tr = 0
        best_value = medians[0] + stds[0] * samples[k, 0]
        for tr in range(tr_count):
            start = tr * candidate_count
            stop = start + candidate_count
            median = medians[tr]
            std = stds[tr]
            if tr == 0:
                start = 1
            for i in range(start, stop):
                value = median + std * samples[k, i]
                if value > best_value:
                    best = i
                    best_tr = tr
                    best_value = value
        for j in range(dim):
            selected[k, j] = candidates[best, j]
        selected_tr[k] = best_tr
        for sample in range(batch_size):
            samples[sample, best] = -np.inf


@njit(cache=True, nogil=True, error_model="numpy", boundscheck=False, fastmath={"contract"})
def _group_indices(tr_index, grouped, counts):
    for i in range(counts.size):
        counts[i] = 0
    for i in range(tr_index.size):
        tr = tr_index[i]
        grouped[tr, counts[tr]] = i
        counts[tr] += 1


@njit(cache=True, nogil=True, error_model="numpy", boundscheck=False)
def _normalize(y, median, std, out):
    for i in range(y.size):
        out[i] = (y[i] - median) / std


@njit(cache=True, nogil=True, error_model="numpy", boundscheck=False, fastmath={"contract"})
def _update_tr(x, y, indices, count, x_store, y_store, n_data, best_x, best_y, succ, fail, length, tau_fail):
    best_index = indices[0]
    batch_best = y[best_index]
    for i in range(1, count):
        index = indices[i]
        if y[index] > batch_best:
            best_index = index
            batch_best = y[index]

    previous_best = best_y
    if batch_best > previous_best + 1e-3 * abs(previous_best):
        succ += 1
        fail = 0
    else:
        succ = 0
        fail += count
    if batch_best > best_y:
        best_y = batch_best
        for j in range(best_x.size):
            best_x[j] = x[best_index, j]
    if succ >= TAU_SUCC:
        length = min(length * 2.0, L_MAX)
        succ = 0
    if fail >= tau_fail:
        length *= 0.5
        fail = 0

    end = min(n_data + count, x_store.shape[0])
    for dst in range(n_data, end):
        src = indices[dst - n_data]
        y_store[dst] = y[src]
        for j in range(best_x.size):
            x_store[dst, j] = x[src, j]
    return end, best_y, succ, fail, length


class _GP(ExactGP):
    def __init__(self, train_x, train_y, likelihood):
        super().__init__(train_x, train_y, likelihood)
        self.mean_module = ConstantMean()
        self.covar_module = ScaleKernel(
            MaternKernel(nu=2.5, ard_num_dims=train_x.shape[1], lengthscale_constraint=LENGTHSCALE_CONSTRAINT),
            outputscale_constraint=OUTPUTSCALE_CONSTRAINT,
        )

    def forward(self, x):
        return MultivariateNormal(self.mean_module(x), self.covar_module(x))

    def fit_model(self, likelihood):
        self.train()
        likelihood.train()
        mll = ExactMarginalLogLikelihood(likelihood, self)
        optimizer = torch.optim.Adam(self.parameters(), lr=0.1)
        train_x = self.train_inputs[0]
        train_y = self.train_targets
        for _ in range(N_TRAINING_STEPS):
            optimizer.zero_grad(set_to_none=True)
            loss = -mll(self(train_x), train_y)
            loss.backward()
            optimizer.step()

    def sample_predictions(self, likelihood, x, n_samples):
        with torch.inference_mode():
            return likelihood(self(torch.as_tensor(x, device=DEVICE, dtype=DTYPE))).sample(
                torch.Size([n_samples])
            ).numpy()


class _TrustRegion:
    def __init__(self, x_init, y_init, lower, upper, MAX_EVALS, candidate_count):
        self.dim = x_init.shape[1]
        self.lower = lower
        self.upper = upper
        self.candidate_count = candidate_count
        self.tau_fail = max(5, self.dim)
        self.rng = np.random.default_rng()
        cap = max(int(MAX_EVALS), x_init.shape[0])
        self._x_store = np.empty((cap, self.dim), dtype=np.float64)
        self._y_store = np.empty(cap, dtype=np.float64)
        self._normalized_y = np.empty(cap, dtype=np.float64)
        self._x_tensor = torch.from_numpy(self._x_store)
        self._y_tensor = torch.from_numpy(self._normalized_y)
        self.best_x = np.empty(self.dim, dtype=np.float64)
        self._low = np.empty(self.dim, dtype=np.float64)
        self._span = np.empty(self.dim, dtype=np.float64)
        self.gp = None
        self.likelihood = None
        self._rng_state = np.empty(4, dtype=np.uint64)
        self.initialize(x_init, y_init)

    def initialize(self, x_init, y_init):
        x_init = np.asarray(x_init, dtype=np.float64)
        y_init = np.asarray(y_init, dtype=np.float64).reshape(-1)
        n = x_init.shape[0]
        self._x_store[:n] = x_init
        self._y_store[:n] = y_init
        self._n_data = n
        self.X = self._x_store[:n]
        self.Y = self._y_store[:n]
        self.length = L_INIT
        self.succ = self.fail = 0
        best = int(np.argmax(self.Y))
        self.best_x[:] = self.X[best]
        self.best_y = float(self.Y[best])
        self._fit_gp(reset=True)
        self.needs_training = False

    def _fit_gp(self, reset=False):
        y = self.Y
        self.y_median = float(np.median(y))
        self.y_std = float(np.std(y))
        if self.y_std < 1e-6:
            self.y_std = 1.0
        _normalize(y, self.y_median, self.y_std, self._normalized_y)
        train_x = self._x_tensor[:self._n_data]
        train_y = self._y_tensor[:self._n_data]
        if reset:
            self.likelihood = GaussianLikelihood(noise_constraint=NOISE_CONSTRAINT).to(device=DEVICE, dtype=DTYPE)
            self.gp = _GP(train_x, train_y, self.likelihood).to(device=DEVICE, dtype=DTYPE)
            self.gp.initialize(**{
                "covar_module.outputscale": 1.0,
                "covar_module.base_kernel.lengthscale": 0.5,
                "likelihood.noise": 0.005,
            })
        else:
            self.gp.set_train_data(inputs=train_x, targets=train_y, strict=False)
        self.gp.fit_model(self.likelihood)
        self.gp.eval()
        self.likelihood.eval()

    def suggest_candidates(self, n_samples, out, sobol_buffer):
        if self.needs_training:
            self._fit_gp()
            self.needs_training = False
        lengthscale = self.gp.covar_module.base_kernel.lengthscale.detach().numpy().reshape(-1)
        _tr_bounds(lengthscale, self.best_x, self.length, self.lower, self.upper, self._low, self._span)
        SobolEngine(self.dim, scramble=True, seed=self.rng.bit_generator.random_raw() % 1_000_000).draw(
            self.candidate_count, out=sobol_buffer, dtype=DTYPE
        )
        _fill_candidates(self.best_x, sobol_buffer.numpy(), self._low, self._span,
                         min(20.0 / self.dim, 1.0), self.rng.bit_generator.random_raw() >> 1,
                         out, self._rng_state)
        return self.gp.sample_predictions(self.likelihood, out, n_samples)

    def update(self, x, y, indices, count):
        self._n_data, self.best_y, self.succ, self.fail, self.length = _update_tr(
            x, y, indices, count, self._x_store, self._y_store, self._n_data, self.best_x,
            self.best_y, self.succ, self.fail, self.length, self.tau_fail,
        )
        self.X = self._x_store[:self._n_data]
        self.Y = self._y_store[:self._n_data]
        self.needs_training = True


class TuRBO(_Solver):
    def __init__(self, dim, MAX_EVALS, tr_count=DEFAULT_TR_COUNT, batch_size=DEFAULT_BATCH_SIZE):
        super().__init__(dim, MAX_EVALS)
        self.tr_count = int(tr_count)
        self.batch_size = int(batch_size)
        self.init_per_tr = self.dim * 2
        self.candidate_count = min(100 * self.dim, 5000)
        self._tr_list = []
        self._reinit_queue = []
        self._init_buffer = np.empty((self.tr_count * self.init_per_tr, self.dim), dtype=np.float64)
        self._lhs_perm = np.empty(self.init_per_tr, dtype=np.int64)
        self._rng_state = np.empty(4, dtype=np.uint64)
        total_candidates = self.tr_count * self.candidate_count
        self._candidate_pool = np.empty((total_candidates, self.dim), dtype=np.float64)
        self._sample_pool = np.empty((self.batch_size, total_candidates), dtype=np.float64)
        self._sample_median = np.empty(self.tr_count, dtype=np.float64)
        self._sample_std = np.empty(self.tr_count, dtype=np.float64)
        self._selected_candidates = np.empty((self.batch_size, self.dim), dtype=np.float64)
        self._selected_tr_indices = np.empty(self.batch_size, dtype=np.int64)
        self._group_indices = np.empty((self.tr_count, self.batch_size), dtype=np.int64)
        self._group_counts = np.empty(self.tr_count, dtype=np.int64)
        self._sobol_buffer = torch.empty((self.candidate_count, self.dim), device=DEVICE, dtype=DTYPE)

    def _lhs_into(self, out):
        _lhs(out, self._lhs_perm, self.lower, self.upper, self.rng.bit_generator.random_raw() >> 1, self._rng_state)

    def _ask_initial_tr(self):
        self._pending_kind = 0
        out = self._init_buffer[:self.init_per_tr]
        self._lhs_into(out)
        return out

    def _ask_reinit_tr(self):
        self._pending_kind = 1
        self._pending_tr_indices = tuple(self._reinit_queue)
        self._reinit_queue.clear()
        count = len(self._pending_tr_indices)
        for i in range(count):
            start = i * self.init_per_tr
            self._lhs_into(self._init_buffer[start:start + self.init_per_tr])
        return self._init_buffer[:count * self.init_per_tr]

    def _ask_turbo_batch(self):
        for i, tr in enumerate(self._tr_list):
            start = i * self.candidate_count
            end = start + self.candidate_count
            self._sample_pool[:, start:end] = tr.suggest_candidates(
                self.batch_size, self._candidate_pool[start:end], self._sobol_buffer
            )
            self._sample_median[i] = tr.y_median
            self._sample_std[i] = tr.y_std
        _select_candidates(self._sample_pool, self._candidate_pool, self.candidate_count,
                           self._sample_median, self._sample_std, self._selected_candidates,
                           self._selected_tr_indices)
        self._pending_kind = 2
        return self._selected_candidates

    def ask(self):
        if len(self._tr_list) < self.tr_count:
            return self._ask_initial_tr()
        if self._reinit_queue:
            return self._ask_reinit_tr()
        return self._ask_turbo_batch()

    def tell(self, x, fitness):
        x, fitness = super().tell(x, fitness)
        if self._pending_kind == 0:
            self._tr_list.append(_TrustRegion(x, fitness, self.lower, self.upper, self.MAX_EVALS, self.candidate_count))
            if len(self._tr_list) == self.tr_count:
                self._tr_list = tuple(self._tr_list)
        elif self._pending_kind == 1:
            for i, tr_idx in enumerate(self._pending_tr_indices):
                start = i * self.init_per_tr
                self._tr_list[tr_idx].initialize(x[start:start + self.init_per_tr], fitness[start:start + self.init_per_tr])
        else:
            _group_indices(self._selected_tr_indices, self._group_indices, self._group_counts)
            for tr_idx, tr in enumerate(self._tr_list):
                count = self._group_counts[tr_idx]
                if count:
                    tr.update(x, fitness, self._group_indices[tr_idx], count)
                    if tr.length < L_MIN:
                        self._reinit_queue.append(tr_idx)
