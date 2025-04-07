from pyomo.environ import *
import os
import tkinter as tk
from tkinter import filedialog

from pyomo.util.infeasible import log_infeasible_constraints
import pandas as pd

from pyomo.opt import SolverFactory

import importlib
import utils.load_data as _ld
import utils.modelbuilder as _md

importlib.reload(_ld)
importlib.reload(_md)

def select_file():
    root = tk.Tk()
    root.withdraw()  # Hide the root window
    
    # Set initial directory to the database folder
    initial_dir = "database"
    
    file_path = filedialog.askopenfilename(
        title="Select Excel File",
        initialdir=initial_dir,
        filetypes=[("Excel Files", "*.xlsx *.xls")]
    )
    return file_path

def main(file_path, **kwargs):

    solver_selection = kwargs.pop('solver_selection')
    carbonprice_include = kwargs.get('carboprice_include', False)
    max_renew = kwargs.get('max_renew', 10)
    allow_replace_same_technology = kwargs.get('allow_replace_same_technology', False)
    max_count_include = kwargs.get('max_count_include', True)

    # 1. Load Data
    data = _ld.load_data(file_path)

    # 2. Build the Unified Model
    model = _md.build_unified_model(data,
                                    carbonprice_include=carbonprice_include,
                                    max_renew=max_renew,
                                    allow_replace_same_technology=allow_replace_same_technology,
                                    max_count_include=max_count_include)

    # Solve the Model
    solver = SolverFactory(solver_selection)
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
    
    # Add dictionaries for annualized CAPEX and fuel/feedstock costs
    annual_global_annualized_capex = {yr: 0.0 for yr in model.years}
    annual_global_fuel_cost = {yr: 0.0 for yr in model.years}
    annual_global_feedstock_cost = {yr: 0.0 for yr in model.years}
    annual_global_production = {yr: 0.0 for yr in model.years}
    
    # Add dictionary for technology production tracking
    tech_production = {yr: {tech: 0.0 for tech in model.technologies} for yr in model.years}

    # Dictionary to store system-specific results
    system_results = {}

    # Dictionary to store system-specific CAPEX
    system_capex_values = {sys: {yr: 0.0 for yr in model.years} for sys in model.systems}

    # Collect Results (Facility Level)
    for sys in model.systems:
        print(f"\n=== Results for Furnace Site: {sys} ===\n")

        # Prepare empty containers for this system
        system_results[sys] = {
            'yearly_metrics': [],
            'fuel_consumption_table': [],
            'feedstock_consumption_table': [],
            'technology_statuses': [],
            'annualized_capex': [],  # Add container for annualized CAPEX
            'tech_production': []    # Add container for technology production
        }

        # Baseline info
        baseline_tech = data['baseline'].loc[sys, 'technology']
        introduced_year = data['baseline'].loc[sys, 'introduced_year']
        lifespan = model.lifespan_param[baseline_tech]

        # Track technology replacements and renewals for annualization
        tech_investments = {}  # {(tech, start_year): capex_amount}

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
                
                # Track production by technology
                tech_production_amount = value(model.prod_active[sys, tech, yr])
                tech_production[yr][tech] += tech_production_amount
                
                # Store system-level technology production
                system_results[sys]['tech_production'].append({
                    "Year": yr,
                    "Technology": tech,
                    "Production": tech_production_amount
                })

            # Update global metrics
            annual_global_capex[yr] += capex_cost
            annual_global_renewal_cost[yr] += renewal_cost
            annual_global_opex[yr] += opex_cost
            annual_global_total_emissions[yr] += total_emissions
            for fuel in model.fuels:
                annual_global_fuel_consumption[yr][fuel] += fuel_consumption[fuel]
            for mat in model.feedstocks:
                annual_global_feedstock_consumption[yr][mat] += feedstock_consumption[mat]

            # Track new technology investments for annualization
            for tech in model.technologies:
                # If technology is replaced in this year
                if value(model.replace[sys, tech, yr]) > 0.5:
                    tech_investments[(tech, yr)] = model.capex_param[tech, yr]
                
                # If technology is renewed in this year
                if value(model.renew[sys, tech, yr]) > 0.5:
                    tech_investments[(tech, yr)] = model.renewal_param[tech, yr]
            
            # Calculate fuel and feedstock costs
            fuel_cost = sum(
                model.fuel_cost_param[fuel, yr] * value(model.fuel_consumption[sys, fuel, yr]) 
                for fuel in model.fuels
            )
            feedstock_cost = sum(
                model.feedstock_cost_param[mat, yr] * value(model.feedstock_consumption[sys, mat, yr]) 
                for mat in model.feedstocks
            )
            
            annual_global_fuel_cost[yr] += fuel_cost
            annual_global_feedstock_cost[yr] += feedstock_cost
            annual_global_production[yr] += value(model.production[sys, yr])

            # Store CAPEX for this system and year
            for tech in model.technologies:
                if value(model.replace[sys, tech, yr]) > 0.5:
                    system_capex_values[sys][yr] += model.capex_param[tech, yr]

        # Calculate annualized CAPEX for this system
        for yr in model.years:
            annualized_capex = 0.0
            
            # For baseline technology in first year
            if yr == min(model.years) and baseline_tech in model.technologies:
                # Calculate remaining years of life for baseline tech
                remaining_years = max(0, introduced_year + lifespan - yr)
                if remaining_years > 0:
                    # Simply divide the remaining CAPEX evenly over the remaining years
                    # for a more uniform distribution
                    baseline_capex = model.capex_param[baseline_tech, yr]
                    annualized_capex += baseline_capex / remaining_years
            
            # For all technology investments (replacements and renewals)
            for (tech, start_yr), capex_amount in tech_investments.items():
                # Only include if the investment happened in or before current year
                if start_yr <= yr and yr < start_yr + 20:  # 20-year annualization period
                    annualized_capex += capex_amount / 20.0
            
            system_results[sys]['annualized_capex'].append({
                "Year": yr,
                "Annualized CAPEX": annualized_capex
            })
            
            annual_global_annualized_capex[yr] += annualized_capex

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

    # Calculate discounted costs for total cost sheet
    actual_discount_rate = 0.02  # 2% for CAPEX, OPEX, RENEWAL
    nominal_discount_rate = 0.02  # 2% for fuel and feedstock
    
    base_year = min(model.years)
    discounted_costs = []
    unit_costs = []
    
    # Calculate baseline emissions for MAC calculation
    baseline_emissions = {}
    for yr in model.years:
        if yr == min(model.years):
            baseline_emissions[yr] = annual_global_total_emissions[yr]
        else:
            # Assume baseline emissions would remain the same as first year
            baseline_emissions[yr] = baseline_emissions[min(model.years)]
    
    # Calculate cumulative discounted costs for MAC
    cumulative_discounted_cost = 0
    cumulative_emission_reduction = 0
    
    for yr in sorted(model.years):
        actual_discount_factor = 1 / ((1 + actual_discount_rate) ** (yr - base_year))
        nominal_discount_factor = 1 / ((1 + nominal_discount_rate) ** (yr - base_year))
        
        discounted_capex = annual_global_capex[yr] * actual_discount_factor
        discounted_renewal = annual_global_renewal_cost[yr] * actual_discount_factor
        discounted_opex = annual_global_opex[yr] * actual_discount_factor
        discounted_fuel = annual_global_fuel_cost[yr] * nominal_discount_factor
        discounted_feedstock = annual_global_feedstock_cost[yr] * nominal_discount_factor
        
        total_discounted = discounted_capex + discounted_renewal + discounted_opex + discounted_fuel + discounted_feedstock
        
        # Calculate unit costs (per unit of production)
        production = annual_global_production[yr]
        if production > 0:
            unit_capex = annual_global_capex[yr] / production
            unit_renewal = annual_global_renewal_cost[yr] / production
            unit_opex = annual_global_opex[yr] / production
            unit_fuel = annual_global_fuel_cost[yr] / production
            unit_feedstock = annual_global_feedstock_cost[yr] / production
            unit_annualized_capex = annual_global_annualized_capex[yr] / production
            unit_total = (annual_global_capex[yr] + annual_global_renewal_cost[yr] + 
                          annual_global_opex[yr] + annual_global_fuel_cost[yr] + 
                          annual_global_feedstock_cost[yr]) / production
        else:
            unit_capex = unit_renewal = unit_opex = unit_fuel = unit_feedstock = unit_annualized_capex = unit_total = 0
        
        # Calculate emission reduction from baseline
        emission_reduction = baseline_emissions[yr] - annual_global_total_emissions[yr]
        
        # Update cumulative values for MAC calculation
        cumulative_discounted_cost += total_discounted
        cumulative_emission_reduction += emission_reduction
        
        # Calculate MAC (Marginal Abatement Cost)
        mac = 0
        if cumulative_emission_reduction > 0:
            mac = cumulative_discounted_cost / cumulative_emission_reduction
        
        discounted_costs.append({
            "Year": yr,
            "Discounted CAPEX": discounted_capex,
            "Discounted Renewal": discounted_renewal,
            "Discounted OPEX": discounted_opex,
            "Discounted Fuel Cost": discounted_fuel,
            "Discounted Feedstock Cost": discounted_feedstock,
            "Total Discounted Cost": total_discounted,
            "Emission Reduction (tCO2e)": emission_reduction,
            "Cumulative Discounted Cost": cumulative_discounted_cost,
            "Cumulative Emission Reduction (tCO2e)": cumulative_emission_reduction,
            "Marginal Abatement Cost ($/tCO2e)": mac
        })
        
        unit_costs.append({
            "Year": yr,
            "Unit CAPEX ($/unit)": unit_capex,
            "Unit Renewal ($/unit)": unit_renewal,
            "Unit OPEX ($/unit)": unit_opex,
            "Unit Fuel Cost ($/unit)": unit_fuel,
            "Unit Feedstock Cost ($/unit)": unit_feedstock,
            "Unit Annualized CAPEX ($/unit)": unit_annualized_capex,
            "Total Unit Cost ($/unit)": unit_total,
            "Emissions Intensity (tCO2e/unit)": annual_global_total_emissions[yr] / production if production > 0 else 0
        })

    # Export to Excel
    output_excel_path = "results/Model_Output_Domestic_Share.xlsx"
    technology_data = {}  # Dictionary to collect Year-Technology pairs for each system

    with pd.ExcelWriter(output_excel_path, engine='openpyxl') as writer:
        # Global summary
        annual_summary_df.to_excel(writer, sheet_name='Global Annual Summary')
        
        # Add annualized CAPEX sheet
        annualized_capex_data = []
        for yr in sorted(model.years):
            row = {"Year": yr, "Global Annualized CAPEX": annual_global_annualized_capex[yr]}
            for sys in model.systems:
                sys_annualized = next((item["Annualized CAPEX"] for item in system_results[sys]['annualized_capex'] if item["Year"] == yr), 0)
                row[f"{sys} Annualized CAPEX"] = sys_annualized
            annualized_capex_data.append(row)
        
        annualized_capex_df = pd.DataFrame(annualized_capex_data).set_index("Year")
        annualized_capex_df.to_excel(writer, sheet_name='Annualized CAPEX')
        
        # Add total discounted cost sheet
        discounted_costs_df = pd.DataFrame(discounted_costs).set_index("Year")
        discounted_costs_df.to_excel(writer, sheet_name='Discounted Costs')
        
        # Add unit cost and MAC sheet
        unit_costs_df = pd.DataFrame(unit_costs).set_index("Year")
        unit_costs_df.to_excel(writer, sheet_name='Unit Costs and MAC')
        
        # Add system CAPEX sheet - simple version with just CAPEX by system
        system_capex_data = []
        for yr in sorted(model.years):
            row = {"Year": yr}
            for sys in model.systems:
                # Get CAPEX for this system and year from the yearly_metrics
                sys_metrics = next((item for item in system_results[sys]['yearly_metrics'] if item["Year"] == yr), None)
                if sys_metrics:
                    row[f"{sys}"] = sys_metrics["CAPEX"]
                else:
                    row[f"{sys}"] = 0.0
            system_capex_data.append(row)
        
        system_capex_df = pd.DataFrame(system_capex_data).set_index("Year")
        system_capex_df.to_excel(writer, sheet_name='System CAPEX')
        
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
            desired_order = ['Global Annual Summary', 'Annualized CAPEX', 'Discounted Costs', 
                             'Unit Costs and MAC', 'System CAPEX', 'Technology']
            all_sheets = writer.book.worksheets
            ordered_sheets = [sheet for name in desired_order for sheet in all_sheets if sheet.title == name]
            ordered_sheets += [sheet for sheet in all_sheets if sheet.title not in desired_order]
            writer.book._sheets = ordered_sheets

        # Add technology production share sheet
        tech_production_data = []
        for yr in sorted(model.years):
            total_production = annual_global_production[yr]
            row = {"Year": yr, "Total Production": total_production}
            
            # Add absolute production by technology
            for tech in model.technologies:
                row[f"{tech} Production"] = tech_production[yr][tech]
            
            # Add percentage share by technology
            if total_production > 0:
                for tech in model.technologies:
                    row[f"{tech} Share (%)"] = (tech_production[yr][tech] / total_production) * 100
            else:
                for tech in model.technologies:
                    row[f"{tech} Share (%)"] = 0
                    
            tech_production_data.append(row)
        
        tech_production_df = pd.DataFrame(tech_production_data).set_index("Year")
        tech_production_df.to_excel(writer, sheet_name='Technology Production Share')
        
        # System-level technology production sheets
        for sys in model.systems:
            # Create a pivot table for this system's technology production
            tech_prod_df = pd.DataFrame(system_results[sys]['tech_production'])
            tech_prod_pivot = tech_prod_df.pivot_table(
                index='Year', 
                columns='Technology', 
                values='Production', 
                aggfunc='sum'
            ).fillna(0)
            
            # Calculate percentage shares
            tech_prod_pivot_pct = tech_prod_pivot.div(tech_prod_pivot.sum(axis=1), axis=0) * 100
            tech_prod_pivot_pct.columns = [f"{col} Share (%)" for col in tech_prod_pivot_pct.columns]
            
            # Combine absolute and percentage values
            combined_df = pd.concat([tech_prod_pivot, tech_prod_pivot_pct], axis=1)
            combined_df.to_excel(writer, sheet_name=f"{sys}_Tech_Production")

            merged_tech_df.to_excel(writer, sheet_name='Technology', index=False)
            desired_order = ['Global Annual Summary', 'Annualized CAPEX', 'Discounted Costs', 
                             'Unit Costs and MAC', 'System CAPEX', 'Technology Production Share', 'Technology']
            all_sheets = writer.book.worksheets
            ordered_sheets = [sheet for name in desired_order for sheet in all_sheets if sheet.title == name]
            ordered_sheets += [sheet for sheet in all_sheets if sheet.title not in desired_order]
            writer.book._sheets = ordered_sheets


if __name__ == "__main__":
    file_path = select_file()
    if not file_path:
        print("No file selected. Exiting.")
    else:
        output = main(file_path,
                      solver_selection='appsi_highs',
                      carboprice_include=False,
                      max_renew=10,
                      allow_replace_same_technology=False)
