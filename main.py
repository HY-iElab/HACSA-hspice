from os import chdir
from pathlib import Path
chdir(Path(__file__).resolve().parent)

from Instance.AutoCircuit import AutoCircuit
run_name = 0 
circuit = AutoCircuit(run_name = run_name, deck_path="sample/deck_ts", deck_imports=["sample/pdk"], parallel=False, digits=3)
circuit.registerSpecs(
    ms0=["negative_total_current_uA"],
    ma0=["gain_db", "log10_ugbw", "pm_deg"],
)
circuit.setTargetSpec([-5.2232, 38.2163, 6.6529, 60.0])#, 70.4884])
circuit.setPreWeight([1 / 50.0, 1 / 40.0, 1 / 2.0, 1 / 64.0])#, 1 / 40.0])
circuit.setPostWeight([1 / 50.0, 1 / 40.0, 1 / 2.0, 0.0])#, 1 / 40.0])
circuit.setDesignSpace({
    # Design Space: (lower, upper, resolution, unit, is_log)
    "I": (1.0, 5.0, None, "u", True),
    "R": (1.0, 1e3, None, "k", True),
    "C": (10, 1000, None, "f", False),
    "L": (180, 360, 5, "n", False),
    "W": (45, 90, 5, "n", False),
    "M": (1, 60, 1, "", False),
    "M0": (20, 60, 1, "", False),
})
# circuit.autoFoM(k=7, target=False)
# circuit.testDeck()

from Store.StoreParetoFront import StoreParetoFront
store = StoreParetoFront(design_dim=circuit.design_dim
                         , spec_dim=circuit.spec_dim
                         , reject_spec=[-100.0, 0.0, 6.0, 40.0]#, 40.0]
                         , temp_folder=circuit.temp_folder
                         , run_name=run_name)

from Solver.CMAES import *
MAX_EVALS = 20000
solver = CMAES(dim=circuit.design_dim, MAX_EVALS=MAX_EVALS)


import time
start_time = time.time()
evaluations_done = 0
while evaluations_done < MAX_EVALS:
    candidates = solver.ask()

    circuit.design_batch = candidates.copy()
    circuit.evaluateDesign()
    evaluations_done += circuit.batch_size

    store.updateArchive(circuit.design_batch, circuit.spec_batch, circuit.fom_batch)
    if store.updateBestFoM(circuit):
        print(f"[{evaluations_done}/{MAX_EVALS}] best FoM = {store.best_fom}")
        if store.isTargetAcheived(): break  # Comment out to prevent stopping at target. 

    solver.tell(circuit.design_batch, circuit.fom_batch)
store.saveArchive(circuit)

print(f"Simulation: {evaluations_done}\n")
print(f"Best FoM: {store.best_fom:.6f}\n")
print(f"Elapsed Time: {time.time() - start_time:.2f} seconds\n")
