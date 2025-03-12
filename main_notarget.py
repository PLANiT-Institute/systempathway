from pyomo.environ import *
from pyomo.util.infeasible import log_infeasible_constraints
import pandas as pd
import importlib
import utils.load_data as _ld
import utils.modelbuilder as _md
import os

importlib.reload(_ld)
importlib.reload(_md)

def main(file_path, **kwargs):
    carbonprice_include = kwargs.get('carboprice_include', False)
    max_renew = kwargs.get('max_renew', 0)
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
    
    # Additional metrics based on reference code
    annual_global_capex = {yr: 0.0 for yr in model.years}
    annual_global_opex = {yr: 0.0 for yr in model.years}
    annual_global_fuel_consumption = {yr: {fuel: 0.0 for fuel in model.fuels} for yr in model.years}
    annual_global_tech_adoption = {yr: {tech: 0 for tech in model.technologies} for yr in model.years}
    
    # Add fuel cost tracking
    annual_global_fuel_cost = {yr: {fuel: 0.0 for fuel in model.fuels} for yr in model.years}
    annual_global_total_fuel_cost = {yr: 0.0 for yr in model.years}
    
    # Get fuel prices from the data
    fuel_prices = {}
    if 'fuel_cost' in data:
        for index, row in data['fuel_cost'].iterrows():
            if 'fuel' in row and 'cost' in row:
                fuel_prices[row['fuel']] = row['cost']
    
    # If no fuel prices found in data, use default values
    if not fuel_prices:
        print("Warning: No fuel cost data found in input file. Using default fuel prices.")
        fuel_prices = {
            'coal': 100,       # $/ton
            'natural_gas': 5,  # $/MMBtu
            'electricity': 70, # $/MWh
            'hydrogen': 5,     # $/kg
            'biomass': 120,    # $/ton
            'oil': 80,         # $/barrel
            'coke': 300,       # $/ton
            'COG': 4,          # $/MMBtu
            'BFG': 2,          # $/MMBtu
            'BOFG': 3,         # $/MMBtu
        }
    else:
        print("Loaded fuel prices from input data:")
        for fuel, price in fuel_prices.items():
            print(f"  {fuel}: ${price}")
    
    # Try to initialize feedstock consumption if the model has feedstocks
    annual_global_feedstock_consumption = {}
    if hasattr(model, 'feedstocks'):
        annual_global_feedstock_consumption = {yr: {feedstock: 0.0 for feedstock in model.feedstocks} for yr in model.years}

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
            
            # Add technology adoption data
            for tech in model.technologies:
                try:
                    if hasattr(model, 'active_technology'):
                        annual_global_tech_adoption[yr][tech] += value(model.active_technology[sys, tech, yr])
                except:
                    pass
            
            # Add fuel consumption data and calculate fuel costs
            for fuel in model.fuels:
                try:
                    fuel_amount = 0
                    if hasattr(model, 'fuel_consumption'):
                        fuel_amount = value(model.fuel_consumption[sys, fuel, yr])
                    elif hasattr(model, 'fuel_use'):
                        fuel_amount = value(model.fuel_use[sys, fuel, yr])
                    
                    if fuel_amount > 0:
                        annual_global_fuel_consumption[yr][fuel] += fuel_amount
                        
                        # Calculate fuel cost - try both lowercase and original case
                        fuel_price = fuel_prices.get(fuel.lower(), fuel_prices.get(fuel, 0))
                        fuel_cost = fuel_amount * fuel_price
                        annual_global_fuel_cost[yr][fuel] += fuel_cost
                        annual_global_total_fuel_cost[yr] += fuel_cost
                except:
                    pass
            
            # Add feedstock consumption data if available
            if hasattr(model, 'feedstocks'):
                for feedstock in model.feedstocks:
                    try:
                        if hasattr(model, 'feedstock_consumption'):
                            annual_global_feedstock_consumption[yr][feedstock] += value(model.feedstock_consumption[sys, feedstock, yr])
                        elif hasattr(model, 'feedstock_use'):
                            annual_global_feedstock_consumption[yr][feedstock] += value(model.feedstock_use[sys, feedstock, yr])
                    except:
                        pass
            
            # Add cost data
            try:
                # Try to get CAPEX
                if hasattr(model, 'capex') and yr in model.capex:
                    annual_global_capex[yr] += value(model.capex[yr])
                elif hasattr(model, 'capex_cost') and yr in model.capex_cost:
                    annual_global_capex[yr] += value(model.capex_cost[yr])
                
                # Try to get OPEX
                if hasattr(model, 'opex') and yr in model.opex:
                    annual_global_opex[yr] += value(model.opex[yr])
                elif hasattr(model, 'opex_cost') and yr in model.opex_cost:
                    annual_global_opex[yr] += value(model.opex_cost[yr])
            except:
                pass

    # Print results
    print("\n=== Annual Global Results ===")
    for yr in model.years:
        print(f"\nYear {yr}:")
        print(f"Total Emissions: {annual_global_total_emissions[yr]:.2f}")
        print(f"Total Production: {annual_global_production[yr]:.2f}")
        if annual_global_production[yr] > 0:
            print(f"Emission Intensity: {annual_global_total_emissions[yr]/annual_global_production[yr]:.4f}")
        print(f"Total Fuel Cost: {annual_global_total_fuel_cost[yr]:.2f}")
        
        # Calculate and print cost intensity
        total_cost = annual_global_capex[yr] + annual_global_opex[yr] + annual_global_total_fuel_cost[yr]
        if annual_global_production[yr] > 0:
            cost_intensity = total_cost / annual_global_production[yr]
            print(f"Cost Intensity: {cost_intensity:.2f} $/unit")
            print(f"  CAPEX Intensity: {annual_global_capex[yr]/annual_global_production[yr]:.2f} $/unit")
            print(f"  OPEX Intensity: {annual_global_opex[yr]/annual_global_production[yr]:.2f} $/unit")
            print(f"  Fuel Cost Intensity: {annual_global_total_fuel_cost[yr]/annual_global_production[yr]:.2f} $/unit")

    return {
        "annual_global_total_emissions": annual_global_total_emissions,
        "annual_global_production": annual_global_production,
        "annual_global_capex": annual_global_capex,
        "annual_global_opex": annual_global_opex,
        "annual_global_fuel_consumption": annual_global_fuel_consumption,
        "annual_global_fuel_cost": annual_global_fuel_cost,
        "annual_global_total_fuel_cost": annual_global_total_fuel_cost,
        "annual_global_feedstock_consumption": annual_global_feedstock_consumption if hasattr(model, 'feedstocks') else {},
        "annual_global_tech_adoption": annual_global_tech_adoption,
        "fuel_prices": fuel_prices,  # Add fuel prices to the output
        "model": model,
        "result": result,
        "data": data
    }

