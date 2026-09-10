import csv
import os
import shutil
import numpy as np

class Store:
    def __init__(self, design_dim, spec_dim, temp_folder, reject_spec=None, run_name="", deck_name="input/deck"):
        self.run_name = run_name
        self.result_folder = f"result_{run_name}" if run_name != "" else "result"
        self.temp_folder = temp_folder
        self.container_cap = 1024
        self.size = 0
        self.design_container = np.empty((self.container_cap, design_dim), dtype=np.float64)
        self.spec_container = np.empty((self.container_cap, spec_dim), dtype=np.float64)
        self.fom_container = np.empty((self.container_cap,), dtype=np.float64)

        self.best_fom = -float("inf")
        self.reject_spec = (
            np.full(spec_dim, -np.inf, dtype=np.float64)
            if reject_spec is None
            else np.array(reject_spec, dtype=np.float64)
        )
        
        shutil.rmtree(self.result_folder, ignore_errors=True)
        os.makedirs(self.result_folder)
                

    def expandContainer(self):
        new_cap = self.container_cap * 2
        new_spec_container = np.empty((new_cap, self.spec_container.shape[1]), dtype=np.float64)
        new_fom_container = np.empty((new_cap,), dtype=np.float64)
        new_design_container = np.empty((new_cap, self.design_container.shape[1]), dtype=np.float64)    
        new_spec_container[:self.container_cap] = self.spec_container
        new_fom_container[:self.container_cap] = self.fom_container
        new_design_container[:self.container_cap] = self.design_container
        self.spec_container = new_spec_container
        self.fom_container = new_fom_container
        self.design_container = new_design_container
        self.container_cap = new_cap

    def updateArchive(self, design_batch, spec_batch, fom_batch):
        raise NotImplementedError
    
    def saveArchive(self, circuit):
        for name in os.listdir(self.result_folder):
            if name.startswith("param_") or name.startswith("spec_"):
                os.remove(os.path.join(self.result_folder, name))

        circuit.design_batch = self.design_container[: self.size].copy()
        circuit.batch_size = self.size
        circuit.setSizeFromDesignBatch()
        circuit.writeCircuit(self.result_folder)

        with open(os.path.join(self.result_folder, "result_spec.csv"), "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(("idx", "fom", *circuit.spec_names))
            for idx in range(self.size):
                writer.writerow((idx, self.fom_container[idx], *self.spec_container[idx]))
    
    def resetBestFoM(self):
        self.best_fom = -float("inf")

    def updateBestFoM(self, circuit):
        if circuit.valid_batch is None or circuit.valid_batch.all():
            best_idx = int(circuit.fom_batch.argmax())
        else:
            valid_indices = np.flatnonzero(circuit.valid_batch)
            if valid_indices.size == 0:
                return False
            best_idx = int(valid_indices[circuit.fom_batch[valid_indices].argmax()])
        current_best = float(circuit.fom_batch[best_idx])
        if current_best > self.best_fom:
            self.best_fom = current_best
            shutil.copyfile(os.path.join(self.temp_folder, f"param_{best_idx}"), os.path.join(self.result_folder, "best_param"))
            with open(os.path.join(self.result_folder, "best_spec"), "w") as file:
                for name, value in zip(circuit.spec_names, circuit.spec_batch[best_idx]):
                    file.write(f"{name} {value}\n")
                file.write(f"fom {self.best_fom}\n")
            return True
        return False
    
    def isTargetAcheived(self):
        return self.best_fom >= 0.0
