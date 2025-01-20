from pyomo.environ import (
    NonNegativeReals, Binary, value
)

import pandas as pd


def display_selected_technologies(model):
    print("\n=== Selected Technologies per System per Year ===\n")
    for sys in model.systems:
        for yr in model.years:
            selected_techs = []
            for tech in model.technologies:
                if pyomo_value(model.active_technology[sys, tech, yr]) > 0.5:
                    selected_techs.append(tech)
            techs_str = ', '.join(selected_techs) if selected_techs else 'None'
            print(f"System: {sys}, Year: {yr}, Technology: {techs_str}")

def display_selected_fuels(model):
    print("\n=== Selected Fuels per System per Year ===\n")
    for sys in model.systems:
        for yr in model.years:
            selected_fuels = []
            for fuel in model.fuels:
                if pyomo_value(model.fuel_select[sys, fuel, yr]) > 0.5:
                    selected_fuels.append(fuel)
            fuels_str = ', '.join(selected_fuels) if selected_fuels else 'None'
            print(f"System: {sys}, Year: {yr}, Fuel: {fuels_str}")

def display_selected_materials(model):
    print("\n=== Selected Materials per System per Year ===\n")
    for sys in model.systems:
        for yr in model.years:
            selected_mats = []
            for mat in model.materials:
                if pyomo_value(model.material_select[sys, mat, yr]) > 0.5:
                    selected_mats.append(mat)
            mats_str = ', '.join(selected_mats) if selected_mats else 'None'
            print(f"System: {sys}, Year: {yr}, Material: {mats_str}")

def display_production_levels(model):
    print("\n=== Production Levels per System per Year ===\n")
    for sys in model.systems:
        for yr in model.years:
            production = pyomo_value(model.production[sys, yr])
            print(f"System: {sys}, Year: {yr}, Production: {production}")

def display_total_cost(model):
    total_cost = pyomo_value(model.total_cost)
    print(f"\n=== Total Cost of the Solution: {total_cost} ===\n")

def export_results_to_excel(model, annual_global_capex, annual_global_renewal_cost, annual_global_opex, annual_global_total_emissions):
    """
    Export detailed results to an Excel file with separate sheets for each furnace site
    and a summary sheet for annual global metrics.
    """
    with pd.ExcelWriter('model_results.xlsx') as writer:
        # Iterate over each system to create separate sheets
        for sys in model.systems:
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
                capex_cost = sum(
                    model.capex_param[tech, yr] * value(model.replace_prod_active[sys, tech, yr])
                    for tech in model.technologies
                )

                if yr == min(model.years):
                    if baseline_tech in model.technologies:
                        capex_adjustment = model.capex_param[baseline_tech, yr] * (
                            (lifespan - (yr - introduced_year)) / lifespan
                        ) * value(model.production[sys, yr])
                        capex_cost += capex_adjustment
                    else:
                        print(f"Warning: Baseline technology '{baseline_tech}' not found in model.technologies for system '{sys}'.")

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

                fuel_consumption = {
                    fuel: value(model.fuel_consumption[sys, fuel, yr]) for fuel in model.fuels
                }

                material_consumption = {
                    mat: value(model.material_consumption[sys, mat, yr]) for mat in model.materials
                }

                yearly_metrics.append({
                    "Year": yr,
                    "CAPEX": capex_cost,
                    "Renewal Cost": renewal_cost,
                    "OPEX": opex_cost,
                    "Total Emissions": total_emissions
                })

                fuel_consumption_table.append({"Year": yr, **fuel_consumption})
                material_consumption_table.append({"Year": yr, **material_consumption})

                for tech in model.technologies:
                    technology_statuses.append({
                        "Year": yr,
                        "Technology": tech,
                        "Continue": value(model.continue_technology[sys, tech, yr]),
                        "Replace": value(model.replace[sys, tech, yr]),
                        "Renew": value(model.renew[sys, tech, yr]),
                        "Active": value(model.active_technology[sys, tech, yr])
                    })

            # Convert Yearly Metrics to DataFrame
            costs_df = pd.DataFrame(yearly_metrics).set_index("Year")
            costs_df.to_excel(writer, sheet_name=f'{sys}_Costs_and_Emissions')

            # Convert Fuel Consumption to DataFrame
            fuel_df = pd.DataFrame(fuel_consumption_table).set_index("Year")
            fuel_df.to_excel(writer, sheet_name=f'{sys}_Fuel_Consumption')

            # Convert Material Consumption to DataFrame
            material_df = pd.DataFrame(material_consumption_table).set_index("Year")
            material_df.to_excel(writer, sheet_name=f'{sys}_Material_Consumption')

            # Convert Technology Statuses to DataFrame
            technology_df = pd.DataFrame(technology_statuses)
            technology_df.to_excel(writer, sheet_name=f'{sys}_Technology_Statuses', index=False)

        # Create a summary sheet for annual global metrics
        annual_summary = []
        for yr in sorted(model.years):
            total_cost = annual_global_capex[yr] + annual_global_renewal_cost[yr] + annual_global_opex[yr]
            annual_summary.append({
                "Year": yr,
                "Total CAPEX": annual_global_capex[yr],
                "Total Renewal Cost": annual_global_renewal_cost[yr],
                "Total OPEX": annual_global_opex[yr],
                "Total Cost": total_cost,
                "Total Emissions": annual_global_total_emissions[yr]
            })

        annual_summary_df = pd.DataFrame(annual_summary).set_index("Year")
        annual_summary_df.to_excel(writer, sheet_name='Annual_Global_Summary')
