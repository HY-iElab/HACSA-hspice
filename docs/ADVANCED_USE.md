# Advanced usage / 고급 사용

<details open>
<summary><strong>English</strong></summary>

<a id="en"></a>

For basic usage, see [README_en.md](../README.md#en).

- [Custom optimization loop](#en-custom-optimization-loop)
- [Custom FoM](#en-custom-fom)
- [Storing results](#en-storing-results)
- [Custom solver](#en-custom-solver)
- [Custom deck or specs](#en-custom-deck-or-specs)

In [hacsa.py](../hacsa.py), `run(config)` → `optimize(**config)` connects the following components.

| Component | Role |
|---|---|
| `Circuit` | Converts design variables to simulator inputs and computes specs and the FoM |
| `AutoCircuit` | Implements `Circuit` according to the deck requirements in the README |
| `Solver` | Proposes designs to evaluate and uses their scores to guide the search |
| `Store` | Retains evaluation results and saves them to files |

<a id="en-overall-workflow"></a>

<a id="en-custom-optimization-loop"></a>

## Custom optimization loop

This example assumes that you have [implemented](#en-custom-solver) `Solver/MySolver.py`. Run the code from the project folder.

```python
from json import load

from Instance.AutoCircuit import AutoCircuit


with open("sample_manual.json", encoding="utf-8") as file:
    config = load(file)

circuit = AutoCircuit(
    deck_path=config["deck_path"],
    deck_imports=config["deck_imports"],
    run_name=config["run_name"],
)
circuit.registerSpecs(**config["specs"])
circuit.setDesignSpace(config["design_space"])
circuit.setTargetSpec(config["target_spec"])
circuit.setPreWeight(config["pre_weight"])
circuit.setPostWeight(config["post_weight"])
```

The example uses `sample_manual.json`, which provides both targets and weights.

- `AutoCircuit(...)`: Reads the deck to identify design variables and creates the circuit to simulate. Pass `deck_path`, `deck_imports`, and `run_name` directly from the configuration used in the README. For an approach other than `AutoCircuit`, see [Custom deck or specs](#en-custom-deck-or-specs).
- `registerSpecs(**config["specs"])`: Registers the specs for each file suffix from the JSON configuration. `**` passes `{"ms0": [...], "ma0": [...]}` as the arguments `ms0=[...], ma0=[...]`. Set targets and weights after registration.
- `setDesignSpace(...)`: Sets the search ranges for the design variables.
- `setTargetSpec(...)`: Sets the target value for each spec.
- `setPreWeight(...)`, `setPostWeight(...)`: Set the FoM weights before and after the targets are met.

[MyStore](#en-storing-results) is a storage class that this example assumes you have implemented in `Store/MyStore.py`.

```python
from Store.MyStore import MyStore

store = MyStore(
    design_dim=circuit.design_dim,
    spec_dim=circuit.spec_dim,
    temp_folder=circuit.temp_folder,
    reject_spec=config["reject_spec"],
    run_name=config["run_name"],
)

from Solver.MySolver import MySolver

max_evals = config["max_evals"]
early_stop = config.get("early_stop", False)
solver = MySolver(dim=circuit.design_dim, MAX_EVALS=max_evals)
```

- `store`: Retains results according to the criteria implemented in `MyStore`. `circuit.design_dim` and `circuit.spec_dim` are the numbers of design variables and specs, respectively. `circuit.temp_folder` is the working folder containing the simulation files.
- `max_evals`, `early_stop`: The evaluation count and early stopping setting from the JSON configuration. `early_stop` defaults to `False` if omitted.
- `solver`: Passes the number of design variables as `dim` and the evaluation count as `MAX_EVALS` to `MySolver`. A custom solver may also accept other inputs.

```python
evaluations_done = 0
while evaluations_done < max_evals:
    candidates = solver.ask()
    circuit.design_batch = candidates.copy()
    circuit.evaluateDesign()
    evaluations_done += circuit.batch_size

    store.updateArchive(circuit.design_batch, circuit.spec_batch, circuit.fom_batch)
    if store.updateBestFoM(circuit):
        if early_stop and store.isTargetAcheived():
            break

    solver.tell(circuit.design_batch, circuit.fom_batch)

store.saveArchive(circuit)
```

- `candidates` contains `batch_size` candidate designs. Each design specifies the netlist's design variable values in the range 0–1.
- `circuit.evaluateDesign()` evaluates the candidates with HSPICE.
- `Circuit.calculateFoM()` computes the FoM from the evaluated specs, and the solver and store use the results. To change the scoring function, see [Custom FoM](#en-custom-fom).
- `spec_batch` and `fom_batch` follow the same design order as `design_batch`.
- `solver.tell` passes `design_batch`, rounded and normalized to represent the values actually simulated, and its scores, `fom_batch`, back to the solver.

Inspect the saved results as follows.

```python
print(circuit.spec_names)
print(store.best_fom)
print(store.size)
print(store.result_folder)
print(store.spec_container[:store.size])
```

- `circuit.spec_names`: Spec names and their output order.
- `store.best_fom`: Highest FoM among the evaluated designs.
- `store.result_folder`: Folder containing the [result files](RESULTS.md#en).
- `store.spec_container[:store.size]`: Spec array for the retained designs. `store.size` is the number of retained designs; columns follow `circuit.spec_names`.

<a id="en-adjustments-before-running"></a>

### Adjustments before running

To specify the installation path, set `circuit.simulator = "path/to/hspice"` before evaluation. `AutoCircuit(..., parallel=False)` evaluates designs sequentially; the default, `True`, evaluates the designs in each batch in parallel.

When adjusting targets and weights yourself, you can use the following after registering specs and calling `setDesignSpace(...)`.

```python
circuit.autoFoM(k=7, target=False)
circuit.testDeck()
```

- `autoFoM`: Computes targets and both weight arrays from `2**k` Sobol samples. `target=True` (default) keeps the current targets; `weights=False` keeps both weight arrays. Only `failed` values for each spec are excluded from its statistics.
- `testDeck()`: Creates the `low` and `high` decks, with all design variables at their lower and upper bounds, respectively, along with `param_low` and `param_high`, then runs HSPICE. Inspect the run output and measurement files to check the deck. After the check, create a new circuit object for optimization.

The existing [main.py](../main.py) example configures the two-stage circuit directly in Python and evaluates designs sequentially, stopping when the targets are met. JSON runs default to parallel evaluation and continue until the evaluation budget is reached.

<a id="en-fom-contract"></a>

<a id="en-custom-fom"></a>

## Custom FoM

Assign a Python function to `config["fom"]` to customize the FoM calculation. Functions cannot be stored in JSON.

```python
from json import load
import numpy as np
from hacsa import run


def my_fom(spec_batch, target_spec, pre_weight, post_weight):
    margins = spec_batch - target_spec
    return np.minimum(margins, 0.0) @ pre_weight


with open("sample_manual.json", encoding="utf-8") as file:
    config = load(file)

config["run_name"] = "custom_fom"
config["max_evals"] = 200
config["fom"] = my_fom

circuit, store = run(config)
```

`run(config)` returns `circuit` and `store` after optimization and saving are complete.

For a batch of N designs with S specs, the array shapes are:

| Name | Meaning | NumPy array shape |
|---|---|---|
| `spec_batch` | Specs for each design; one design per row | (N, S) |
| `target_spec` | Target value for each spec | (S,) |
| `pre_weight` | Weights before the targets are met | (S,) |
| `post_weight` | Weights after the targets are met | (S,) |
| Return value | One score per design, in input order | (N,) |

The specs and all three configuration arrays follow **the registration order in `specs`** (`circuit.spec_names`). Keep all arguments in the function signature, even if some are unused.

The solver treats higher scores as better. With `"early_stop": true`, the run stops when the best FoM is 0 or greater, so return a negative score when any target is unmet and a nonnegative score when all targets are met. See [FoM definition](../README.md#en-fom-definition) for the default calculation.

<a id="en-example-ldo-scoring"></a>

### Example: LDO scoring

Suppose the specs are registered in `specs` in the order `[-T_R, -I_Q, I_LOAD_MAX]`. Since lower `T_R` and `I_Q` values are better, their signs are reversed in the output.

$$
\mathrm{LDO\_FoM}
= \frac{T_R \times I_Q}{I_{\mathrm{LOAD\_MAX}}}
$$

Before the targets are met, reduce the shortfalls. Afterward, maximize the reciprocal of the expression above. All three physical quantities and all `pre_weight` values must be positive.

```python
import numpy as np


def ldo_fom(spec_batch, target_spec, pre_weight, post_weight):
    fom_batch = np.minimum(
        spec_batch - target_spec, 0.0
    ) @ pre_weight

    target_met = fom_batch == 0.0
    negative_t_r = spec_batch[target_met, 0]
    negative_i_q = spec_batch[target_met, 1]
    i_load_max = spec_batch[target_met, 2]

    ldo_fom = negative_t_r * negative_i_q / i_load_max
    fom_batch[target_met] = 1.0 / ldo_fom
    return fom_batch
```

`target_met` selects designs that meet all targets. The product of the two negative specs is `T_R × I_Q`. Define this function in your script and set `config["fom"] = ldo_fom`. Adjust the JSON configuration to match the LDO deck and its spec order.

<a id="en-storing-results"></a>

## Storing results

Implement `MyStore` from the earlier example as follows and save it in `Store/MyStore.py`. This implementation retains every result that passes `reject_spec`. For the default `StoreParetoFront` selection criteria and how to use the result files, see [RESULTS_en.md](RESULTS.md#en).

```python
import numpy as np
from Store.Store import Store


class MyStore(Store):
    def updateArchive(self, design_batch, spec_batch, fom_batch):
        while self.size + spec_batch.shape[0] > self.container_cap:
            self.expandContainer()

        for i in range(spec_batch.shape[0]):
            if np.any(spec_batch[i] < self.reject_spec):
                continue

            idx = self.size
            self.design_container[idx] = design_batch[i]
            self.spec_container[idx] = spec_batch[i]
            self.fom_container[idx] = fom_batch[i]
            self.size += 1
```

After loading the JSON configuration into `config`, assign the storage class and run `hacsa.run`. Classes cannot be stored in JSON, so assign the class in Python.

```python
from hacsa import run

config["store_type"] = MyStore
circuit, store = run(config)
```

If `reject_spec` is omitted, `MyStore` retains all results.

To use other retention criteria, subclass [Store](../Store/Store.py) and implement `updateArchive`. Corresponding rows in the three input arrays refer to the same design, and design variable values are normalized to 0–1.

To use the default `saveArchive(circuit)`, maintain the following values:

- `self.size`: Number of retained designs.
- `self.design_container[:self.size]`: Design variable array.
- `self.spec_container[:self.size]`: Spec array.
- `self.fom_container[:self.size]`: FoM array.

Use `expandContainer()` to increase array capacity. If you change the constructor (`__init__`), accept `design_dim`, `spec_dim`, `reject_spec`, `temp_folder`, and `run_name` as keyword arguments, and call `super().__init__(design_dim, spec_dim, temp_folder, reject_spec, run_name)` to prepare the default arrays and results folder. If archive updates run concurrently with other work, finish them before saving, as in [StoreParetoFront](../Store/StoreParetoFront.py).

You can use the default implementations of `updateBestFoM(circuit)` and `isTargetAcheived()`. When the best FoM improves, `param_i` is copied to `best_param`. `best_spec` is written from `circuit.spec_names` and the corresponding row of `spec_batch`, with the FoM appended. This record is independent of whether `reject_spec` allows the design into the archive.

<a id="en-custom-solver"></a>

## Custom solver

To choose a built-in solver, see [Choosing a solver in the README](../README.md#en-choosing-a-solver).

Subclass [Solver](../Solver/Solver.py), define `MySolver` in `Solver/MySolver.py`, and set `"solver": "MySolver"` in the JSON configuration. The file and class names must match.

| Method to implement | Role |
|---|---|
| `__init__(self, dim, MAX_EVALS)` | Receives the number of design variables and the evaluation budget |
| `ask()` | Returns the next N candidate designs as an (N, dim) NumPy array, with each variable in the range 0–1 |
| `tell(x, fitness)` | Receives the evaluated designs (N, dim) and scores (N,) and uses them to guide the search; higher scores are better |

The calling code handles simulation and storage. If the constructor needs additional arguments, give them defaults or instantiate the solver directly in Python, as shown in [Custom optimization loop](#en-custom-optimization-loop).

<a id="en-lower-bound-on-scores-passed-to-the-solver"></a>

### Lower bound on scores passed to the solver

The default `Solver.tell(x, fitness, sentinel=-1e3)` clamps `fitness` using `np.maximum(sentinel, fitness)`. LSHADE and TuRBO use this operation. It applies to every score below the bound, including scores from valid designs, and does not change the stored FoM.

When changing this bound in a custom solver, keep it below valid scores. A bound that is too high can give failed and valid designs the same score; one that is too low can affect solvers that use score differences. CMAES bypasses this clamp and uses the ranking of the original scores.

<a id="en-custom-deck-or-specs"></a>

## Custom deck or specs

The default workflow creates an `AutoCircuit`. To use a different `Circuit`, write the object initialization and optimization loop in Python.

Subclass [Circuit](../Instance/Circuit.py) and set the number of design variables, `design_dim`, and the spec names and order, `spec_names`, in the constructor. Accept the FoM function as `fom` and pass it to the parent constructor.

The default `evaluateDesign()` runs in the order below. Implement the methods marked as required, and also override `simulateCircuit` if the simulator must be run differently.

| Order | Method | Role | Implementation |
|---:|---|---|---|
| 1 | `reserveDesignBatch()` | Prepares `batch_size`, result arrays, and runnable deck files for the number of designs | Required |
| 2 | `setSizeFromDesignBatch()` | Converts design variable values from 0–1 to actual circuit values | Required |
| 3 | `writeCircuit(folder)` | Writes `param_0`, `param_1`, … to the specified folder | Required |
| 4 | `renormalizeDesignBatch()` | Converts actual values adjusted by rounding or similar operations back to 0–1 and updates `design_batch` | Required |
| 5 | `simulateCircuit(i)` → `evaluateSpec(i, folder)` | Simulates each design and reads its specs | Spec reading required |
| 6 | `calculateFoM()` | Computes `fom_batch` using the assigned FoM function | Use the default implementation |

For N designs, `design_batch` must have shape (N, design_dim), and `spec_batch` must have shape (N, spec_dim). `spec_batch[i]` contains real values in `spec_names` order, and the design variables in the corresponding row must represent the values actually simulated.

The default `simulateCircuit(i)` runs `hspice -i 0`, `hspice -i 1`, … in the working folder. Saving the best FoM requires `param_i` and the corresponding row of specs. If `valid_batch` is provided, only rows marked `True` are candidates for the best FoM; the default, `None`, includes all rows. To support deck checks, also implement `testDeck()`.

<a id="en-reading-measurement-results"></a>

### Reading measurement results

`AutoCircuit.registerSpecs(...)` creates a parser for each suffix and fixes the spec names and their column indices in the result array. Input order determines `spec_names` order, and spec names are case-insensitive. Registration also recreates the target and weight arrays with zeros, so call it before setting their values.

`evaluateSpec(i, folder)` fills `spec_batch[i]` as follows.

1. Opens each registered `<i>.<suffix>` file once in binary mode.
2. If the name to the left of `=` is a registered spec, reads the value on the right as a `float` and writes it to the corresponding column.
3. If the value is `failed`, writes `-1e10` to that column.
4. Once all required specs have been found, stops reading that file and moves to the next suffix.

The parser does not interpret the meaning of analyses or `.measure` statements. Entries may appear in any order within a result file, but every registered name must be present.

If a registered file is missing, execution stops when the parser tries to open it. If the file exists but a name is missing, its column is left unwritten and may contain a previous or uninitialized value. Missing entries are not converted to `failed`. The `temp/error` folder is created, but parameter files are not moved there. `failed` does not change `valid_batch`; it affects the FoM and `reject_spec` filtering rather than a separate validity filter.

`Circuit` computes the FoM, `Solver` performs the search, and `Store` retains results. A custom parser must preserve the design and spec order. The solver and store do not recalculate the FoM.

</details>

<details>
<summary><strong>한국어</strong></summary>

<a id="ko"></a>

기본 사용법은 [README.md](../README.md#ko)를 참고한다.

- [Custom optimization loop](#ko-custom-optimization-loop)
- [Custom FoM](#ko-custom-fom)
- [Storing results](#ko-storing-results)
- [Custom solver](#ko-custom-solver)
- [Custom deck or specs](#ko-custom-deck-or-specs)

[hacsa.py](../hacsa.py)의 `run(config)` → `optimize(**config)`는 다음 요소를 연결한다.

| 구성 요소 | 역할 |
|---|---|
| `Circuit` | 설계 변수를 시뮬레이터 입력으로 바꾸고 spec과 FoM을 계산한다 |
| `AutoCircuit` | README의 deck 규칙에 맞춰 구현된 `Circuit`이다 |
| `Solver` | 평가할 설계안을 제안하고 점수를 받아 탐색을 진행한다 |
| `Store` | 평가 결과를 보관하고 파일로 저장한다 |

<a id="ko-전체-실행-흐름"></a>

<a id="ko-custom-optimization-loop"></a>

## Custom optimization loop

다음은 사용자가 `Solver/MySolver.py`를 [구현](#ko-custom-solver)했다고 가정한 예제이다. (코드는 프로젝트 폴더에서 실행한다)

```python
from json import load

from Instance.AutoCircuit import AutoCircuit


with open("sample_manual.json", encoding="utf-8") as file:
    config = load(file)

circuit = AutoCircuit(
    deck_path=config["deck_path"],
    deck_imports=config["deck_imports"],
    run_name=config["run_name"],
)
circuit.registerSpecs(**config["specs"])
circuit.setDesignSpace(config["design_space"])
circuit.setTargetSpec(config["target_spec"])
circuit.setPreWeight(config["pre_weight"])
circuit.setPostWeight(config["post_weight"])
```

이 예제는 target과 weight가 모두 있는 `sample_manual.json`을 사용한다.

- `AutoCircuit(...)`: deck을 읽어 설계 변수를 파악하고, 시뮬레이션할 회로를 만든다. `deck_path`, `deck_imports`, `run_name`은 README에서 사용한 설정을 그대로 전달한다. (AutoCircuit과 다른 방식을 원한다면 [Custom deck or specs](#ko-custom-deck-or-specs)를 참고 바람)
- `registerSpecs(**config["specs"])`: JSON의 suffix별 spec을 등록한다. `**`는 `{"ms0": [...], "ma0": [...]}`를 `ms0=[...], ma0=[...]` 인자로 전달한다. target과 weight는 등록 후 설정한다.
- `setDesignSpace(...)`: 설계 변수의 탐색 범위를 지정한다.
- `setTargetSpec(...)`: 각 spec의 목표값을 지정한다.
- `setPreWeight(...)`, `setPostWeight(...)`: target 달성 전과 후의 FoM 가중치를 지정한다.

[MyStore](#ko-storing-results)는 사용자가 `Store/MyStore.py`에 구현했다고 가정한 저장 클래스이다.

```python
from Store.MyStore import MyStore

store = MyStore(
    design_dim=circuit.design_dim,
    spec_dim=circuit.spec_dim,
    temp_folder=circuit.temp_folder,
    reject_spec=config["reject_spec"],
    run_name=config["run_name"],
)

from Solver.MySolver import MySolver

max_evals = config["max_evals"]
early_stop = config.get("early_stop", False)
solver = MySolver(dim=circuit.design_dim, MAX_EVALS=max_evals)
```

- `store`: `MyStore`에 구현한 기준으로 결과를 보관한다. `circuit.design_dim`과 `circuit.spec_dim`은 각각 설계 변수 수와 spec 수이며, `circuit.temp_folder`는 시뮬레이션 파일이 있는 작업 폴더이다.
- `max_evals`, `early_stop`: JSON의 평가 횟수와 조기 종료 설정이다. `early_stop`을 생략하면 `False`를 사용한다.
- `solver`: `MySolver`에 설계 변수 수를 `dim`으로, 평가 횟수를 `MAX_EVALS`로 전달한다. custom solver이므로 다른 입력도 취할 수 있다.

```python
evaluations_done = 0
while evaluations_done < max_evals:
    candidates = solver.ask()
    circuit.design_batch = candidates.copy()
    circuit.evaluateDesign()
    evaluations_done += circuit.batch_size

    store.updateArchive(circuit.design_batch, circuit.spec_batch, circuit.fom_batch)
    if store.updateBestFoM(circuit):
        if early_stop and store.isTargetAcheived():
            break

    solver.tell(circuit.design_batch, circuit.fom_batch)

store.saveArchive(circuit)
```

- `candidates`는 `batch_size` 개의 설계안이다. 각 설계안은 netlist 설계 변수의 값을 0~1 범위로 지정한다.
- `candidates`는 `circuit.evaluateDesign()`을 통해 HSPICE로 평가된다.
- 평가된 spec은 `Circuit.calculateFoM()`에서 FoM으로 계산되며 solver와 store는 그 결과를 사용한다. FoM 계산식을 바꾸려면 [Custom FoM](#ko-custom-fom)을 참고한다.
- `spec_batch`와 `fom_batch`는 `design_batch`와 같은 설계안 순서를 따른다.
- `solver.tell`은 실제 시뮬레이션한 값으로 반올림·환산된 `design_batch`와 그 점수 `fom_batch`를 solver에게 전달한다. 

저장한 결과는 다음처럼 확인한다.

```python
print(circuit.spec_names)
print(store.best_fom)
print(store.size)
print(store.result_folder)
print(store.spec_container[:store.size])
```

- `circuit.spec_names`: spec 이름과 저장 순서.
- `store.best_fom`: 평가한 설계안 중 최고 FoM.
- `store.result_folder`: [결과 파일](RESULTS.md#ko)을 저장한 폴더.
- `store.spec_container[:store.size]`: 보관한 설계안의 spec 배열. `store.size`는 보관한 설계안 수이며, 각 열은 `circuit.spec_names` 순서이다.

<a id="ko-실행-전-조정"></a>

### 실행 전 조정

설치 위치를 직접 지정하려면 평가 전에 `circuit.simulator = "path/to/hspice"`로 설정한다. `AutoCircuit(..., parallel=False)`는 순차 평가이며, 기본값 `True`는 batch의 설계안을 병렬로 평가한다.

target·weight를 직접 조정할 때는 spec 등록과 `setDesignSpace(...)` 뒤에 다음을 사용할 수 있다.

```python
circuit.autoFoM(k=7, target=False)
circuit.testDeck()
```

- `autoFoM`: `2**k`개의 Sobol 표본으로 target과 두 weight를 구한다. `target=True`(기본값)는 설정된 target을 유지하고, `weights=False`는 두 weight를 유지한다. 각 spec의 `failed` 값만 통계에서 제외한다.
- `testDeck()`: 모든 설계 변수가 하한인 `low`와 상한인 `high` deck, `param_low`, `param_high`를 만들고 HSPICE를 실행한다. 실행 출력과 측정 파일로 deck을 점검한다. 점검을 마친 뒤 최적화할 회로는 다시 생성한다.

기존 [main.py](../main.py)는 two-stage 회로를 Python에서 직접 구성하는 예제이며, 순차 평가하고 target 달성 시 종료한다. JSON 실행의 기본값은 병렬 평가·평가 횟수까지 진행이다.

<a id="ko-fom-contract"></a>

<a id="ko-custom-fom"></a>

## Custom FoM

`config["fom"]`에 Python 함수를 지정해 FoM 계산을 바꾼다. 함수는 JSON에 저장할 수 없다.

```python
from json import load
import numpy as np
from hacsa import run


def my_fom(spec_batch, target_spec, pre_weight, post_weight):
    margins = spec_batch - target_spec
    return np.minimum(margins, 0.0) @ pre_weight


with open("sample_manual.json", encoding="utf-8") as file:
    config = load(file)

config["run_name"] = "custom_fom"
config["max_evals"] = 200
config["fom"] = my_fom

circuit, store = run(config)
```

`run(config)`는 최적화와 저장을 마친 뒤 `circuit`, `store`를 반환한다.

한 번에 평가하는 설계안이 N개, spec이 S개일 때 배열 크기는 다음과 같다.

| 이름 | 의미 | NumPy 배열 크기 |
|---|---|---|
| `spec_batch` | 설계안별 spec. 한 행이 한 설계안 | (N, S) |
| `target_spec` | spec별 목표값 | (S,) |
| `pre_weight` | target 달성 전 가중치 | (S,) |
| `post_weight` | target 달성 후 가중치 | (S,) |
| 반환값 | 입력 순서대로 설계안마다 점수 하나 | (N,) |

spec과 세 설정 배열은 **`specs`의 등록 순서**(`circuit.spec_names`)를 따른다. 사용하지 않는 인자도 함수 정의에는 남겨 둔다.

solver는 점수가 클수록 좋다고 판단한다. `"early_stop": true`이면 최고 FoM이 0 이상일 때 종료하므로, target 미달에는 음수, 모두 달성하면 0 이상을 반환한다. 기본 계산식은 [FoM 정의](../README.md#ko-fom-정의)를 참고한다.

<a id="ko-예-ldo-점수-계산"></a>

### 예: LDO 점수 계산

`specs`에 `[-T_R, -I_Q, I_LOAD_MAX]` 순서로 spec을 등록했다고 하자. 작을수록 좋은 `T_R`, `I_Q`는 부호를 반전해 저장한다.

$$
\mathrm{LDO\_FoM}
= \frac{T_R \times I_Q}{I_{\mathrm{LOAD\_MAX}}}
$$

target 달성 전에는 부족분을 줄이고, 달성 후에는 위 값의 역수를 키운다. 세 물리량과 모든 `pre_weight` 값은 양수여야 한다.

```python
import numpy as np


def ldo_fom(spec_batch, target_spec, pre_weight, post_weight):
    fom_batch = np.minimum(
        spec_batch - target_spec, 0.0
    ) @ pre_weight

    target_met = fom_batch == 0.0
    negative_t_r = spec_batch[target_met, 0]
    negative_i_q = spec_batch[target_met, 1]
    i_load_max = spec_batch[target_met, 2]

    ldo_fom = negative_t_r * negative_i_q / i_load_max
    fom_batch[target_met] = 1.0 / ldo_fom
    return fom_batch
```

`target_met`은 모든 target을 만족한 설계안을 고른다. 두 음수 spec의 곱은 `T_R × I_Q`이다. 실행 코드에 이 함수를 정의하고 `config["fom"] = ldo_fom`으로 지정한다. JSON도 해당 LDO deck과 spec 순서에 맞춘다.

<a id="ko-storing-results"></a>

## Storing results

앞 예제의 `MyStore`를 다음처럼 구현해 `Store/MyStore.py`에 저장한다. 이 구현은 `reject_spec`을 통과한 결과를 모두 보관한다. 기본 저장소인 `StoreParetoFront`의 선별 기준과 결과 파일 사용법은 [RESULTS.md](RESULTS.md#ko)를 참고한다.

```python
import numpy as np
from Store.Store import Store


class MyStore(Store):
    def updateArchive(self, design_batch, spec_batch, fom_batch):
        while self.size + spec_batch.shape[0] > self.container_cap:
            self.expandContainer()

        for i in range(spec_batch.shape[0]):
            if np.any(spec_batch[i] < self.reject_spec):
                continue

            idx = self.size
            self.design_container[idx] = design_batch[i]
            self.spec_container[idx] = spec_batch[i]
            self.fom_container[idx] = fom_batch[i]
            self.size += 1
```

JSON 설정을 읽은 `config`에 저장 클래스를 지정하고 `hacsa.run`으로 실행한다. 클래스는 JSON에 담을 수 없어 Python에서 지정한다.

```python
from hacsa import run

config["store_type"] = MyStore
circuit, store = run(config)
```

`reject_spec`을 생략하면 `MyStore`는 모든 결과를 보관한다.

다른 저장 기준도 [Store](../Store/Store.py)를 상속해 `updateArchive`에 구현한다. 세 입력 배열의 같은 행은 같은 설계안이며, 설계 변수는 0~1로 환산된 값이다.

기본 `saveArchive(circuit)`로 저장하려면 다음 값을 유지한다.

- `self.size`: 보관한 설계안 수
- `self.design_container[:self.size]`: 설계 변수 배열
- `self.spec_container[:self.size]`: spec 배열
- `self.fom_container[:self.size]`: FoM 배열

배열 공간은 `expandContainer()`로 늘린다. 생성자(`__init__`)를 바꾸면 `design_dim`, `spec_dim`, `reject_spec`, `temp_folder`, `run_name`을 이름으로 받고, `super().__init__(design_dim, spec_dim, temp_folder, reject_spec, run_name)`으로 기본 배열과 결과 폴더를 준비한다. 결과 정리를 다른 작업과 동시에 진행한다면 [StoreParetoFront](../Store/StoreParetoFront.py)처럼 저장 전에 정리를 끝낸다.

`updateBestFoM(circuit)`과 `isTargetAcheived()`는 기본 구현을 쓸 수 있다. 최고 FoM이 갱신되면 `param_i`를 `best_param`으로 복사하고, `circuit.spec_names`와 해당 `spec_batch` 행으로 `best_spec`을 쓴 뒤 FoM을 덧붙인다. 이 기록은 `reject_spec`에 따른 보관 여부와 별개이다.

<a id="ko-custom-solver"></a>

## Custom solver

기본 제공 solver 중에서 선택하려면 [README의 Solver 선택](../README.md#ko-solver-선택)을 참고한다.

[Solver](../Solver/Solver.py)를 상속해 `Solver/MySolver.py`에 `MySolver` 클래스를 만들고, JSON에 `"solver": "MySolver"`를 지정한다. 파일 이름과 클래스 이름은 같아야 한다.

| 구현할 부분 | 역할 |
|---|---|
| `__init__(self, dim, MAX_EVALS)` | 설계 변수 수와 평가 횟수 기준을 받는다 |
| `ask()` | 다음에 평가할 설계안 N개를 (N, dim) NumPy 배열로 반환한다. 각 변수는 0~1 범위이다 |
| `tell(x, fitness)` | 평가한 설계안 (N, dim)과 점수 (N,)을 받아 탐색에 반영한다. 점수는 클수록 좋다 |

시뮬레이션과 저장은 실행 코드가 담당한다. 추가 생성자 인자가 필요하면 기본값을 두거나, [Custom optimization loop](#ko-custom-optimization-loop)을 참고해 Python에서 직접 생성한다.

<a id="ko-solver에-전달되는-점수-하한"></a>

### Solver에 전달되는 점수 하한

기본 `Solver.tell(x, fitness, sentinel=-1e3)`는 `fitness`를 `np.maximum(sentinel, fitness)`로 제한한다. LSHADE와 TuRBO가 이 처리를 사용한다. 실패 설계안뿐 아니라 하한보다 낮은 모든 점수에 적용하며, 저장된 FoM은 바꾸지 않는다.

custom solver에서 하한을 바꿀 때는 정상 점수보다 낮게 잡는다. 너무 높으면 실패 설계안과 정상 설계안이 같은 점수로 처리될 수 있고, 너무 낮으면 점수 차이를 사용하는 solver의 탐색에 영향을 줄 수 있다. CMAES는 이 하한 처리를 거치지 않고 원래 점수의 순위를 사용한다.

<a id="ko-custom-deck-or-specs"></a>

## Custom deck or specs

기본 실행은 `AutoCircuit`을 생성한다. 다른 `Circuit`을 쓰려면 객체 생성과 최적화 루프를 Python으로 작성한다.

[Circuit](../Instance/Circuit.py)을 상속하고 생성자에서 설계 변수 수 `design_dim`과 spec 이름·순서 `spec_names`를 정한다. FoM 함수를 `fom`으로 받아 부모 생성자에도 전달한다.

기본 `evaluateDesign()`의 실행 순서이다. ‘직접 구현’ 항목을 작성하고, 시뮬레이터 실행 방식이 다르면 `simulateCircuit`도 바꾼다.

| 순서 | 메서드 | 역할 | 구현 |
|---:|---|---|---|
| 1 | `reserveDesignBatch()` | 설계안 수에 맞춰 `batch_size`, 결과 배열, 실행용 deck 파일을 준비한다 | 직접 구현 |
| 2 | `setSizeFromDesignBatch()` | 0~1의 설계 변수 값을 실제 회로 값으로 바꾼다 | 직접 구현 |
| 3 | `writeCircuit(folder)` | 지정 폴더에 `param_0`, `param_1`, …을 쓴다 | 직접 구현 |
| 4 | `renormalizeDesignBatch()` | 반올림 등으로 바뀐 실제 값을 다시 0~1로 환산해 `design_batch`에 반영한다 | 직접 구현 |
| 5 | `simulateCircuit(i)` → `evaluateSpec(i, folder)` | 각 설계안을 실행하고 spec을 읽는다 | spec 읽기 직접 구현 |
| 6 | `calculateFoM()` | 지정한 FoM 함수로 `fom_batch`를 계산한다 | 기본 구현 사용 |

N개 설계안에 대해 `design_batch`는 (N, design_dim), `spec_batch`는 (N, spec_dim) 크기여야 한다. `spec_batch[i]`는 `spec_names` 순서의 실수 값이며, 같은 행의 설계 변수는 실제 시뮬레이션한 값과 일치해야 한다.

기본 `simulateCircuit(i)`는 작업 폴더에서 `hspice -i 0`, `hspice -i 1`, …을 실행한다. 최고 FoM 저장에는 `param_i` 파일과 해당 행의 spec이 필요하다. `valid_batch`가 있으면 `True`인 행만 최고 FoM 후보로 사용하며, 기본값 `None`이면 모든 행을 사용한다. deck 점검 기능을 제공하려면 `testDeck()`도 구현한다.

<a id="ko-측정-결과-읽기"></a>

### 측정 결과 읽기

`AutoCircuit.registerSpecs(...)`는 suffix마다 parser를 만들고 spec 이름과 결과 배열의 열 번호를 고정한다. 입력 순서가 `spec_names` 순서이며, spec 이름은 대소문자를 구분하지 않는다. 등록하면 target·weight 배열도 0으로 다시 만들므로 설정 전에 호출한다.

`evaluateSpec(i, folder)`는 다음 순서로 `spec_batch[i]`를 채운다.

1. 등록한 `<i>.<suffix>` 파일을 binary mode로 한 번 연다.
2. `=` 왼쪽 이름이 등록된 spec이면 오른쪽 값을 `float`로 읽어 해당 열에 쓴다.
3. 값이 `failed`이면 그 열에 `-1e10`을 쓴다.
4. 필요한 spec을 모두 찾으면 그 파일 읽기를 끝내고 다음 suffix로 넘어간다.

이 parser는 analysis나 `.measure`의 의미를 해석하지 않는다. 결과 파일 안의 순서는 자유지만 등록한 이름은 모두 있어야 한다.

등록한 파일이 없으면 파일 읽기에서 실행이 중단된다. 파일은 있으나 이름이 빠지면 해당 열이 채워지지 않아 이전 값이나 초기화되지 않은 값이 남을 수 있다. 누락을 `failed`로 바꾸는 처리는 없으며, `temp/error`도 생성만 하고 param을 옮기지 않는다. `failed`는 `valid_batch`를 바꾸지 않으므로 별도의 유효성 필터 대신 FoM 계산과 `reject_spec`에 반영된다.

FoM 계산은 `Circuit`, 탐색은 `Solver`, 보관은 `Store`가 담당한다. custom parser는 같은 설계안·spec 순서를 유지하고, solver나 store에서 FoM을 다시 계산하지 않는다.

</details>
