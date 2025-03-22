import pandas as pd

def load_data(file_path):
    """
    Load all relevant data from the Excel file.
    """
    data = {}
    data['baseline'] = pd.read_excel(file_path, sheet_name='baseline', index_col=0)
    data['emission'] = pd.read_excel(file_path, sheet_name='emission', index_col=0)

    data['baseline']['fuels'] = data['baseline']['fuel'].apply(lambda x: str(x).split(', '))
    data['baseline']['fuel_shares'] = data['baseline']['fuel_share'].apply(lambda x: list(map(float, str(x).split(', '))))
    data['baseline']['feedstocks'] = data['baseline']['feedstock'].apply(lambda x: str(x).split(', '))
    data['baseline']['feedstock_shares'] = data['baseline']['feedstock_share'].apply(lambda x: list(map(float, str(x).split(', '))))

    data['technology'] = pd.read_excel(file_path, sheet_name='technology', index_col=0)
    data['fuel_cost'] = pd.read_excel(file_path, sheet_name='fuel_cost', index_col=0)
    data['fuel_intensity'] = pd.read_excel(file_path, sheet_name='fuel_intensity', index_col=0)
    data['feedstock_cost'] = pd.read_excel(file_path, sheet_name='feedstock_cost', index_col=0)
    data['feedstock_intensity'] = pd.read_excel(file_path, sheet_name='feedstock_intensity', index_col=0)
    data['capex'] = pd.read_excel(file_path, sheet_name='capex', index_col=0)
    data['opex'] = pd.read_excel(file_path, sheet_name='opex', index_col=0)
    data['renewal'] = pd.read_excel(file_path, sheet_name='renewal', index_col=0)
    data['carbonprice'] = pd.read_excel(file_path, sheet_name='carbonprice', index_col=0)

    technology_fuel_pairs_df = pd.read_excel(file_path, sheet_name='technology_fuel_pairs')
    data['technology_fuel_pairs'] = technology_fuel_pairs_df.groupby('technology')['fuel'].apply(list).to_dict()
    data['fuel_max_ratio'] = technology_fuel_pairs_df.set_index(['technology', 'fuel'])['max'].to_dict()
    data['fuel_min_ratio'] = technology_fuel_pairs_df.set_index(['technology', 'fuel'])['min'].to_dict()

    technology_feedstock_pairs_df = pd.read_excel(file_path, sheet_name='technology_feedstock_pairs')
    data['technology_feedstock_pairs'] = technology_feedstock_pairs_df.groupby('technology')['feedstock'].apply(list).to_dict()
    data['feedstock_max_ratio'] = technology_feedstock_pairs_df.set_index(['technology', 'feedstock'])['max'].to_dict()
    data['feedstock_min_ratio'] = technology_feedstock_pairs_df.set_index(['technology', 'feedstock'])['min'].to_dict()

    data['technology_introduction'] = pd.read_excel(file_path, sheet_name='technology', index_col=0)['introduction'].to_dict()
    # data['emission_system'] = pd.read_excel(file_path, sheet_name='emission_system', index_col=0)
    data['fuel_emission'] = pd.read_excel(file_path, sheet_name='fuel_emission', index_col=0)
    data['feedstock_emission'] = pd.read_excel(file_path, sheet_name='feedstock_emission', index_col=0)
    data['technology_ei'] = pd.read_excel(file_path, sheet_name='technology_ei', index_col=0)
    data['fuel_introduction'] = pd.read_excel(file_path, sheet_name='fuel_introduction', index_col=0)['introduction']
    data['feedstock_introduction'] = pd.read_excel(file_path, sheet_name='feedstock_introduction', index_col=0)['introduction']
    
    data['production'] = pd.read_excel(file_path, sheet_name='production', index_col=0)

    return data
