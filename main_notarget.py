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
    annual_global_renewal_cost = {yr: 0.0 for yr in model.years}  # Added renewal cost tracking
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

    # Try to initialize feedstock consumption if the model has feedstocks
    annual_global_feedstock_consumption = {}
    if hasattr(model, 'feedstocks'):
        annual_global_feedstock_consumption = {yr: {feedstock: 0.0 for feedstock in model.feedstocks} for yr in model.years}

    # Track system-level costs
    system_costs = {}
    for sys in model.systems:
        system_costs[sys] = {
            'capex': {yr: 0.0 for yr in model.years},
            'opex': {yr: 0.0 for yr in model.years},
            'renewal': {yr: 0.0 for yr in model.years},
            'fuel': {yr: 0.0 for yr in model.years}
        }

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
                        
                        # Add to system-level fuel cost
                        system_costs[sys]['fuel'][yr] += fuel_cost
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
            
            # DIRECTLY EXTRACT COSTS FROM THE OPTIMIZATION MODEL VARIABLES
            # These are the actual costs used in the objective function
            for tech in model.technologies:
                try:
                    # Extract CAPEX from replace_prod_active
                    if hasattr(model, 'replace_prod_active') and hasattr(model, 'capex_param'):
                        if (tech, yr) in model.capex_param and (sys, tech, yr) in model.replace_prod_active:
                            capex = value(model.capex_param[tech, yr] * model.replace_prod_active[sys, tech, yr])
                            system_costs[sys]['capex'][yr] += capex
                            annual_global_capex[yr] += capex
                            print(f"Added direct CAPEX for system {sys}, tech {tech}, year {yr}: {capex}")
                    
                    # Extract RENEWAL cost from renew_prod_active
                    if hasattr(model, 'renew_prod_active') and hasattr(model, 'renewal_param'):
                        if (tech, yr) in model.renewal_param and (sys, tech, yr) in model.renew_prod_active:
                            renewal = value(model.renewal_param[tech, yr] * model.renew_prod_active[sys, tech, yr])
                            system_costs[sys]['renewal'][yr] += renewal
                            annual_global_renewal_cost[yr] += renewal
                            print(f"Added direct RENEWAL cost for system {sys}, tech {tech}, year {yr}: {renewal}")
                    
                    # Extract OPEX from prod_active
                    if hasattr(model, 'prod_active') and hasattr(model, 'opex_param'):
                        if (tech, yr) in model.opex_param and (sys, tech, yr) in model.prod_active:
                            opex = value(model.opex_param[tech, yr] * model.prod_active[sys, tech, yr])
                            system_costs[sys]['opex'][yr] += opex
                            annual_global_opex[yr] += opex
                            print(f"Added direct OPEX for system {sys}, tech {tech}, year {yr}: {opex}")
                except Exception as e:
                    print(f"Error extracting direct costs for system {sys}, tech {tech}, year {yr}: {e}")
    
    # Print the model's variable names to help diagnose what's available
    print("\n=== Model Variables ===")
    var_names = [name for name in dir(model) if not name.startswith('_') and isinstance(getattr(model, name), pyomo.environ.Var)]
    print("Variable names:", var_names)
    
    # Print the model's parameter names to help diagnose what's available
    print("\n=== Model Parameters ===")
    param_names = [name for name in dir(model) if not name.startswith('_') and isinstance(getattr(model, name), pyomo.environ.Param)]
    print("Parameter names:", param_names)
    
    # Print the first few indices of key parameters to understand their structure
    for param_name in ['capex_param', 'opex_param', 'renewal_param']:
        if hasattr(model, param_name):
            param = getattr(model, param_name)
            try:
                indices = list(param.keys())
                if indices:
                    print(f"Parameter {param_name} has indices like: {indices[:3]}")
                    # For the first index, print the value
                    first_idx = indices[0]
                    print(f"  Value at {first_idx}: {value(param[first_idx])}")
            except:
                pass
    
    # Extract cost data from the model - more comprehensive approach
    # Try multiple possible variable names for each cost type
    
    # CAPEX - Try technology-level first, then system-level, then global
    try:
        # First check if we have technology-specific CAPEX variables
        if hasattr(model, 'capex_tech'):
            print("Found capex_tech variable")
            for sys in model.systems:
                for tech in model.technologies:
                    for yr in model.years:
                        try:
                            if (sys, tech, yr) in model.capex_tech:
                                tech_capex = value(model.capex_tech[sys, tech, yr])
                                system_costs[sys]['capex'][yr] += tech_capex
                                annual_global_capex[yr] += tech_capex
                        except:
                            pass
        elif hasattr(model, 'technology_capex'):
            print("Found technology_capex variable")
            for sys in model.systems:
                for tech in model.technologies:
                    for yr in model.years:
                        try:
                            if (sys, tech, yr) in model.technology_capex:
                                tech_capex = value(model.technology_capex[sys, tech, yr])
                                system_costs[sys]['capex'][yr] += tech_capex
                                annual_global_capex[yr] += tech_capex
                        except:
                            pass
        
        # Check for any variable that might contain CAPEX information
        for var_name in var_names:
            if 'capex' in var_name.lower() and var_name not in ['capex_tech', 'technology_capex', 'system_capex', 'capex_system', 'capex', 'capex_cost']:
                print(f"Found potential CAPEX variable: {var_name}")
                var = getattr(model, var_name)
                try:
                    for idx in var.keys():
                        # Try to determine if this is a system-year index
                        if isinstance(idx, tuple) and len(idx) == 2:
                            sys_candidate, yr_candidate = idx
                            if sys_candidate in model.systems and yr_candidate in model.years:
                                system_costs[sys_candidate]['capex'][yr_candidate] += value(var[idx])
                                annual_global_capex[yr_candidate] += value(var[idx])
                                print(f"  Added CAPEX for system {sys_candidate}, year {yr_candidate}: {value(var[idx])}")
                        # Try to determine if this is a system-tech-year index
                        elif isinstance(idx, tuple) and len(idx) == 3:
                            sys_candidate, tech_candidate, yr_candidate = idx
                            if sys_candidate in model.systems and tech_candidate in model.technologies and yr_candidate in model.years:
                                system_costs[sys_candidate]['capex'][yr_candidate] += value(var[idx])
                                annual_global_capex[yr_candidate] += value(var[idx])
                                print(f"  Added CAPEX for system {sys_candidate}, tech {tech_candidate}, year {yr_candidate}: {value(var[idx])}")
                except Exception as e:
                    print(f"  Error processing {var_name}: {e}")
        
        # Then check for system-level CAPEX again (in case we missed any)
        if hasattr(model, 'capex_by_system'):
            print("Found capex_by_system variable")
            for sys in model.systems:
                for yr in model.years:
                    try:
                        if (sys, yr) in model.capex_by_system:
                            system_capex = value(model.capex_by_system[sys, yr])
                            # Only add if we haven't already counted this
                            if system_costs[sys]['capex'][yr] == 0:
                                system_costs[sys]['capex'][yr] += system_capex
                                annual_global_capex[yr] += system_capex
                    except:
                        pass
        
        # Finally check for global CAPEX
        if hasattr(model, 'capex'):
            print("Found global capex variable")
            # Global CAPEX
            for yr in model.years:
                try:
                    if yr in model.capex:
                        # Only add if we haven't already counted this
                        if annual_global_capex[yr] == 0:
                            annual_global_capex[yr] = value(model.capex[yr])
                except:
                    pass
        elif hasattr(model, 'capex_cost'):
            print("Found global capex_cost variable")
            # Alternative global CAPEX
            for yr in model.years:
                try:
                    if yr in model.capex_cost:
                        # Only add if we haven't already counted this
                        if annual_global_capex[yr] == 0:
                            annual_global_capex[yr] = value(model.capex_cost[yr])
                except:
                    pass
        
        # If we have global CAPEX but no system breakdown, distribute based on production
        if any(annual_global_capex[yr] > 0 for yr in model.years) and all(system_costs[sys]['capex'][yr] == 0 for sys in model.systems for yr in model.years):
            print("Distributing global CAPEX to systems based on production share")
            for yr in model.years:
                total_production = sum(value(model.production[sys, yr]) for sys in model.systems)
                if total_production > 0:
                    for sys in model.systems:
                        production_share = value(model.production[sys, yr]) / total_production
                        system_costs[sys]['capex'][yr] = annual_global_capex[yr] * production_share
    except Exception as e:
        print(f"Error extracting CAPEX data: {e}")
    
    # OPEX - Similar comprehensive approach as CAPEX
    try:
        # First check if we have technology-specific OPEX variables
        if hasattr(model, 'opex_tech'):
            print("Found opex_tech variable")
            for sys in model.systems:
                for tech in model.technologies:
                    for yr in model.years:
                        try:
                            if (sys, tech, yr) in model.opex_tech:
                                tech_opex = value(model.opex_tech[sys, tech, yr])
                                system_costs[sys]['opex'][yr] += tech_opex
                                annual_global_opex[yr] += tech_opex
                        except:
                            pass
        elif hasattr(model, 'technology_opex'):
            print("Found technology_opex variable")
            for sys in model.systems:
                for tech in model.technologies:
                    for yr in model.years:
                        try:
                            if (sys, tech, yr) in model.technology_opex:
                                tech_opex = value(model.technology_opex[sys, tech, yr])
                                system_costs[sys]['opex'][yr] += tech_opex
                                annual_global_opex[yr] += tech_opex
                        except:
                            pass
        
        # Check for any variable that might contain OPEX information
        for var_name in var_names:
            if 'opex' in var_name.lower() and var_name not in ['opex_tech', 'technology_opex', 'system_opex', 'opex_system', 'opex', 'opex_cost']:
                print(f"Found potential OPEX variable: {var_name}")
                var = getattr(model, var_name)
                try:
                    for idx in var.keys():
                        # Try to determine if this is a system-year index
                        if isinstance(idx, tuple) and len(idx) == 2:
                            sys_candidate, yr_candidate = idx
                            if sys_candidate in model.systems and yr_candidate in model.years:
                                system_costs[sys_candidate]['opex'][yr_candidate] += value(var[idx])
                                annual_global_opex[yr_candidate] += value(var[idx])
                                print(f"  Added OPEX for system {sys_candidate}, year {yr_candidate}: {value(var[idx])}")
                        # Try to determine if this is a system-tech-year index
                        elif isinstance(idx, tuple) and len(idx) == 3:
                            sys_candidate, tech_candidate, yr_candidate = idx
                            if sys_candidate in model.systems and tech_candidate in model.technologies and yr_candidate in model.years:
                                system_costs[sys_candidate]['opex'][yr_candidate] += value(var[idx])
                                annual_global_opex[yr_candidate] += value(var[idx])
                                print(f"  Added OPEX for system {sys_candidate}, tech {tech_candidate}, year {yr_candidate}: {value(var[idx])}")
                except Exception as e:
                    print(f"  Error processing {var_name}: {e}")
        
        # Then check for system-level OPEX again
        if hasattr(model, 'opex_by_system'):
            print("Found opex_by_system variable")
            for sys in model.systems:
                for yr in model.years:
                    try:
                        if (sys, yr) in model.opex_by_system:
                            system_opex = value(model.opex_by_system[sys, yr])
                            # Only add if we haven't already counted this
                            if system_costs[sys]['opex'][yr] == 0:
                                system_costs[sys]['opex'][yr] += system_opex
                                annual_global_opex[yr] += system_opex
                    except:
                        pass
        
        # Finally check for global OPEX
        if hasattr(model, 'opex'):
            print("Found global opex variable")
            # Global OPEX
            for yr in model.years:
                try:
                    if yr in model.opex:
                        # Only add if we haven't already counted this
                        if annual_global_opex[yr] == 0:
                            annual_global_opex[yr] = value(model.opex[yr])
                except:
                    pass
        elif hasattr(model, 'opex_cost'):
            print("Found global opex_cost variable")
            # Alternative global OPEX
            for yr in model.years:
                try:
                    if yr in model.opex_cost:
                        # Only add if we haven't already counted this
                        if annual_global_opex[yr] == 0:
                            annual_global_opex[yr] = value(model.opex_cost[yr])
                except:
                    pass
        
        # If we have global OPEX but no system breakdown, distribute based on production
        if any(annual_global_opex[yr] > 0 for yr in model.years) and all(system_costs[sys]['opex'][yr] == 0 for sys in model.systems for yr in model.years):
            print("Distributing global OPEX to systems based on production share")
            for yr in model.years:
                total_production = sum(value(model.production[sys, yr]) for sys in model.systems)
                if total_production > 0:
                    for sys in model.systems:
                        production_share = value(model.production[sys, yr]) / total_production
                        system_costs[sys]['opex'][yr] = annual_global_opex[yr] * production_share
    except Exception as e:
        print(f"Error extracting OPEX data: {e}")
    
    # RENEWAL costs - Similar comprehensive approach
    try:
        # First check if we have technology-specific renewal cost variables
        if hasattr(model, 'renewal_cost_tech'):
            print("Found renewal_cost_tech variable")
            for sys in model.systems:
                for tech in model.technologies:
                    for yr in model.years:
                        try:
                            if (sys, tech, yr) in model.renewal_cost_tech:
                                tech_renewal = value(model.renewal_cost_tech[sys, tech, yr])
                                system_costs[sys]['renewal'][yr] += tech_renewal
                                annual_global_renewal_cost[yr] += tech_renewal
                        except:
                            pass
        elif hasattr(model, 'technology_renewal_cost'):
            print("Found technology_renewal_cost variable")
            for sys in model.systems:
                for tech in model.technologies:
                    for yr in model.years:
                        try:
                            if (sys, tech, yr) in model.technology_renewal_cost:
                                tech_renewal = value(model.technology_renewal_cost[sys, tech, yr])
                                system_costs[sys]['renewal'][yr] += tech_renewal
                                annual_global_renewal_cost[yr] += tech_renewal
                        except:
                            pass
        
        # Check for any variable that might contain renewal cost information
        for var_name in var_names:
            if ('renewal' in var_name.lower() or 'renew_cost' in var_name.lower()) and var_name not in ['renewal_cost_tech', 'technology_renewal_cost', 'system_renewal_cost', 'renewal_cost_system', 'renewal_cost']:
                print(f"Found potential renewal cost variable: {var_name}")
                var = getattr(model, var_name)
                try:
                    for idx in var.keys():
                        # Try to determine if this is a system-year index
                        if isinstance(idx, tuple) and len(idx) == 2:
                            sys_candidate, yr_candidate = idx
                            if sys_candidate in model.systems and yr_candidate in model.years:
                                system_costs[sys_candidate]['renewal'][yr_candidate] += value(var[idx])
                                annual_global_renewal_cost[yr_candidate] += value(var[idx])
                                print(f"  Added renewal cost for system {sys_candidate}, year {yr_candidate}: {value(var[idx])}")
                        # Try to determine if this is a system-tech-year index
                        elif isinstance(idx, tuple) and len(idx) == 3:
                            sys_candidate, tech_candidate, yr_candidate = idx
                            if sys_candidate in model.systems and tech_candidate in model.technologies and yr_candidate in model.years:
                                system_costs[sys_candidate]['renewal'][yr_candidate] += value(var[idx])
                                annual_global_renewal_cost[yr_candidate] += value(var[idx])
                                print(f"  Added renewal cost for system {sys_candidate}, tech {tech_candidate}, year {yr_candidate}: {value(var[idx])}")
                except Exception as e:
                    print(f"  Error processing {var_name}: {e}")
        
        # Then check for system-level renewal costs again
        if hasattr(model, 'renewal_cost_by_system'):
            print("Found renewal_cost_by_system variable")
            for sys in model.systems:
                for yr in model.years:
                    try:
                        if (sys, yr) in model.renewal_cost_by_system:
                            system_renewal = value(model.renewal_cost_by_system[sys, yr])
                            # Only add if we haven't already counted this
                            if system_costs[sys]['renewal'][yr] == 0:
                                system_costs[sys]['renewal'][yr] += system_renewal
                                annual_global_renewal_cost[yr] += system_renewal
                    except:
                        pass
        
        # Finally check for global renewal costs
        if hasattr(model, 'renewal_cost'):
            print("Found global renewal_cost variable")
            # Global renewal cost
            for yr in model.years:
                try:
                    if yr in model.renewal_cost:
                        # Only add if we haven't already counted this
                        if annual_global_renewal_cost[yr] == 0:
                            annual_global_renewal_cost[yr] = value(model.renewal_cost[yr])
                except:
                    pass
        
        # If no direct renewal cost variable, try to calculate from renewal decisions
        if all(annual_global_renewal_cost[yr] == 0 for yr in model.years) and hasattr(model, 'renew'):
            print("Calculating renewal costs from renewal decisions")
            # Try to get renewal unit costs
            renewal_unit_costs = {}
            if hasattr(model, 'renewal_unit_cost'):
                for tech in model.technologies:
                    try:
                        renewal_unit_costs[tech] = value(model.renewal_unit_cost[tech])
                    except:
                        pass
            elif hasattr(model, 'tech_renewal_cost'):
                for tech in model.technologies:
                    try:
                        renewal_unit_costs[tech] = value(model.tech_renewal_cost[tech])
                    except:
                        pass
            
            # If we have renewal unit costs, calculate renewal costs
            if renewal_unit_costs:
                for sys in model.systems:
                    for tech in model.technologies:
                        for yr in model.years:
                            try:
                                if (sys, tech, yr) in model.renew:
                                    renewal_decision = value(model.renew[sys, tech, yr])
                                    if renewal_decision > 0.001 and tech in renewal_unit_costs:
                                        renewal_cost = renewal_decision * renewal_unit_costs[tech]
                                        system_costs[sys]['renewal'][yr] += renewal_cost
                                        annual_global_renewal_cost[yr] += renewal_cost
                            except:
                                pass
        
        # If we have global renewal costs but no system breakdown, distribute based on production
        if any(annual_global_renewal_cost[yr] > 0 for yr in model.years) and all(system_costs[sys]['renewal'][yr] == 0 for sys in model.systems for yr in model.years):
            print("Distributing global renewal costs to systems based on production share")
            for yr in model.years:
                total_production = sum(value(model.production[sys, yr]) for sys in model.systems)
                if total_production > 0:
                    for sys in model.systems:
                        production_share = value(model.production[sys, yr]) / total_production
                        system_costs[sys]['renewal'][yr] = annual_global_renewal_cost[yr] * production_share
    except Exception as e:
        print(f"Error extracting RENEWAL cost data: {e}")
    
    # Print a summary of cost extraction
    print("\n=== Cost Extraction Summary ===")
    for yr in model.years:
        print(f"\nYear {yr} costs:")
        print(f"  CAPEX: {annual_global_capex[yr]:.2f}")
        print(f"  OPEX: {annual_global_opex[yr]:.2f}")
        print(f"  Renewal: {annual_global_renewal_cost[yr]:.2f}")
        print(f"  Fuel: {annual_global_total_fuel_cost[yr]:.2f}")
        print(f"  Total: {annual_global_capex[yr] + annual_global_opex[yr] + annual_global_renewal_cost[yr] + annual_global_total_fuel_cost[yr]:.2f}")
    
    # Print system-level costs for verification
    print("\n=== System-Level Cost Summary ===")
    for sys in model.systems:
        print(f"\nSystem: {sys}")
        for yr in model.years:
            print(f"  Year {yr}:")
            print(f"    CAPEX: {system_costs[sys]['capex'][yr]:.2f}")
            print(f"    OPEX: {system_costs[sys]['opex'][yr]:.2f}")
            print(f"    Renewal: {system_costs[sys]['renewal'][yr]:.2f}")
            print(f"    Fuel: {system_costs[sys]['fuel'][yr]:.2f}")
            print(f"    Total: {system_costs[sys]['capex'][yr] + system_costs[sys]['opex'][yr] + system_costs[sys]['renewal'][yr] + system_costs[sys]['fuel'][yr]:.2f}")
    
    # If we couldn't extract any cost data, print a warning
    if all(annual_global_capex[yr] == 0 for yr in model.years):
        print("\nWARNING: Could not extract any CAPEX data from the model.")
        print("Available model attributes:", [attr for attr in dir(model) if not attr.startswith('_')])
    
    if all(annual_global_opex[yr] == 0 for yr in model.years):
        print("\nWARNING: Could not extract any OPEX data from the model.")
    
    if all(annual_global_renewal_cost[yr] == 0 for yr in model.years):
        print("\nWARNING: Could not extract any RENEWAL cost data from the model.")

    # Print results
    print("\n=== Annual Global Results ===")
    for yr in model.years:
        print(f"\nYear {yr}:")
        print(f"Total Emissions: {annual_global_total_emissions[yr]:.2f}")
        print(f"Total Production: {annual_global_production[yr]:.2f}")
        if annual_global_production[yr] > 0:
            print(f"Emission Intensity: {annual_global_total_emissions[yr]/annual_global_production[yr]:.4f}")
        
        # Print cost breakdown
        print(f"CAPEX: {annual_global_capex[yr]:.2f}")
        print(f"OPEX: {annual_global_opex[yr]:.2f}")
        print(f"Renewal Cost: {annual_global_renewal_cost[yr]:.2f}")
        print(f"Fuel Cost: {annual_global_total_fuel_cost[yr]:.2f}")
        
        # Calculate total cost including renewal
        total_cost = annual_global_capex[yr] + annual_global_opex[yr] + annual_global_renewal_cost[yr] + annual_global_total_fuel_cost[yr]
        print(f"Total Cost: {total_cost:.2f}")
        
        # Calculate and print cost intensity
        if annual_global_production[yr] > 0:
            cost_intensity = total_cost / annual_global_production[yr]
            print(f"Cost Intensity: {cost_intensity:.2f} $/unit")
            print(f"  CAPEX Intensity: {annual_global_capex[yr]/annual_global_production[yr]:.2f} $/unit")
            print(f"  OPEX Intensity: {annual_global_opex[yr]/annual_global_production[yr]:.2f} $/unit")
            print(f"  Renewal Intensity: {annual_global_renewal_cost[yr]/annual_global_production[yr]:.2f} $/unit")
            print(f"  Fuel Cost Intensity: {annual_global_total_fuel_cost[yr]/annual_global_production[yr]:.2f} $/unit")

    return {
        "annual_global_total_emissions": annual_global_total_emissions,
        "annual_global_production": annual_global_production,
        "annual_global_capex": annual_global_capex,
        "annual_global_opex": annual_global_opex,
        "annual_global_renewal_cost": annual_global_renewal_cost,  # Added renewal cost
        "annual_global_fuel_consumption": annual_global_fuel_consumption,
        "annual_global_fuel_cost": annual_global_fuel_cost,
        "annual_global_total_fuel_cost": annual_global_total_fuel_cost,
        "annual_global_feedstock_consumption": annual_global_feedstock_consumption if hasattr(model, 'feedstocks') else {},
        "annual_global_tech_adoption": annual_global_tech_adoption,
        "system_costs": system_costs,  # Added system-level cost breakdown
        "fuel_prices": fuel_prices,
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
    fuel_prices = output["fuel_prices"]
    system_costs = output["system_costs"]
    
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
            
            # Add system costs
            row_data["CAPEX"] = system_costs[sys]['capex'][yr]
            row_data["OPEX"] = system_costs[sys]['opex'][yr]
            row_data["Renewal_Cost"] = system_costs[sys]['renewal'][yr]
            row_data["Fuel_Cost"] = system_costs[sys]['fuel'][yr]
            row_data["Total_Cost"] = (
                system_costs[sys]['capex'][yr] + 
                system_costs[sys]['opex'][yr] + 
                system_costs[sys]['renewal'][yr] + 
                system_costs[sys]['fuel'][yr]
            )
            
            # Add cost intensity if production is non-zero
            if row_data["Production"] > 0:
                row_data["Cost_Intensity"] = row_data["Total_Cost"] / row_data["Production"]
                row_data["CAPEX_Intensity"] = system_costs[sys]['capex'][yr] / row_data["Production"]
                row_data["OPEX_Intensity"] = system_costs[sys]['opex'][yr] / row_data["Production"]
                row_data["Renewal_Intensity"] = system_costs[sys]['renewal'][yr] / row_data["Production"]
                row_data["Fuel_Cost_Intensity"] = system_costs[sys]['fuel'][yr] / row_data["Production"]
            
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
            
            # Fuel consumption
            for fuel in model.fuels:
                try:
                    fuel_amount = 0
                    if hasattr(model, 'fuel_consumption'):
                        fuel_amount = value(model.fuel_consumption[sys, fuel, yr])
                    elif hasattr(model, 'fuel_use'):
                        fuel_amount = value(model.fuel_use[sys, fuel, yr])
                    
                    if fuel_amount > 0.001:
                        row_data[f"Fuel_{fuel}"] = fuel_amount
                except:
                    pass
            
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
        row_data["Total_Renewal_Cost"] = output["annual_global_renewal_cost"][yr]
        row_data["Total_Fuel_Cost"] = output["annual_global_total_fuel_cost"][yr]
        
        # Total cost including renewal
        total_cost = (
            output["annual_global_capex"][yr] + 
            output["annual_global_opex"][yr] + 
            output["annual_global_renewal_cost"][yr] + 
            output["annual_global_total_fuel_cost"][yr]
        )
        row_data["Total_Cost"] = total_cost
        
        # Add cost intensity (cost per unit of production)
        if output["annual_global_production"][yr] > 0:
            row_data["Cost_Intensity"] = total_cost / output["annual_global_production"][yr]
            row_data["CAPEX_Intensity"] = output["annual_global_capex"][yr] / output["annual_global_production"][yr]
            row_data["OPEX_Intensity"] = output["annual_global_opex"][yr] / output["annual_global_production"][yr]
            row_data["Renewal_Intensity"] = output["annual_global_renewal_cost"][yr] / output["annual_global_production"][yr]
            row_data["Fuel_Cost_Intensity"] = output["annual_global_total_fuel_cost"][yr] / output["annual_global_production"][yr]
        else:
            row_data["Cost_Intensity"] = 0
            row_data["CAPEX_Intensity"] = 0
            row_data["OPEX_Intensity"] = 0
            row_data["Renewal_Intensity"] = 0
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
                        
                        # Add technology-specific costs if available
                        try:
                            if hasattr(model, 'capex_param') and (tech, yr) in model.capex_param:
                                tech_row['CAPEX_Rate'] = value(model.capex_param[tech, yr])
                                if hasattr(model, 'replace_prod_active') and (sys, tech, yr) in model.replace_prod_active:
                                    tech_row['CAPEX'] = value(model.capex_param[tech, yr] * model.replace_prod_active[sys, tech, yr])
                        except:
                            pass
                        
                        try:
                            if hasattr(model, 'opex_param') and (tech, yr) in model.opex_param:
                                tech_row['OPEX_Rate'] = value(model.opex_param[tech, yr])
                                if hasattr(model, 'prod_active') and (sys, tech, yr) in model.prod_active:
                                    tech_row['OPEX'] = value(model.opex_param[tech, yr] * model.prod_active[sys, tech, yr])
                        except:
                            pass
                        
                        try:
                            if hasattr(model, 'renewal_param') and (tech, yr) in model.renewal_param:
                                tech_row['Renewal_Rate'] = value(model.renewal_param[tech, yr])
                                if hasattr(model, 'renew_prod_active') and (sys, tech, yr) in model.renew_prod_active:
                                    tech_row['Renewal_Cost'] = value(model.renewal_param[tech, yr] * model.renew_prod_active[sys, tech, yr])
                        except:
                            pass
                        
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
        renewal = output["annual_global_renewal_cost"][yr]
        fuel_cost = output["annual_global_total_fuel_cost"][yr]
        total_cost = capex + opex + renewal + fuel_cost
        
        # Calculate cost intensity
        cost_intensity = total_cost / production if production > 0 else 0
        
        # Calculate component intensities
        capex_intensity = capex / production if production > 0 else 0
        opex_intensity = opex / production if production > 0 else 0
        renewal_intensity = renewal / production if production > 0 else 0
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
            'Renewal_Cost': renewal,
            'Renewal_Intensity': renewal_intensity,
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
    
    # 9. Add a dedicated Cost Breakdown sheet
    cost_breakdown_data = []
    for sys in model.systems:
        for yr in model.years:
            cost_breakdown_data.append({
                'System': sys,
                'Year': yr,
                'CAPEX': system_costs[sys]['capex'][yr],
                'OPEX': system_costs[sys]['opex'][yr],
                'Renewal_Cost': system_costs[sys]['renewal'][yr],
                'Fuel_Cost': system_costs[sys]['fuel'][yr],
                'Total_Cost': (
                    system_costs[sys]['capex'][yr] + 
                    system_costs[sys]['opex'][yr] + 
                    system_costs[sys]['renewal'][yr] + 
                    system_costs[sys]['fuel'][yr]
                )
            })
    
    if cost_breakdown_data:
        cost_breakdown_df = pd.DataFrame(cost_breakdown_data)
        cost_breakdown_df.to_excel(writer, sheet_name='Cost_Breakdown', index=False)
    
    # 10. Add a dedicated Technology Cost Parameters sheet
    tech_cost_params = []
    if hasattr(model, 'capex_param') or hasattr(model, 'opex_param') or hasattr(model, 'renewal_param'):
        for tech in model.technologies:
            for yr in model.years:
                row = {'Technology': tech, 'Year': yr}
                
                # Add CAPEX parameter
                if hasattr(model, 'capex_param'):
                    try:
                        if (tech, yr) in model.capex_param:
                            row['CAPEX_Rate'] = value(model.capex_param[tech, yr])
                    except:
                        pass
                
                # Add OPEX parameter
                if hasattr(model, 'opex_param'):
                    try:
                        if (tech, yr) in model.opex_param:
                            row['OPEX_Rate'] = value(model.opex_param[tech, yr])
                    except:
                        pass
                
                # Add Renewal parameter
                if hasattr(model, 'renewal_param'):
                    try:
                        if (tech, yr) in model.renewal_param:
                            row['Renewal_Rate'] = value(model.renewal_param[tech, yr])
                    except:
                        pass
                
                # Only add row if it has at least one cost parameter
                if len(row) > 2:
                    tech_cost_params.append(row)
    
    if tech_cost_params:
        tech_cost_params_df = pd.DataFrame(tech_cost_params)
        tech_cost_params_df.to_excel(writer, sheet_name='Technology_Cost_Parameters', index=False)
    
    # Save and close the Excel file
    writer.close()
    print(f"Results saved to {output_file}")
    return output_file

if __name__ == "__main__":
    file_path = 'database/steel_data_0310_global.xlsx'
    output = main(file_path, 
                 carboprice_include=False,
                 max_renew=2,
                 allow_replace_same_technology=False)
    
    if output:
        # Save results to the specific file name
        save_results_to_excel(output, 'results_notarget.xlsx')