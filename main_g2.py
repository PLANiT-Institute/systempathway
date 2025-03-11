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
    print("\n=== Annual Global Results ===")
    for yr in model.years:
        print(f"\nYear {yr}:")
        print(f"Total Emissions: {annual_global_total_emissions[yr]:.2f}")
        print(f"Total Production: {annual_global_production[yr]:.2f}")
        if annual_global_production[yr] > 0:
            print(f"Emission Intensity: {annual_global_total_emissions[yr]/annual_global_production[yr]:.4f}")

    return {
        "annual_global_total_emissions": annual_global_total_emissions,
        "annual_global_production": annual_global_production,
        "model": model,
        "result": result
    }

if __name__ == "__main__":
    file_path = 'database/steel_data_0310_g1.xlsx'
    output = main(file_path, 
                 carboprice_include=False,
                 max_renew=2,
                 allow_replace_same_technology=False)
 
    # Save results to Excel
    if output:
        print("\n=== Saving results to Excel ===")
        model = output["model"]
        result = output["result"]
        
        # Create a new Excel writer
        excel_file = 'results_g1.xlsx'
        writer = pd.ExcelWriter(excel_file, engine='openpyxl')
        
        # Create dataframes for different result types
        
        # 1. Emissions by system, technology, and year
        emissions_tech_data = []
        for sys in model.systems:
            for yr in model.years:
                for tech in model.technologies:
                    try:
                        tech_emissions = value(model.emission_by_tech[sys, tech, yr])
                        if tech_emissions > 0.001:  # Filter out very small values
                            emissions_tech_data.append({
                                'System': sys,
                                'Year': yr,
                                'Technology': tech,
                                'Emissions': tech_emissions
                            })
                    except:
                        pass  # Skip if variable doesn't exist
        
        if emissions_tech_data:
            emissions_tech_df = pd.DataFrame(emissions_tech_data)
            emissions_tech_df.to_excel(writer, sheet_name='Emissions_by_Tech', index=False)
        
        # 2. Emissions by system and year
        emissions_data = []
        for sys in model.systems:
            for yr in model.years:
                system_emissions = sum(value(model.emission_by_tech[sys, tech, yr]) for tech in model.technologies)
                emissions_data.append({
                    'System': sys,
                    'Year': yr,
                    'Emissions': system_emissions,
                    'Production': value(model.production[sys, yr]),
                    'Emission_Intensity': system_emissions / value(model.production[sys, yr]) if value(model.production[sys, yr]) > 0 else 0
                })
        
        emissions_df = pd.DataFrame(emissions_data)
        emissions_df.to_excel(writer, sheet_name='Emissions', index=False)
        
        # 3. Global summary by year
        global_data = []
        for yr in model.years:
            global_data.append({
                'Year': yr,
                'Total_Emissions': output["annual_global_total_emissions"][yr],
                'Total_Production': output["annual_global_production"][yr],
                'Global_Emission_Intensity': output["annual_global_total_emissions"][yr] / output["annual_global_production"][yr] if output["annual_global_production"][yr] > 0 else 0
            })
        
        global_df = pd.DataFrame(global_data)
        global_df.to_excel(writer, sheet_name='Global_Summary', index=False)
        
        # 4. Fuel consumption by system, fuel, and year
        fuel_data = []
        for sys in model.systems:
            for yr in model.years:
                for fuel in model.fuels:
                    try:
                        if hasattr(model, 'fuel_use'):
                            fuel_amount = value(model.fuel_use[sys, fuel, yr])
                            if fuel_amount > 0.001:  # Filter out very small values
                                fuel_data.append({
                                    'System': sys,
                                    'Year': yr,
                                    'Fuel': fuel,
                                    'Consumption': fuel_amount
                                })
                    except:
                        pass  # Skip if variable doesn't exist
        
        if fuel_data:
            fuel_df = pd.DataFrame(fuel_data)
            fuel_df.to_excel(writer, sheet_name='Fuel_Consumption', index=False)
        
        # 5. Feedstock consumption by system, feedstock, and year
        feedstock_data = []
        for sys in model.systems:
            for yr in model.years:
                for feedstock in model.feedstocks:
                    try:
                        if hasattr(model, 'feedstock_use'):
                            feedstock_amount = value(model.feedstock_use[sys, feedstock, yr])
                            if feedstock_amount > 0.001:  # Filter out very small values
                                feedstock_data.append({
                                    'System': sys,
                                    'Year': yr,
                                    'Feedstock': feedstock,
                                    'Consumption': feedstock_amount
                                })
                    except:
                        pass  # Skip if variable doesn't exist
        
        if feedstock_data:
            feedstock_df = pd.DataFrame(feedstock_data)
            feedstock_df.to_excel(writer, sheet_name='Feedstock_Consumption', index=False)
        
        # 6. Technology use by system, technology, and year
        tech_data = []
        for sys in model.systems:
            for yr in model.years:
                for tech in model.technologies:
                    try:
                        # Try different possible variable names for technology use
                        if hasattr(model, 'production_by_tech'):
                            tech_amount = value(model.production_by_tech[sys, tech, yr])
                        elif hasattr(model, 'technology_production'):
                            tech_amount = value(model.technology_production[sys, tech, yr])
                        elif hasattr(model, 'tech_production'):
                            tech_amount = value(model.tech_production[sys, tech, yr])
                        else:
                            # If no specific tech production variable, check if this tech contributes to emissions
                            tech_amount = value(model.emission_by_tech[sys, tech, yr]) > 0.001
                            
                        if tech_amount > 0.001:  # Filter out very small values
                            tech_data.append({
                                'System': sys,
                                'Year': yr,
                                'Technology': tech,
                                'Production': tech_amount
                            })
                    except:
                        pass  # Skip if variable doesn't exist
        
        if tech_data:
            tech_df = pd.DataFrame(tech_data)
            tech_df.to_excel(writer, sheet_name='Technology_Use', index=False)
        
        # 7. Renewal decisions (if the variable exists)
        renewal_data = []
        for sys in model.systems:
            for yr in model.years:
                for tech in model.technologies:
                    try:
                        if hasattr(model, 'renewal') and value(model.renewal[sys, tech, yr]) > 0.001:
                            renewal_data.append({
                                'System': sys,
                                'Year': yr,
                                'Technology': tech,
                                'Renewal_Amount': value(model.renewal[sys, tech, yr])
                            })
                    except:
                        pass  # Skip if variable doesn't exist
        
        if renewal_data:
            renewal_df = pd.DataFrame(renewal_data)
            renewal_df.to_excel(writer, sheet_name='Renewals', index=False)
        
        # 8. Export all model variables (to help identify what's available)
        var_data = []
        for v in model.component_objects(Var, active=True):
            var_name = str(v)
            print(f"Found variable: {var_name}")  # Print variable names to help debugging
            for index in v:
                try:
                    var_data.append({
                        'Variable': var_name,
                        'Index': str(index),
                        'Value': value(v[index])
                    })
                except:
                    pass  # Skip if can't get value
        
        if var_data:
            var_df = pd.DataFrame(var_data)
            var_df.to_excel(writer, sheet_name='All_Variables', index=False)
        
        # Save and close the Excel file
        writer.close()
        print(f"Results saved to {excel_file}")