def inspect_model_structure(model):
    """
    Inspect the model structure and print out all components and variables.
    """
    print("\n=== Model Structure Inspection ===")
    
    # Print all sets
    print("\nSets in the model:")
    for s in model.component_objects(Set, active=True):
        print(f"  Set: {s.name}")
        try:
            if len(s) <= 20:  # Only print if not too large
                print(f"    Values: {[x for x in s]}")
        except:
            print("    (Unable to list values)")
    
    # Print all parameters
    print("\nParameters in the model:")
    for p in model.component_objects(Param, active=True):
        print(f"  Parameter: {p.name}")
        try:
            if len(p) <= 5:  # Only print a few examples
                print(f"    Example values: {[p[idx] for idx in list(p.keys())[:5]]}")
        except:
            print("    (Unable to list values)")
    
    # Print all variables
    print("\nVariables in the model:")
    for v in model.component_objects(Var, active=True):
        print(f"  Variable: {v.name}")
        try:
            if len(v) <= 5:  # Only print a few examples
                print(f"    Example indices: {list(v.keys())[:5]}")
        except:
            print("    (Unable to list indices)")
    
    # Print all constraints
    print("\nConstraints in the model:")
    for c in model.component_objects(Constraint, active=True):
        print(f"  Constraint: {c.name}")
        try:
            if len(c) <= 5:  # Only print a few examples
                print(f"    Example indices: {list(c.keys())[:5]}")
        except:
            print("    (Unable to list indices)")

