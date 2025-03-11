from pyomo.environ import *
from pyomo.util.infeasible import log_infeasible_constraints
import pandas as pd
import importlib
import utils.load_data as _ld
import utils.modelbuilder as _md

importlib.reload(_ld)
importlib.reload(_md)

def optimize_by_group(file_path, group_dict, global_emission_limit=None, allocation_method='production_share', **kwargs):
    """
    Run separate optimization for each group of systems with a divided global emission constraint.
    
    Parameters:
    -----------
    file_path : str
        Path to the Excel file containing data
    group_dict : dict
        Dictionary with group names as keys and lists of system names as values
    global_emission_limit : dict or None
        Dictionary with years as keys and emission limits as values
        If None, no global emission constraint will be applied
    allocation_method : str
        Method to allocate global emission limit to groups
        Options: 'production_share', 'equal', 'historical', 'custom', 'efficiency_weighted'
    kwargs : dict
        Additional arguments to pass to the model builder
    
    Returns:
    --------
    dict
        Results for each group and combined results
    """
    carbonprice_include = kwargs.get('carboprice_include', False)
    max_renew = kwargs.get('max_renew', 10)
    allow_replace_same_technology = kwargs.get('allow_replace_same_technology', False)

    # Load full data
    full_data = _ld.load_data(file_path)
    
    # Print available systems
    print("\nActual system names in the data:")
    if 'production' in full_data:
        print("\nFrom production data:")
        print(full_data['production'].index.tolist())
    if 'emission' in full_data:
        print("\nFrom emission data:")
        print(full_data['emission'].index.tolist())
        
    # If global emission limit is provided, we need to allocate it among groups
    group_emission_limits = None
    if global_emission_limit:
        # First run a baseline model to get historical data for allocation
        print("\n=== Running baseline model to determine emission allocations ===")
        baseline_model = _md.build_unified_model(full_data,
                                             carbonprice_include=kwargs.get('carboprice_include', False),
                                             max_renew=kwargs.get('max_renew', 10),
                                             allow_replace_same_technology=kwargs.get('allow_replace_same_technology', False))
        
        # Solve the baseline model
        solver = SolverFactory('glpk')
        if not solver.available():
            raise RuntimeError("GLPK solver is not available. Please install it or choose another solver.")
        
        baseline_result = solver.solve(baseline_model, tee=False)
        
        if (baseline_result.solver.status != 'ok') or (baseline_result.solver.termination_condition != 'optimal'):
            print("Warning: Baseline model did not solve optimally. Using default allocation method.")
            allocation_method = 'equal'
        
        # Calculate baseline metrics for allocation
        baseline_group_production = {group: {yr: 0.0 for yr in baseline_model.years} for group in group_dict}
        baseline_group_emissions = {group: {yr: 0.0 for yr in baseline_model.years} for group in group_dict}
        baseline_group_intensity = {group: {yr: 0.0 for yr in baseline_model.years} for group in group_dict}
        baseline_total_production = {yr: 0.0 for yr in baseline_model.years}
        baseline_total_emissions = {yr: 0.0 for yr in baseline_model.years}
        
        # For efficiency-weighted allocation, we'll store inverted emission intensity
        # (higher value = more efficient = less emissions per unit of production)
        baseline_group_efficiency = {group: {yr: 0.0 for yr in baseline_model.years} for group in group_dict}
        baseline_total_efficiency_weighted_production = {yr: 0.0 for yr in baseline_model.years}
        
        # Collect baseline data
        for sys in baseline_model.systems:
            # Find which group this system belongs to
            for group, systems in group_dict.items():
                if sys in systems:
                    for yr in baseline_model.years:
                        production = value(baseline_model.production[sys, yr])
                        emissions = sum(value(baseline_model.emission_by_tech[sys, tech, yr]) 
                                      for tech in baseline_model.technologies)
                        
                        baseline_group_production[group][yr] += production
                        baseline_group_emissions[group][yr] += emissions
                        baseline_total_production[yr] += production
                        baseline_total_emissions[yr] += emissions
                    break
        
        # Calculate group emission intensities and efficiencies
        for group in group_dict:
            for yr in baseline_model.years:
                if baseline_group_production[group][yr] > 0:
                    # Emission intensity = emissions / production
                    baseline_group_intensity[group][yr] = baseline_group_emissions[group][yr] / baseline_group_production[group][yr]
                    
                    # Efficiency = 1 / intensity (higher is better)
                    # We add a small epsilon to avoid division by zero
                    epsilon = 1e-10
                    baseline_group_efficiency[group][yr] = 1.0 / (baseline_group_intensity[group][yr] + epsilon)
                else:
                    baseline_group_intensity[group][yr] = 0.0
                    baseline_group_efficiency[group][yr] = 0.0
        
        # Calculate efficiency-weighted production for each group
        for group in group_dict:
            for yr in baseline_model.years:
                efficiency_weighted_production = baseline_group_production[group][yr] * baseline_group_efficiency[group][yr]
                baseline_total_efficiency_weighted_production[yr] += efficiency_weighted_production
        
        # Allocate global emission limit to groups based on selected method
        group_emission_limits = {group: {} for group in group_dict}
        
        for yr in global_emission_limit:
            if yr not in baseline_model.years:
                # If year not in baseline, use equal allocation
                for group in group_dict:
                    group_emission_limits[group][yr] = global_emission_limit[yr] / len(group_dict)
                continue
                
            if allocation_method == 'equal':
                # Equal allocation
                for group in group_dict:
                    group_emission_limits[group][yr] = global_emission_limit[yr] / len(group_dict)
                    
            elif allocation_method == 'production_share':
                # Allocation based on production share
                for group in group_dict:
                    if baseline_total_production[yr] > 0:
                        share = baseline_group_production[group][yr] / baseline_total_production[yr]
                        group_emission_limits[group][yr] = global_emission_limit[yr] * share
                    else:
                        # If no production, fall back to equal allocation
                        group_emission_limits[group][yr] = global_emission_limit[yr] / len(group_dict)
                        
            elif allocation_method == 'historical':
                # Allocation based on historical emissions
                for group in group_dict:
                    if baseline_total_emissions[yr] > 0:
                        share = baseline_group_emissions[group][yr] / baseline_total_emissions[yr]
                        group_emission_limits[group][yr] = global_emission_limit[yr] * share
                    else:
                        # If no emissions, fall back to equal allocation
                        group_emission_limits[group][yr] = global_emission_limit[yr] / len(group_dict)
            
            elif allocation_method == 'efficiency_weighted':
                # Allocation based on production weighted by efficiency (inverse of emission intensity)
                # This gives more emissions budget to cleaner producers
                for group in group_dict:
                    if baseline_total_efficiency_weighted_production[yr] > 0:
                        # Share of efficiency-weighted production
                        efficiency_weighted_production = baseline_group_production[group][yr] * baseline_group_efficiency[group][yr]
                        share = efficiency_weighted_production / baseline_total_efficiency_weighted_production[yr]
                        group_emission_limits[group][yr] = global_emission_limit[yr] * share
                    else:
                        # Fall back to production share
                        if baseline_total_production[yr] > 0:
                            share = baseline_group_production[group][yr] / baseline_total_production[yr]
                            group_emission_limits[group][yr] = global_emission_limit[yr] * share
                        else:
                            # If no production either, equal allocation
                            group_emission_limits[group][yr] = global_emission_limit[yr] / len(group_dict)
            
            elif allocation_method == 'custom':
                # Custom allocation (should be provided in kwargs)
                custom_allocation = kwargs.get('custom_allocation', {})
                for group in group_dict:
                    if group in custom_allocation and yr in custom_allocation[group]:
                        group_emission_limits[group][yr] = global_emission_limit[yr] * custom_allocation[group][yr]
                    else:
                        # If no custom allocation, fall back to equal allocation
                        group_emission_limits[group][yr] = global_emission_limit[yr] / len(group_dict)
        
        # Print the emission allocation with additional information
        print("\n=== Emission allocation to groups ===")
        for yr in global_emission_limit:
            print(f"\nYear {yr} - Global limit: {global_emission_limit[yr]:.2f}")
            
            print("\nGroup metrics:")
            print(f"{'Group':<10} {'Production':<12} {'Emissions':<12} {'Intensity':<12} {'Efficiency':<12} {'Allocation':<12} {'Share %':<8}")
            print("-" * 80)
            
            for group in group_dict:
                if yr in baseline_group_production[group]:
                    prod = baseline_group_production[group][yr]
                    emis = baseline_group_emissions[group][yr]
                    intens = baseline_group_intensity[group][yr]
                    effic = baseline_group_efficiency[group][yr]
                    alloc = group_emission_limits[group][yr]
                    share = (group_emission_limits[group][yr]/global_emission_limit[yr]*100)
                    
                    print(f"{group:<10} {prod:<12.2f} {emis:<12.2f} {intens:<12.4f} {effic:<12.4f} {alloc:<12.2f} {share:<8.1f}%")
            
            if allocation_method == 'efficiency_weighted':
                print("\nNote: Efficiency is calculated as 1/intensity (higher is better)")
                print("      Allocation is proportional to production * efficiency")
                      
        print(f"\nAllocation method: {allocation_method}")
        print("="*50)

    # Initialize results dictionary
    results = {
        "groups": {},
        "combined": {
            "annual_emissions": {},
            "annual_production": {},
            "emission_intensity": {}
        }
    }
    
    # Create an Excel writer for combined results
    with pd.ExcelWriter('group_optimization_results.xlsx') as writer:
        # Process each group separately
        for group_name, systems in group_dict.items():
            print(f"\n\n{'='*30}")
            print(f"Processing Group: {group_name}")
            print(f"Systems: {systems}")
            print(f"{'='*30}\n")
            
            # Filter data for just this group's systems
            group_data = {}
            for key, df in full_data.items():
                if isinstance(df, pd.DataFrame) and hasattr(df, 'index'):
                    # Only include rows for systems in this group
                    if any(sys in systems for sys in df.index):
                        group_data[key] = df.loc[[sys for sys in df.index if sys in systems]]
                    else:
                        group_data[key] = df
                else:
                    group_data[key] = df
            
            # Build model for this group
            model = _md.build_unified_model(group_data,
                                          carbonprice_include=carbonprice_include,
                                          max_renew=max_renew,
                                          allow_replace_same_technology=allow_replace_same_technology)
            
            # Add emission limit constraint if applicable
            if group_emission_limits:
                # Create a new constraint for emission limit for this group
                def group_emission_limit_rule(model, yr):
                    if yr in group_emission_limits[group_name]:
                        total_emissions = sum(
                            model.emission_by_tech[sys, tech, yr] 
                            for sys in model.systems 
                            for tech in model.technologies
                        )
                        return total_emissions <= group_emission_limits[group_name][yr]
                    else:
                        # If no limit for this year, constraint is always satisfied
                        return Constraint.Skip
                
                # Add the constraint to the model
                model.group_emission_limit = Constraint(model.years, rule=group_emission_limit_rule)
                
                print(f"Added emission limit constraint for {group_name}")
                for yr in sorted(group_emission_limits[group_name].keys()):
                    print(f"  Year {yr}: {group_emission_limits[group_name][yr]:.2f}")
            
            solver = SolverFactory('glpk')
            if not solver.available():
                raise RuntimeError("GLPK solver is not available. Please install it or choose another solver.")
            
            result = solver.solve(model, tee=True)
            
            if (result.solver.status == 'ok') and (result.solver.termination_condition == 'optimal'):
                print(f"\n=== Solver found an optimal solution for {group_name}. ===\n")
            elif result.solver.termination_condition == 'infeasible':
                print(f"\n=== Solver found the model to be infeasible for {group_name}. ===\n")
                log_infeasible_constraints(model)
                continue
            else:
                print(f"\n=== Solver Status for {group_name}: {result.solver.status} ===\n")
                print(f"=== Termination Condition: {result.solver.termination_condition} ===\n")
                continue
            
            # Initialize metrics for this group
            annual_emissions = {yr: 0.0 for yr in model.years}
            annual_production = {yr: 0.0 for yr in model.years}
            annual_capex = {yr: 0.0 for yr in model.years}
            annual_renewal_cost = {yr: 0.0 for yr in model.years}
            annual_opex = {yr: 0.0 for yr in model.years}
            annual_tech_adoption = {yr: {tech: 0 for tech in model.technologies} for yr in model.years}
            annual_fuel_consumption = {yr: {fuel: 0.0 for fuel in model.fuels} for yr in model.years}
            annual_feedstock_consumption = {yr: {fs: 0.0 for fs in model.feedstocks} for yr in model.years}
            
            # Track system-level results
            system_results = {}
            
            # Collect results for each system in this group
            for sys in systems:
                if sys not in model.systems:
                    print(f"Warning: System {sys} not found in model systems.")
                    continue
                
                yearly_metrics = []
                fuel_consumption_table = []
                material_consumption_table = []
                technology_statuses = []
                
                baseline_tech = group_data['baseline'].loc[sys, 'technology']
                introduced_year = group_data['baseline'].loc[sys, 'introduced_year']
                lifespan = model.lifespan_param[baseline_tech]
                
                for yr in model.years:
                    # Calculate costs
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
                    
                    # Calculate emissions and other metrics
                    total_emissions = sum(
                        value(model.emission_by_tech[sys, tech, yr]) for tech in model.technologies
                    )
                    
                    fuel_consumption = {fuel: value(model.fuel_consumption[sys, fuel, yr]) for fuel in model.fuels}
                    feedstock_consumption = {fs: value(model.feedstock_consumption[sys, fs, yr]) for fs in model.feedstocks}
                    
                    # Add to group totals
                    annual_emissions[yr] += total_emissions
                    annual_production[yr] += value(model.production[sys, yr])
                    annual_capex[yr] += capex_cost
                    annual_renewal_cost[yr] += renewal_cost
                    annual_opex[yr] += opex_cost
                    
                    for fuel in model.fuels:
                        annual_fuel_consumption[yr][fuel] += fuel_consumption[fuel]
                    
                    for fs in model.feedstocks:
                        annual_feedstock_consumption[yr][fs] += feedstock_consumption[fs]
                    
                    # Collect system-level metrics
                    yearly_metrics.append({
                        "Year": yr, "CAPEX": capex_cost, "Renewal Cost": renewal_cost,
                        "OPEX": opex_cost, "Total Emissions": total_emissions, 
                        "Production": value(model.production[sys, yr])
                    })
                    
                    fuel_consumption_table.append({"Year": yr, **fuel_consumption})
                    material_consumption_table.append({"Year": yr, **feedstock_consumption})
                    
                    # Track technology statuses
                    for tech in model.technologies:
                        active = value(model.active_technology[sys, tech, yr])
                        annual_tech_adoption[yr][tech] += active
                        
                        technology_statuses.append({
                            "Year": yr, "Technology": tech,
                            "Continue": value(model.continue_technology[sys, tech, yr]),
                            "Replace": value(model.replace[sys, tech, yr]),
                            "Renew": value(model.renew[sys, tech, yr]),
                            "Active": active
                        })
                
                # Store system results
                system_results[sys] = {
                    'costs': pd.DataFrame(yearly_metrics).set_index("Year"),
                    'fuel': pd.DataFrame(fuel_consumption_table).set_index("Year"),
                    'feedstock': pd.DataFrame(material_consumption_table).set_index("Year"),
                    'technology': pd.DataFrame(technology_statuses)
                }
                
                # Export system results to Excel
                system_results[sys]['costs'].to_excel(writer, sheet_name=f'{group_name}_{sys}_Costs')
                system_results[sys]['fuel'].to_excel(writer, sheet_name=f'{group_name}_{sys}_Fuel')
                system_results[sys]['feedstock'].to_excel(writer, sheet_name=f'{group_name}_{sys}_Feedstock')
                system_results[sys]['technology'].to_excel(writer, sheet_name=f'{group_name}_{sys}_Technology')
            
            # Calculate emission intensity
            emission_intensity = {}
            for yr in model.years:
                if annual_production[yr] > 0:
                    emission_intensity[yr] = annual_emissions[yr] / annual_production[yr]
                else:
                    emission_intensity[yr] = 0.0
            
            # Store group results
            results["groups"][group_name] = {
                "annual_emissions": annual_emissions,
                "annual_production": annual_production,
                "emission_intensity": emission_intensity,
                "annual_capex": annual_capex,
                "annual_renewal_cost": annual_renewal_cost,
                "annual_opex": annual_opex,
                "annual_tech_adoption": annual_tech_adoption,
                "annual_fuel_consumption": annual_fuel_consumption,
                "annual_feedstock_consumption": annual_feedstock_consumption,
                "systems": system_results
            }
            
            # Prepare group summary for Excel
            group_summary = []
            for yr in sorted(model.years):
                total_cost = annual_capex[yr] + annual_renewal_cost[yr] + annual_opex[yr]
                group_summary.append({
                    "Year": yr,
                    "Total Production": annual_production[yr],
                    "Total Emissions": annual_emissions[yr],
                    "Emission Intensity": emission_intensity[yr],
                    "Total CAPEX": annual_capex[yr],
                    "Total Renewal Cost": annual_renewal_cost[yr],
                    "Total OPEX": annual_opex[yr],
                    "Total Cost": total_cost,
                    **{f"Fuel Consumption ({fuel})": annual_fuel_consumption[yr][fuel] for fuel in model.fuels},
                    **{f"Material Consumption ({fs})": annual_feedstock_consumption[yr][fs] for fs in model.feedstocks},
                    **{f"Tech Adoption ({tech})": annual_tech_adoption[yr][tech] for tech in model.technologies},
                })
            
            group_summary_df = pd.DataFrame(group_summary).set_index("Year")
            group_summary_df.to_excel(writer, sheet_name=f'{group_name}_Summary')
            
            # Print group results
            print(f"\n=== Results for Group: {group_name} ===")
            print(group_summary_df)
            
            # Update combined results
            for yr in model.years:
                # Initialize year entries if they don't exist
                if yr not in results["combined"]["annual_emissions"]:
                    results["combined"]["annual_emissions"][yr] = 0.0
                    results["combined"]["annual_production"][yr] = 0.0
                
                # Add this group's values to the combined totals
                results["combined"]["annual_emissions"][yr] += annual_emissions[yr]
                results["combined"]["annual_production"][yr] += annual_production[yr]
        
        # Calculate combined emission intensity
        for yr in results["combined"]["annual_emissions"]:
            if results["combined"]["annual_production"][yr] > 0:
                results["combined"]["emission_intensity"][yr] = (
                    results["combined"]["annual_emissions"][yr] / 
                    results["combined"]["annual_production"][yr]
                )
            else:
                results["combined"]["emission_intensity"][yr] = 0.0
        
        # Create combined summary for Excel
        combined_summary = []
        for yr in sorted(results["combined"]["annual_emissions"].keys()):
            combined_summary.append({
                "Year": yr,
                "Total Production": results["combined"]["annual_production"][yr],
                "Total Emissions": results["combined"]["annual_emissions"][yr],
                "Emission Intensity": results["combined"]["emission_intensity"][yr]
            })
        
        combined_summary_df = pd.DataFrame(combined_summary).set_index("Year")
        combined_summary_df.to_excel(writer, sheet_name='Combined_Summary')
        
        # Create group comparison sheet
        comparison_data = []
        for yr in sorted(results["combined"]["annual_emissions"].keys()):
            row = {"Year": yr}
            
            for group_name in results["groups"]:
                row[f"{group_name}_Production"] = results["groups"][group_name]["annual_production"][yr]
                row[f"{group_name}_Emissions"] = results["groups"][group_name]["annual_emissions"][yr]
                row[f"{group_name}_Intensity"] = results["groups"][group_name]["emission_intensity"][yr]
            
            row["Combined_Production"] = results["combined"]["annual_production"][yr]
            row["Combined_Emissions"] = results["combined"]["annual_emissions"][yr]
            row["Combined_Intensity"] = results["combined"]["emission_intensity"][yr]
            
            comparison_data.append(row)
        
        comparison_df = pd.DataFrame(comparison_data).set_index("Year")
        comparison_df.to_excel(writer, sheet_name='Group_Comparison')
    
    # Print combined results
    print("\n\n" + "="*50)
    print("COMBINED RESULTS ACROSS ALL GROUPS")
    print("="*50)
    
    for yr in sorted(results["combined"]["annual_emissions"].keys()):
        print(f"\nYear {yr}:")
        print(f"Total Production: {results['combined']['annual_production'][yr]:.2f}")
        print(f"Total Emissions: {results['combined']['annual_emissions'][yr]:.2f}")
        print(f"Emission Intensity: {results['combined']['emission_intensity'][yr]:.4f}")
    
    print(f"\nResults exported to 'group_optimization_results.xlsx'")
    
    return results

