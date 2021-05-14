from pytao import Tao
import numpy as np
import json
import time
from typing import List
from importlib.resources import files
from lcls_live.datamaps import get_datamaps
from lcls_live.datamaps.klystron import KlystronDataMap
from lume_model.variables import ScalarInputVariable, ArrayInputVariable, ArrayOutputVariable, InputVariable, OutputVariable

TAO_OUTKEYS = """ele.name
ele.ix_ele
ele.ix_branch
ele.a.beta
ele.a.alpha
ele.a.eta
ele.a.etap
ele.a.gamma
ele.a.phi
ele.b.beta
ele.b.alpha
ele.b.eta
ele.b.etap
ele.b.gamma
ele.b.phi
ele.x.eta
ele.x.etap
ele.y.eta
ele.y.etap
ele.s
ele.l
ele.e_tot
ele.p0c
ele.mat6
ele.vec0
""".split()

def get_tao(ALL_DATAMAPS, pvdata):
    lines = []
    for dm in ALL_DATAMAPS:
        lines += dm.as_tao(pvdata)
    return lines

class AccModel:
    def __init__(self, pv_defaults="data/PVDATA-2021-04-21T08:10:25.000000-07:00.json"):
        # Basic model with options
        INIT = '-init $LCLS_LATTICE/bmad/models/cu_hxr/tao.init -slice OTR2:END -noplot'

        self.tao = Tao(INIT)

        self.dms = get_datamaps("cu_hxr")

        if pv_defaults:
            with open(pv_defaults) as data_file:
                pvdata = json.load(data_file)  


        #build input variables
        self.input_variables = {}
        for dm in self.dms:
            for pv in dm.pvlist:
                value = pvdata.get(pv)
                if value is None:
                    value = 0

                if isinstance(value, (float, int, type(None))):
                    self.input_variables[pv] = ScalarInputVariable(name=pv, range=[-np.inf, np.inf], default=value)

                elif isinstance(value, (list)):
                    self.input_variables[pv] = ArrayInputVariable(name=pv, default=np.array(value))


        cmds = get_tao(self.dms, pvdata)
        output = self.init_tao(cmds)

        self.output_variables = {}
        for key in TAO_OUTKEYS:
            if key == "ele.name":
                self.output_variables[key] = ArrayOutputVariable(name=key, value_type="string")

            else:
                self.output_variables[key] = ArrayOutputVariable(name=key)

    def init_tao(self, cmds):
        
        init_cmds = """
        set global lattice_calc_on = F
        set lattice model=design ! Reset the lattice
        set ele quad::* field_master = T
        """.split('\n')

        final_cmds = """
        set global lattice_calc_on = T
        !set global plot_on = T
        """.split('\n')

        for cmd in init_cmds:
            self.tao.cmd(cmd)

        for cmd in cmds[1]:
            self.tao.cmd(cmd)

        for cmd in final_cmds:
            self.tao.cmd(cmd)

        output = {k:self.tao.lat_list('*', k) for k in TAO_OUTKEYS}

        n = len(output["ele.name"])

        output["ele.mat6"] = output["ele.mat6"].reshape(len(output["ele.mat6"])//36, 6, 6)
        output["ele.vec0"] = output["ele.vec0"].reshape(len(output["ele.vec0"])//6, 6)

        return output



    def run_tao(self, cmds):
        init_cmds = """
        set global lattice_calc_on = F
        set lattice model=design ! Reset the lattice
        !set ele quad::* field_master = T
        """.split('\n')

        final_cmds = """
        set global lattice_calc_on = T
        !set global plot_on = T
        !sc
        """.split('\n')

        for cmd in init_cmds:
            self.tao.cmd(cmd)

        for cmd in cmds:
            self.tao.cmd(cmd)

        for cmd in final_cmds:
            self.tao.cmd(cmd)

        output = {k:self.tao.lat_list('*', k) for k in TAO_OUTKEYS}

        n = len(output["ele.name"])
        output["ele.mat6"] = output["ele.mat6"].reshape(len(output["ele.mat6"])//36, 6, 6)
        output["ele.vec0"] = output["ele.vec0"].reshape(len(output["ele.vec0"])//6, 6)

        return output


    def evaluate(self, input_variables) -> List[OutputVariable]:

        for variable in input_variables:
            
            self.input_variables[variable.name] = variable

        time1 = time.time()
        cmds = []
        for dm in self.dms:
            pvdata = {variable.name: variable.value for variable in input_variables}

            if isinstance(dm, (KlystronDataMap,)):

                if dm.swrd_pvname:
                    pvdata[dm.swrd_pvname] = self.input_variables[dm.swrd_pvname].value

                if dm.enld_pvname:
                    pvdata[dm.enld_pvname] =self.input_variables[dm.enld_pvname].value

                if dm.phase_pvname:
                    pvdata[dm.phase_pvname] =self.input_variables[dm.phase_pvname].value

                if dm.accelerate_pvname:
                    pvdata[dm.accelerate_pvname] =self.input_variables[dm.accelerate_pvname].value


                if dm.pvlist & pvdata.keys():

                    if dm.has_fault_pvnames:
                        fault_pvs = [self.input_variables[dm.swrd_pvname], self.input_variables[dm.stat_pvname], self.input_variables[dm.hdsc_pvname], self.input_variables[dm.dsta_pvname]]
                        pvdata.update({pv.name: pv.value for pv in fault_pvs})

            cmds += dm.as_tao(pvdata)
            
        cmds = [cmd for cmd in cmds if "! Bad value" not in cmd]
        output = self.run_tao(cmds)

        for variable in self.output_variables.values():
            variable.value = np.array(output[variable.name])
        

        return self.output_variables.values()

if __name__ == "__main__":
    from lume_model.utils import save_variables
    model = AccModel()
    
  #  save_variables(model.input_variables, model.output_variables, "files/model_variables.pickle")