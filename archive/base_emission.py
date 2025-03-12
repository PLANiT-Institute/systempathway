import pandas as pd
import numpy as np
from utils.load_data import load_data

def calculate_baseline_emissions(file_path):
    """
    Calculate baseline emissions for each system from the provided Excel file.
    
    Parameters:
    -----------
    file_path : str
        Path to the Excel file containing data
    
    Returns:
    --------
    dict
        Dictionary with system names as keys and their baseline emissions as values
    """
    # Load the data using the proper loader
    data = load_data(file_path)
    
    # Initialize dictionary to store baseline emissions for each system
    baseline_emissions = {}
    
    # Get the first year (baseline year)
    if 'emission' in data and not data['emission'].empty:
        years = data['emission'].columns.tolist()
        baseline_year = min(years)
    else:
        print("Warning: No emission data found or emission data is empty.")
        return baseline_emissions
    
    # Calculate baseline emissions for each system
    for system in data['baseline'].index:
        # Get baseline technology, fuels, and feedstocks for this system
        baseline_tech = data['baseline'].loc[system, 'technology']
        baseline_production = data['baseline'].loc[system, 'production']
        baseline_fuels = data['baseline'].loc[system, 'fuels']  # Now using transformed column
        baseline_fuel_shares = data['baseline'].loc[system, 'fuel_shares']  # Now using transformed column
        baseline_feedstocks = data['baseline'].loc[system, 'feedstocks']  # Now using transformed column
        baseline_feedstock_shares = data['baseline'].loc[system, 'feedstock_shares']  # Now using transformed column
        
        # Initialize emissions for this system
        system_emissions = 0.0
        
        # Calculate emissions from fuels
        for i, fuel in enumerate(baseline_fuels):
            if i < len(baseline_fuel_shares):
                fuel_share = baseline_fuel_shares[i]
                fuel_intensity = data['fuel_intensity'].loc[fuel, baseline_year] if fuel in data['fuel_intensity'].index else 0
                fuel_emission_factor = data['fuel_emission'].loc[fuel, baseline_year] if fuel in data['fuel_emission'].index else 0
                
                # Calculate fuel consumption and associated emissions
                fuel_consumption = baseline_production * fuel_share * fuel_intensity
                fuel_emissions = fuel_consumption * fuel_emission_factor
                
                system_emissions += fuel_emissions
        
        # Calculate emissions from feedstocks
        for i, feedstock in enumerate(baseline_feedstocks):
            if i < len(baseline_feedstock_shares):
                feedstock_share = baseline_feedstock_shares[i]
                feedstock_intensity = data['feedstock_intensity'].loc[feedstock, baseline_year] if feedstock in data['feedstock_intensity'].index else 0
                feedstock_emission_factor = data['feedstock_emission'].loc[feedstock, baseline_year] if feedstock in data['feedstock_emission'].index else 0
                
                # Calculate feedstock consumption and associated emissions
                feedstock_consumption = baseline_production * feedstock_share * feedstock_intensity
                feedstock_emissions = feedstock_consumption * feedstock_emission_factor
                
                system_emissions += feedstock_emissions
        
        # Apply technology emission intensity factor
        if baseline_tech in data['technology_ei'].index:
            tech_ei_factor = data['technology_ei'].loc[baseline_tech, baseline_year]
            system_emissions *= tech_ei_factor
        
        # Store the calculated emissions
        baseline_emissions[system] = system_emissions
    
    return baseline_emissions