def save_comprehensive_results(model, data, output_path='results'):
    """
    Save comprehensive results from the model to Excel files.
    """
    # Create output directory if it doesn't exist
    if not os.path.exists(output_path):
        os.makedirs(output_path)
    
    timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
    
    # 1. Save model structure information
    structure_file = f"{output_path}/model_structure_{timestamp}.txt"
    with open(structure_file, 'w') as f:
        # Write sets
        f.write("=== SETS ===\n")
        for s in model.component_objects(Set, active=True):
            f.write(f"Set: {s.name}\n")
            try:
                if len(s) <= 100:  # Limit to reasonable size
                    f.write(f"  Values: {[x for x in s]}\n")
                else:
                    f.write(f"  (Set too large to display, size: {len(s)})\n")
            except:
                f.write("  (Unable to list values)\n")
        
        # Write variables
        f.write("\n=== VARIABLES ===\n")
        for v in model.component_objects(Var, active=True):
            f.write(f"Variable: {v.name}\n")
            try:
                f.write(f"  Size: {len(v)}\n")
                if len(v) <= 10:  # Only print a few examples
                    for idx in list(v.keys())[:10]:
                        f.write(f"  {idx}: {value(v[idx])}\n")
                else:
                    f.write("  (Too many indices to display)\n")
            except:
                f.write("  (Unable to access values)\n")
    
    print(f"Model structure saved to {structure_file}")
    
    # 2. Save all variables to Excel
    all_vars_file = f"{output_path}/all_variables_{timestamp}.xlsx"
    all_vars_data = []
    
    for v in model.component_objects(Var, active=True):
        var_name = v.name
        for idx in v:
            try:
                val = value(v[idx])
                if abs(val) > 1e-6:  # Only include non-zero values
                    # Convert index to string representation
                    if isinstance(idx, tuple):
                        idx_str = ', '.join(str(i) for i in idx)
                    else:
                        idx_str = str(idx)
                    
                    all_vars_data.append({
                        'Variable': var_name,
                        'Index': idx_str,
                        'Value': val
                    })
            except:
                pass  # Skip if can't get value
    
    if all_vars_data:
        all_vars_df = pd.DataFrame(all_vars_data)
        all_vars_df.to_excel(all_vars_file, index=False)
        print(f"All variables saved to {all_vars_file}")
    
    # 3. Save specific results by category
    results_file = f"{output_path}/optimization_results_{timestamp}.xlsx"
    writer = pd.ExcelWriter(results_file, engine='openpyxl')
    
    # Emissions by technology
    emissions_tech_data = []
    for sys in model.systems:
        for yr in model.years:
            for tech in model.technologies:
                try:
                    tech_emissions = value(model.emission_by_tech[sys, tech, yr])
                    if abs(tech_emissions) > 1e-6:  # Only include non-zero values
                        emissions_tech_data.append({
                            'System': sys,
                            'Year': yr,
                            'Technology': tech,
                            'Emissions': tech_emissions
                        })
                except:
                    pass
    
    if emissions_tech_data:
        emissions_tech_df = pd.DataFrame(emissions_tech_data)
        emissions_tech_df.to_excel(writer, sheet_name='Emissions_by_Tech', index=False)
    
    # System emissions and production
    system_data = []
    for sys in model.systems:
        for yr in model.years:
            try:
                system_emissions = sum(value(model.emission_by_tech[sys, tech, yr]) for tech in model.technologies)
                production = value(model.production[sys, yr])
                
                system_data.append({
                    'System': sys,
                    'Year': yr,
                    'Emissions': system_emissions,
                    'Production': production,
                    'Emission_Intensity': system_emissions / production if production > 0 else 0
                })
            except:
                pass
    
    if system_data:
        system_df = pd.DataFrame(system_data)
        system_df.to_excel(writer, sheet_name='System_Results', index=False)
    
    # Try to find technology production/use variables
    tech_production_data = []
    
    # Check for various possible variable names
    possible_tech_vars = [
        'production_by_tech', 'technology_production', 'tech_production',
        'technology_use', 'tech_use', 'active_technology'
    ]
    
    tech_var_found = False
    for var_name in possible_tech_vars:
        if hasattr(model, var_name):
            tech_var = getattr(model, var_name)
            tech_var_found = True
            
            for idx in tech_var:
                try:
                    if len(idx) >= 3:  # Assuming index structure is (system, tech, year)
                        sys, tech, yr = idx[0], idx[1], idx[2]
                        tech_amount = value(tech_var[idx])
                        
                        if abs(tech_amount) > 1e-6:  # Only include non-zero values
                            tech_production_data.append({
                                'System': sys,
                                'Year': yr,
                                'Technology': tech,
                                'Production/Use': tech_amount
                            })
                except:
                    pass
    
    # If no specific tech variable found, infer from emissions
    if not tech_var_found:
        print("No specific technology production variable found. Inferring from emissions...")
        for sys in model.systems:
            for yr in model.years:
                for tech in model.technologies:
                    try:
                        # If this tech contributes to emissions, it must be in use
                        if value(model.emission_by_tech[sys, tech, yr]) > 1e-6:
                            tech_production_data.append({
                                'System': sys,
                                'Year': yr,
                                'Technology': tech,
                                'Production/Use': 'In Use (inferred from emissions)'
                            })
                    except:
                        pass
    
    if tech_production_data:
        tech_production_df = pd.DataFrame(tech_production_data)
        tech_production_df.to_excel(writer, sheet_name='Technology_Use', index=False)
    
    # Try to find fuel use variables
    fuel_data = []
    if hasattr(model, 'fuel_use'):
        for idx in model.fuel_use:
            try:
                if len(idx) >= 3:  # Assuming index structure is (system, fuel, year)
                    sys, fuel, yr = idx[0], idx[1], idx[2]
                    fuel_amount = value(model.fuel_use[idx])
                    
                    if abs(fuel_amount) > 1e-6:  # Only include non-zero values
                        fuel_data.append({
                            'System': sys,
                            'Year': yr,
                            'Fuel': fuel,
                            'Consumption': fuel_amount
                        })
            except:
                pass
    
    if fuel_data:
        fuel_df = pd.DataFrame(fuel_data)
        fuel_df.to_excel(writer, sheet_name='Fuel_Consumption', index=False)
    
    # Try to find feedstock use variables
    feedstock_data = []
    if hasattr(model, 'feedstock_use'):
        for idx in model.feedstock_use:
            try:
                if len(idx) >= 3:  # Assuming index structure is (system, feedstock, year)
                    sys, feedstock, yr = idx[0], idx[1], idx[2]
                    feedstock_amount = value(model.feedstock_use[idx])
                    
                    if abs(feedstock_amount) > 1e-6:  # Only include non-zero values
                        feedstock_data.append({
                            'System': sys,
                            'Year': yr,
                            'Feedstock': feedstock,
                            'Consumption': feedstock_amount
                        })
            except:
                pass
    
    if feedstock_data:
        feedstock_df = pd.DataFrame(feedstock_data)
        feedstock_df.to_excel(writer, sheet_name='Feedstock_Consumption', index=False)
    
    # Try to find renewal decisions
    renewal_data = []
    if hasattr(model, 'renewal'):
        for idx in model.renewal:
            try:
                if len(idx) >= 3:  # Assuming index structure is (system, tech, year)
                    sys, tech, yr = idx[0], idx[1], idx[2]
                    renewal_amount = value(model.renewal[idx])
                    
                    if abs(renewal_amount) > 1e-6:  # Only include non-zero values
                        renewal_data.append({
                            'System': sys,
                            'Year': yr,
                            'Technology': tech,
                            'Renewal_Amount': renewal_amount
                        })
            except:
                pass
    
    if renewal_data:
        renewal_df = pd.DataFrame(renewal_data)
        renewal_df.to_excel(writer, sheet_name='Renewals', index=False)
    
    # Save and close
    writer.close()
    print(f"Optimization results saved to {results_file}")
    
    return {
        'structure_file': structure_file,
        'all_vars_file': all_vars_file,
        'results_file': results_file
    }

