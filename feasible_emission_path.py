from pyomo.environ import (
    NonNegativeReals, Binary, SolverFactory, value, Any
)
from pyomo.util.infeasible import log_infeasible_constraints
import pandas as pd
import importlib
import utils.load_data as _ld
import utils.modelbuilder as _md
import utils.output_analysis as _oa
import os
from datetime import datetime

importlib.reload(_ld)
importlib.reload(_md)
importlib.reload(_oa)


def derive_feasible_emission_path(**kwargs):
    carbonprice_include = kwargs.get('carboprice_include', False)
    max_renew = kwargs.get('max_renew', 10)
    allow_replace_same_technology = kwargs.get('allow_replace_same_technology', False)

    # Load Data
    file_path = 'database/steel_data.xlsx'
    data = _ld.load_data(file_path)

    # Build Model without Emission Constraint
    model = _md.build_unified_model(data,
                                    carbonprice_include=carbonprice_include,
                                    max_renew=max_renew,
                                    allow_replace_same_technology=allow_replace_same_technology)

    # Remove emission_limit_constraint (comment out in modelbuilder.py or override here)
    if not carbonprice_include:
        # Temporarily disable constraint for this run
        if hasattr(model, 'emission_limit_constraint'):
            model.emission_limit_constraint.deactivate()

    # Solve Model
    solver = SolverFactory('glpk')
    if not solver.available():
        raise RuntimeError("GLPK solver is not available.")

    result = solver.solve(model, tee=True)

    # Check Solver Status
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

    # Extract Annual Emissions (Feasible Path)
    annual_emissions = {yr: 0.0 for yr in model.years}
    for yr in model.years:
        total_emission = sum(value(model.emission_by_tech[sys, tech, yr])
                             for sys in model.systems for tech in model.technologies)
        annual_emissions[yr] = total_emission

    # Display Feasible Emission Path
    print("\n=== Feasible Greenhouse Gas Emission Reduction Path (ton-CO2) ===\n")
    print("| Year | Total Emissions |")
    print("|------|-----------------|")
    for yr in sorted(annual_emissions.keys()):
        print(f"| {yr:<4} | {annual_emissions[yr]:>15.2f} |")

    # Export to CSV
    output_dir = 'feasible_emission_paths'
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_path = os.path.join(output_dir, f'feasible_emission_path_{timestamp}.csv')
    df = pd.DataFrame([
        {"Year": yr, "Total Emissions": annual_emissions[yr]}
        for yr in sorted(annual_emissions.keys())
    ])
    df.to_csv(csv_path, index=False)
    print(f"\nFeasible emission path exported to: {csv_path}")

    # Optional: Detailed Results (similar to main.py)
    annual_global_capex = {yr: sum(model.capex_param[tech, yr] * value(model.replace_prod_active[sys, tech, yr])
                                   for sys in model.systems for tech in model.technologies) for yr in model.years}
    annual_global_opex = {yr: sum(model.opex_param[tech, yr] * value(model.prod_active[sys, tech, yr])
                                  for sys in model.systems for tech in model.technologies) for yr in model.years}

    print("\n=== Annual Global Costs (Sample) ===")
    print("| Year | CAPEX          | OPEX          |")
    print("|------|----------------|---------------|")
    for yr in sorted(model.years):
        print(f"| {yr:<4} | {annual_global_capex[yr]:>14.2f} | {annual_global_opex[yr]:>13.2f} |")


if __name__ == "__main__":
    derive_feasible_emission_path(
        carbonprice_include=False,
        max_renew=10,  # Increased for flexibility
        allow_replace_same_technology=True  # Allow more switching options
    )