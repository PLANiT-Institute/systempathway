import pandas as pd

def load_data(file_path):
    """
    Load and structure all relevant data from the Excel file.
    """
    data = {}

    # 1. Read the Excel file
    xls = pd.ExcelFile(file_path)

    # 2. Load baseline data (existing furnace sites)
    data['baseline'] = pd.read_excel(xls, sheet_name='baseline', index_col=0)
    data['emission'] = pd.read_excel(xls, sheet_name='emission', index_col=0)

    # 3. Parse multi-fuel and multi-feedstock info from baseline
    data['baseline']['fuels'] = data['baseline']['fuel'].apply(lambda x: str(x).split(', '))
    data['baseline']['fuel_shares'] = data['baseline']['fuel_share'].apply(lambda x: list(map(float, str(x).split(', '))))
    data['baseline']['feedstock'] = data['baseline']['feedstock'].apply(lambda x: str(x).split(', '))
    data['baseline']['feedstock_shares'] = data['baseline']['feedstock_share'].apply(lambda x: list(map(float, str(x).split(', '))))

    # 4. Load potential furnace technologies
    data['technology'] = pd.read_excel(xls, sheet_name='technology', index_col=0)

    # 5. Fuel-related data
    data['fuel_cost'] = pd.read_excel(xls, sheet_name='fuel_cost', index_col=0)
    data['fuel_intensity'] = pd.read_excel(xls, sheet_name='fuel_intensity', index_col=0)

    # 6. Feedstock-related data
    data['feedstock_cost'] = pd.read_excel(xls, sheet_name='feedstock_cost', index_col=0)
    data['feedstock_intensity'] = pd.read_excel(xls, sheet_name='feedstock_intensity', index_col=0)

    # 7. Financial data
    data['capex'] = pd.read_excel(xls, sheet_name='capex', index_col=0)
    data['opex'] = pd.read_excel(xls, sheet_name='opex', index_col=0)
    data['renewal'] = pd.read_excel(xls, sheet_name='renewal', index_col=0)
    data['carbonprice'] = pd.read_excel(xls, sheet_name='carbonprice', index_col=0)

    # 8. Technology-Fuel pairs (incl. min/max ratios)
    technology_fuel_pairs_df = pd.read_excel(xls, sheet_name='technology_fuel_pairs')
    data['technology_fuel_pairs'] = technology_fuel_pairs_df.groupby('technology')['fuel'].apply(list).to_dict()
    data['fuel_max_ratio'] = technology_fuel_pairs_df.set_index(['technology', 'fuel'])['max'].to_dict()
    data['fuel_min_ratio'] = technology_fuel_pairs_df.set_index(['technology', 'fuel'])['min'].to_dict()

    # 9. Technology-Feedstock pairs (incl. min/max ratios)
    technology_feedstock_pairs_df = pd.read_excel(xls, sheet_name='technology_feedstock_pairs')
    data['technology_feedstock_pairs'] = technology_feedstock_pairs_df.groupby('technology')['feedstock'].apply(list).to_dict()
    data['feedstock_max_ratio'] = technology_feedstock_pairs_df.set_index(['technology', 'feedstock'])['max'].to_dict()
    data['feedstock_min_ratio'] = technology_feedstock_pairs_df.set_index(['technology', 'feedstock'])['min'].to_dict()

    # 10. Technology introduction years
    data['technology_introduction'] = pd.read_excel(xls, sheet_name='technology', index_col=0)['introduction'].to_dict()

    # 11. Emission-related data
    data['fuel_emission'] = pd.read_excel(xls, sheet_name='fuel_emission', index_col=0)
    data['feedstock_emission'] = pd.read_excel(xls, sheet_name='feedstock_emission', index_col=0)
    data['technology_ei'] = pd.read_excel(xls, sheet_name='technology_ei', index_col=0)

    data['fuel_introduction'] = pd.read_excel(xls, sheet_name='fuel_introduction', index_col=0)['introduction']
    data['feedstock_introduction'] = pd.read_excel(xls, sheet_name='feedstock_introduction', index_col=0)['introduction']

    # 12. **Load the flow sheet** to define input→output technology order
    data['flow'] = pd.read_excel(xls, sheet_name='flow')  # e.g., columns: [input_stage, output_stage, introduction_year]

    return data
