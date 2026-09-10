from importlib import import_module
from json import load
from os import chdir
from pathlib import Path
from sys import argv
from time import time

from Instance.AutoCircuit import AutoCircuit
from Instance.Circuit import default_fom
from Store.StoreParetoFront import StoreParetoFront

project_path = Path(__file__).resolve().parent


def optimize(deck_path, design_space, max_evals, specs, reject_spec=None, target_spec=None,
             pre_weight=None, post_weight=None, auto_fom=7, run_name="",
             deck_imports=(), parallel=True, digits=3, fom=default_fom,
             solver="CMAES", store_type=StoreParetoFront, early_stop=False):
    chdir(project_path)
    circuit = AutoCircuit(
        run_name=run_name,
        deck_path=deck_path,
        deck_imports=deck_imports,
        parallel=parallel,
        digits=digits,
        fom=fom,
    )
    circuit.registerSpecs(**specs)
    circuit.setDesignSpace(design_space)

    auto_target = target_spec is None
    auto_weights = pre_weight is None or post_weight is None

    if auto_target:
        print("Warning: target_spec is missing; using an automatic target.")
    else:
        circuit.setTargetSpec(target_spec)

    if auto_weights:
        print("Warning: pre_weight or post_weight is missing; using automatic weights.")
    else:
        circuit.setPreWeight(pre_weight)
        circuit.setPostWeight(post_weight)

    if auto_target or auto_weights:
        circuit.autoFoM(auto_fom, target=not auto_target, weights=auto_weights)

    store = store_type(
        design_dim=circuit.design_dim,
        spec_dim=circuit.spec_dim,
        reject_spec=reject_spec,
        temp_folder=circuit.temp_folder,
        run_name=run_name,
    )
    solver = getattr(import_module(f"Solver.{solver}"), solver)(
        dim=circuit.design_dim, MAX_EVALS=max_evals
    )

    start_time = time()
    evaluations_done = 0
    while evaluations_done < max_evals:
        candidates = solver.ask()
        circuit.design_batch = candidates.copy()
        circuit.evaluateDesign()
        evaluations_done += circuit.batch_size

        store.updateArchive(circuit.design_batch, circuit.spec_batch, circuit.fom_batch)
        if store.updateBestFoM(circuit):
            print(f"[{evaluations_done}/{max_evals}] best FoM = {store.best_fom}")
            if early_stop and store.isTargetAcheived():
                break

        solver.tell(circuit.design_batch, circuit.fom_batch)

    store.saveArchive(circuit)
    print(f"Simulation: {evaluations_done}\n")
    print(f"Best FoM: {store.best_fom:.6f}\n")
    print(f"Elapsed Time: {time() - start_time:.2f} seconds\n")
    return circuit, store


def run(config):
    return optimize(**config)


if __name__ == "__main__":
    with open(argv[1], encoding="utf-8") as file:
        run(load(file))
