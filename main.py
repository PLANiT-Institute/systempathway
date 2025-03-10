from pyomo.environ import *

from pyomo.util.infeasible import log_infeasible_constraints
import pandas as pd
import os

import importlib
import utils.load_data as _ld
import utils.modelbuilder as _md

importlib.reload(_ld)
importlib.reload(_md)

def main(file_path, group_dict=None, **kwargs):

    carbonprice_include = kwargs.get('carboprice_include', False)
    max_renew = kwargs.get('max_renew', 10)
    allow_replace_same_technology = kwargs.get('allow_replace_same_technology', False)
    # --------------------------
    # 7. Load Data
    # --------------------------

    data = _ld.load_data(file_path)
    
    # Filter systems based on group_dict if provided
    if group_dict:
        # Convert set to list for pandas indexing
        selected_systems = list(set([sys for sys_list in group_dict.values() for sys in sys_list]))
        data = {key: df.loc[selected_systems] if isinstance(df, pd.DataFrame) and not df.empty else df 
                for key, df in data.items()}

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
    annual_global_feedstock_consumption = {yr: {fs: 0.0 for fs in model.feedstocks} for yr in model.years}
    annual_global_tech_adoption = {yr: {tech: 0 for tech in model.technologies} for yr in model.years}
    
    # Initialize Group Metrics if group_dict is provided
    group_emissions = {grp: {yr: 0.0 for yr in model.years} for grp in group_dict} if group_dict else None
    group_production = {grp: {yr: 0.0 for yr in model.years} for grp in group_dict} if group_dict else None
    group_production_weighted_ei = {grp: {yr: 0.0 for yr in model.years} for grp in group_dict} if group_dict else None

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
            feedstock_consumption = {fs: value(model.feedstock_consumption[sys, fs, yr]) for fs in model.feedstocks}

            yearly_metrics.append({
                "Year": yr, "CAPEX": capex_cost, "Renewal Cost": renewal_cost,
                "OPEX": opex_cost, "Total Emissions": total_emissions
            })
            fuel_consumption_table.append({"Year": yr, **fuel_consumption})
            material_consumption_table.append({"Year": yr, **feedstock_consumption})
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
            for fs in model.feedstocks:
                annual_global_feedstock_consumption[yr][fs] += feedstock_consumption[fs]

            # Track group metrics if group_dict is provided
            if group_dict:
                for grp, sys_list in group_dict.items():
                    if sys in sys_list:
                        group_emissions[grp][yr] += total_emissions
                        group_production[grp][yr] += value(model.production[sys, yr])
                        # Calculate production-weighted emission intensity for this system
                        system_prod_weighted_ei = sum(
                            value(model.prod_active[sys, tech, yr]) * 
                            (model.emission_intensity_param[tech] if hasattr(model, 'emission_intensity_param') else 0)
                            for tech in model.technologies
                        )
                        group_production_weighted_ei[grp][yr] += system_prod_weighted_ei
                        break

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
            **{f"Material Consumption ({fs})": annual_global_feedstock_consumption[yr][fs] for fs in model.feedstocks},
            **{f"Tech Adoption ({tech})": annual_global_tech_adoption[yr][tech] for tech in model.technologies},
        })

    annual_summary_df = pd.DataFrame(annual_summary).set_index("Year")
    print(annual_summary_df)
    
    # Export results to Excel
    print("\n=== Exporting results to Excel ===")
    with pd.ExcelWriter('results_output.xlsx') as writer:
        # Global summary
        annual_summary_df.to_excel(writer, sheet_name='Global_Summary')
        
        # System-specific results
        system_results = {}
        for sys in model.systems:
            # Create a dictionary to store all dataframes for this system
            system_results[sys] = {}
            
            # Prepare data for this system
            yearly_metrics = []
            fuel_consumption_table = []
            feedstock_consumption_table = []
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
                feedstock_consumption = {fs: value(model.feedstock_consumption[sys, fs, yr]) for fs in model.feedstocks}
                
                yearly_metrics.append({
                    "Year": yr, "CAPEX": capex_cost, "Renewal Cost": renewal_cost,
                    "OPEX": opex_cost, "Total Emissions": total_emissions
                })
                fuel_consumption_table.append({"Year": yr, **fuel_consumption})
                feedstock_consumption_table.append({"Year": yr, **feedstock_consumption})
                
                for tech in model.technologies:
                    technology_statuses.append({
                        "Year": yr, "Technology": tech,
                        "Continue": value(model.continue_technology[sys, tech, yr]),
                        "Replace": value(model.replace[sys, tech, yr]),
                        "Renew": value(model.renew[sys, tech, yr]),
                        "Active": value(model.active_technology[sys, tech, yr])
                    })
            
                # Create dataframes
                system_results[sys]['costs'] = pd.DataFrame(yearly_metrics).set_index("Year")
                system_results[sys]['fuel'] = pd.DataFrame(fuel_consumption_table).set_index("Year")
                system_results[sys]['feedstock'] = pd.DataFrame(feedstock_consumption_table).set_index("Year")
                system_results[sys]['technology'] = pd.DataFrame(technology_statuses)
                
                # Export to Excel
                system_results[sys]['costs'].to_excel(writer, sheet_name=f'{sys}_Costs')
                system_results[sys]['fuel'].to_excel(writer, sheet_name=f'{sys}_Fuel')
                system_results[sys]['feedstock'].to_excel(writer, sheet_name=f'{sys}_Feedstock')
                system_results[sys]['technology'].to_excel(writer, sheet_name=f'{sys}_Technology')
            
            # Export production data
            production_data = []
            for yr in model.years:
                production_data.append({
                    "System": sys,
                    "Year": yr,
                    "Production": value(model.production[sys, yr])
                })
            production_df = pd.DataFrame(production_data)
            production_df.to_excel(writer, sheet_name='Production', index=False)
        
    print(f"Results exported to 'results_output.xlsx'")

    # Calculate and display group emission allocations if group_dict is provided
    if group_dict:
        print("\n=== Grouped Emission Allocations ===")
        group_emission_allocation = {}
        for yr in model.years:
            group_emission_allocation[yr] = {}
            for grp in group_dict:
                if group_production_weighted_ei[grp][yr] > 0:
                    group_emission_allocation[yr][grp] = group_emissions[grp][yr] / group_production_weighted_ei[grp][yr]
                else:
                    group_emission_allocation[yr][grp] = 0
        
        # Create DataFrame for group emission allocations
        group_allocation_df = pd.DataFrame.from_dict(
            {(yr, grp): group_emission_allocation[yr][grp] 
             for yr in model.years for grp in group_dict},
            orient='index', columns=['Allocated Emissions']
        )
        group_allocation_df.index = pd.MultiIndex.from_tuples(group_allocation_df.index, names=['Year', 'Group'])
        group_allocation_df = group_allocation_df.unstack(level='Group')
        print(group_allocation_df)
        
        # Add to Excel export
        with pd.ExcelWriter('results_output.xlsx', mode='a') if os.path.exists('results_output.xlsx') else pd.ExcelWriter('results_output.xlsx') as writer:
            group_allocation_df.to_excel(writer, sheet_name='Group_Emissions')
            
            # Also export group emissions and production
            pd.DataFrame({(yr, grp): group_emissions[grp][yr] 
                         for yr in model.years for grp in group_dict}).unstack().to_excel(writer, sheet_name='Group_Total_Emissions')
            
            pd.DataFrame({(yr, grp): group_production[grp][yr] 
                         for yr in model.years for grp in group_dict}).unstack().to_excel(writer, sheet_name='Group_Production')

    return {
        "annual_summary": annual_summary_df,
        "group_emission_allocation": group_emission_allocation if group_dict else None,
        "annual_global_total_emissions": annual_global_total_emissions
    }

if __name__ == "__main__":
    file_path = 'database/steel_data.xlsx'
    
    # Define groups of systems to analyze
    group_dict = {
        "Group A": ["Sys1", "Sys2"],
        "Group B": ["Sys3", "Sys4"]
    }
    
    output = main(file_path,
                  group_dict=group_dict,  # Pass the group dictionary
                  carboprice_include=False,
                  max_renew=10,
                  allow_replace_same_technology=False)
 