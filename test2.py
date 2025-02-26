import pandas as pd
import os
from datetime import datetime

def calculate_baseline_emissions(year=2025):
    """
    Calculate baseline emissions from fuel and material consumption for each system in 2025,
    using data directly from the provided excerpt.
    """
    # Baseline data from excerpt
    baseline_data = {
        "system": [
            "Gwangyang BF1", "Gwangyang BF5", "Pohang BF3", "Gwangyang BF3", "HyundaiBF1",
            "HyundaiBF2", "HyundaiBF3", "Pohang BF4", "Gwangyang BF4", "Gwangyang BF2",
            "Pohang BF2", "Pohang FNX3", "Pohang FNX2"
        ],
        "technology": ["BAT BF-BOF"] * 13,
        "fuel": ["Coke_BB, Thermal coal_BB, BF gas_BB, COG_BB, BOF gas_BB, Natural gas_BB, Hydrogen_BB, Electricity_BB, Steam_BB"] * 13,
        "fuel_share": ["0.34, 0.097, 0.374, 0.114, 0.059, 0.016"] * 13,
        "material": ["Iron ore_BB, Scrap_BB"] * 13,
        "material_share": ["0.81, 0.19"] * 13,
        "production": [4722000, 4237000, 4128000, 4127000, 4000000, 4000000, 4000000, 3804000, 3624000, 3239000, 1914000, 1683000, 1280000]
    }
    baseline_df = pd.DataFrame(baseline_data)
    baseline_df.set_index("system", inplace=True)
    baseline_df['fuels'] = baseline_df['fuel'].apply(lambda x: x.split(', '))
    baseline_df['fuel_shares'] = baseline_df['fuel_share'].apply(lambda x: list(map(float, x.split(', '))))
    baseline_df['materials'] = baseline_df['material'].apply(lambda x: x.split(', '))
    baseline_df['material_shares'] = baseline_df['material_share'].apply(lambda x: list(map(float, x.split(', '))))

    # Fuel efficiency (energy-fuel / ton-production)
    fuel_efficiency_data = {
        "Coke_BB": 13.97, "Thermal coal_BB": 13.97, "BF gas_BB": 13.97, "COG_BB": 13.97,
        "BOF gas_BB": 13.97, "Natural gas_BB": 13.97, "Hydrogen_BB": 13.97, "Electricity_BB": 13.97,
        "Steam_BB": 13.97
    }
    fuel_efficiency_df = pd.DataFrame([fuel_efficiency_data], index=[2025]).T

    # Fuel emission (ton-CO2 / energy-fuel)
    fuel_emission_data = {
        "Coke_BB": 0.0, "Thermal coal_BB": 0.095, "BF gas_BB": 0.26, "COG_BB": 0.044,
        "BOF gas_BB": 0.192, "Natural gas_BB": 0.055, "Natural gas_EAF": 0.055,
        "Electricity_EAF": 0.0, "Steam_EAF": 0.0
    }
    fuel_emission_df = pd.DataFrame([fuel_emission_data], index=[2025]).T

    # Material efficiency (ton-material / ton-production, assuming 1 unless specified)
    material_efficiency_data = {
        "Iron ore_BB": 1.0, "Scrap_BB": 1.0  # Simplified assumption; adjust if data differs
    }
    material_efficiency_df = pd.DataFrame([material_efficiency_data], index=[2025]).T

    # Material emission (ton-CO2 / ton-material)
    material_emission_data = {
        "Iron ore_BB": 0.0, "Scrap_BB": 0.0
    }
    material_emission_df = pd.DataFrame([material_emission_data], index=[2025]).T

    # Technology emission intensity (multiplier)
    technology_ei_data = {
        "BAT BF-BOF": 1.0
    }
    technology_ei_df = pd.DataFrame([technology_ei_data], index=[2025]).T

    # Initialize results
    baseline_emissions = {}
    global_fuel_emissions = {}
    global_material_emissions = {}
    global_total_emissions = 0.0

    # Process each system
    for sys in baseline_df.index:
        production = baseline_df.loc[sys, 'production']
        baseline_tech = baseline_df.loc[sys, 'technology']
        fuels = baseline_df.loc[sys, 'fuels']
        fuel_shares = baseline_df.loc[sys, 'fuel_shares']
        materials = baseline_df.loc[sys, 'materials']
        material_shares = baseline_df.loc[sys, 'material_shares']

        # Fuel consumption and emissions
        fuel_consumption = {}
        fuel_emission_total = 0.0
        for fuel, share in zip(fuels, fuel_shares):
            efficiency = fuel_efficiency_df.loc[fuel, year]
            consumption = production * share * efficiency  # energy-fuel
            fuel_consumption[fuel] = consumption
            emission_factor = fuel_emission_df.loc[fuel, year] if fuel in fuel_emission_df.index else 0.0
            if fuel not in fuel_emission_df.index:
                print(f"Warning: Emission factor for fuel '{fuel}' not found for year {year}. Assuming 0.0.")
            fuel_emission = consumption * emission_factor
            fuel_emission_total += fuel_emission
            global_fuel_emissions[fuel] = global_fuel_emissions.get(fuel, 0.0) + fuel_emission

        # Material consumption and emissions
        material_consumption = {}
        material_emission_total = 0.0
        for mat, share in zip(materials, material_shares):
            efficiency = material_efficiency_df.loc[mat, year]
            consumption = production * share * efficiency  # ton-material
            material_consumption[mat] = consumption
            emission_factor = material_emission_df.loc[mat, year] if mat in material_emission_df.index else 0.0
            if mat not in material_emission_df.index:
                print(f"Warning: Emission factor for material '{mat}' not found for year {year}. Assuming 0.0.")
            material_emission = consumption * emission_factor
            material_emission_total += material_emission
            global_material_emissions[mat] = global_material_emissions.get(mat, 0.0) + material_emission

        # Total emissions with technology intensity
        tech_ei = technology_ei_df.loc[baseline_tech, year]
        total_emission = tech_ei * (fuel_emission_total + material_emission_total)

        # Store results
        baseline_emissions[sys] = {
            "Fuel Consumption": fuel_consumption,
            "Fuel Emissions": {fuel: fuel_consumption[fuel] * (fuel_emission_df.loc[fuel, year] if fuel in fuel_emission_df.index else 0.0) for fuel in fuels},
            "Material Consumption": material_consumption,
            "Material Emissions": {mat: material_consumption[mat] * (material_emission_df.loc[mat, year] if mat in material_emission_df.index else 0.0) for mat in materials},
            "Total Emissions": total_emission
        }
        global_total_emissions += total_emission

    # Display results
    print(f"\n=== Baseline Emissions for Year {year} ===\n")
    for sys, results in baseline_emissions.items():
        print(f"System: {sys}")
        print("Fuel Consumption (energy-fuel):")
        for fuel, cons in results["Fuel Consumption"].items():
            print(f"  {fuel}: {cons:.2f}")
        print("Fuel Emissions (ton-CO2):")
        for fuel, emis in results["Fuel Emissions"].items():
            print(f"  {fuel}: {emis:.2f}")
        print("Material Consumption (ton-material):")
        for mat, cons in results["Material Consumption"].items():
            print(f"  {mat}: {cons:.2f}")
        print("Material Emissions (ton-CO2):")
        for mat, emis in results["Material Emissions"].items():
            print(f"  {mat}: {emis:.2f}")
        print(f"Total Emissions (ton-CO2): {results['Total Emissions']:.2f}\n")

    # Global summary
    print("=== Global Baseline Emissions ===")
    print("Global Fuel Emissions (ton-CO2):")
    for fuel, emis in global_fuel_emissions.items():
        print(f"  {fuel}: {emis:.2f}")
    print("Global Material Emissions (ton-CO2):")
    for mat, emis in global_material_emissions.items():
        print(f"  {mat}: {emis:.2f}")
    print(f"Global Total Emissions (ton-CO2): {global_total_emissions:.2f}")

    # Export to CSV
    output_dir = 'baseline_emissions'
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_path = os.path.join(output_dir, f'baseline_emissions_{year}_{timestamp}.csv')

    rows = []
    for sys, results in baseline_emissions.items():
        row = {"System": sys}
        row.update({f"Fuel Consumption ({fuel})": cons for fuel, cons in results["Fuel Consumption"].items()})
        row.update({f"Fuel Emissions ({fuel})": emis for fuel, emis in results["Fuel Emissions"].items()})
        row.update({f"Material Consumption ({mat})": cons for mat, cons in results["Material Consumption"].items()})
        row.update({f"Material Emissions ({mat})": emis for mat, emis in results["Material Emissions"].items()})
        row["Total Emissions"] = results["Total Emissions"]
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(csv_path, index=False)
    print(f"\nBaseline emissions exported to: {csv_path}")

if __name__ == "__main__":
    calculate_baseline_emissions()