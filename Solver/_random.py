import numpy as np
from numba import njit


@njit(cache=True, inline="always")
def _rotl64(x, k):
    return (x << np.uint64(k)) | (x >> np.uint64(64 - k))


@njit(cache=True, inline="always")
def _next_u64(state):
    result = _rotl64(state[1] * np.uint64(5), 7) * np.uint64(9)
    t = state[1] << np.uint64(17)
    state[2] ^= state[0]
    state[3] ^= state[1]
    state[1] ^= state[2]
    state[0] ^= state[3]
    state[2] ^= t
    state[3] = _rotl64(state[3], 45)
    return result


@njit(cache=True, inline="always")
def _splitmix64(x):
    x += np.uint64(0x9E3779B97F4A7C15)
    z = x
    z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    return x, z ^ (z >> np.uint64(31))


@njit(cache=True, inline="always")
def _seed_rng(state, seed):
    x = np.uint64(seed)
    for i in range(4):
        x, state[i] = _splitmix64(x)


@njit(cache=True, inline="always")
def _random53(state):
    return _next_u64(state) >> np.uint64(11)


@njit(cache=True, inline="always")
def _random(state):
    return float(_random53(state)) * 1.1102230246251565e-16


@njit(cache=True, inline="always")
def _random_open(state):
    return (float(_next_u64(state) >> np.uint64(11)) + 0.5) * 1.1102230246251565e-16


@njit(cache=True, inline="always")
def _randint(state, high):
    limit = np.uint64(9007199254740992 - 9007199254740992 % high)
    value = _next_u64(state) >> np.uint64(11)
    while value >= limit:
        value = _next_u64(state) >> np.uint64(11)
    return np.int64(value % np.uint64(high))
