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
    data['baseline']['materials'] = data['baseline']['material'].apply(lambda x: str(x).split(', '))
    data['baseline']['material_shares'] = data['baseline']['material_share'].apply(lambda x: list(map(float, str(x).split(', '))))

    data['technology'] = pd.read_excel(file_path, sheet_name='technology', index_col=0)
    data['fuel_cost'] = pd.read_excel(file_path, sheet_name='fuel_cost', index_col=0)
    data['fuel_efficiency'] = pd.read_excel(file_path, sheet_name='fuel_efficiency', index_col=0)
    data['material_cost'] = pd.read_excel(file_path, sheet_name='material_cost', index_col=0)
    data['material_efficiency'] = pd.read_excel(file_path, sheet_name='material_efficiency', index_col=0)
    data['capex'] = pd.read_excel(file_path, sheet_name='capex', index_col=0)
    data['opex'] = pd.read_excel(file_path, sheet_name='opex', index_col=0)
    data['renewal'] = pd.read_excel(file_path, sheet_name='renewal', index_col=0)
    data['carbonprice'] = pd.read_excel(file_path, sheet_name='carbonprice', index_col=0)

    technology_fuel_pairs_df = pd.read_excel(file_path, sheet_name='technology_fuel_pairs')
    data['technology_fuel_pairs'] = technology_fuel_pairs_df.groupby('technology')['fuel'].apply(list).to_dict()
    data['fuel_max_ratio'] = technology_fuel_pairs_df.set_index(['technology', 'fuel'])['max'].to_dict()
    data['fuel_min_ratio'] = technology_fuel_pairs_df.set_index(['technology', 'fuel'])['min'].to_dict()

    technology_material_pairs_df = pd.read_excel(file_path, sheet_name='technology_material_pairs')
    data['technology_material_pairs'] = technology_material_pairs_df.groupby('technology')['material'].apply(list).to_dict()
    data['material_max_ratio'] = technology_material_pairs_df.set_index(['technology', 'material'])['max'].to_dict()
    data['material_min_ratio'] = technology_material_pairs_df.set_index(['technology', 'material'])['min'].to_dict()

    data['technology_introduction'] = pd.read_excel(file_path, sheet_name='technology', index_col=0)['introduction'].to_dict()
    # data['emission_system'] = pd.read_excel(file_path, sheet_name='emission_system', index_col=0)
    data['fuel_emission'] = pd.read_excel(file_path, sheet_name='fuel_emission', index_col=0)
    data['material_emission'] = pd.read_excel(file_path, sheet_name='material_emission', index_col=0)
    data['technology_ei'] = pd.read_excel(file_path, sheet_name='technology_ei', index_col=0)
    data['fuel_introduction'] = pd.read_excel(file_path, sheet_name='fuel_introduction', index_col=0)['introduction']
    data['material_introduction'] = pd.read_excel(file_path, sheet_name='material_introduction', index_col=0)['introduction']

    return data
