import os
import re
import shutil
import subprocess
import numpy as np


def default_fom(spec_batch, target_spec, pre_weight, post_weight):
    margins = spec_batch - target_spec
    fom_batch = np.minimum(margins, 0.0) @ pre_weight
    target_met = fom_batch == 0.0
    fom_batch[target_met] = margins[target_met] @ post_weight
    return fom_batch


class Circuit:
    def __init__(
        self,
        design_dim: int,
        spec_names: tuple,
        run_name="",
        deck_path="input/deck",
        deck_imports=(),
        fom=default_fom,
    ):
        self.temp_folder = f"temp_{run_name}" if run_name != "" else "temp"
        self.deck_path = deck_path
        self.simulator = "hspice"

        self.design_dim = design_dim        
        self.spec_names = spec_names
        self.spec_dim = len(spec_names)
        self.batch_size = 0
        self.valid_batch = None

        self.design_batch = None
        self.target_spec = np.zeros(self.spec_dim, dtype=np.float64)
        self.pre_weight = np.zeros(self.spec_dim, dtype=np.float64)
        self.post_weight = np.zeros(self.spec_dim, dtype=np.float64)
        self.fom = fom

        shutil.rmtree(self.temp_folder, ignore_errors=True)
        os.makedirs(self.temp_folder)
        os.makedirs(os.path.join(self.temp_folder, "error"))
        for path in deck_imports:
            shutil.copyfile(path, os.path.join(self.temp_folder, os.path.basename(path)))


    def writeCircuit(self, folder): raise NotImplementedError
    def evaluateSpec(self, i, folder): raise NotImplementedError

    def simulateCircuit(self, i):
        subprocess.Popen(
            (self.simulator, "-i", str(i)),
            cwd=self.temp_folder,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).wait()

    def testDeck(self): raise NotImplementedError
    def reserveDesignBatch(self): raise NotImplementedError             

    def evaluateDesign(self):
        self.reserveDesignBatch()    
        self.setSizeFromDesignBatch()        
        self.writeCircuit(self.temp_folder)
        self.renormalizeDesignBatch()
        for i in range(self.batch_size):
            self.simulateCircuit(i)
            self.evaluateSpec(i, self.temp_folder)    
        self.calculateFoM()

    def setTargetSpec(self, target_spec):
        self.target_spec[:] = target_spec
        target_spec = ", ".join(f"{name}: {value}" for name, value in zip(self.spec_names, self.target_spec))
        print(f"Target Spec: {target_spec}")

    def setPreWeight(self, weight):
        self.pre_weight[:] = weight
        weight_spec = ", ".join(f"{name}: {value}" for name, value in zip(self.spec_names, self.pre_weight))
        print(f"Pre-Weight: {weight_spec}")

    def setPostWeight(self, weight):
        self.post_weight[:] = weight
        weight_spec = ", ".join(f"{name}: {value}" for name, value in zip(self.spec_names, self.post_weight))
        print(f"Post-Weight: {weight_spec}")

    def calculateFoM(self):
        self.fom_batch = self.fom(
            self.spec_batch,
            self.target_spec,
            self.pre_weight,
            self.post_weight,
        )
