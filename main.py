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


    # Solve the Model
    solver = SolverFactory('glpk')
    if not solver.available():
        raise RuntimeError("GLPK solver is not available. Please install it or choose another solver.")

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

    # Initialize Annual Global Metrics
    annual_global_capex = {yr: 0.0 for yr in model.years}
    annual_global_renewal_cost = {yr: 0.0 for yr in model.years}
    annual_global_opex = {yr: 0.0 for yr in model.years}
    annual_global_total_emissions = {yr: 0.0 for yr in model.years}
    annual_global_fuel_consumption = {yr: {fuel: 0.0 for fuel in model.fuels} for yr in model.years}
    annual_global_material_consumption = {yr: {mat: 0.0 for mat in model.materials} for yr in model.years}
    annual_global_tech_adoption = {yr: {tech: 0 for tech in model.technologies} for yr in model.years}

    # Collect Results (Facility Level)
    for sys in model.systems:
        print(f"\n=== Results for Furnace Site: {sys} ===\n")
        yearly_metrics = []
        fuel_consumption_table = []
        material_consumption_table = []
        technology_statuses = []

        baseline_tech = data['baseline'].loc[sys, 'technology']
        introduced_year = data['baseline'].loc[sys, 'introduced_year']
        lifespan = model.lifespan_param[baseline_tech]

        for yr in model.years:
            capex_cost = sum(
                model.capex_param[tech, yr] * value(model.replace_prod_active[sys, tech, yr])
                for tech in model.technologies
            )
            if yr == min(model.years) and baseline_tech in model.technologies:
                capex_adjustment = model.capex_param[baseline_tech, yr] * (
                        (lifespan - (yr - introduced_year)) / lifespan
                ) * value(model.production[sys, yr])
                capex_cost += capex_adjustment

            renewal_cost = sum(
                model.renewal_param[tech, yr] * value(model.renew_prod_active[sys, tech, yr])
                for tech in model.technologies
            )
            opex_cost = sum(
                model.opex_param[tech, yr] * value(model.prod_active[sys, tech, yr])
                for tech in model.technologies
            )
            total_emissions = sum(
                value(model.emission_by_tech[sys, tech, yr]) for tech in model.technologies
            )
            fuel_consumption = {fuel: value(model.fuel_consumption[sys, fuel, yr]) for fuel in model.fuels}
            material_consumption = {mat: value(model.material_consumption[sys, mat, yr]) for mat in model.materials}

            yearly_metrics.append({
                "Year": yr, "CAPEX": capex_cost, "Renewal Cost": renewal_cost,
                "OPEX": opex_cost, "Total Emissions": total_emissions
            })
            fuel_consumption_table.append({"Year": yr, **fuel_consumption})
            material_consumption_table.append({"Year": yr, **material_consumption})
            for tech in model.technologies:
                active = value(model.active_technology[sys, tech, yr])
                technology_statuses.append({
                    "Year": yr, "Technology": tech,
                    "Continue": value(model.continue_technology[sys, tech, yr]),
                    "Replace": value(model.replace[sys, tech, yr]),
                    "Renew": value(model.renew[sys, tech, yr]),
                    "Active": active
                })
                annual_global_tech_adoption[yr][tech] += active  # Sum tech adoption

            annual_global_capex[yr] += capex_cost
            annual_global_renewal_cost[yr] += renewal_cost
            annual_global_opex[yr] += opex_cost
            annual_global_total_emissions[yr] += total_emissions
            for fuel in model.fuels:
                annual_global_fuel_consumption[yr][fuel] += fuel_consumption[fuel]
            for mat in model.materials:
                annual_global_material_consumption[yr][mat] += material_consumption[mat]

        costs_df = pd.DataFrame(yearly_metrics).set_index("Year")
        print("=== Costs and Emissions by Year ===")
        print(costs_df)

        fuel_df = pd.DataFrame(fuel_consumption_table).set_index("Year")
        print("\n=== Fuel Consumption by Year ===")
        print(fuel_df)

        material_df = pd.DataFrame(material_consumption_table).set_index("Year")
        print("\n=== Material Consumption by Year ===")
        print(material_df)

        technology_df = pd.DataFrame(technology_statuses)
        technology_df_filtered = technology_df[
            technology_df[['Active', 'Continue', 'Replace', 'Renew']].sum(axis=1) >= 1]
        technology_df_filtered.set_index(['Year', 'Technology'], inplace=True)
        desired_columns = ['Continue', 'Replace', 'Renew', 'Active']
        technology_df_filtered = technology_df_filtered[desired_columns]
        print("\n=== Technology Statuses ===\n")
        print(technology_df_filtered)

    # Display Annual Global Metrics (Enhanced)
    print("\n=== Annual Global Total Costs, Emissions, Fuel, Material Consumption, and Technology Adoption ===")
    annual_summary = []
    for yr in sorted(model.years):
        total_cost = annual_global_capex[yr] + annual_global_renewal_cost[yr] + annual_global_opex[yr]
        annual_summary.append({
            "Year": yr,
            "Total CAPEX": annual_global_capex[yr],
            "Total Renewal Cost": annual_global_renewal_cost[yr],
            "Total OPEX": annual_global_opex[yr],
            "Total Cost": total_cost,
            "Total Emissions": annual_global_total_emissions[yr],
            **{f"Fuel Consumption ({fuel})": annual_global_fuel_consumption[yr][fuel] for fuel in model.fuels},
            **{f"Material Consumption ({mat})": annual_global_material_consumption[yr][mat] for mat in model.materials},
            **{f"Tech Adoption ({tech})": annual_global_tech_adoption[yr][tech] for tech in model.technologies},
        })

    annual_summary_df = pd.DataFrame(annual_summary).set_index("Year")
    print(annual_summary_df)


if __name__ == "__main__":
    file_path = 'database/steel_data.xlsx'
    output = main(file_path,
                  carboprice_include=False,
                  max_renew = 10,
                  allow_replace_same_technology = False)
