# HACSA-hspice

<details>
<summary><strong>English</strong></summary>

<a id="en"></a>

HACSA-hspice is a Python interface for analog circuit sizing with HSPICE.

<a id="en-installation"></a>

## Installation

<a id="en-hspice"></a>

### HSPICE

This program requires HSPICE decks to follow a specific format. For custom handling outside these requirements, see [Advanced usage](docs/ADVANCED_USE.md#en).

<a id="en-python-dependencies"></a>

### Python dependencies

Python 3.6.2 or later.

```bash
python -m pip install -r requirements.txt
```

<a id="en-running-an-optimization"></a>

## Running an optimization

Pass a JSON configuration file to `hacsa.py`.

```bash
python hacsa.py sample_manual.json
```

This command optimizes `sample/deck_fc` and saves the results in `result_0`. Any existing `temp_0` and `result_0` folders are replaced at the start of the run.

<a id="en-configuration-file"></a>

### Configuration file

The following example sets targets and weights manually (see `sample_manual.json`).

```json
{
  "run_name": 0,
  "deck_path": "sample/deck_fc",
  "deck_imports": ["sample/pdk"],
  "specs": {
    "ms0": ["negative_total_current_uA"],
    "ma0": ["gain_db", "log10_ugbw", "pm_deg", "cmrr_db"]
  },
  "reject_spec": [-100.0, 0.0, 6.0, 40.0, 40.0],
  "max_evals": 20000,
  "target_spec": [-5.2232, 38.2163, 6.6529, 60.0, 70.4884],
  "pre_weight": [0.02, 0.025, 0.5, 0.015625, 0.025],
  "post_weight": [0.02, 0.025, 0.5, 0.0, 0.025],
  "design_space": {
    "R": [1.0, 1000.0, null, "k", true],
    "C": [10, 1000, null, "f", false],
    "L": [180, 360, 5, "n", false],
    "W": [45, 90, 5, "n", false],
    "M": [1, 60, 1, "", false],
    "M0": [20, 60, 1, "", false]
  }
}
```

- `run_name`: Run identifier. An empty string uses `temp` and `result`; `"xxx"` uses `temp_xxx` and `result_xxx`.
- `deck_path`: Path to the deck. Relative paths are resolved from the folder containing `hacsa.py`; absolute paths are also supported.
- `deck_imports`: List of files to copy into the working folder alongside the deck. Use `sample/pdk` for the `.include "pdk"` line in `deck_fc`. List multiple files in order inside `[ ]`, or omit this field if no supporting files are needed.
- `specs`: Names of the specs to read from each HSPICE result file. `ms0` and `ma0` are file suffixes. The order of the entries and names determines the spec order (see [Register spec locations](#en-3-register-spec-locations)).
- `reject_spec`: Lower bounds on the performance metrics (specs) of designs to retain. A design is excluded if any spec falls below its bound. Omitting this field disables this filter. The default store retains the Pareto set of the designs that pass.
- `max_evals`: Evaluation count at which the solver should stop. Evaluations run in batches, so the actual count may be slightly higher.
- `early_stop`: Whether to stop when the targets are met (default: `false`).
- `target_spec`: Minimum target value for each spec (set automatically if omitted).
- `pre_weight`: Positive weights applied to the figure of merit (FoM) when any target is unmet.
- `post_weight`: Nonnegative weights applied to the FoM when all targets are met. If either weight array is omitted, both are set automatically.
- `design_space`: [Search ranges](#en-design-space-definition) for the deck's design variables. Each array is ordered as `[lower, upper, resolution, unit, is_log]`.

`reject_spec`, `target_spec`, `pre_weight`, and `post_weight` must all follow the registration order in `specs`. The mapping for `sample/deck_fc` is shown below.

| Index | Spec registered in `specs` | `reject_spec` | `target_spec` | `pre_weight` | `post_weight` |
|---:|---|---:|---:|---:|---:|
| 0 | `negative_total_current_uA` | -100.0 | -5.2232 | 0.02 | 0.02 |
| 1 | `gain_db` | 0.0 | 38.2163 | 0.025 | 0.025 |
| 2 | `log10_ugbw` | 6.0 | 6.6529 | 0.5 | 0.5 |
| 3 | `pm_deg` | 40.0 | 60.0 | 0.015625 | 0.0 |
| 4 | `cmrr_db` | 40.0 | 70.4884 | 0.025 | 0.025 |

Optional JSON fields:

- `solver`: [Solver to use](#en-choosing-a-solver) (default: `"CMAES"`).
- `auto_fom`: Exponent controlling the number of Sobol samples for automatic configuration (default: `7`). The sample count is `2^auto_fom`.
- `parallel`: How HSPICE evaluates designs. `true` evaluates them in parallel (default); `false` evaluates them sequentially.
- `digits`: Maximum number of decimal places for parameters written to the deck (default: `3`, as in 0.xxx). When `resolution` is `null`, the search increment is `10**(-digits)`.

<a id="en-choosing-a-solver"></a>

### Choosing a solver

To use a different solver, add `solver` to the JSON configuration.

```json
"solver": "LSHADE"
```

Built-in solvers and their underlying papers:

- `CMAES`: Nikolaus Hansen and Andreas Ostermeier, [*Adapting Arbitrary Normal Mutation Distributions in Evolution Strategies: The Covariance Matrix Adaptation*](https://doi.org/10.1109/ICEC.1996.542381), 1996.
- `LSHADE`: Ryoji Tanabe and Alex S. Fukunaga, [*Improving the Search Performance of SHADE Using Linear Population Size Reduction*](https://doi.org/10.1109/CEC.2014.6900380), 2014.
- `TuRBO`: David Eriksson, Michael Pearce, Jacob Gardner, Ryan D. Turner, Matthias Poloczek, [*Scalable Global Optimization via Local Bayesian Optimization*](https://proceedings.neurips.cc/paper/2019/hash/6c990b7aca7bc7058f5e98ea909e924b-Abstract.html), 2019.

To use a custom solver, implement the `Solver` interface and place it in the `Solver` folder. The file and class names must match (`XXX.py` → `class XXX`).

<a id="en-automatic-targets-and-weights"></a>

### Automatic targets and weights

Supplied targets and a complete pair of weight arrays are used as provided. Missing targets or weights are derived by evaluating Sobol samples with HSPICE.

| `target_spec` | `pre_weight`, `post_weight` | Behavior |
|---|---|---|
| Provided | Both provided | No automatic sample evaluation |
| Omitted | Both provided | Set targets automatically |
| Provided | One or both omitted | Set both weight arrays automatically |
| Omitted | One or both omitted | Set targets and both weight arrays automatically |

Omit both targets and weights, as in `sample_auto.json`, to use the automatically computed values as a starting point for tuning the FoM.

```bash
python hacsa.py sample_auto.json
```

The contents of `sample_auto.json` are shown below.

```json
{
  "run_name": 0,
  "deck_path": "sample/deck_ts",
  "deck_imports": ["sample/pdk"],
  "specs": {
    "ms0": ["negative_total_current_uA"],
    "ma0": ["gain_db", "log10_ugbw", "pm_deg"]
  },
  "reject_spec": [-100.0, 0.0, 6.0, 40.0],
  "max_evals": 20000,
  "design_space": {
    "I": [1.0, 5.0, null, "u", true],
    "C": [10, 1000, null, "f", false],
    "L": [180, 360, 5, "n", false],
    "W": [45, 90, 5, "n", false],
    "M": [1, 60, 1, "", false],
    "M0": [20, 60, 1, "", false]
  }
}
```

Add `auto_fom` to change the sample count for automatic targets and weights from the default $2^7 = 128$. These evaluations run before the solver starts and do not count toward `max_evals`.

For each spec, the automatic calculation excludes failed measurements and computes the mean, minimum, and maximum. Valid values for other specs from the same design are still included. Each spec must have at least one valid measurement.

<a id="en-deck-requirements"></a>

## Deck requirements

To use `AutoCircuit`, the deck must meet the following requirements.

<a id="en-1-include-the-parameter-file"></a>

### 1. Include the parameter file

```spice
.include "@PARAM_PATH@"
```

During execution, `@PARAM_PATH@` is replaced with `param_0`, `param_1`, and so on.

<a id="en-2-name-the-design-variables"></a>

### 2. Name the design variables

Use HSPICE parameter expressions such as `'L0'`, `'W0'`, and `'M0'` for design variables to tune.

```spice
MN0 out in 0 0 nmos l='L0' w='W0' m='M0'
R0 out n1 'R0'
C0 n1 0 'C0'
```

Naming rules:

- The prefix consists of English letters and underscores: `L`, `W`, `M`, `R`, `C`, `_Aa_Bce_`, `AaaeE_FG`.
- Within each prefix, use consecutive integer suffixes starting at 0, as in `L0`, `L1`, and `L2`. Even a single variable needs a suffix, as in `R0`.

<a id="en-3-register-spec-locations"></a>

### 3. Register spec locations

Specs are computed by the deck's analyses and `.measure` statements. Add the following option so that `AutoCircuit` can read results in `name = value` format.

```spice
.option measform=2
```

In the JSON configuration, use `specs` to specify the result file suffixes and the spec names to read.

```json
"specs": {
  "ms0": ["negative_total_current_uA"],
  "ma0": ["gain_db", "log10_ugbw", "pm_deg", "cmrr_db"]
}
```

This example registers the specs for `sample/deck_fc`. If the runnable deck is named `0`, current is read from `0.ms0` and the other four specs from `0.ma0`. `AutoCircuit` does not infer measurement files or spec names from the deck.

Spec order follows **the order of entries in `specs`, then the order of names in each array**. In this example, the order is current, gain, log10_ugbw, PM, and CMRR. All four configuration arrays follow this order. Entries within the measurement files may appear in a different order.

Each registered file must contain all names specified for it. A measurement value of `failed` is read as `-1e10` for that spec only. See [Reading measurement results](docs/ADVANCED_USE.md#en-reading-measurement-results) for the distinction between missing files or names and failed measurements.

Write all specs so that higher values are better. For quantities where lower values are better, reverse the sign in the deck. Use existing analysis and `.measure` definitions that satisfy this rule.

<a id="en-minimal-example"></a>

## Minimal example

Suppose you are connecting an HSPICE deck with one design variable, `'R0'`, and one spec, `gain_db`, written to the `ma0` file. Apply the following settings to the existing circuit, analyses, and `.measure` statements.

```spice
.include "@PARAM_PATH@"
.option measform=2

RLOAD out 0 'R0'
```

The code above shows the parts needed to connect the deck. The deck must also contain the existing analysis and `.measure` statements that measure `gain_db`.

The corresponding JSON configuration:

```json
{
  "run_name": "minimal",
  "deck_path": "path/to/deck",
  "specs": {"ma0": ["gain_db"]},
  "reject_spec": [0.0],
  "max_evals": 100,
  "target_spec": [40.0],
  "pre_weight": [0.025],
  "post_weight": [0.0],
  "design_space": {
    "R": [1.0, 100.0, 1.0, "k", true]
  }
}
```

`'R0'` in the deck maps to `"R"` in `design_space`. As the only spec, `gain_db` occupies index 0 in all four spec arrays, with a target of 40 dB.

<a id="en-design-space-definition"></a>

## Design space definition

`design_space` defines a default range for each design variable prefix and any ranges needed for individual variables.

```json
"L": [180, 360, 5, "n", false]
```

Each array contains `[lower, upper, resolution, unit, is_log]`.

- `lower`, `upper`: Lower and upper bounds on the actual value.
- `resolution`: Allowed increment between design variable values. Even when this is `null`, values are written with at most `digits` decimal places.
- `unit`: Unit suffix appended to the value in the parameter file (`""` for none).
- `is_log`: `true` for a logarithmic scale; `false` for a linear scale. Logarithmic scaling requires positive lower and upper bounds.

With this configuration, each `L` value is one of `180n`, `185n`, `190n`, ..., `360n`.

A prefix entry supplies the default for all design variables with that prefix. An individual variable entry overrides the default for that variable only.

```json
"M": [1, 60, 1, "", false],
"M10": [30, 60, 1, "", false]
```

Only `M10` uses the range `30`–`60`; all other `M` variables use `1`–`60`. Each prefix in the deck needs either a default entry or an entry for every individual variable. Entries in `design_space` that do not correspond to variables in the deck are unused.

The solver proposes a value `v` in `[0, 1]`, which is converted to an actual value `x` as follows.

Linear scale:

$$
x = \mathrm{lower} + v(\mathrm{upper} - \mathrm{lower})
$$

Logarithmic scale:

$$
x = 10^{\log_{10}(\mathrm{lower}) + v(\log_{10}(\mathrm{upper}) - \log_{10}(\mathrm{lower}))}
$$

The converted value is rounded to the specified `resolution`. `is_log` does not change the value range, but it can affect solver performance.

<a id="en-fom-definition"></a>

## FoM definition

The FoM is the score that the `Solver` maximizes. The default FoM uses separate calculations before and after the targets are met.

While any target remains unmet, only shortfalls contribute to the score.

$$
\mathrm{pre\_FoM}
= \sum_i \min(\mathrm{spec}_i - \mathrm{target}_i, 0)
\times \mathrm{pre\_weight}_i
$$

A design that meets every target has a `pre_FoM` of 0. The following score is applied to that design.

$$
\mathrm{post\_FoM}
= \sum_i (\mathrm{spec}_i - \mathrm{target}_i)
\times \mathrm{post\_weight}_i
$$

If `early_stop` is `true`, the run stops when the best FoM is 0 or greater. Use the default, `false`, to keep improving the score after the targets are met.

For a custom FoM, see the [FoM contract](docs/ADVANCED_USE.md#en-fom-contract).

<a id="en-result-files"></a>

## Result files

Results are saved in `result_{run_name}` (`result` if `run_name` is empty).

The following files are updated whenever the best FoM improves during the run:

- `best_param`: Parameters of the design with the highest FoM.
- `best_spec`: Specs and FoM of that design.

The default store, `StoreParetoFront`, saves the Pareto set of designs whose specs all meet or exceed `reject_spec` in the results folder.

- `param_0`, `param_1`, ...: Parameters of the designs retained in the archive.
- `result_spec.csv`: Index, FoM, and specs of each design.

See [RESULTS_en.md](docs/RESULTS.md#en) for the folder and file structure, Pareto selection criteria, and performance comparisons using the CSV.

<a id="en-checklist"></a>

## Checklist

- The deck must include `.option measform=2`.
- The suffixes in `specs` must match the HSPICE result files, and each file must contain every spec name registered for it.
- If the deck contains `'L0'`, `design_space` must have an entry for `"L"` or `"L0"`.
- The registration order in `specs` must match the order of `reject_spec`, `target_spec`, `pre_weight`, and `post_weight`.
- When setting these arrays manually, each must have as many entries as there are specs registered in `specs`.
- Reverse the sign in the deck for specs where lower values are better.
- Before running, check whether you need to keep the existing temporary and results folders for the same `run_name`.

See [ADVANCED_USE_en.md](docs/ADVANCED_USE.md#en) for solver, FoM, and store choices, and for custom `Circuit` implementations.

</details>

<details>
<summary><strong>한국어</strong></summary>

<a id="ko"></a>

HACSA-hspice는 HSPICE 기반 analog circuit sizing용 Python interface이다.

<a id="ko-설치"></a>

## 설치

<a id="ko-hspice"></a>

### HSPICE

이 프로그램은 HSPICE deck의 형태를 제한한다. 그 제한을 따르지 않는 독자적인 처리는 [ADVANCED_USE](docs/ADVANCED_USE.md#ko) 참고한다.

<a id="ko-python-의존성"></a>

### Python 의존성

Python 3.6.2 이상.

```bash
python -m pip install -r requirements.txt
```

<a id="ko-실행"></a>

## 실행

`hacsa.py`에 JSON 설정 파일을 전달한다.

```bash
python hacsa.py sample_manual.json
```

이 명령은 `sample/deck_fc`의 최적화 결과를 `result_0`에 저장한다. 실행 시작 시 기존 `temp_0`과 `result_0`은 교체된다.

<a id="ko-설정-파일"></a>

### 설정 파일

target과 weight를 직접 지정한 설정 예제이다(`sample_manual.json` 참고).

```json
{
  "run_name": 0,
  "deck_path": "sample/deck_fc",
  "deck_imports": ["sample/pdk"],
  "specs": {
    "ms0": ["negative_total_current_uA"],
    "ma0": ["gain_db", "log10_ugbw", "pm_deg", "cmrr_db"]
  },
  "reject_spec": [-100.0, 0.0, 6.0, 40.0, 40.0],
  "max_evals": 20000,
  "target_spec": [-5.2232, 38.2163, 6.6529, 60.0, 70.4884],
  "pre_weight": [0.02, 0.025, 0.5, 0.015625, 0.025],
  "post_weight": [0.02, 0.025, 0.5, 0.0, 0.025],
  "design_space": {
    "R": [1.0, 1000.0, null, "k", true],
    "C": [10, 1000, null, "f", false],
    "L": [180, 360, 5, "n", false],
    "W": [45, 90, 5, "n", false],
    "M": [1, 60, 1, "", false],
    "M0": [20, 60, 1, "", false]
  }
}
```

- `run_name`: 실행 식별자. 빈 문자열이면 `temp`와 `result`, `"xxx"`이면 `temp_xxx`와 `result_xxx`.
- `deck_path`: deck 경로. 상대 경로는 `hacsa.py` 폴더 기준이며, 절대 경로도 지원.
- `deck_imports`: deck과 같은 실행 폴더에 복사할 파일 경로 목록. deck_fc의 `.include "pdk"`를 위해 `sample/pdk`를 지정한다. 여러 파일은 [ ] 안에 순서대로 나열하고, 보조 파일이 없으면 생략한다.
- `specs`: HSPICE 결과 파일별로 읽을 spec 이름. `ms0`, `ma0`는 파일 suffix이며, 항목과 이름을 나열한 순서가 spec 순서이다([Spec 위치 등록](#ko-3-spec-위치-등록) 참고).
- `reject_spec`: 보관할 design의 spec 하한. 하나라도 미달하면 design을 제외한다(생략 시 필터 미적용). 기본 저장소는 통과한 design 중 Pareto set을 보관한다.
- `max_evals`: solver의 평가 종료 기준 횟수. batch 단위로 평가하므로 실제 횟수는 조금 넘을 수 있다.
- `early_stop`: target 달성 시 종료 여부(기본값 `false`).
- `target_spec`: 각 spec의 최소 목표값(생략 시 자동 설정).
- `pre_weight`: 하나라도 target 미달일 때 FoM에 적용할 양의 가중치.
- `post_weight`: 모든 target 달성 시 FoM에 적용할 0 이상의 가중치. 두 weight 중 하나라도 생략하면 둘 다 자동 설정.
- `design_space`: deck의 설계 변수별 [탐색 범위](#ko-design-space-정의). 배열 순서는 `[lower, upper, resolution, unit, is_log]`.

`reject_spec`, `target_spec`, `pre_weight`, `post_weight`는 모두 `specs`의 등록 순서를 따른다(`sample/deck_fc`의 대응은 아래 표 참조).

| index | `specs`에 등록한 spec | `reject_spec` | `target_spec` | `pre_weight` | `post_weight` |
|---:|---|---:|---:|---:|---:|
| 0 | `negative_total_current_uA` | -100.0 | -5.2232 | 0.02 | 0.02 |
| 1 | `gain_db` | 0.0 | 38.2163 | 0.025 | 0.025 |
| 2 | `log10_ugbw` | 6.0 | 6.6529 | 0.5 | 0.5 |
| 3 | `pm_deg` | 40.0 | 60.0 | 0.015625 | 0.0 |
| 4 | `cmrr_db` | 40.0 | 70.4884 | 0.025 | 0.025 |

JSON에 추가할 수 있는 선택 항목이다.

- `solver`: [사용할 solver](#ko-solver-선택)(기본값 `"CMAES"`).
- `auto_fom`: 자동 설정용 Sobol 표본 수의 지수(기본값 `7`). 표본 수는 `2^auto_fom`.
- `parallel`: HSPICE의 design 평가 방식. `true`는 병렬(기본값), `false`는 순차 평가.
- `digits`: deck에 기록할 파라미터의 최대 소수 자릿수(기본값 `3`, 0.xxx). `resolution`이 `null`이면 탐색 간격은 `10**(-digits)`.

<a id="ko-solver-선택"></a>

### Solver 선택

다른 solver를 사용하려면 JSON에 `solver`를 추가한다.

```json
"solver": "LSHADE"
```

기본 지원 solver와 기반 논문:

- `CMAES`: Nikolaus Hansen and Andreas Ostermeier, [*Adapting Arbitrary Normal Mutation Distributions in Evolution Strategies: The Covariance Matrix Adaptation*](https://doi.org/10.1109/ICEC.1996.542381), 1996.
- `LSHADE`: Ryoji Tanabe and Alex S. Fukunaga, [*Improving the Search Performance of SHADE Using Linear Population Size Reduction*](https://doi.org/10.1109/CEC.2014.6900380), 2014.
- `TuRBO`: David Eriksson, Michael Pearce, Jacob Gardner, Ryan D. Turner, Matthias Poloczek, [*Scalable Global Optimization via Local Bayesian Optimization*](https://proceedings.neurips.cc/paper/2019/hash/6c990b7aca7bc7058f5e98ea909e924b-Abstract.html), 2019.

`Solver` interface를 구현해 `Solver` 폴더에 두면 custom solver를 사용할 수 있다. 파일과 클래스 이름은 같아야 한다(`XXX.py` → `class XXX`).

<a id="ko-target과-weight-자동-설정"></a>

### Target과 weight 자동 설정

입력한 target과 weight pair는 그대로 쓰고, 빠진 쪽만 HSPICE로 Sobol 표본을 평가해 구한다.

| `target_spec` | `pre_weight`, `post_weight` | 동작 |
|---|---|---|
| 입력 | 둘 다 입력 | 자동 표본 평가 없음 |
| 생략 | 둘 다 입력 | target만 자동 설정 |
| 입력 | 하나 이상 생략 | 두 weight을 자동 설정 |
| 생략 | 하나 이상 생략 | target과 두 weight을 모두 자동 설정 |

`sample_auto.json`처럼 target과 weight를 모두 생략하면 자동 설정한 값을 FoM 튜닝의 시작점으로 쓸 수 있다.

```bash
python hacsa.py sample_auto.json
```

`sample_auto.json`은 다음과 같다.

```json
{
  "run_name": 0,
  "deck_path": "sample/deck_ts",
  "deck_imports": ["sample/pdk"],
  "specs": {
    "ms0": ["negative_total_current_uA"],
    "ma0": ["gain_db", "log10_ugbw", "pm_deg"]
  },
  "reject_spec": [-100.0, 0.0, 6.0, 40.0],
  "max_evals": 20000,
  "design_space": {
    "I": [1.0, 5.0, null, "u", true],
    "C": [10, 1000, null, "f", false],
    "L": [180, 360, 5, "n", false],
    "W": [45, 90, 5, "n", false],
    "M": [1, 60, 1, "", false],
    "M0": [20, 60, 1, "", false]
  }
}
```

`auto_fom`을 추가해 target·weight 자동 설정용 표본 수를 기본 $2^7 = 128$에서 바꾼다. 이 평가는 solver 실행 전에 수행하며 `max_evals`에 포함되지 않는다.

자동 계산은 각 spec의 측정 실패값만 제외하고 mean/min/max를 구한다. 같은 design의 다른 spec이 정상이면 그 값은 계산에 포함한다. 각 spec에는 정상 측정값이 하나 이상 필요하다.

<a id="ko-deck-작성-규칙"></a>

## Deck 작성 규칙

`AutoCircuit`을 사용하려면 deck이 다음 규칙을 만족해야 한다.

<a id="ko-1-param-파일-include"></a>

### 1. Param 파일 include

```spice
.include "@PARAM_PATH@"
```

`@PARAM_PATH@`는 실행 중 `param_0`, `param_1`, ...로 치환된다.

<a id="ko-2-설계-변수-이름"></a>

### 2. 설계 변수 이름

튜닝할 설계 변수는 HSPICE parameter expression인 `'L0'`, `'W0'`, `'M0'` 형식으로 지정한다.

```spice
MN0 out in 0 0 nmos l='L0' w='W0' m='M0'
R0 out n1 'R0'
C0 n1 0 'C0'
```

이름 규칙은 다음과 같다.

- prefix는 영문자와 `_`의 조합이다: `L`, `W`, `M`, `R`, `C`, `_Aa_Bce_`, `AaaeE_FG`
- 같은 prefix의 변수에는 `L0`, `L1`, `L2`처럼 0부터 연속된 정수 suffix를 붙인다. 변수가 하나여도 `R0`처럼 번호를 붙인다.

<a id="ko-3-spec-위치-등록"></a>

### 3. Spec 위치 등록

spec은 deck의 analysis와 `.measure`로 계산한다. `AutoCircuit`이 `name = value` 형식의 결과를 읽도록 다음 option을 넣는다.

```spice
.option measform=2
```

JSON의 `specs`에는 결과 파일 suffix와 읽을 spec 이름을 지정한다.

```json
"specs": {
  "ms0": ["negative_total_current_uA"],
  "ma0": ["gain_db", "log10_ugbw", "pm_deg", "cmrr_db"]
}
```

`sample/deck_fc`의 등록 예이다. 실행용 deck 이름이 `0`이면 `0.ms0`에서 전류를, `0.ma0`에서 나머지 네 spec을 읽는다. `AutoCircuit`은 deck을 해석해 측정 파일이나 spec 이름을 추론하지 않는다.

spec 순서는 **`specs`의 항목 순서 → 각 배열의 이름 순서**이다. 위 예는 전류, gain, log10_ugbw, PM, CMRR 순서이며 네 설정 배열도 이 순서를 따른다. 측정 파일 안의 기록 순서는 달라도 된다.

각 등록 파일에 지정한 이름이 모두 있어야 한다. 측정값이 `failed`이면 그 spec만 `-1e10`으로 읽는다. 누락된 파일·이름과 실패값의 차이는 [측정 결과 읽기](docs/ADVANCED_USE.md#ko-측정-결과-읽기)를 참고한다.

모든 spec은 클수록 좋게 저장해야 한다. 작을수록 좋은 값은 deck에서 부호를 반전한다. analysis와 `.measure`는 이 규칙을 만족하는 기존 정의를 사용한다.

<a id="ko-최소-예제"></a>

## 최소 예제

설계 변수 `'R0'` 하나와 `ma0` 파일에 출력하는 spec `gain_db` 하나가 있는 HSPICE deck을 연결한다고 하자. 기존 회로·analysis·`.measure`에 다음 설정을 적용한다.

```spice
.include "@PARAM_PATH@"
.option measform=2

RLOAD out 0 'R0'
```

위 코드는 연결에 필요한 부분이다. `gain_db`를 측정하는 기존 analysis와 `.measure`도 deck에 있어야 한다.

이 deck에 대응하는 JSON 설정:

```json
{
  "run_name": "minimal",
  "deck_path": "path/to/deck",
  "specs": {"ma0": ["gain_db"]},
  "reject_spec": [0.0],
  "max_evals": 100,
  "target_spec": [40.0],
  "pre_weight": [0.025],
  "post_weight": [0.0],
  "design_space": {
    "R": [1.0, 100.0, 1.0, "k", true]
  }
}
```

deck의 `'R0'`는 `design_space`의 `"R"`에 대응한다. `gain_db`는 유일한 spec이므로 네 spec 배열의 index 0에 대응하며 target은 40 dB이다.

<a id="ko-design-space-정의"></a>

## Design Space 정의

`design_space`는 각 설계 변수 prefix의 기본 범위와 필요한 개별 범위를 정의한다.

```json
"L": [180, 360, 5, "n", false]
```

배열의 의미는 `[lower, upper, resolution, unit, is_log]`이다.

- `lower`, `upper`: 실제 값의 하한과 상한
- `resolution`: 설계 변수 값의 허용 간격. `null`이어도 소수점 아래 `digits`자리까지만 표시된다.
- `unit`: param 파일의 값 뒤에 붙일 단위(없으면 `""`).
- `is_log`: log scale이면 `true`, linear scale이면 `false`. log scale의 하한과 상한은 양수여야 한다.

이 설정의 `L` 값은 `180n`, `185n`, `190n`, ..., `360n` 중 하나이다.

prefix 항목은 같은 prefix의 모든 설계 변수에 적용할 기본값이다. 개별 변수 항목은 해당 변수의 기본값만 덮어쓴다.

```json
"M": [1, 60, 1, "", false],
"M10": [30, 60, 1, "", false]
```

`M10`만 `30`~`60`, 나머지 `M` 변수는 `1`~`60`을 사용한다. deck의 각 prefix에는 기본 항목 또는 모든 개별 항목이 필요하다. deck에 없는 `design_space` 항목은 사용하지 않는다.

solver가 제안한 `[0, 1]` 범위의 값 `v`는 실제 값 `x`로 다음처럼 변환된다.

linear scale:

$$
x = \mathrm{lower} + v(\mathrm{upper} - \mathrm{lower})
$$

log scale:

$$
x = 10^{\log_{10}(\mathrm{lower}) + v(\log_{10}(\mathrm{upper}) - \log_{10}(\mathrm{lower}))}
$$

변환한 값은 `resolution`에 맞춰 반올림된다. `is_log`는 값의 범위를 바꾸지 않지만 solver 성능에는 영향을 줄 수 있다.

<a id="ko-fom-정의"></a>

## FoM 정의

FoM은 `Solver`가 최대화하는 점수이다. 기본 FoM은 target 달성 전과 후를 나누어 계산한다.

target을 만족하지 못한 동안에는 부족분만 반영한다.

$$
\mathrm{pre\_FoM}
= \sum_i \min(\mathrm{spec}_i - \mathrm{target}_i, 0)
\times \mathrm{pre\_weight}_i
$$

모든 target을 만족한 design의 `pre_FoM`은 0이다. 이 design에는 다음 점수를 적용한다.

$$
\mathrm{post\_FoM}
= \sum_i (\mathrm{spec}_i - \mathrm{target}_i)
\times \mathrm{post\_weight}_i
$$

`early_stop`이 `true`이면 최고 FoM이 0 이상일 때 종료한다. 달성 후 점수를 더 높이려면 기본값 `false`를 사용한다.

독자적인 FoM 설계는 [FoM Contract](docs/ADVANCED_USE.md#ko-fom-contract)를 참고한다.

<a id="ko-결과-파일"></a>

## 결과 파일

결과는 `result_{run_name}` 디렉토리에 저장한다(`run_name`이 비면 `result`).

실행 중 best FoM과 함께 갱신되는 파일:

- `best_param`: FoM이 가장 큰 design의 parameter
- `best_spec`: 해당 design의 spec과 FoM

기본 저장소 `StoreParetoFront`는 모든 spec이 `reject_spec` 이상인 design 중 Pareto set을 result 디렉토리에 저장한다.

- `param_0`, `param_1`, ...: archive에 남은 design의 parameter
- `result_spec.csv`: 각 design의 index, FoM, spec

폴더·파일 구조, Pareto 선별 기준, CSV 성능 비교는 [RESULTS.md](docs/RESULTS.md#ko)를 참고한다.

<a id="ko-점검-항목"></a>

## 점검 항목

- deck에 `.option measform=2`가 있어야 한다.
- `specs`의 suffix가 HSPICE 결과 파일과 일치하고, 각 파일에 등록한 spec 이름이 모두 있어야 한다.
- deck에 `'L0'`가 있다면 `design_space`에 `"L"`이나 `"L0"` 항목이 있어야 한다.
- `specs`의 등록 순서와 `reject_spec`, `target_spec`, `pre_weight`, `post_weight` 순서가 일치해야 한다.
- 수동 설정에서는 네 spec 배열의 길이가 `specs`에 등록한 spec 개수와 같아야 한다.
- 작을수록 좋은 spec은 deck에서 부호를 반전해야 한다.
- 같은 `run_name`의 기존 temp/result 폴더가 필요한지 확인한 뒤 실행한다.

solver·FoM·store 선택과 custom `Circuit`은 [ADVANCED_USE.md](docs/ADVANCED_USE.md#ko)를 참고한다.

</details>

## License

This project is available for **academic and non-commercial research use** under the terms of the [iElab Research License](LICENSE.md).

Use by for-profit organizations, including internal research, evaluation, and product-related development, requires prior written permission.

For commercial licensing or other permissions, please contact **iElab@hanyang University (PI: Jaemyung Lim)** at **limjm@hanyang.ac.kr**.
