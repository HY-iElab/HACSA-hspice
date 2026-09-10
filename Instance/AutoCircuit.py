import os
import re
from concurrent.futures import ThreadPoolExecutor
import subprocess
from itertools import repeat
import numpy as np
from torch.quasirandom import SobolEngine
from .Circuit import Circuit as _Circuit, default_fom


FAILED_SPEC = -1e10


class AutoCircuit(_Circuit):
    def __init__(
        self,
        run_name="",
        deck_path="sample/deck_ts",
        deck_imports=(),
        parallel=True,
        digits=3,
        fom=default_fom,
    ):
        with open(deck_path, "r") as file: deck = file.read()
        self.design_structure = self.getDesignStructure(deck)
        self.design_functions = ()
        self.spec_parsers = ()
        self.digits = int(digits)
        super().__init__(
            sum(self.design_structure.values()),
            (),
            run_name=run_name,
            deck_path=deck_path,
            deck_imports=deck_imports,
            fom=fom,
        )
        if parallel:
            os.environ["META_QUEUE"] = "1"
            self.evaluateDesign = self._evaluateDesignParallel


    def registerSpecs(self, **specs):
        parsers = []
        spec_names = []
        offset = 0
        for suffix, names in specs.items():
            names = tuple(names)
            parsers.append(self._makeSpecParser(suffix, names, offset))
            spec_names.extend(names)
            offset += len(names)

        self.spec_parsers = tuple(parsers)
        self.spec_names = tuple(spec_names)
        self.spec_dim = len(spec_names)
        self.target_spec = np.zeros(self.spec_dim, dtype=np.float64)
        self.pre_weight = np.zeros(self.spec_dim, dtype=np.float64)
        self.post_weight = np.zeros(self.spec_dim, dtype=np.float64)

    def _makeSpecParser(self, suffix, names, offset):
        indices = {name.casefold().encode(): offset + index for index, name in enumerate(names)}
        count = len(names)
        suffix = f".{suffix}"

        def parse(path, row, indices=indices, count=count, suffix=suffix):
            found = 0
            with open(path + suffix, "rb") as file:
                for line in file:
                    equal = line.find(b"=")
                    if equal < 0: continue
                    index = indices.get(line[:equal].strip().lower())
                    if index is None: continue
                    value = line[equal + 1:].strip()
                    if value == b"failed": row[index] = FAILED_SPEC
                    else: row[index] = float(value)
                    found += 1
                    if found == count: break

        return parse

    def getDesignStructure(self, deck):
        structure = {}
        for name, index in re.findall(r"'([A-Za-z_]+)([0-9]+)'", deck):
            structure[name] = max(structure.get(name, 0), int(index) + 1)
        return structure

    def setDesignSpace(self, design_space): # Design Space: (lower, upper, resolution, unit, is_log)
        design_index = 0
        functions = []
        for name, count in self.design_structure.items():
            for parameter_index in range(count):
                parameter = f"{name}{parameter_index}"
                space = design_space[parameter] if parameter in design_space else design_space[name]
                functions.append(self._makeDesignFunction(parameter, design_index, *space))
                design_index += 1
        self.design_functions = tuple(functions)

    def autoFoM(self, k, target=True, weights=True):
        self.design_batch = SobolEngine(self.design_dim).draw_base2(k).numpy()
        self.evaluateDesign()
        valid_spec_columns = tuple(
            self.spec_batch[self.spec_batch[:, i] != FAILED_SPEC, i]
            for i in range(self.spec_dim)
        )
        assert all(values.size > 0 for values in valid_spec_columns), "autoFoM requires a valid value for every spec"
        if not target:
            self.setTargetSpec([values.mean() for values in valid_spec_columns])
        if weights:
            spec_min = np.array([values.min() for values in valid_spec_columns])
            spec_max = np.array([values.max() for values in valid_spec_columns])
            self.setPreWeight(1.0 / np.maximum(self.target_spec - spec_min, 1e-6))
            self.setPostWeight(1.0 / np.maximum(spec_max - self.target_spec, 1e-6))

    def _makeDesignFunction(self, name, index, lower, upper, resolution, unit, is_log):
        lower = float(lower)
        upper = float(upper)
        unit = str(unit)
        label = f".param {name}="

        if is_log:
            log_lower = np.log10(lower)
            log_span = np.log10(upper) - log_lower

            def scale(v, log_lower=log_lower, log_span=log_span):
                return 10.0 ** (log_lower + v * log_span)

            def unscale(x, log_lower=log_lower, log_span=log_span):
                return (np.log10(x) - log_lower) / log_span
        else:
            span = upper - lower

            def scale(v, lower=lower, span=span):
                return lower + v * span

            def unscale(x, lower=lower, span=span):
                return (x - lower) / span
        
        resolution = float(f"1e-{self.digits}") if resolution is None else float(resolution)

        if resolution.is_integer():
            def stringify(value, label=label, unit=unit):
                return f"{label}{int(value)}{unit}\n"
        else:
            def stringify(value, label=label, unit=unit):
                return f"{label}{value:.{self.digits}f}{unit}\n"

        def emit(size, index=index, scale=scale, unscale=unscale, lower=lower, resolution=resolution, stringify=stringify):
            v = size[:, index]
            x = scale(v)
            x = lower + np.floor((x - lower) / resolution + 0.5) * resolution
            v[:] = unscale(x)
            return tuple(stringify(value) for value in x)

        return emit

    def setSizeFromDesignBatch(self): pass
    def renormalizeDesignBatch(self): pass

    def writeCircuit(self, folder="temp"):
        size = self.design_batch
        blocks = tuple(emit(size) for emit in self.design_functions)
        for i in range(self.batch_size):
            with open(os.path.join(folder, f"param_{i}"), "w") as file:
                file.write("".join(block[i] for block in blocks))

    def evaluateSpec(self, i, folder="temp"):
        path = os.path.join(folder, str(i))
        row = self.spec_batch[i]
        for parse in self.spec_parsers: parse(path, row)

    def reserveDesignBatch(self):
        if self.batch_size != self.design_batch.shape[0]:
            prev_batch_size, self.batch_size = self.batch_size, self.design_batch.shape[0]
            self.spec_batch = np.empty((self.batch_size, self.spec_dim), dtype=np.float64)
            self.fom_batch = np.empty(self.batch_size, dtype=np.float64)
            self.valid_batch = np.ones(self.batch_size, dtype=np.bool_)

            pattern = re.compile(r"@([A-Za-z0-9_]+)_PATH@")
            with open(self.deck_path, "r") as file: prototype = file.read()
            for i in range(prev_batch_size, self.batch_size):
                path = os.path.join(self.temp_folder, str(i))
                if os.path.exists(path): continue
                text = pattern.sub(lambda m: f"{m.group(1).lower()}_{i}", prototype)
                with open(path, "w", buffering=1024*1024) as file: file.write(text)

    def testDeck(self):
        self.design_batch = np.array([[0.0] * self.design_dim, [1.0] * self.design_dim])
        self.batch_size = 2
        self.setSizeFromDesignBatch()
        self.writeCircuit(self.temp_folder)
        pattern = re.compile(r"@([A-Za-z0-9_]+)_PATH@")
        with open(self.deck_path, "r") as file: prototype = file.read()
        for i, name in enumerate(("low", "high")):
            os.rename(os.path.join(self.temp_folder, f"param_{i}"), os.path.join(self.temp_folder, f"param_{name}"))
            text = pattern.sub(lambda m: f"{m.group(1).lower()}_{name}", prototype)
            with open(os.path.join(self.temp_folder, name), "w") as file: file.write(text)
            subprocess.Popen((self.simulator, "-i", name), cwd=self.temp_folder).wait()


# Only used for parallel evaluation
    def _writeSimulateEvaluate(self, i, blocks):
        with open(os.path.join(self.temp_folder, f"param_{i}"), "w") as file:
            file.write("".join(block[i] for block in blocks))
        self.simulateCircuit(i)
        self.evaluateSpec(i, self.temp_folder)

    def _evaluateDesignParallel(self):
        self.reserveDesignBatch()
        size = self.design_batch
        blocks = tuple(emit(size) for emit in self.design_functions)
        with ThreadPoolExecutor() as executor:
            for _ in executor.map(self._writeSimulateEvaluate, range(self.batch_size), repeat(blocks)): pass
        self.calculateFoM()