def save_results_to_excel(output, output_file='results_global.xlsx'):
    """
    Save the optimization results to a specific Excel file based on the reference code.
    """
    print(f"\n=== Saving results to {output_file} ===")
    
    model = output["model"]
    fuel_prices = output["fuel_prices"]  # Get fuel prices from output
    
    # Create a new Excel writer
    writer = pd.ExcelWriter(output_file, engine='openpyxl')
    
    # 1. System-level results
    system_results = []
    for sys in model.systems:
        for yr in model.years:
            row_data = {"System": sys, "Year": yr}
            
            # Production
            row_data["Production"] = value(model.production[sys, yr])
            
            # Emissions
            system_emissions = sum(value(model.emission_by_tech[sys, tech, yr]) for tech in model.technologies)
            row_data["Emissions"] = system_emissions
            row_data["Emission_Intensity"] = system_emissions / row_data["Production"] if row_data["Production"] > 0 else 0
            
            # Technology use
            active_techs = []
            for tech in model.technologies:
                try:
                    if hasattr(model, 'active_technology'):
                        active = value(model.active_technology[sys, tech, yr])
                        if active > 0.001:
                            active_techs.append(tech)
                            row_data[f"Tech_{tech}"] = active
                except:
                    pass
            
            row_data["Active_Technologies"] = ", ".join(active_techs)
            
            # Fuel consumption and costs
            system_fuel_cost = 0
            for fuel in model.fuels:
                try:
                    fuel_amount = 0
                    if hasattr(model, 'fuel_consumption'):
                        fuel_amount = value(model.fuel_consumption[sys, fuel, yr])
                    elif hasattr(model, 'fuel_use'):
                        fuel_amount = value(model.fuel_use[sys, fuel, yr])
                    
                    if fuel_amount > 0.001:
                        row_data[f"Fuel_{fuel}"] = fuel_amount
                        
                        # Add fuel cost if we have it
                        if yr in output["annual_global_fuel_cost"] and fuel in output["annual_global_fuel_cost"][yr]:
                            # Calculate per-system fuel cost based on consumption proportion
                            global_fuel_consumption = output["annual_global_fuel_consumption"][yr][fuel]
                            if global_fuel_consumption > 0:
                                proportion = fuel_amount / global_fuel_consumption
                                fuel_cost = proportion * output["annual_global_fuel_cost"][yr][fuel]
                                row_data[f"Fuel_Cost_{fuel}"] = fuel_cost
                                system_fuel_cost += fuel_cost
                except:
                    pass
            
            # Add total fuel cost for this system
            if system_fuel_cost > 0:
                row_data["Total_Fuel_Cost"] = system_fuel_cost
            
            # Calculate system cost intensity if we have production
            if row_data["Production"] > 0:
                # Estimate system CAPEX and OPEX based on production proportion
                if output["annual_global_production"][yr] > 0:
                    production_proportion = row_data["Production"] / output["annual_global_production"][yr]
                    system_capex = production_proportion * output["annual_global_capex"][yr]
                    system_opex = production_proportion * output["annual_global_opex"][yr]
                    
                    # Calculate total system cost and cost intensity
                    system_total_cost = system_capex + system_opex + system_fuel_cost
                    row_data["Total_Cost"] = system_total_cost
                    row_data["Cost_Intensity"] = system_total_cost / row_data["Production"]
            
            # Feedstock consumption if available
            if hasattr(model, 'feedstocks'):
                for feedstock in model.feedstocks:
                    try:
                        if hasattr(model, 'feedstock_consumption'):
                            feedstock_amount = value(model.feedstock_consumption[sys, feedstock, yr])
                        elif hasattr(model, 'feedstock_use'):
                            feedstock_amount = value(model.feedstock_use[sys, feedstock, yr])
                        else:
                            feedstock_amount = 0
                        
                        if feedstock_amount > 0.001:
                            row_data[f"Feedstock_{feedstock}"] = feedstock_amount
                    except:
                        pass
            
            system_results.append(row_data)
    
    if system_results:
        system_df = pd.DataFrame(system_results)
        system_df.to_excel(writer, sheet_name='System_Results', index=False)
    
    # 2. Global summary by year
    annual_summary = []
    for yr in sorted(model.years):
        row_data = {"Year": yr}
        
        # Emissions and production
        row_data["Total_Emissions"] = output["annual_global_total_emissions"][yr]
        row_data["Total_Production"] = output["annual_global_production"][yr]
        row_data["Global_Emission_Intensity"] = (
            output["annual_global_total_emissions"][yr] / output["annual_global_production"][yr] 
            if output["annual_global_production"][yr] > 0 else 0
        )
        
        # Costs
        row_data["Total_CAPEX"] = output["annual_global_capex"][yr]
        row_data["Total_OPEX"] = output["annual_global_opex"][yr]
        row_data["Total_Fuel_Cost"] = output["annual_global_total_fuel_cost"][yr]
        total_cost = output["annual_global_capex"][yr] + output["annual_global_opex"][yr] + output["annual_global_total_fuel_cost"][yr]
        row_data["Total_Cost"] = total_cost
        
        # Add cost intensity (cost per unit of production)
        if output["annual_global_production"][yr] > 0:
            row_data["Cost_Intensity"] = total_cost / output["annual_global_production"][yr]
            row_data["CAPEX_Intensity"] = output["annual_global_capex"][yr] / output["annual_global_production"][yr]
            row_data["OPEX_Intensity"] = output["annual_global_opex"][yr] / output["annual_global_production"][yr]
            row_data["Fuel_Cost_Intensity"] = output["annual_global_total_fuel_cost"][yr] / output["annual_global_production"][yr]
        else:
            row_data["Cost_Intensity"] = 0
            row_data["CAPEX_Intensity"] = 0
            row_data["OPEX_Intensity"] = 0
            row_data["Fuel_Cost_Intensity"] = 0
        
        # Fuel consumption
        for fuel in model.fuels:
            if fuel in output["annual_global_fuel_consumption"][yr]:
                fuel_amount = output["annual_global_fuel_consumption"][yr][fuel]
                if fuel_amount > 0.001:
                    row_data[f"Fuel_Consumption_{fuel}"] = fuel_amount
                    
                    # Add fuel cost
                    if fuel in output["annual_global_fuel_cost"][yr]:
                        fuel_cost = output["annual_global_fuel_cost"][yr][fuel]
                        if fuel_cost > 0.001:
                            row_data[f"Fuel_Cost_{fuel}"] = fuel_cost
        
        # Feedstock consumption if available
        if hasattr(model, 'feedstocks') and output["annual_global_feedstock_consumption"]:
            for feedstock in model.feedstocks:
                if feedstock in output["annual_global_feedstock_consumption"][yr]:
                    feedstock_amount = output["annual_global_feedstock_consumption"][yr][feedstock]
                    if feedstock_amount > 0.001:
                        row_data[f"Feedstock_Consumption_{feedstock}"] = feedstock_amount
        
        # Technology adoption
        for tech in model.technologies:
            if tech in output["annual_global_tech_adoption"][yr]:
                tech_adoption = output["annual_global_tech_adoption"][yr][tech]
                if tech_adoption > 0.001:
                    row_data[f"Tech_Adoption_{tech}"] = tech_adoption
        
        annual_summary.append(row_data)
    
    if annual_summary:
        annual_df = pd.DataFrame(annual_summary)
        annual_df.to_excel(writer, sheet_name='Global_Summary', index=False)
    
    # 3. Technology use by system, technology, and year
    tech_data = []
    for sys in model.systems:
        for yr in model.years:
            for tech in model.technologies:
                try:
                    # Try different ways to get technology usage
                    if hasattr(model, 'active_technology'):
                        tech_amount = value(model.active_technology[sys, tech, yr])
                    elif hasattr(model, 'prod_active'):
                        tech_amount = value(model.prod_active[sys, tech, yr])
                    else:
                        # If no specific tech variable, check if this tech contributes to emissions
                        tech_amount = value(model.emission_by_tech[sys, tech, yr]) > 0.001
                    
                    if tech_amount > 0.001:  # Only include technologies with significant usage
                        tech_row = {
                            'System': sys,
                            'Year': yr,
                            'Technology': tech,
                            'Usage': tech_amount
                        }
                        
                        # Add technology status if available
                        if hasattr(model, 'continue_technology'):
                            tech_row['Continue'] = value(model.continue_technology[sys, tech, yr])
                        if hasattr(model, 'replace'):
                            tech_row['Replace'] = value(model.replace[sys, tech, yr])
                        if hasattr(model, 'renew'):
                            tech_row['Renew'] = value(model.renew[sys, tech, yr])
                        
                        tech_data.append(tech_row)
                except:
                    pass
    
    if tech_data:
        tech_df = pd.DataFrame(tech_data)
        tech_df.to_excel(writer, sheet_name='Technology_Use', index=False)
    
    # 4. Fuel consumption by system, fuel, and year
    fuel_data = []
    for sys in model.systems:
        for yr in model.years:
            for fuel in model.fuels:
                try:
                    fuel_amount = 0
                    if hasattr(model, 'fuel_consumption'):
                        fuel_amount = value(model.fuel_consumption[sys, fuel, yr])
                    elif hasattr(model, 'fuel_use'):
                        fuel_amount = value(model.fuel_use[sys, fuel, yr])
                    
                    if fuel_amount > 0.001:  # Only include significant values
                        # Get fuel price - try both lowercase and original case
                        fuel_price = fuel_prices.get(fuel.lower(), fuel_prices.get(fuel, 0))
                        fuel_cost = fuel_amount * fuel_price
                        
                        fuel_data.append({
                            'System': sys,
                            'Year': yr,
                            'Fuel': fuel,
                            'Consumption': fuel_amount,
                            'Unit_Price': fuel_price,
                            'Fuel_Cost': fuel_cost
                        })
                except:
                    pass
    
    if fuel_data:
        fuel_df = pd.DataFrame(fuel_data)
        fuel_df.to_excel(writer, sheet_name='Fuel_Consumption', index=False)
    
    # 5. Feedstock consumption by system, feedstock, and year (if available)
    if hasattr(model, 'feedstocks'):
        feedstock_data = []
        for sys in model.systems:
            for yr in model.years:
                for feedstock in model.feedstocks:
                    try:
                        if hasattr(model, 'feedstock_consumption'):
                            feedstock_amount = value(model.feedstock_consumption[sys, feedstock, yr])
                        elif hasattr(model, 'feedstock_use'):
                            feedstock_amount = value(model.feedstock_use[sys, feedstock, yr])
                        else:
                            continue
                        
                        if feedstock_amount > 0.001:  # Only include significant values
                            feedstock_data.append({
                                'System': sys,
                                'Year': yr,
                                'Feedstock': feedstock,
                                'Consumption': feedstock_amount
                            })
                    except:
                        pass
        
        if feedstock_data:
            feedstock_df = pd.DataFrame(feedstock_data)
            feedstock_df.to_excel(writer, sheet_name='Feedstock_Consumption', index=False)
    
    # 6. Add a dedicated Fuel Costs sheet
    fuel_costs_data = []
    for sys in model.systems:
        for yr in model.years:
            for fuel in model.fuels:
                try:
                    fuel_amount = 0
                    if hasattr(model, 'fuel_consumption'):
                        fuel_amount = value(model.fuel_consumption[sys, fuel, yr])
                    elif hasattr(model, 'fuel_use'):
                        fuel_amount = value(model.fuel_use[sys, fuel, yr])
                    
                    if fuel_amount > 0.001:  # Only include significant values
                        # Get fuel price - try both lowercase and original case
                        fuel_price = fuel_prices.get(fuel.lower(), fuel_prices.get(fuel, 0))
                        fuel_cost = fuel_amount * fuel_price
                        
                        fuel_costs_data.append({
                            'System': sys,
                            'Year': yr,
                            'Fuel': fuel,
                            'Consumption': fuel_amount,
                            'Unit_Price': fuel_price,
                            'Fuel_Cost': fuel_cost
                        })
                except:
                    pass
    
    if fuel_costs_data:
        # Create the main fuel costs dataframe
        fuel_costs_df = pd.DataFrame(fuel_costs_data)
        
        # Create a summary by year
        summary_by_year = []
        for yr in sorted(model.years):
            year_data = fuel_costs_df[fuel_costs_df['Year'] == yr]
            total_cost = year_data['Fuel_Cost'].sum()
            
            summary_by_year.append({
                'Year': yr,
                'Total_Fuel_Cost': total_cost
            })
        
        # Create a summary by fuel type
        summary_by_fuel = []
        for fuel in model.fuels:
            fuel_data = fuel_costs_df[fuel_costs_df['Fuel'] == fuel]
            if not fuel_data.empty:
                total_consumption = fuel_data['Consumption'].sum()
                total_cost = fuel_data['Fuel_Cost'].sum()
                
                summary_by_fuel.append({
                    'Fuel': fuel,
                    'Total_Consumption': total_consumption,
                    'Total_Cost': total_cost,
                    'Average_Unit_Price': total_cost / total_consumption if total_consumption > 0 else 0
                })
        
        # Save the main data
        fuel_costs_df.to_excel(writer, sheet_name='Fuel_Costs', index=False)
        
        # Add the summaries if they exist
        if summary_by_year:
            summary_year_df = pd.DataFrame(summary_by_year)
            summary_year_df.to_excel(writer, sheet_name='Fuel_Cost_By_Year', index=False)
        
        if summary_by_fuel:
            summary_fuel_df = pd.DataFrame(summary_by_fuel)
            summary_fuel_df.to_excel(writer, sheet_name='Fuel_Cost_By_Type', index=False)
    
    # 7. Add a dedicated Cost Intensity sheet
    cost_intensity_data = []
    for yr in sorted(model.years):
        # Get production and costs
        production = output["annual_global_production"][yr]
        capex = output["annual_global_capex"][yr]
        opex = output["annual_global_opex"][yr]
        fuel_cost = output["annual_global_total_fuel_cost"][yr]
        total_cost = capex + opex + fuel_cost
        
        # Calculate cost intensity
        cost_intensity = total_cost / production if production > 0 else 0
        
        # Calculate component intensities
        capex_intensity = capex / production if production > 0 else 0
        opex_intensity = opex / production if production > 0 else 0
        fuel_cost_intensity = fuel_cost / production if production > 0 else 0
        
        # Add to data
        cost_intensity_data.append({
            'Year': yr,
            'Production': production,
            'Total_Cost': total_cost,
            'Cost_Intensity': cost_intensity,
            'CAPEX': capex,
            'CAPEX_Intensity': capex_intensity,
            'OPEX': opex,
            'OPEX_Intensity': opex_intensity,
            'Fuel_Cost': fuel_cost,
            'Fuel_Cost_Intensity': fuel_cost_intensity
        })
    
    if cost_intensity_data:
        cost_intensity_df = pd.DataFrame(cost_intensity_data)
        cost_intensity_df.to_excel(writer, sheet_name='Cost_Intensity', index=False)
    
    # 8. Add a Fuel Prices sheet
    fuel_prices_data = []
    for fuel, price in fuel_prices.items():
        fuel_prices_data.append({
            'Fuel': fuel,
            'Unit_Price': price
        })
    
    if fuel_prices_data:
        fuel_prices_df = pd.DataFrame(fuel_prices_data)
        fuel_prices_df.to_excel(writer, sheet_name='Fuel_Prices', index=False)
    
    # Save and close the Excel file
    writer.close()
    print(f"Results saved to {output_file}")
    return output_file

if __name__ == "__main__":
    file_path = 'database/steel_data_0310_notarget.xlsx'
    output = main(file_path, 
                 carboprice_include=False,
                 max_renew=2,
                 allow_replace_same_technology=False)
    
    if output:
        # Save results to the specific file name
        save_results_to_excel(output, 'results_notarget.xlsx')