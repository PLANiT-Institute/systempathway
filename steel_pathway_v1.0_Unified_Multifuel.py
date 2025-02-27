from pyomo.environ import *

from pyomo.util.infeasible import log_infeasible_constraints
import pandas as pd

import importlib
import utils.load_data as _ld
import utils.modelbuilder as _md

importlib.reload(_ld)
importlib.reload(_md)

def main(file_path, **kwargs):

    carbonprice_include = kwargs.get('carboprice_include', False)
    max_renew = kwargs.get('max_renew', 10)
    allow_replace_same_technology = kwargs.get('allow_replace_same_technology', False
                                               )
    # --------------------------
    # 7. Load Data
    # --------------------------

    data = _ld.load_data(file_path)

    # --------------------------
    # 8. Build the Unified Model
    # --------------------------
    model = _md.build_unified_model(data,
                                carbonprice_include=carbonprice_include,
                                max_renew=max_renew,
                                allow_replace_same_technology=allow_replace_same_technology)


    # --------------------------
    # 9. Solve the Model
    # --------------------------
    # Try solving
    solver = SolverFactory("glpk")

    if not solver.available():
        raise RuntimeError("Solver is not available.")

    result = solver.solve(model, tee=True)

    # --------------------------
    # 10. Check Solver Status
    # --------------------------
    if (result.solver.status == 'ok') and (result.solver.termination_condition == 'optimal'):
        print("\n=== Solver found an optimal solution. ===\n")
    elif result.solver.termination_condition == 'infeasible':
        print("\n=== Solver found the model to be infeasible. ===\n")
        log_infeasible_constraints(model)
        return  # Exit the function as no solution exists
    else:
        # Something else is wrong
        print(f"\n=== Solver Status: {result.solver.status} ===\n")
        print(f"=== Termination Condition: {result.solver.termination_condition} ===\n")
        return  # Exit the function as the solution is not optimal


    return "Work"

if __name__ == "__main__":
    file_path = 'database/steel_data.xlsx'
    output = main(file_path,
                  carboprice_include=False,
                  max_renew = 10,
                  allow_replace_same_technology = False)
