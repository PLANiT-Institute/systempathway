import pandas as pd

def process_kepco_data(filepath, year, selected_sheet):
    """
    Process KEPCO Excel data to generate a DataFrame with datetime as index
    and temporal values (based on season and timezone).

    Parameters:
    - filepath (str): Path to the Excel file.
    - year (int): The year to generate the datetime index.
    - selected_sheet (str): The sheet name for the selected rates (e.g., "HV_C_I").

    Returns:
    - pd.DataFrame: Temporal DataFrame with datetime index and corresponding rates.
    - float: Contract fee (krw/kw).
    """
    # Load necessary sheets
    timezone_df = pd.read_excel(filepath, sheet_name="timezone")
    season_df = pd.read_excel(filepath, sheet_name="season")
    contract_df = pd.read_excel(filepath, sheet_name="contract", index_col=0)
    rates_df = pd.read_excel(filepath, sheet_name=selected_sheet, index_col=0)

    # Validate user input
    if selected_sheet not in contract_df.index:
        raise ValueError(f"Selected sheet {selected_sheet} is not valid.")

    # Generate datetime index for the entire year
    date_range = pd.date_range(start=f"{year}-01-01", end=f"{year}-12-31 23:00", freq="h")

    # Map seasons based on months
    month_to_season = season_df.set_index("month")["season"].to_dict()
    month_to_int = {
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5,
        "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
    }
    datetime_season = pd.Series(index=date_range, dtype="object")
    for month, season in month_to_season.items():
        month_index = month_to_int[month]
        datetime_season[date_range.month == month_index] = season

    # Map timezones based on hours and months (keep timezone values in uppercase)
    timezone_mapping = timezone_df.set_index("hours")
    datetime_timezone = pd.Series(index=date_range, dtype="object")
    for month in timezone_mapping.columns:
        month_index = month_to_int[month]
        for hour in range(24):
            datetime_timezone[(date_range.month == month_index) & (date_range.hour == hour)] = timezone_mapping.loc[hour, month]

    # Create a DataFrame with datetime index and map rates based on season and timezone
    temporal_df = pd.DataFrame(index=date_range)
    temporal_df["season"] = datetime_season
    temporal_df["timezone"] = datetime_timezone

    # Map rates from the selected sheet
    temporal_df["rate"] = temporal_df.apply(
        lambda row: rates_df.loc[row["timezone"], row["season"]],
        axis=1
    )

    # Extract contract fee
    contract_fee = contract_df.loc[selected_sheet, "fees"]

    return temporal_df, contract_fee