def calculate_emissions_for_2025(file_path):
    """
    Calculate emissions for the year 2025 based on baseline data.
    
    Parameters:
    -----------
    file_path : str
        Path to the Excel file containing data
    
    Returns:
    --------
    dict
        Dictionary with system names as keys and their 2025 emissions as values
    """
    # Load the data using the proper loader
    data = load_data(file_path)
    
    # Initialize dictionary to store 2025 emissions for each system
    emissions_2025 = {}
    
    # Define the target year
    target_year = 2025
    
    # Calculate emissions for each system
    for system in data['baseline'].index:
        # Get baseline technology, fuels, and feedstocks for this system
        baseline_tech = data['baseline'].loc[system, 'technology']
        baseline_production = data['baseline'].loc[system, 'production']
        baseline_fuels = data['baseline'].loc[system, 'fuels']  # Now using transformed column
        baseline_fuel_shares = data['baseline'].loc[system, 'fuel_shares']  # Now using transformed column
        baseline_feedstocks = data['baseline'].loc[system, 'feedstocks']  # Now using transformed column
        baseline_feedstock_shares = data['baseline'].loc[system, 'feedstock_shares']  # Now using transformed column
        
        # Initialize emissions for this system
        system_emissions = 0.0
        
        # Calculate emissions from fuels
        for i, fuel in enumerate(baseline_fuels):
            if i < len(baseline_fuel_shares):
                fuel_share = baseline_fuel_shares[i]
                # Use 2025 data if available, otherwise use the closest available year
                fuel_intensity = get_value_for_year(data['fuel_intensity'], fuel, target_year)
                fuel_emission_factor = get_value_for_year(data['fuel_emission'], fuel, target_year)
                
                # Calculate fuel consumption and associated emissions
                fuel_consumption = baseline_production * fuel_share * fuel_intensity
                fuel_emissions = fuel_consumption * fuel_emission_factor
                
                system_emissions += fuel_emissions
        
        # Calculate emissions from feedstocks
        for i, feedstock in enumerate(baseline_feedstocks):
            if i < len(baseline_feedstock_shares):
                feedstock_share = baseline_feedstock_shares[i]
                # Use 2025 data if available, otherwise use the closest available year
                feedstock_intensity = get_value_for_year(data['feedstock_intensity'], feedstock, target_year)
                feedstock_emission_factor = get_value_for_year(data['feedstock_emission'], feedstock, target_year)
                
                # Calculate feedstock consumption and associated emissions
                feedstock_consumption = baseline_production * feedstock_share * feedstock_intensity
                feedstock_emissions = feedstock_consumption * feedstock_emission_factor
                
                system_emissions += feedstock_emissions
        
        # Apply technology emission intensity factor
        if baseline_tech in data['technology_ei'].index:
            tech_ei_factor = get_value_for_year(data['technology_ei'], baseline_tech, target_year)
            system_emissions *= tech_ei_factor
        
        # Store the calculated emissions
        emissions_2025[system] = system_emissions
    
    return emissions_2025

def get_value_for_year(dataframe, item, year):
    """
    Get the value for a specific year from a dataframe.
    If the year is not available, use the closest available year.
    
    Parameters:
    -----------
    dataframe : pandas.DataFrame
        DataFrame containing the data
    item : str
        Item (row) to get the value for
    year : int
        Year (column) to get the value for
    
    Returns:
    --------
    float
        Value for the specified item and year
    """
    if item not in dataframe.index:
        return 0
    
    if year in dataframe.columns:
        return dataframe.loc[item, year]
    
    # If year is not available, use the closest available year
    available_years = [y for y in dataframe.columns if isinstance(y, (int, float))]
    if not available_years:
        return 0
    
    closest_year = min(available_years, key=lambda y: abs(y - year))
    return dataframe.loc[item, closest_year]

def main():
    """
    Main function to run the emission calculation tool.
    """
    file_path = 'database/steel_data_0310.xlsx'
    
    # Calculate baseline emissions
    baseline_emissions = calculate_baseline_emissions(file_path)
    print("\n=== Baseline Emissions by System ===")
    for system, emissions in baseline_emissions.items():
        print(f"{system}: {emissions:.2f}")
    
    # Calculate emissions for 2025
    emissions_2025 = calculate_emissions_for_2025(file_path)
    print("\n=== 2025 Emissions by System ===")
    for system, emissions in emissions_2025.items():
        print(f"{system}: {emissions:.2f}")
    
    # Calculate the change from baseline to 2025
    print("\n=== Emission Change from Baseline to 2025 ===")
    for system in baseline_emissions.keys():
        if system in emissions_2025:
            change = emissions_2025[system] - baseline_emissions[system]
            percent_change = (change / baseline_emissions[system]) * 100 if baseline_emissions[system] != 0 else 0
            print(f"{system}: {change:.2f} ({percent_change:.2f}%)")

if __name__ == "__main__":
    main()
