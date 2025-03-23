from pyomo.environ import *
import os

from pyomo.util.infeasible import log_infeasible_constraints
import pandas as pd

from pyomo.opt import SolverFactory

import importlib
import utils.load_data as _ld
import utils.modelbuilder as _md

importlib.reload(_ld)
importlib.reload(_md)

def main(file_path, **kwargs):

    carbonprice_include = kwargs.get('carboprice_include', False)
    max_renew = kwargs.get('max_renew', 10)
    allow_replace_same_technology = kwargs.get('allow_replace_same_technology', False)

    # 1. Load Data
    data = _ld.load_data(file_path)

    # 2. Build the Unified Model
    model = _md.build_unified_model(data,
                                    carbonprice_include=carbonprice_include,
                                    max_renew=max_renew,
                                    allow_replace_same_technology=allow_replace_same_technology)

    # Solve the Model
    solver = SolverFactory('appsi_highs')
    result = solver.solve(model, tee=True, load_solutions=True)

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
    annual_global_feedstock_consumption = {yr: {mat: 0.0 for mat in model.feedstocks} for yr in model.years}
    annual_global_tech_adoption = {yr: {tech: 0 for tech in model.technologies} for yr in model.years}

    # Dictionary to store system-specific results
    system_results = {}

    # Collect Results (Facility Level)
    for sys in model.systems:
        print(f"\n=== Results for Furnace Site: {sys} ===\n")

        # Prepare empty containers for this system
        system_results[sys] = {
            'yearly_metrics': [],
            'fuel_consumption_table': [],
            'feedstock_consumption_table': [],
            'technology_statuses': []
        }

        # Baseline info
        baseline_tech = data['baseline'].loc[sys, 'technology']
        introduced_year = data['baseline'].loc[sys, 'introduced_year']
        lifespan = model.lifespan_param[baseline_tech]

        for yr in model.years:
            # CAPEX
            capex_cost = sum(
                model.capex_param[tech, yr] * value(model.replace_prod_active[sys, tech, yr])
                for tech in model.technologies
            )
            # If baseline tech is in the first model year
            if yr == min(model.years) and baseline_tech in model.technologies:
                capex_adjustment = (
                    model.capex_param[baseline_tech, yr]
                    * ((lifespan - (yr - introduced_year)) / lifespan)
                    * value(model.production[sys, yr])
                )
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

            # Fuel & feedstock consumption
            fuel_consumption = {fuel: value(model.fuel_consumption[sys, fuel, yr]) for fuel in model.fuels}
            feedstock_consumption = {mat: value(model.feedstock_consumption[sys, mat, yr]) for mat in model.feedstocks}

            # Store system-level data
            system_results[sys]['yearly_metrics'].append({
                "Year": yr,
                "CAPEX": capex_cost,
                "Renewal Cost": renewal_cost,
                "OPEX": opex_cost,
                "Total Emissions": total_emissions
            })
            system_results[sys]['fuel_consumption_table'].append({"Year": yr, **fuel_consumption})
            system_results[sys]['feedstock_consumption_table'].append({"Year": yr, **feedstock_consumption})

            # Technology statuses
            for tech in model.technologies:
                active = value(model.active_technology[sys, tech, yr])
                system_results[sys]['technology_statuses'].append({
                    "Year": yr,
                    "Technology": tech,
                    "Continue": value(model.continue_technology[sys, tech, yr]),
                    "Replace": value(model.replace[sys, tech, yr]),
                    "Renew": value(model.renew[sys, tech, yr]),
                    "Active": active
                })
                annual_global_tech_adoption[yr][tech] += active

            # Update global metrics
            annual_global_capex[yr] += capex_cost
            annual_global_renewal_cost[yr] += renewal_cost
            annual_global_opex[yr] += opex_cost
            annual_global_total_emissions[yr] += total_emissions
            for fuel in model.fuels:
                annual_global_fuel_consumption[yr][fuel] += fuel_consumption[fuel]
            for mat in model.feedstocks:
                annual_global_feedstock_consumption[yr][mat] += feedstock_consumption[mat]

        # Print for console
        costs_df = pd.DataFrame(system_results[sys]['yearly_metrics']).set_index("Year")
        print("=== Costs and Emissions by Year ===")
        print(costs_df)

        fuel_df = pd.DataFrame(system_results[sys]['fuel_consumption_table']).set_index("Year")
        print("\n=== Fuel Consumption by Year ===")
        print(fuel_df)

        feedstock_df = pd.DataFrame(system_results[sys]['feedstock_consumption_table']).set_index("Year")
        print("\n=== feedstock Consumption by Year ===")
        print(feedstock_df)

        technology_df = pd.DataFrame(system_results[sys]['technology_statuses'])
        technology_df_filtered = technology_df[
            technology_df[['Active', 'Continue', 'Replace', 'Renew']].sum(axis=1) >= 1
        ]
        technology_df_filtered.set_index(['Year', 'Technology'], inplace=True)
        desired_columns = ['Continue', 'Replace', 'Renew', 'Active']
        technology_df_filtered = technology_df_filtered[desired_columns]
        print("\n=== Technology Statuses ===\n")
        print(technology_df_filtered)

    # Display Annual Global Metrics (Enhanced)
    print("\n=== Annual Global Total Costs, Emissions, Fuel, feedstock Consumption, and Technology Adoption ===")
    annual_summary = []
    for yr in sorted(model.years):
        total_cost = annual_global_capex[yr] + annual_global_renewal_cost[yr] + annual_global_opex[yr]
        row = {
            "Year": yr,
            "Total CAPEX": annual_global_capex[yr],
            "Total Renewal Cost": annual_global_renewal_cost[yr],
            "Total OPEX": annual_global_opex[yr],
            "Total Cost": total_cost,
            "Total Emissions": annual_global_total_emissions[yr],
        }
        for fuel in model.fuels:
            row[f"Fuel Consumption ({fuel})"] = annual_global_fuel_consumption[yr][fuel]
        for mat in model.feedstocks:
            row[f"feedstock Consumption ({mat})"] = annual_global_feedstock_consumption[yr][mat]
        for tech in model.technologies:
            row[f"Tech Adoption ({tech})"] = annual_global_tech_adoption[yr][tech]
        annual_summary.append(row)

    annual_summary_df = pd.DataFrame(annual_summary).set_index("Year")
    print(annual_summary_df)

    # Export to Excel
    output_excel_path = "results/Model_Output.xlsx"
    technology_data = {}  # Dictionary to collect Year-Technology pairs for each system

    with pd.ExcelWriter(output_excel_path, engine='openpyxl') as writer:
        # Global summary
        annual_summary_df.to_excel(writer, sheet_name='Global Annual Summary')

        # System-level sheets
        for sys in model.systems:
            costs_df = pd.DataFrame(system_results[sys]['yearly_metrics'])
            costs_df.to_excel(writer, sheet_name=f"{sys}_CostsEmissions", index=False)

            fuel_df = pd.DataFrame(system_results[sys]['fuel_consumption_table'])
            fuel_df.to_excel(writer, sheet_name=f"{sys}_Fuel", index=False)

            feedstock_df = pd.DataFrame(system_results[sys]['feedstock_consumption_table'])
            feedstock_df.to_excel(writer, sheet_name=f"{sys}_Feedstock", index=False)

            tech_df = pd.DataFrame(system_results[sys]['technology_statuses'])
            tech_df_filtered = tech_df[
                tech_df[['Active', 'Continue', 'Replace', 'Renew']].sum(axis=1) >= 1
                ]
            tech_df_filtered.to_excel(writer, sheet_name=f"{sys}_Tech", index=False)

            # Save for merged technology sheet
            technology_data[sys] = tech_df_filtered[['Year', 'Technology']].reset_index(drop=True)

        # Merge all system technology info on Year
        merged_tech_df = pd.DataFrame({'Year': sorted(set().union(*[df['Year'] for df in technology_data.values()]))})
        for sys, df in technology_data.items():
            merged_tech_df = merged_tech_df.merge(df, on='Year', how='left', suffixes=('', f'_{sys}'))
            merged_tech_df.rename(columns={'Technology': f'{sys}_Technology'}, inplace=True)

            merged_tech_df.to_excel(writer, sheet_name='Technology', index=False)
            desired_order = ['Global Annual Summary', 'Technology']
            all_sheets = writer.book.worksheets
            ordered_sheets = [sheet for name in desired_order for sheet in all_sheets if sheet.title == name]
            ordered_sheets += [sheet for sheet in all_sheets if sheet.title not in desired_order]
            writer.book._sheets = ordered_sheets


if __name__ == "__main__":
    file_path = 'database/Steel Data Mar 10.xlsx'
    output = main(file_path,
                  carboprice_include=False,
                  max_renew=10,
                  allow_replace_same_technology=False)