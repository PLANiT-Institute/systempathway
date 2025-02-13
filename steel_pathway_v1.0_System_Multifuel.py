import pandas as pd
from pyomo.environ import (
    NonNegativeReals, Binary, SolverFactory
)

import importlib
import utils.load_data as _ld
import utils.modelbuilder as _md

importlib.reload(_ld)
importlib.reload(_md)

def main(**kwargs):

    carbonprice_include = kwargs.get('carboprice_include', False)
    max_renew = kwargs.get('max_renew', 10)
    allow_replace_same_technology = kwargs.get('allow_replace_same_technology', False)
    # Load data
    file_path = 'database/steel_data.xlsx'
    data = _ld.load_data(file_path)
    solver = SolverFactory('glpk')
    results_dict = {}

    for system_name in data['baseline'].index:
        print(f"\n=== Solving for furnace site: {system_name} ===")

        baseline_row = data['baseline'].loc[system_name]

        # Build and solve the model
        model = _md.build_model_for_system(system_name, baseline_row, data,
                                       carbonprice_include=carbonprice_include,
                                       max_renew=max_renew,
                                       allow_replace_same_technology=allow_replace_same_technology,)
        result = solver.solve(model, tee=True)

        if result.solver.status == 'ok' and result.solver.termination_condition == 'optimal':
            print(f"\n=== Results for {system_name} ===")
            production_value = baseline_row['production']

            yearly_metrics = []
            fuel_consumption_table = []
            material_consumption_table = []

            for yr in model.years:
                # Calculate costs
                capex_cost = sum(
                    model.capex_param[tech, yr] * model.replace[tech, yr].value * production_value
                    for tech in model.technologies
                )

                # Adjust CAPEX for the first year and baseline technology
                if yr == min(model.years):
                    capex_cost += model.capex_param[baseline_row['technology'], yr] * (
                        model.lifespan_param[baseline_row['technology']] - (yr - baseline_row['introduced_year'])
                    ) / model.lifespan_param[baseline_row['technology']] * production_value

                renewal_cost = sum(
                    model.renewal_param[tech, yr] * model.renew[tech, yr].value * production_value
                    for tech in model.technologies
                )
                opex_cost = sum(
                    model.opex_param[tech, yr] * model.active_technology[tech, yr].value * production_value
                    for tech in model.technologies
                )

                # Calculate emissions
                total_emissions = sum(
                    model.emission_by_tech[tech, yr].value for tech in model.technologies
                )

                # Calculate fuel consumption
                fuel_consumption = {
                    fuel: model.fuel_consumption[fuel, yr].value for fuel in model.fuels
                }

                # Calculate material consumption
                material_consumption = {
                    mat: model.material_consumption[mat, yr].value for mat in model.materials
                }

                # Add yearly data
                yearly_metrics.append({
                    "Year": yr,
                    "CAPEX": capex_cost,
                    "Renewal Cost": renewal_cost,
                    "OPEX": opex_cost,
                    "Total Emissions": total_emissions
                })

                # Add to fuel and material consumption tables
                fuel_consumption_table.append({"Year": yr, **fuel_consumption})
                material_consumption_table.append({"Year": yr, **material_consumption})

            # Convert costs to DataFrame
            costs_df = pd.DataFrame(yearly_metrics).set_index("Year")
            print("\n=== Costs and Emissions by Year ===")
            print(costs_df)

            # Convert fuel and material consumption to DataFrames
            fuel_df = pd.DataFrame(fuel_consumption_table).set_index("Year")
            material_df = pd.DataFrame(material_consumption_table).set_index("Year")

            print("\n=== Fuel Consumption by Year ===")
            print(fuel_df)

            print("\n=== Material Consumption by Year ===")
            print(material_df)

            # Extract technology statuses
            technology_statuses = []
            for yr in model.years:
                for tech in model.technologies:
                    technology_statuses.append({
                        "Year": yr,
                        "Technology": tech,
                        "Continue": model.continue_technology[tech, yr].value,
                        "Replace": model.replace[tech, yr].value,
                        "Renew": model.renew[tech, yr].value,
                        "Active": model.active_technology[tech, yr].value
                    })

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

        else:
            print(
                f"Solver failed for {system_name}. Status: {result.solver.status}, Condition: {result.solver.termination_condition}")


if __name__ == "__main__":
    main(carboprice_include=False,
         max_renew = 10,
         allow_replace_same_technology = False)
    # soft lifespan does not work well
