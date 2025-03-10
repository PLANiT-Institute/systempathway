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
        introduced_year = row['introduced_year']

        if baseline_year < introduced_year:
            issues.append(
                f"System {system}: Technology {tech} is used before its introduction year ({introduced_year}).")

    return issues


def check_lifespan_constraints(data):
    """Ensure that technology lifespan does not expire before the baseline year."""
    issues = []
    baseline_year = 2025

    for system, row in data['baseline'].iterrows():
        tech = row['technology']
        introduced_year = row['introduced_year']
        lifespan = data['technology'].loc[tech, 'lifespan']

        if introduced_year + lifespan < baseline_year:
            issues.append(
                f"System {system}: Technology {tech} was introduced in {introduced_year} with lifespan {lifespan}, expiring before the baseline year {baseline_year}.")

    return issues


def validate_tech_fuel_material_pairs(data):
    """Validate tech-fuel and tech-feedstock pair constraints."""
    issues = []

    for system, row in data['baseline'].iterrows():
        tech = row['technology']
        fuels, fuel_shares = row['fuels'], row['fuel_shares']
        feedstocks, feedstock_shares = row['feedstock'], row['feedstock_shares']

        # Fuel Pair Check
        if tech in data['technology_fuel_pairs']:
            allowed_fuels = data['technology_fuel_pairs'][tech]
            for f, share in zip(fuels, fuel_shares):
                if f not in allowed_fuels:
                    issues.append(f"System {system}: Fuel {f} is used in technology {tech}, but it's not allowed.")
                elif (tech, f) in data['fuel_min_ratio'] and share <= data['fuel_min_ratio'][(tech, f)]:
                    issues.append(
                        f"System {system}: Fuel {f} share ({share}) is below min share ({data['fuel_min_ratio'][(tech, f)]}).")

        # Feedstock Pair Check
        if tech in data['technology_feedstock_pairs']:
            allowed_feedstocks = data['technology_feedstock_pairs'][tech]
            for m, share in zip(feedstocks, feedstock_shares):
                if m not in allowed_feedstocks:
                    issues.append(f"System {system}: Feedstock {m} is used in technology {tech}, but it's not allowed.")
                elif (tech, m) in data['feedstock_min_ratio'] and share <= data['feedstock_min_ratio'][(tech, m)]:
                    issues.append(
                        f"System {system}: Feedstock {m} share ({share}) is below min share ({data['feedstock_min_ratio'][(tech, m)]}).")

    return issues


# def verify_baseline_emission_consistency(data):
#     """Check if baseline year emissions match or exceed calculated emissions."""
#     issues = []
#     baseline_year = 2025

#     for system, row in data['baseline'].iterrows():
#         tech = row['technology']
#         fuels, fuel_shares = row['fuels'], row['fuel_shares']
#         feedstocks, feedstock_shares = row['feedstocks'], row['feedstock_shares']
#         production = row['production']

#         # Calculate emissions
#         total_fuel_emission = sum(
#             fuel_shares[i] * production * data['fuel_intensity'].loc[f, baseline_year] * data['fuel_emission'].loc[
#                 f, baseline_year]
#             for i, f in enumerate(fuels) if f in data['fuel_emission'].index
#         )
#         total_feedstock_emission = sum(
#             feedstock_shares[i] * production * data['feedstock_intensity'].loc[m, baseline_year] *
#             data['feedstock_emission'].loc[m, baseline_year]
#             for i, m in enumerate(feedstocks) if m in data['feedstock_emission'].index
#         )

#         calculated_emission = data['technology_ei'].loc[tech, baseline_year] * (
#                     total_fuel_emission + total_feedstock_emission)
#         reported_emission = data['emission_system'].loc[system, baseline_year]

#         if reported_emission < calculated_emission:
#             issues.append(
#                 f"System {system}: Reported emission {reported_emission} is lower than calculated emission {calculated_emission}.")

#     return issues


def validate_data(data):
    """Run all validation functions and return issues."""
    issues = {
        "Introduced Year Constraints": check_introduced_year_constraints(data),
        "Lifespan Constraints": check_lifespan_constraints(data),
        "Tech-Fuel and Tech-Feedstock Pairs": validate_tech_fuel_material_pairs(data),
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
