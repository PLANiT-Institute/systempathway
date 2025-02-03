from pyomo.environ import (
    NonNegativeReals, Binary, SolverFactory, value, Any
)
from pyomo.util.infeasible import log_infeasible_constraints
import pandas as pd

import importlib
import utils.load_data as _ld
import utils.modelbuilder as _md

importlib.reload(_ld)
importlib.reload(_md)

def main(**kwargs):

    carbonprice_include = kwargs.get('carboprice_include', False)
    max_renew = kwargs.get('max_renew', 10)
    allow_replace_same_technology = kwargs.get('allow_replace_same_technology', False
                                               )
    # --------------------------
    # 7. Load Data
    # --------------------------
    file_path = 'database/steel_data.xlsx'  # Update with your actual file path
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
    solver = SolverFactory('glpk')  # Ensure GLPK is installed
    if not solver.available():
        raise RuntimeError("GLPK solver is not available. Please install it or choose another solver.")

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

    # --------------------------
    # 11. Initialize Annual Global Metrics
    # --------------------------
    annual_global_capex = {yr: 0.0 for yr in model.years}
    annual_global_renewal_cost = {yr: 0.0 for yr in model.years}
    annual_global_opex = {yr: 0.0 for yr in model.years}
    annual_global_total_emissions = {yr: 0.0 for yr in model.years}

    # --------------------------
    # 12. Display and Collect Detailed Results
    # --------------------------
    for sys in model.systems:
        print(f"\n=== Results for Furnace Site: {sys} ===\n")

        # Initialize lists to store yearly data
        yearly_metrics = []
        fuel_consumption_table = []
        material_consumption_table = []
        technology_statuses = []

        # Extract baseline technology information
        baseline_tech = data['baseline'].loc[sys, 'technology']
        introduced_year = data['baseline'].loc[sys, 'introduced_year']
        lifespan = model.lifespan_param[baseline_tech]

        for yr in model.years:
            # Calculate Costs
            # CAPEX: Only applied if the technology is replaced
            capex_cost = sum(
                model.capex_param[tech, yr] * value(model.replace_prod_active[sys, tech, yr])
                for tech in model.technologies
            )

            # Adjust CAPEX for the first year and baseline technology
            if yr == min(model.years):
                if baseline_tech in model.technologies:
                    capex_adjustment = model.capex_param[baseline_tech, yr] * (
                        (lifespan - (yr - introduced_year)) / lifespan
                    ) * value(model.production[sys, yr])
                    capex_cost += capex_adjustment
                else:
                    print(f"Warning: Baseline technology '{baseline_tech}' not found in model.technologies for system '{sys}'.")

            # Renewal Cost: Only applied if the technology is renewed
            renewal_cost = sum(
                model.renewal_param[tech, yr] * value(model.renew_prod_active[sys, tech, yr])
                for tech in model.technologies
            )

            # OPEX: Always applied for active technologies
            opex_cost = sum(
                model.opex_param[tech, yr] * value(model.prod_active[sys, tech, yr])
                for tech in model.technologies
            )

            # Calculate Emissions
            total_emissions = sum(
                value(model.emission_by_tech[sys, tech, yr]) for tech in model.technologies
            )

            # Calculate Fuel Consumption
            fuel_consumption = {
                fuel: value(model.fuel_consumption[sys, fuel, yr]) for fuel in model.fuels
            }

            # Calculate Material Consumption
            material_consumption = {
                mat: value(model.material_consumption[sys, mat, yr]) for mat in model.materials
            }

            # Collect Yearly Metrics
            yearly_metrics.append({
                "Year": yr,
                "CAPEX": capex_cost,
                "Renewal Cost": renewal_cost,
                "OPEX": opex_cost,
                "Total Emissions": total_emissions
            })

            # Collect Fuel Consumption Data
            fuel_consumption_table.append({"Year": yr, **fuel_consumption})

            # Collect Material Consumption Data
            material_consumption_table.append({"Year": yr, **material_consumption})

            # Collect Technology Statuses
            for tech in model.technologies:
                technology_statuses.append({
                    "Year": yr,
                    "Technology": tech,
                    "Continue": value(model.continue_technology[sys, tech, yr]),
                    "Replace": value(model.replace[sys, tech, yr]),
                    "Renew": value(model.renew[sys, tech, yr]),
                    "Active": value(model.active_technology[sys, tech, yr])
                })

            # Accumulate Annual Global Metrics
            annual_global_capex[yr] += capex_cost
            annual_global_renewal_cost[yr] += renewal_cost
            annual_global_opex[yr] += opex_cost
            annual_global_total_emissions[yr] += total_emissions

        # Convert Yearly Metrics to DataFrame
        costs_df = pd.DataFrame(yearly_metrics).set_index("Year")
        print("=== Costs and Emissions by Year ===")
        print(costs_df)

        # Convert Fuel Consumption to DataFrame
        fuel_df = pd.DataFrame(fuel_consumption_table).set_index("Year")
        print("\n=== Fuel Consumption by Year ===")
        print(fuel_df)

        # Convert Material Consumption to DataFrame
        material_df = pd.DataFrame(material_consumption_table).set_index("Year")
        print("\n=== Material Consumption by Year ===")
        print(material_df)

        # Display Technology Statuses
        print("\n=== Technology Statuses ===")

        technology_df = pd.DataFrame(technology_statuses)

        # Filter rows where at least one status indicator is 1
        technology_df_filtered = technology_df[
            technology_df[['Active', 'Continue', 'Replace', 'Renew']].sum(axis=1) >= 1
            ]

        # Set MultiIndex if 'System' is available
        if 'System' in technology_df_filtered.columns:
            technology_df_filtered.set_index(['System', 'Year', 'Technology'], inplace=True)
        else:
            technology_df_filtered.set_index(['Year', 'Technology'], inplace=True)

        # Rearrange columns
        desired_columns = ['Continue', 'Replace', 'Renew', 'Active']
        technology_df_filtered = technology_df_filtered[desired_columns]

        # Display the DataFrame
        print("\n=== Technology Statuses ===\n")
        print(technology_df_filtered)


    # --------------------------
    # 13. Display Annual Global Metrics
    # --------------------------
    print("\n=== Annual Global Total Costs, Emissions, Fuel Consumption, and Material Consumption ===")
    annual_summary = []

    # Initialize annual global metrics for fuel and material consumption
    annual_global_fuel_consumption = {yr: {fuel: 0.0 for fuel in model.fuels} for yr in model.years}
    annual_global_material_consumption = {yr: {mat: 0.0 for mat in model.materials} for yr in model.years}

    # Aggregate data
    for yr in sorted(model.years):
        total_cost = annual_global_capex[yr] + annual_global_renewal_cost[yr] + annual_global_opex[yr]

        # Accumulate fuel and material consumption
        for sys in model.systems:
            for fuel in model.fuels:
                annual_global_fuel_consumption[yr][fuel] += value(model.fuel_consumption[sys, fuel, yr])
            for mat in model.materials:
                annual_global_material_consumption[yr][mat] += value(model.material_consumption[sys, mat, yr])

        annual_summary.append({
            "Year": yr,
            "Total CAPEX": annual_global_capex[yr],
            "Total Renewal Cost": annual_global_renewal_cost[yr],
            "Total OPEX": annual_global_opex[yr],
            "Total Cost": total_cost,
            "Total Emissions": annual_global_total_emissions[yr],
            **{f"Fuel Consumption ({fuel})": annual_global_fuel_consumption[yr][fuel] for fuel in model.fuels},
            **{f"Material Consumption ({mat})": annual_global_material_consumption[yr][mat] for mat in model.materials},
        })

    # Create a DataFrame for the annual summary
    annual_summary_df = pd.DataFrame(annual_summary).set_index("Year")
    # annual_summary_df.to_excel("model_results.xlsx")
    print(annual_summary_df)

    # Optionally, export the annual summary to Excel or another format

    # --------------------------
    # 14. Export Results to Excel
    # --------------------------
    # export_results_to_excel(model, annual_global_capex, annual_global_renewal_cost, annual_global_opex, annual_global_total_emissions)
    # print("\n=== Results have been exported to 'model_results.xlsx' ===\n")

if __name__ == "__main__":

    main(carboprice_include=False,
         max_renew = 1,
         allow_replace_same_technology = False)