def multiyear_pricing(temporal_df, contract_fee, start_year, num_years, rate_increase, annualised_contract=False):
    """
    Generate a long DataFrame with hourly data for multiple years and cumulative rate increase,
    optionally annualizing the contract fee.

    Parameters:
    - temporal_df (pd.DataFrame): The base DataFrame with hourly rates for one year.
    - contract_fee (float): The contract fee (krw/kw).
    - start_year (int): Starting year for the data.
    - num_years (int): Number of years to include in the data.
    - rate_increase (float): Annual rate increase (e.g., 0.05 for 5%).
    - annualised_contract (bool): If True, annualize contract fees across hourly data.

    Returns:
    - pd.DataFrame: Long DataFrame with datetime index, escalated rates, and contract fees (if annualized).
    - float: Updated contract fee for the final year.
    """
    all_years_df = []
    preset_df = temporal_df.copy()
    preset_df.index = preset_df.index.strftime("%m-%d %H:%M")

    # Add February 29 to the preset_df if it doesn't already exist
    if not any(preset_df.index.str.startswith("02-29")):
        feb_28_data = preset_df.loc["02-28 00:00":"02-28 23:00"].copy()
        feb_29_data = feb_28_data.copy()
        feb_29_data.index = feb_29_data.index.str.replace("02-28", "02-29")
        preset_df = pd.concat([preset_df, feb_29_data])

    # Initialize a list to store contract fees for each year
    contract_fees = []

    # Process each year
    for year in range(start_year, start_year + num_years):
        # Generate the correct date range for the current year (accounts for leap years)
        date_range = pd.date_range(start=f"{year}-01-01", end=f"{year}-12-31 23:00", freq="h")

        # Create an empty DataFrame for the current year
        current_year_df = pd.DataFrame(index=date_range, columns=temporal_df.columns)

        # Align indices and fill current_year_df with matching values from preset_df
        current_year_df.index = current_year_df.index.strftime("%m-%d %H:%M")
        matching_indices = current_year_df.index.intersection(preset_df.index)
        current_year_df.loc[matching_indices, :] = preset_df.loc[matching_indices, :].values

        # Adjust rates with annual rate increase
        current_year_df['rate'] = current_year_df['rate'] * (1 + rate_increase) ** (year - start_year)

        # Restore the full datetime index for the current year
        current_year_df.index = date_range

        # Calculate the contract fee for the current year
        current_year_contract_fee = contract_fee * (1 + rate_increase) ** (year - start_year)
        contract_fees.append({"year": year, "rate": current_year_contract_fee})

        # If annualized contract fees are needed, divide by the number of hours in the year
        if annualised_contract:
            hours_in_year = len(date_range)
            current_year_df['contract_fee'] = current_year_contract_fee / hours_in_year

        # Append the current year DataFrame to the list
        all_years_df.append(current_year_df)

    # Combine all years into a single DataFrame
    long_df = pd.concat(all_years_df)

    # Return the long DataFrame and contract fees as a DataFrame
    return long_df, pd.DataFrame(contract_fees)

def create_rec_grid(start_year, end_year, initial_rec, rate_increase):
    """
    Generate a DataFrame for REC values with annual increments.

    Parameters:
    - start_year (int): The starting year for the REC values.
    - end_year (int): The ending year for the REC values.
    - initial_rec (float): The initial REC value for the first year.
    - rate_increase (float): Annual rate increase (e.g., 0.05 for 5%).

    Returns:
    - pd.DataFrame: A DataFrame with REC values for each year.
    """
    rec_values = {
        year: initial_rec * (1 + rate_increase) ** (year - start_year)
        for year in range(start_year, end_year + 1)
    }
    return pd.DataFrame({"value": rec_values})

