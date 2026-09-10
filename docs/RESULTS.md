# Viewing and reusing results / 결과 확인과 재사용

<details open>
<summary><strong>English</strong></summary>

<a id="en"></a>

The optimization results from the following command are saved in `result_0`.

```bash
python hacsa.py sample_manual.json
```

`sample_manual.json` sets `run_name` to `0`. This guide assumes the default circuit, `AutoCircuit`, and the default store, [StoreParetoFront](#en-why-save-the-pareto-set).

<a id="en-generated-folders-and-files"></a>

## Generated folders and files

The folder structure below assumes that some designs are retained. The number of numbered files depends on the evaluation batch size and the number of retained designs.

```text
HACSA-hspice/
├── sample_manual.json
├── sample/
│   ├── deck_fc
│   └── pdk
├── temp_0/
│   ├── pdk
│   ├── 0
│   ├── 1
│   ├── ...
│   ├── param_0
│   ├── param_1
│   ├── ...
│   ├── 0.ms0
│   ├── 0.ma0
│   ├── 1.ms0
│   ├── 1.ma0
│   ├── ...
│   └── error/
└── result_0/
    ├── best_param
    ├── best_spec
    ├── param_0
    ├── param_1
    ├── ...
    └── result_spec.csv
```

| File | Contents and purpose |
|---|---|
| `sample_manual.json` | Run configuration, including search ranges, targets, and weights |
| `sample/deck_fc`, `sample/pdk` | Input deck and the model file it includes |
| `temp_0/pdk` | Model file copied from `deck_imports` into the working folder |
| `temp_0/0`, `temp_0/1`, ... | [Runnable copies](#en-how-files-are-created-during-a-run) of the input deck, named with numbers and no extension |
| `temp_0/param_i` | Parameters used to simulate design i in the batch |
| `temp_0/i.ms0`, `temp_0/i.ma0` | Measurement results from that simulation; values are read by the names registered in `specs` |
| `temp_0/error/` | Folder created during circuit initialization; the current HSPICE parser does not move files here |
| `result_0/best_param`, `result_0/best_spec` | Parameters and specs of the design with the highest FoM; the last line of `best_spec` also records the FoM |
| `result_0/param_i` | Parameters of retained design i, corresponding to the CSV row whose `idx` is i |
| `result_0/result_spec.csv` | [Table of indices, FoMs, and specs](#en-comparing-designs-in-the-csv) for the retained designs |

Other HSPICE output files may also remain in the working folder. The table above lists the files used by HACSA.

The working folder, `temp_0`, reuses the same numbers for each batch, so it does not contain the full evaluation history. `result_0` assigns new numbers to retained designs. **Do not assume that `temp_0/param_0` and `result_0/param_0` represent the same design.**

`best_param` and `best_spec` are saved whenever the best FoM improves during the run. `result_0/param_i` and the CSV are saved when optimization finishes. If no designs pass the retention criteria, the CSV contains only column headers and no `param_i` files are saved.

A `run_name` of `"fc"` uses `temp_fc` and `result_fc`; an empty string uses `temp` and `result`. Rerunning with the same `run_name` replaces both folders, so copy any results you want to keep elsewhere before running again.

To simulate a saved design again, use `.include` in your deck to load its `param_i` or `best_param` file, then run the deck directly with HSPICE.

Find the names registered in `specs` in the new measurement results and compare their values with the selected CSV row. HSPICE computes the specs as defined in the deck; HACSA computes the FoM.

To reproduce a design later, keep its parameters together with the input deck, supporting files such as models, and JSON configuration used for evaluation. These input files are not copied to the results folder automatically.

<a id="en-comparing-designs-in-the-csv"></a>

## Comparing designs in the CSV

Open `result_0/result_spec.csv` in a spreadsheet application. If it appears in a single column, set the delimiter to a comma. For `sample/deck_fc`, the first CSV row is:

```csv
idx,fom,negative_total_current_uA,gain_db,log10_ugbw,pm_deg,cmrr_db
```

- `idx`: Number of the corresponding `param_{idx}` file in the same folder. Use this value to find the file, even after sorting, rather than the row number.
- `fom`: Design's FoM; higher is better. The CSV is not sorted by FoM.
- Remaining columns: Specs in the registration order in `specs`. Each row represents one design.

Sort by `fom` or a spec of interest to select candidates, and plot two specs on the X and Y axes of a scatter plot to explore their relationship. For example, a current consumption versus bandwidth plot shows how much current is needed for higher bandwidth.

The CSV preserves the signs and units used by the deck. With the column order above and the first data row at row 2, use these formulas to recover the physical quantities.

| Stored spec | Meaning | Formula for a new column |
|---|---|---|
| `negative_total_current_uA` | Total current consumption with its sign reversed | `=-C2` gives current in µA |
| `log10_ugbw` | Base-10 logarithm of bandwidth in Hz | `=10^E2` gives bandwidth in Hz |

Fill the formulas down the remaining rows and create a scatter plot of the two new columns.

<a id="en-why-save-the-pareto-set"></a>

## Why save the Pareto set?

`StoreParetoFront` retains the Pareto set of designs whose specs all meet or exceed `reject_spec`. A design is excluded if another is at least as good in every spec and better in at least one.

In this example, higher values are better for both specs (gain and bandwidth), and the retention thresholds are 50 dB and 5 MHz, respectively.

| Design | Gain (dB) | Bandwidth (MHz) | Retention decision |
|---|---:|---:|---|
| A | 60 | 10 | Retain. Higher bandwidth than B |
| B | 65 | 8 | Retain. Higher gain than A |
| C | 55 | 7 | Exclude. Both specs are lower than those of A and B |
| D | 45 | 15 | Exclude. Gain is below the retention threshold |

A and B show the trade-off between gain and bandwidth. Retaining only these candidates lets you choose a design for the performance you need without reviewing many unnecessary parameter files. If all specs are identical, only one design is retained. Selection uses the specs rather than the FoM.

Pareto selection still applies when `reject_spec` is omitted. `target_spec` sets the targets used for the FoM and early stopping; it is separate from the retention thresholds in `reject_spec`.

`best_param` and `best_spec` are saved independently of `reject_spec`, so their design may not appear in the CSV.

<a id="en-how-files-are-created-during-a-run"></a>

## How files are created during a run

The input deck is copied for each design, with its parameter path replaced, and the copy is run. For design 0 in a batch, `temp_0/0` uses the following substitution.

| Input deck | Runnable copy `temp_0/0` |
|---|---|
| `.include "@PARAM_PATH@"` | `.include "param_0"` |

`temp_0/1` uses `param_1` in the same place. The circuit and analysis commands come from the input deck. Files in `deck_imports` are copied into the working folder under their original names. Deck copies are prepared to match the batch size, and `param_i` is rewritten for each evaluation.

Example `param_i` format:

```spice
.param R0=10k
.param C0=100f
```

The solver's design variable values in 0–1 are converted to actual values using the ranges and increments in `design_space`, then written to the file. HSPICE uses the included `.param` values for `'R0'`, `'C0'`, and other variables in the deck. See [Design space definition in the README](../README.md#en-design-space-definition) for the conversion rules.

HSPICE runs copied decks from `temp_0` using commands such as `hspice -i 0`. With `.option measform=2`, measurement results use the format below. For example, current is read from `0.ms0` and gain from `0.ma0`.

```text
negative_total_current_uA = -5.2
gain_db = 60
```

HACSA looks up values by name in the registered files, builds an array in `specs` order, and computes the FoM. It passes the design variables, specs, and FoM to the store. When the best FoM improves, the corresponding parameter file is copied to `best_param`, and the spec array is written to `best_spec` as follows. This example shows the format of a few specs and the FoM.

```text
negative_total_current_uA -5.2
gain_db 60
fom 0.1
```

A measurement value of `failed` is read as `-1e10` for that spec. Missing files or names are separate cases; see [Reading measurement results](ADVANCED_USE.md#en-reading-measurement-results) for how they are handled.

After optimization, the retained design variables are used to create `param_i` files in the results folder, and the specs and FoM are written to the CSV under the same indices. The results folder contains `result_spec.csv` instead of a separate `spec_i` file for each design.

</details>

<details>
<summary><strong>한국어</strong></summary>

<a id="ko"></a>

다음 명령의 최적화 결과는 `result_0` 폴더에서 확인한다.

```bash
python hacsa.py sample_manual.json
```

`sample_manual.json`의 `run_name`은 `0`이다. 기본 회로 `AutoCircuit`과 기본 저장소 [StoreParetoFront](#ko-pareto-set을-저장하는-이유)를 기준으로 설명한다.

<a id="ko-생성되는-폴더와-파일"></a>

## 생성되는 폴더와 파일

보관할 설계안이 있을 때의 폴더 구조이다. 번호가 붙은 파일 수는 평가한 batch 크기와 보관한 설계안 수에 따라 달라진다.

```text
HACSA-hspice/
├── sample_manual.json
├── sample/
│   ├── deck_fc
│   └── pdk
├── temp_0/
│   ├── pdk
│   ├── 0
│   ├── 1
│   ├── ...
│   ├── param_0
│   ├── param_1
│   ├── ...
│   ├── 0.ms0
│   ├── 0.ma0
│   ├── 1.ms0
│   ├── 1.ma0
│   ├── ...
│   └── error/
└── result_0/
    ├── best_param
    ├── best_spec
    ├── param_0
    ├── param_1
    ├── ...
    └── result_spec.csv
```

| 파일 | 내용과 용도 |
|---|---|
| `sample_manual.json` | 탐색 범위, target, weight 등의 실행 설정 |
| `sample/deck_fc`, `sample/pdk` | 입력 deck과 그 deck이 include하는 모델 파일 |
| `temp_0/pdk` | `deck_imports`에서 작업 폴더로 복사한 모델 파일 |
| `temp_0/0`, `temp_0/1`, ... | 입력 deck의 [실행용 복제본](#ko-실행-중-파일이-만들어지는-과정). 확장자 없이 번호를 이름으로 사용한다 |
| `temp_0/param_i` | batch의 i번째 설계안을 시뮬레이션할 parameter |
| `temp_0/i.ms0`, `temp_0/i.ma0` | 해당 시뮬레이션의 measurement 결과. `specs`에 등록한 이름을 읽는다 |
| `temp_0/error/` | 회로 생성 시 만드는 폴더. 현재 HSPICE parser는 여기에 파일을 옮기지 않는다 |
| `result_0/best_param`, `result_0/best_spec` | 최고 FoM을 얻은 설계안의 parameter와 spec. `best_spec` 마지막 줄에는 FoM도 기록한다 |
| `result_0/param_i` | 최종 보관한 i번째 설계안의 parameter. CSV의 `idx`가 i인 행에 대응한다 |
| `result_0/result_spec.csv` | 최종 보관한 설계안들의 [index, FoM, spec을 모은 표](#ko-csv로-설계안-비교하기) |

HSPICE가 만드는 다른 출력 파일도 작업 폴더에 남을 수 있다. 위 표는 HACSA가 사용하는 파일을 보여준다.

작업 폴더 `temp_0`는 batch마다 같은 번호를 재사용하므로 전체 평가 이력은 아니다. `result_0`는 보관한 설계안에 새 번호를 붙인다. **`temp_0/param_0`와 `result_0/param_0`는 같은 설계안이라고 볼 수 없다.**

`best_param`·`best_spec`은 실행 중 최고 FoM 갱신 시, `result_0/param_i`와 CSV는 최적화 완료 시 저장한다. 보관 기준을 통과한 설계안이 없으면 CSV에는 열 이름만 있고 `param_i`는 없다.

`run_name`이 `"fc"`이면 `temp_fc`·`result_fc`, 빈 문자열이면 `temp`·`result` 폴더를 쓴다. 같은 `run_name`으로 재실행하면 두 폴더를 교체하므로, 보관할 결과는 미리 다른 곳으로 복사한다.

저장한 설계안을 다시 시뮬레이션하려면, 사용할 deck에서 해당 `param_i` 또는 `best_param` 파일을 `.include`하고 HSPICE로 직접 실행한다.

재계산한 측정 결과에서 `specs`에 등록한 이름을 찾아 선택한 CSV 행과 비교한다. spec은 HSPICE가 deck의 정의대로, FoM은 HACSA가 계산한다.

나중에 재현하려면 param과 함께 사용한 input deck, 모델 등의 보조 파일, JSON 설정도 보관한다. 이 입력 파일들은 결과 폴더에 자동 복사되지 않는다.

<a id="ko-csv로-설계안-비교하기"></a>

## CSV로 설계안 비교하기

`result_0/result_spec.csv`를 스프레드시트 프로그램으로 연다(한 열로 읽히면 구분자를 쉼표로 지정한다). `sample/deck_fc`의 CSV 첫 행은 다음과 같다.

```csv
idx,fom,negative_total_current_uA,gain_db,log10_ugbw,pm_deg,cmrr_db
```

- `idx`: 같은 폴더의 `param_{idx}` 번호. 정렬 후에도 행 번호 대신 이 값으로 찾는다.
- `fom`: 설계안의 FoM(클수록 좋음). CSV는 FoM 순서로 정렬하지 않는다.
- 나머지 열: `specs`의 등록 순서대로 기록한 spec. 한 행이 한 설계안이다.

`fom`이나 관심 있는 spec으로 정렬해 후보를 고르고, 두 spec을 X·Y축으로 한 산점도로 관계를 살펴본다. 예를 들어 소비 전류·대역폭 산점도에서 대역폭을 높이는 데 필요한 전류를 확인한다.

CSV에는 deck에서 바꾼 부호와 단위가 그대로 저장된다. 위 열 순서에서 첫 데이터가 2행이면 다음 수식으로 물리량을 읽는다.

| 저장된 spec | 의미 | 새 열에 넣을 수식 |
|---|---|---|
| `negative_total_current_uA` | 전체 소비 전류의 부호를 반전한 값 | `=-C2`로 전류를 µA 단위로 읽는다 |
| `log10_ugbw` | Hz 단위 대역폭의 상용로그 | `=10^E2`로 대역폭을 Hz 단위로 읽는다 |

수식을 아래 행에도 적용해 두 열의 산점도를 만든다.

<a id="ko-pareto-set을-저장하는-이유"></a>

## Pareto set을 저장하는 이유

`StoreParetoFront`는 모든 spec이 `reject_spec` 이상인 설계안 중 Pareto set을 보관한다. 다른 설계안이 모든 spec에서 같거나 더 좋고, 하나 이상에서 더 좋으면 해당 설계안은 제외한다.

두 spec(gain, 대역폭)이 클수록 좋고, 저장 하한이 각각 50 dB, 5 MHz인 예시이다.

| 설계안 | Gain (dB) | 대역폭 (MHz) | 보관 여부 |
|---|---:|---:|---|
| A | 60 | 10 | 보관. B보다 대역폭이 높다 |
| B | 65 | 8 | 보관. A보다 gain이 높다 |
| C | 55 | 7 | 제외. A와 B보다 두 spec이 모두 낮다 |
| D | 45 | 15 | 제외. Gain이 저장 하한에 미달한다 |

A와 B는 gain·대역폭의 trade-off를 보여준다. 이런 후보만 남기면 많은 불필요한 parameter 파일을 살피지 않고 필요한 성능에 따라 설계안을 고를 수 있다. 모든 spec이 같으면 하나만 보관하며, 선별에는 FoM 대신 spec들을 사용한다.

`reject_spec`을 생략해도 Pareto 선별은 적용한다. `target_spec`은 FoM과 조기 종료에 쓰는 목표이며, 저장 하한인 `reject_spec`과 별개이다.

`best_param`·`best_spec`은 `reject_spec`과 무관하게 저장되므로, 해당 설계안이 CSV에 없을 수 있다.

<a id="ko-실행-중-파일이-만들어지는-과정"></a>

## 실행 중 파일이 만들어지는 과정

입력 deck은 설계안마다 parameter 경로를 바꿔 복제해 실행한다. batch의 0번째 설계안에 쓸 `temp_0/0`의 치환 예시이다.

| 입력 deck | 실행용 복제본 `temp_0/0` |
|---|---|
| `.include "@PARAM_PATH@"` | `.include "param_0"` |

`temp_0/1`에서는 같은 자리에 `param_1`을 쓴다. 복제본의 회로·해석 명령은 입력 deck에서 가져온다. `deck_imports`의 파일은 원래 이름으로 작업 폴더에 복사한다. 복제본은 batch 크기에 맞춰 준비하고, 평가할 때마다 `param_i`를 다시 쓴다.

`param_i`의 형식 예시이다.

```spice
.param R0=10k
.param C0=100f
```

solver의 0~1 설계 변수는 `design_space`의 범위·간격에 맞는 실제 값으로 변환해 기록한다. HSPICE는 deck의 `'R0'`, `'C0'` 등에 include한 `.param` 값을 사용한다. 변환 규칙은 [README의 Design Space 정의](../README.md#ko-design-space-정의)를 참고한다.

HSPICE는 `temp_0` 안에서 `hspice -i 0`처럼 복제본을 실행한다. `.option measform=2`일 때 측정 결과는 다음 형식이다. 예를 들어 전류는 `0.ms0`, gain은 `0.ma0`에서 읽는다.

```text
negative_total_current_uA = -5.2
gain_db = 60
```

HACSA는 등록한 파일에서 이름으로 값을 찾아 `specs` 순서의 배열을 만들고 FoM을 계산한다. 저장소에는 설계 변수·spec·FoM을 전달한다. 최고 FoM이 갱신되면 해당 param을 `best_param`으로 복사하고, spec 배열을 다음처럼 `best_spec`에 쓴다(일부 spec과 FoM의 형식 예시).

```text
negative_total_current_uA -5.2
gain_db 60
fom 0.1
```

measurement 값이 `failed`이면 해당 spec을 `-1e10`으로 읽는다. 파일이나 이름 자체의 누락은 다른 경우이며, 처리 범위는 [측정 결과 읽기](ADVANCED_USE.md#ko-측정-결과-읽기)를 참고한다.

최적화 후 보관한 설계 변수로 결과 폴더의 `param_i`를 만들고, 같은 번호의 spec·FoM을 CSV에 쓴다. 결과 폴더에는 설계안별 `spec_i` 대신 `result_spec.csv`를 저장한다.

</details>
