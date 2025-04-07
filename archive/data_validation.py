import pandas as pd
import utils.load_data as _ld


def load_and_validate_data():
    file_path = 'database/steel_data2.xlsx'  # Update with your actual file path
    data = _ld.load_data(file_path)

    return validate_data(data)


def check_introduced_year_constraints(data):
    """Ensure no technology is used before its introduction year."""
    issues = []
    baseline_year = 2025

    for system, row in data['baseline'].iterrows():
        tech = row['technology']
        introduced_year = row['introduced_year']

        if baseline_year < introduced_year:
            issues.append(
                f"System {system}: Technology {tech} is used before its introduction year ({introduced_year}).")

    return issues


def check_lifespan_constraints(data):
    """Ensure that technology lifespan does not expire before the baseline year."""
    issues = []
    baseline_year = 2025

    # We assume data['technology'] is a DataFrame with index = technology name
    # and a column named 'lifespan'.

    for system, row in data['baseline'].iterrows():
        tech = row['technology']
        introduced_year = row['introduced_year']

        # Safely retrieve lifespan
        if tech in data['technology'].index:
            lifespan = data['technology'].loc[tech, 'lifespan']
        else:
            lifespan = None

        if lifespan is None:
            issues.append(f"System {system}: Lifespan data missing for technology {tech}.")
            continue

        if introduced_year + lifespan < baseline_year:
            issues.append(
                f"System {system}: Technology {tech} was introduced in {introduced_year} "
                f"with lifespan {lifespan}, expiring before the baseline year {baseline_year}."
            )

    return issues


def validate_tech_fuel_material_pairs(data):
    """Validate tech-fuel and tech-material pair constraints."""
    issues = []

    for system, row in data['baseline'].iterrows():
        tech = row['technology']
        fuels, fuel_shares = row['fuels'], row['fuel_shares']
        materials, material_shares = row['materials'], row['material_shares']

        if len(fuels) != len(fuel_shares):
            issues.append(f"System {system}: Mismatch between number of fuels and fuel shares.")
        if len(materials) != len(material_shares):
            issues.append(f"System {system}: Mismatch between number of materials and material shares.")

        # Fuel Pair Check
        allowed_fuels = data['technology_fuel_pairs'].get(tech, [])
        for f in fuels:
            if f not in allowed_fuels:
                issues.append(f"System {system}: Fuel {f} is used in technology {tech}, but it's not allowed.")

        # Material Pair Check
        allowed_materials = data['technology_material_pairs'].get(tech, [])
        for m in materials:
            if m not in allowed_materials:
                issues.append(f"System {system}: Material {m} is used in technology {tech}, but it's not allowed.")

    return issues


def verify_baseline_emission_consistency(data):
    """Check if baseline year emissions match or exceed calculated emissions."""
    issues = []
    baseline_year = 2025

    for system, row in data['baseline'].iterrows():
        tech = row['technology']
        fuels, fuel_shares = row['fuels'], row['fuel_shares']
        materials, material_shares = row['materials'], row['material_shares']
        production = row['production']

        # Ensure data validity
        if len(fuels) != len(fuel_shares) or len(materials) != len(material_shares):
            issues.append(f"System {system}: Mismatch between fuels/materials and their respective shares.")
            continue

        try:
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

            if reported_emission < calculated_emission:
                issues.append(
                    f"System {system}: Reported emission {reported_emission} is lower than calculated emission {calculated_emission}.")
        except KeyError as e:
            issues.append(f"System {system}: Missing data for emission calculation - {e}.")

    return issues


def check_baseline_shares(data):
    """Ensure that fuel and material shares do not exceed 1 in the baseline year."""
    issues = []

    for system, row in data['baseline'].iterrows():
        fuel_share_sum = sum(row['fuel_shares'])
        material_share_sum = sum(row['material_shares'])

        if fuel_share_sum > 1:
            issues.append(f"System {system}: Sum of fuel shares ({fuel_share_sum}) exceeds 1.")
        if material_share_sum > 1:
            issues.append(f"System {system}: Sum of material shares ({material_share_sum}) exceeds 1.")

    return issues


def validate_data(data):
    """Run all validation functions and return issues."""
    issues = {
        "Introduced Year Constraints": check_introduced_year_constraints(data),
        "Lifespan Constraints": check_lifespan_constraints(data),
        "Tech-Fuel and Tech-Material Pairs": validate_tech_fuel_material_pairs(data),
        "Baseline Emission Consistency": verify_baseline_emission_consistency(data),
        "Baseline Shares Consistency": check_baseline_shares(data)
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
