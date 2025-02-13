import pandas as pd
import utils.load_data as _ld


def load_and_validate_data():
    file_path = 'database/steel_data.xlsx'  # Update with your actual file path
    data = _ld.load_data(file_path)

    return validate_data(data)


def check_introduced_year_constraints(data):
    """Ensure no technology is used before its introduction year."""
    issues = []
    baseline_year = 2025

    for system, row in data['baseline'].iterrows():
        tech = row['technology']
        introduced_year = data['technology'].loc[tech, 'introduction']

        if baseline_year < introduced_year:
            issues.append(
                f"System {system}: Technology {tech} is used before its introduction year ({introduced_year}).")

    return issues


def validate_tech_fuel_material_pairs(data):
    """Validate tech-fuel and tech-material pair constraints."""
    issues = []

    for system, row in data['baseline'].iterrows():
        tech = row['technology']
        fuels, fuel_shares = row['fuels'], row['fuel_shares']
        materials, material_shares = row['materials'], row['material_shares']

        # Fuel Pair Check
        if tech in data['technology_fuel_pairs']:
            allowed_fuels = data['technology_fuel_pairs'][tech]
            for f, share in zip(fuels, fuel_shares):
                if f not in allowed_fuels:
                    issues.append(f"System {system}: Fuel {f} is used in technology {tech}, but it's not allowed.")
                elif (tech, f) in data['fuel_min_ratio'] and share < data['fuel_min_ratio'][(tech, f)]:
                    issues.append(
                        f"System {system}: Fuel {f} share ({share}) is below min share ({data['fuel_min_ratio'][(tech, f)]}).")

        # Material Pair Check
        if tech in data['technology_material_pairs']:
            allowed_materials = data['technology_material_pairs'][tech]
            for m, share in zip(materials, material_shares):
                if m not in allowed_materials:
                    issues.append(f"System {system}: Material {m} is used in technology {tech}, but it's not allowed.")
                elif (tech, m) in data['material_min_ratio'] and share < data['material_min_ratio'][(tech, m)]:
                    issues.append(
                        f"System {system}: Material {m} share ({share}) is below min share ({data['material_min_ratio'][(tech, m)]}).")

    return issues


def verify_baseline_emission_consistency(data):
    """Check if baseline year emissions match calculated emissions."""
    issues = []
    baseline_year = 2025

    for system, row in data['baseline'].iterrows():
        tech = row['technology']
        fuels, fuel_shares = row['fuels'], row['fuel_shares']
        materials, material_shares = row['materials'], row['material_shares']
        production = row['production']

        # Calculate emissions
        total_fuel_emission = sum(
            fuel_shares[i] * production * data['fuel_efficiency'].loc[f, baseline_year] * data['fuel_emission'].loc[
                f, baseline_year]
            for i, f in enumerate(fuels) if f in data['fuel_emission'].index
        )
        total_material_emission = sum(
            material_shares[i] * production * data['material_efficiency'].loc[m, baseline_year] *
            data['material_emission'].loc[m, baseline_year]
            for i, m in enumerate(materials) if m in data['material_emission'].index
        )

        calculated_emission = data['technology_ei'].loc[tech, baseline_year] * (
                    total_fuel_emission + total_material_emission)
        reported_emission = data['emission_system'].loc[system, baseline_year]

        if abs(calculated_emission - reported_emission) > 1e-3:
            issues.append(
                f"System {system}: Emission discrepancy. Reported: {reported_emission}, Calculated: {calculated_emission}.")

    return issues


def check_pair_matching(data):
    """Ensure assigned tech-fuel and tech-material pairs match expectations."""
    issues = []

    for tech in data['technology_fuel_pairs']:
        if tech not in data['technology_material_pairs']:
            issues.append(f"Technology {tech} has fuel pairs but no material pairs defined.")

    for tech in data['technology_material_pairs']:
        if tech not in data['technology_fuel_pairs']:
            issues.append(f"Technology {tech} has material pairs but no fuel pairs defined.")

    return issues


def validate_data(data):
    """Run all validation functions and return issues."""
    issues = {
        "Introduced Year Constraints": check_introduced_year_constraints(data),
        "Tech-Fuel and Tech-Material Pairs": validate_tech_fuel_material_pairs(data),
        "Baseline Emission Consistency": verify_baseline_emission_consistency(data),
        "Pair Matching Consistency": check_pair_matching(data),
    }

    return issues


if __name__ == "__main__":
    validation_results = load_and_validate_data()
    for category, issues in validation_results.items():
        print(f"\n=== {category} ===")
        if issues:
            for issue in issues:
                print(issue)
        else:
            print("No issues found.")
