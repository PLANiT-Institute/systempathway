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
    allow_replace_same_technology = kwargs.get('allow_replace_same_technology', False)

    # Load Data
    data = _ld.load_data(file_path)

    # Build the Model
    model = _md.build_unified_model(data,
                                    carbonprice_include=carbonprice_include,
                                    max_renew=max_renew,
                                    allow_replace_same_technology=allow_replace_same_technology)

    solver = SolverFactory('glpk')
    if not solver.available():
        raise RuntimeError("GLPK solver is not available. Please install it or choose another solver.")

    result = solver.solve(model, tee=True)

    if (result.solver.status == 'ok') and (result.solver.termination_condition == 'optimal'):
        print("\n=== Solver found an optimal solution. ===\n")
    elif result.solver.termination_condition == 'infeasible':
        print("\n=== Solver found the model to be infeasible. ===\n")
        log_infeasible_constraints(model)
        return
    else:
        print(f"\n=== Solver Status: {result.solver.status} ===\n")
        print(f"=== Termination Condition: {result.solver.termination_condition} ===\n")
        return

    # Initialize Annual Global Metrics
    annual_global_total_emissions = {yr: 0.0 for yr in model.years}
    annual_global_production = {yr: 0.0 for yr in model.years}

    # Calculate emissions and production for each system
    for sys in model.systems:
        for yr in model.years:
            # Calculate emissions for this system and year
            system_emissions = sum(
                value(model.emission_by_tech[sys, tech, yr]) for tech in model.technologies
            )
            
            # Add to global totals
            annual_global_total_emissions[yr] += system_emissions
            annual_global_production[yr] += value(model.production[sys, yr])

    # Print results
    print("\n=== Annual Global Results ===")
    for yr in model.years:
        print(f"\nYear {yr}:")
        print(f"Total Emissions: {annual_global_total_emissions[yr]:.2f}")
        print(f"Total Production: {annual_global_production[yr]:.2f}")
        if annual_global_production[yr] > 0:
            print(f"Emission Intensity: {annual_global_total_emissions[yr]/annual_global_production[yr]:.4f}")

    return {
        "annual_global_total_emissions": annual_global_total_emissions,
        "annual_global_production": annual_global_production,
        "model": model,
        "result": result
    }

if __name__ == "__main__":
    file_path = 'database/steel_data_0310.xlsx'
    output = main(file_path, 
                 carboprice_include=False,
                 max_renew=2,
                 allow_replace_same_technology=False)
 