def main():
    file_path = 'database/steel_data.xlsx'
    
    # Define groups of systems to analyze
    group_dict = {
        "Group1": [  # Even positions
            "HyundaiBF1",
            "Pohang FNX3",
            "Gwangyang BF1",
            "Pohang BF2",
            "Pohang BF3",
            "Gwangyang BF4"
        ],
        "Group2": [  # Odd positions
            "Gwangyang BF2",
            "HyundaiBF2",
            "Pohang FNX2",
            "HyundaiBF3",
            "Gwangyang BF5",
            "Gwangyang BF3",
            "Pohang BF4"
        ]
    }
    
    # Define a global emission limit (example: 20% reduction from baseline by 2030)
    # First, run a quick baseline model to get reference emissions
    base_results = main_baseline(file_path)
    baseline_emissions = base_results["annual_global_total_emissions"]
    
    # Define reduction targets (example: linear reduction to 80% of baseline by 2030)
    years = sorted(baseline_emissions.keys())
    start_year = min(years)
    end_year = max(years)
    reduction_target = 0.8  # 20% reduction
    
    # Calculate emission limits for each year
    global_emission_limit = {}
    for yr in years:
        if yr == start_year:
            # No reduction in first year
            global_emission_limit[yr] = baseline_emissions[yr]
        else:
            # Linear interpolation between start_year (100%) and end_year (reduction_target%)
            progress = (yr - start_year) / (end_year - start_year)
            reduction_factor = 1.0 - (progress * (1.0 - reduction_target))
            global_emission_limit[yr] = baseline_emissions[yr] * reduction_factor
    
    # Print the global emission limits
    print("\n=== Global Emission Limits ===")
    for yr in sorted(global_emission_limit.keys()):
        print(f"Year {yr}: {global_emission_limit[yr]:.2f} "
              f"({global_emission_limit[yr]/baseline_emissions[yr]*100:.1f}% of baseline)")
    
    # Run optimization by group with emission constraint
    results = optimize_by_group(
        file_path,
        group_dict=group_dict,
        global_emission_limit=global_emission_limit,
        allocation_method='efficiency_weighted',  # Options: 'production_share', 'equal', 'historical', 'custom', 'efficiency_weighted'
        carboprice_include=False,
        max_renew=10,
        allow_replace_same_technology=False
    )
    
    return results

def main_baseline(file_path, **kwargs):
    """
    Run a baseline optimization to get reference values.
    This function is similar to the simplified version provided in your second code snippet.
    """
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
        print("\n=== Solver found an optimal solution for baseline. ===\n")
    elif result.solver.termination_condition == 'infeasible':
        print("\n=== Solver found the model to be infeasible. ===\n")
        log_infeasible_constraints(model)
        return None
    else:
        print(f"\n=== Solver Status: {result.solver.status} ===\n")
        print(f"=== Termination Condition: {result.solver.termination_condition} ===\n")
        return None

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
    print("\n=== Baseline Annual Global Results ===")
    for yr in model.years:
        print(f"\nYear {yr}:")
        print(f"Total Emissions: {annual_global_total_emissions[yr]:.2f}")
        print(f"Total Production: {annual_global_production[yr]:.2f}")
        if annual_global_production[yr] > 0:
            print(f"Emission Intensity: {annual_global_total_emissions[yr]/annual_global_production[yr]:.4f}")

    return {
        "annual_global_total_emissions": annual_global_total_emissions,
        "annual_global_production": annual_global_production
    }

if __name__ == "__main__":
    results = main()