# Example usage
if __name__ == "__main__":
    # Define the filepath to the KEPCO Excel file
    kepco_filepath = 'database/KEPCO.xlsx'
    
    # Example parameters
    year = 2023
    selected_sheet = "HV_C_I"  # High Voltage Commercial/Industrial rate
    
    # Process KEPCO data for a single year
    temporal_df, contract_fee = process_kepco_data(kepco_filepath, year, selected_sheet)
    print(f"Processed single year data. Contract fee: {contract_fee}")
    print(f"Sample of temporal data:\n{temporal_df.head()}")
    
    # Generate multi-year pricing
    start_year = 2023
    num_years = 10
    rate_increase = 0.03  # 3% annual increase
    
    long_df, contract_fees = multiyear_pricing(
        temporal_df, 
        contract_fee, 
        start_year, 
        num_years, 
        rate_increase,
        annualised_contract=True
    )
    
    print(f"\nMulti-year pricing data generated for {num_years} years.")
    print(f"Contract fees over time:\n{contract_fees}")
    print(f"Sample of long DataFrame:\n{long_df.head()}")
    
    # Generate REC values
    initial_rec = 50  # Initial REC value
    rec_df = create_rec_grid(start_year, start_year + num_years - 1, initial_rec, rate_increase)
    print(f"\nREC values over time:\n{rec_df}")
    
    # Save all results to a single Excel file with multiple sheets
    output_file = f"kepco_analysis_results_{start_year}_to_{start_year+num_years-1}.xlsx"
    
    # Create a Pandas Excel writer using openpyxl as the engine
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        # Save each DataFrame to a different sheet
        temporal_df.to_excel(writer, sheet_name=f'Hourly_Rates_{year}')
        long_df.to_excel(writer, sheet_name='Multiyear_Hourly_Rates')
        contract_fees.to_excel(writer, sheet_name='Contract_Fees')
        rec_df.to_excel(writer, sheet_name='REC_Values')
        
        # Create a summary sheet with key information
        summary_data = {
            'Parameter': [
                'Analysis Period', 
                'Starting Year', 
                'Number of Years', 
                'Rate Sheet Used', 
                'Annual Rate Increase', 
                'Initial Contract Fee', 
                'Final Contract Fee', 
                'Initial REC Value', 
                'Final REC Value'
            ],
            'Value': [
                f"{start_year}-{start_year+num_years-1}",
                start_year,
                num_years,
                selected_sheet,
                f"{rate_increase:.1%}",
                f"{contract_fee:.2f}",
                f"{contract_fees['rate'].iloc[-1]:.2f}",
                f"{initial_rec:.2f}",
                f"{rec_df['value'].iloc[-1]:.2f}"
            ]
        }
        
        summary_df = pd.DataFrame(summary_data)
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
        
        # Add a statistics sheet with monthly and seasonal averages
        # Monthly averages from the first year
        monthly_avg = temporal_df.groupby(temporal_df.index.month)['rate'].mean()
        monthly_avg.index = pd.Series(monthly_avg.index).map(
            {1: 'January', 2: 'February', 3: 'March', 4: 'April', 
             5: 'May', 6: 'June', 7: 'July', 8: 'August',
             9: 'September', 10: 'October', 11: 'November', 12: 'December'}
        )
        
        # Seasonal averages
        seasonal_avg = temporal_df.groupby('season')['rate'].mean()
        
        # Timezone averages
        timezone_avg = temporal_df.groupby('timezone')['rate'].mean()
        
        # Create the statistics DataFrame
        statistics_data = {
            'Monthly_Averages': pd.Series(monthly_avg),
            'Seasonal_Averages': pd.Series(seasonal_avg),
            'Timezone_Averages': pd.Series(timezone_avg)
        }
        
        statistics_df = pd.DataFrame(statistics_data)
        statistics_df.to_excel(writer, sheet_name='Rate_Statistics')
    
    print(f"\nAll results have been saved to '{output_file}'")
    
    # Additionally, create visualizations and save them to another Excel file if needed
    visualization_file = f"kepco_visualizations_{start_year}_to_{start_year+num_years-1}.xlsx"
    
    with pd.ExcelWriter(visualization_file, engine='openpyxl') as writer:
        # Contract fees over years
        contract_fees.to_excel(writer, sheet_name='Contract_Fees_Chart')
        
        # Sample of hourly rates for January 1st of the first year
        day_sample = temporal_df[temporal_df.index.day == 1][temporal_df.index.month == 1].copy()
        day_sample['hour'] = day_sample.index.hour
        day_sample_pivot = day_sample.pivot_table(values='rate', index='hour', columns=['timezone'])
        day_sample_pivot.to_excel(writer, sheet_name='Hourly_Rate_Sample')
        
        # Monthly averages
        monthly_pivot = pd.DataFrame({'Average_Rate': monthly_avg})
        monthly_pivot.to_excel(writer, sheet_name='Monthly_Averages')
        
        # Seasonal averages with timezone breakdown
        seasonal_timezone = temporal_df.pivot_table(
            values='rate', 
            index='season', 
            columns='timezone', 
            aggfunc='mean'
        )
        seasonal_timezone.to_excel(writer, sheet_name='Season_Timezone_Rates')
        
        # REC value progression
        rec_df.to_excel(writer, sheet_name='REC_Value_Progression')
    
    print(f"Additional visualizations have been saved to '{visualization_file}'")