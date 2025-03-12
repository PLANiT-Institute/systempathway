import pandas as pd
import numpy as np
from pyomo.environ import value

def calculate_baseline_emissions(model, data):
    """
    Calculate baseline emissions for each year based on the model parameters.
    
    Args:
        model: The Pyomo model
        data: The input data dictionary
    
    Returns:
        DataFrame with baseline emissions by year and system
    """
    baseline_emissions = []
    
    # Get the first year (baseline year)
    baseline_year = min(model.years)
    
    # Calculate emissions for each system in the baseline year
    for sys in model.systems:
        # Get baseline technology for this system
        baseline_tech = data['baseline'].loc[sys, 'technology']
        
        # Calculate fuel emissions
        fuel_emissions = 0
        for fuel in model.fuels:
            if fuel in model.baseline_fuels[sys]:
                # Get the index for this fuel in baseline_fuels
                idx = model.baseline_fuels[sys].index(fuel)
                
                # Calculate fuel consumption in baseline
                fuel_consumption = (
                    model.baseline_fuel_shares[sys][idx] * 
                    model.baseline_production[sys] * 
                    model.fuel_eff_param[fuel, baseline_year]
                )
                
                # Add emissions from this fuel
                fuel_emissions += fuel_consumption * model.fuel_emission[fuel, baseline_year]
        
        # Calculate feedstock emissions
        feedstock_emissions = 0
        for fs in model.feedstocks:
            if fs in model.baseline_feedstocks[sys]:
                # Get the index for this feedstock
                idx = model.baseline_feedstocks[sys].index(fs)
                
                # Calculate feedstock consumption in baseline
                feedstock_consumption = (
                    model.baseline_feedstock_shares[sys][idx] * 
                    model.baseline_production[sys] * 
                    model.feedstock_eff_param[fs, baseline_year]
                )
                
                # Add emissions from this feedstock
                feedstock_emissions += feedstock_consumption * model.feedstock_emission[fs, baseline_year]
        
        # Apply technology emission intensity factor
        total_emissions = model.technology_ei[baseline_tech, baseline_year] * (fuel_emissions + feedstock_emissions)
        
        # Store the results
        baseline_emissions.append({
            'System': sys,
            'Year': baseline_year,
            'Technology': baseline_tech,
            'Emissions': total_emissions
        })
    
    # Create DataFrame
    baseline_df = pd.DataFrame(baseline_emissions)
    
    # Calculate total baseline emissions
    total_baseline = baseline_df['Emissions'].sum()
    
    # Compare with emission limits
    emission_limits = {yr: value(model.emission_limit[yr]) for yr in model.years}
    
    print(f"Total baseline emissions: {total_baseline}")
    print("\nEmission limits by year:")
    for yr, limit in emission_limits.items():
        print(f"Year {yr}: {limit} {'(Feasible)' if limit >= total_baseline else '(Infeasible)'}")
    
    # Project baseline emissions to future years (assuming no changes)
    for yr in sorted(model.years):
        if yr > baseline_year:
            for sys in model.systems:
                baseline_row = baseline_df[baseline_df['System'] == sys].iloc[0].copy()
                baseline_row['Year'] = yr
                baseline_df = pd.concat([baseline_df, pd.DataFrame([baseline_row])], ignore_index=True)
    
    # Calculate total emissions by year
    yearly_totals = baseline_df.groupby('Year')['Emissions'].sum().reset_index()
    yearly_totals['Emission Limit'] = yearly_totals['Year'].map(emission_limits)
    yearly_totals['Feasible'] = yearly_totals['Emission Limit'] >= yearly_totals['Emissions']
    
    return baseline_df, yearly_totals

def main(model, data):
    """
    Main function to check baseline emissions.
    
    Args:
        model: The Pyomo model
        data: The input data dictionary
    """
    print("=== Baseline Emissions Analysis ===\n")
    
    # Calculate baseline emissions
    baseline_emissions, yearly_totals = calculate_baseline_emissions(model, data)
    
    # Display results
    print("\nBaseline emissions by system:")
    print(baseline_emissions[['System', 'Year', 'Technology', 'Emissions']])
    
    print("\nYearly emission totals vs limits:")
    print(yearly_totals)
    
    # Export to Excel
    with pd.ExcelWriter('baseline_emissions_analysis.xlsx') as writer:
        baseline_emissions.to_excel(writer, sheet_name='Baseline_Emissions', index=False)
        yearly_totals.to_excel(writer, sheet_name='Yearly_Totals', index=False)
    
    print("\nResults exported to 'baseline_emissions_analysis.xlsx'")
    
    # Check if the problem is infeasible due to emission constraints
    if not all(yearly_totals['Feasible']):
        print("\nWARNING: The model may be infeasible due to emission constraints!")
        print("Years with infeasible emission limits:")
        infeasible_years = yearly_totals[~yearly_totals['Feasible']]
        for _, row in infeasible_years.iterrows():
            print(f"Year {row['Year']}: Baseline emissions {row['Emissions']} > Limit {row['Emission Limit']}")
        
        print("\nPossible solutions:")
        print("1. Increase emission limits")
        print("2. Allow more technology options with lower emissions")
        print("3. Adjust the production requirements")
        print("4. Implement carbon pricing instead of hard limits")
    
    return baseline_emissions, yearly_totals

# Replace this comment with actual code to run the analysis
if __name__ == "__main__":
    # Import your model and data here or pass them as arguments when running this script
    # For example:
    # from your_model_module import create_model, load_data
    # model = create_model()
    # data = load_data()
    # baseline_emissions, yearly_totals = main(model, data)
    
    print("To use this module, import it and call main(model, data)")
    print("Example: baseline_emissions, yearly_totals = base_check.main(model, data)")
