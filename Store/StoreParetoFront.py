from concurrent.futures import ThreadPoolExecutor

import numpy as np
from numba import njit

from Store.Store import Store as _Store


DOMINANT = 1
DOMINATED = -1
EQUAL = 0
NON_DOMINATED = 2


@njit(cache=True, nogil=True)
def _compareSpec(left, right):
    left_better = False
    right_better = False

    for idx in range(left.shape[0]):
        if left[idx] > right[idx]:
            left_better = True
        elif left[idx] < right[idx]:
            right_better = True

        if left_better and right_better:
            return NON_DOMINATED

    if left_better:
        return DOMINANT
    if right_better:
        return DOMINATED
    return EQUAL


@njit(cache=True, nogil=True)
def _updateParetoFront(design_container, spec_container, fom_container, size, design_batch, spec_batch, fom_batch, reject_spec):
    batch_size = spec_batch.shape[0]
    spec_dim = spec_batch.shape[1]
    rejected = np.zeros(batch_size, dtype=np.bool_)

    for batch_idx in range(batch_size):
        for spec_idx in range(spec_dim):
            if spec_batch[batch_idx, spec_idx] < reject_spec[spec_idx]:
                rejected[batch_idx] = True
                break

    for left_idx in range(batch_size):
        if rejected[left_idx]: continue

        for right_idx in range(left_idx + 1, batch_size):
            if rejected[right_idx]: continue

            comparison = _compareSpec(spec_batch[left_idx], spec_batch[right_idx])
            if comparison == DOMINANT or comparison == EQUAL:
                rejected[right_idx] = True
            elif comparison == DOMINATED:
                rejected[left_idx] = True
                break

    dist = 0
    for set_idx in range(size):
        is_dominated = False

        for batch_idx in range(batch_size):
            if rejected[batch_idx]: continue

            comparison = _compareSpec(spec_container[set_idx], spec_batch[batch_idx])
            if comparison == DOMINANT or comparison == EQUAL:
                rejected[batch_idx] = True
            elif comparison == DOMINATED:
                is_dominated = True

        if is_dominated: dist += 1
        elif dist != 0:
            target_idx = set_idx - dist
            design_container[target_idx] = design_container[set_idx]
            spec_container[target_idx] = spec_container[set_idx]
            fom_container[target_idx] = fom_container[set_idx]

    size -= dist

    for batch_idx in range(batch_size):
        if rejected[batch_idx]: continue

        design_container[size] = design_batch[batch_idx]
        spec_container[size] = spec_batch[batch_idx]
        fom_container[size] = fom_batch[batch_idx]
        size += 1

    return size


class StoreParetoFront(_Store):
    def __init__(self, design_dim, spec_dim, temp_folder, reject_spec=None, run_name=""):
        super().__init__(design_dim, spec_dim, temp_folder, reject_spec, run_name)
        self._update_executor = ThreadPoolExecutor(max_workers=1)
        self._pending_update = None

    def _reserve(self, count):
        while self.size + count > self.container_cap:
            self.expandContainer()

    def _syncArchive(self):
        if self._pending_update is not None:
            self._pending_update.result()
            self._pending_update = None

    def _updateArchive(self, design_batch, spec_batch, fom_batch):
        self.size = _updateParetoFront(
            self.design_container,
            self.spec_container,
            self.fom_container,
            self.size,
            design_batch,
            spec_batch,
            fom_batch,
            self.reject_spec,
        )

    def updateArchive(self, design_batch, spec_batch, fom_batch):        
        design_batch = np.array(design_batch, dtype=np.float64, copy=True)
        spec_batch = np.array(spec_batch, dtype=np.float64, copy=True)
        fom_batch = np.array(fom_batch, dtype=np.float64, copy=True)
        self._syncArchive()
        self._reserve(spec_batch.shape[0])
        self._pending_update = self._update_executor.submit(self._updateArchive, design_batch, spec_batch, fom_batch)

    def saveArchive(self, circuit):
        self._syncArchive()
        super().saveArchive(circuit)
