import pandas as pd
from pyomo.environ import (
    ConcreteModel, Var, NonNegativeReals, Binary, Param,
    Objective, Constraint, SolverFactory, Set, minimize
)

import pyomo.environ as pyo

def load_data(file_path):
    """
    Load all relevant data from the Excel file.
    """
    data = {}

    # Load baseline data (existing furnace sites)
    data['baseline'] = pd.read_excel(file_path, sheet_name='baseline', index_col=0)

    # Load potential furnace technologies
    data['technology'] = pd.read_excel(file_path, sheet_name='technology', index_col=0)

    # Load fuel-related data
    data['fuel_cost'] = pd.read_excel(file_path, sheet_name='fuel_cost', index_col=0)
    data['fuel_efficiency'] = pd.read_excel(file_path, sheet_name='fuel_efficiency', index_col=0)

    # Load material-related data
    data['material_cost'] = pd.read_excel(file_path, sheet_name='material_cost', index_col=0)
    data['material_efficiency'] = pd.read_excel(file_path, sheet_name='material_efficiency', index_col=0)

    # Load financial data
    data['capex'] = pd.read_excel(file_path, sheet_name='capex', index_col=0)
    data['opex'] = pd.read_excel(file_path, sheet_name='opex', index_col=0)
    data['renewal'] = pd.read_excel(file_path, sheet_name='renewal', index_col=0)

    data['technology_fuel_pairs'] = pd.read_excel(file_path, sheet_name='technology_fuel_pairs').groupby('technology')['fuel'].apply(list).to_dict()
    data['technology_material_pairs'] = pd.read_excel(file_path, sheet_name='technology_material_pairs').groupby('technology')['material'].apply(list).to_dict()
    data['technology_introduction'] = pd.read_excel(file_path, sheet_name='technology', index_col=0)['introduction'].to_dict()

    return data

# Assume build_model_for_system is defined as above

def build_model_for_system(system_name, baseline_row, data):
    """
    Build a Pyomo optimization model for a single furnace site (system),
    ensuring that the initial year (2025) maintains the baseline technology
    and transitions correctly based on replace and renew actions.
    """
    model = ConcreteModel()

    # Define sets from the loaded data
    model.technologies = Set(initialize=data['technology'].index.tolist())
    model.fuels = Set(initialize=data['fuel_cost'].index.tolist())
    model.materials = Set(initialize=data['material_cost'].index.tolist())

    # Include all years, including 2025
    all_years = sorted([int(yr) for yr in data['capex'].columns.tolist()])
    initial_year = 2025  # Fixed baseline year
    model.years = Set(initialize=all_years)  # Include all years

    # Parameters from the baseline
    try:
        production = baseline_row['production']
    except KeyError:
        raise KeyError(f"Missing 'production' data for {system_name} in the baseline sheet.")

    if pd.isna(production):
        raise ValueError(f"'production' value for {system_name} is NaN.")

    remained_lifespan = baseline_row['remained_lifespan']
    baseline_tech = baseline_row['technology']

    # Determine end_of_life_year
    end_of_life_year = initial_year + remained_lifespan - 1

    # Verify end_of_life_year is within model years
    if end_of_life_year not in model.years:
        raise ValueError(f"EoL year {end_of_life_year} not within model years for {system_name}.")

    # Parameters
    model.capex_param = Param(
        model.technologies, model.years,
        initialize=lambda m, tech, yr: data['capex'].loc[tech, yr],
        default=0.0
    )
    model.opex_param = Param(
        model.technologies, model.years,
        initialize=lambda m, tech, yr: data['opex'].loc[tech, yr],
        default=0.0
    )
    model.renewal_param = Param(
        model.technologies, model.years,
        initialize=lambda m, tech, yr: data['renewal'].loc[tech, yr],
        default=0.0
    )
    model.fuel_cost_param = Param(
        model.fuels, model.years,
        initialize=lambda m, f, yr: data['fuel_cost'].loc[f, yr],
        default=0.0
    )
    model.fuel_eff_param = Param(
        model.fuels, model.years,
        initialize=lambda m, f, yr: data['fuel_efficiency'].loc[f, yr],
        default=0.0
    )
    model.material_cost_param = Param(
        model.materials, model.years,
        initialize=lambda m, mat, yr: data['material_cost'].loc[mat, yr],
        default=0.0
    )
    model.material_eff_param = Param(
        model.materials, model.years,
        initialize=lambda m, mat, yr: data['material_efficiency'].loc[mat, yr],
        default=0.0
    )

    # Decision variables
    model.fuel_select = Var(
        model.fuels, model.years,
        domain=Binary,
        doc="1 if fuel is selected in a given year, else 0"
    )
    model.material_select = Var(
        model.materials, model.years,
        domain=Binary,
        doc="1 if material is selected in a given year, else 0"
    )
    model.replace = Var(
        model.technologies, model.years,
        domain=Binary,
        doc="1 if technology is replaced in a given year, else 0"
    )
    model.renew = Var(
        model.technologies, model.years,
        domain=Binary,
        doc="1 if the technology is renewed in a given year, else 0"
    )
    model.fuel_consumption = Var(
        model.fuels, model.years,
        domain=NonNegativeReals,
        doc="Amount of fuel consumed in a given year"
    )
    # Active Technology Variable
    model.active_technology = Var(
        model.technologies, model.years,
        domain=Binary,
        doc="1 if technology is active in a given year, else 0"
    )

    # Production Parameter
    model.production = Param(initialize=production, within=NonNegativeReals)

    # --- 2) Constraints ---

    # # a. Existing technology must remain until baseline lifespan
    # def existing_tech_lifespan_rule(m, tech, yr):
    #     if yr <= end_of_life_year:
    #         if tech == baseline_tech:
    #             return m.active_technology[tech, yr] == 1
    #         else:
    #             return m.active_technology[tech, yr] == 0
    #     return Constraint.Skip
    #
    # model.existing_tech_lifespan_constraint = Constraint(
    #     model.technologies, model.years, rule=existing_tech_lifespan_rule
    # )
    #
    # # b. Disallow replace or renew outside EoL year
    # def no_replace_or_renew_rule(m, tech, yr):
    #     if tech == baseline_tech:
    #         if yr == end_of_life_year:
    #             return m.replace[tech, yr] + m.renew[tech, yr] <= 1
    #         else:
    #             return m.replace[tech, yr] + m.renew[tech, yr] == 0
    #     else:
    #         return m.replace[tech, yr] + m.renew[tech, yr] == 0
    #
    # model.no_replace_or_renew_constraint = Constraint(
    #     model.technologies, model.years, rule=no_replace_or_renew_rule
    # )

    # c. Ensure only one technology is active each year
    def single_active_tech_rule(m, yr):
        return sum(m.active_technology[tech, yr] for tech in m.technologies) == 1

    model.single_active_tech_constraint = Constraint(model.years, rule=single_active_tech_rule)

    # d. Transition Constraints
    def transition_constraints_rule(m, tech, yr):
        if yr == initial_year:
            # Initial year is already fixed by existing_tech_lifespan_constraint
            return Constraint.Skip
        previous_year = yr - 1
        return m.active_technology[tech, yr] >= m.active_technology[tech, previous_year] - m.replace[tech, previous_year] - m.renew[tech, previous_year]

    model.transition_constraints = Constraint(
        model.technologies,
        [yr for yr in model.years if yr > initial_year],
        rule=transition_constraints_rule
    )

    def new_technology_active_rule(m, tech, yr):
        if yr == initial_year:
            return Constraint.Skip
        previous_year = yr - 1
        return m.active_technology[tech, yr] >= m.replace[tech, previous_year]

    model.new_technology_active_constraint = Constraint(
        model.technologies,
        [yr for yr in model.years if yr > initial_year],
        rule=new_technology_active_rule
    )

    # f. Ensure only one fuel is selected each year
    def fuel_selection_rule(m, yr):
        return sum(m.fuel_select[f, yr] for f in m.fuels) == 1

    model.fuel_selection_constraint = Constraint(model.years, rule=fuel_selection_rule)

    # g. Ensure only one material is selected each year
    def material_selection_rule(m, yr):
        return sum(m.material_select[mat, yr] for mat in model.materials) == 1

    model.material_selection_constraint = Constraint(model.years, rule=material_selection_rule)

    # h. Production constraint
    def production_constraint_rule(m, yr):
        return m.production == sum(
            m.fuel_consumption[f, yr] / m.fuel_eff_param[f, yr] for f in m.fuels
        )

    model.production_constraint = Constraint(model.years, rule=production_constraint_rule)

    # i. Link fuel consumption and selection
    M_BIG = 1e6  # A large number to link binary and continuous variables

    def fuel_consumption_limit_rule(m, f, yr):
        return m.fuel_consumption[f, yr] <= m.fuel_select[f, yr] * M_BIG

    model.fuel_consumption_limit_constraint = Constraint(
        model.fuels, model.years, rule=fuel_consumption_limit_rule
    )

    # j. Technology-Fuel Pairing Constraint
    def fuel_technology_link_rule(m, yr, f):
        compatible_replacements = [
            tech for tech in m.technologies if f in data['technology_fuel_pairs'].get(tech, [])
        ]
        return sum(m.replace[tech, yr] for tech in compatible_replacements) >= m.fuel_select[f, yr]

    model.fuel_technology_link_constraint = Constraint(
        model.years, model.fuels, rule=fuel_technology_link_rule
    )

    # k. Technology-Material Pairing Constraint
    def material_technology_link_rule(m, yr, mat):
        compatible_replacements = [
            tech for tech in m.technologies if mat in data['technology_material_pairs'].get(tech, [])
        ]
        return sum(m.replace[tech, yr] for tech in compatible_replacements) >= m.material_select[mat, yr]

    model.material_technology_link_constraint = Constraint(
        model.years, model.materials, rule=material_technology_link_rule
    )

    # l. Introduction Year Constraint
    def introduction_year_constraint_rule(m, tech, yr):
        introduction_year = data['technology_introduction'][tech]
        if yr < introduction_year:
            return m.replace[tech, yr] == 0
        return Constraint.Skip

    model.introduction_year_constraint = Constraint(
        model.technologies, model.years, rule=introduction_year_constraint_rule
    )

    # --- 3) Objective function ---
    def total_cost_rule(m):
        total_cost = 0
        for yr in m.years:
            for tech in m.technologies:
                # Opex for active technology
                total_cost += m.active_technology[tech, yr] * m.opex_param[tech, yr] * m.production

                # Capex if technology is replaced
                total_cost += m.replace[tech, yr] * m.capex_param[tech, yr] * m.production

                # Renewal costs if technology is renewed
                total_cost += m.renew[tech, yr] * m.renewal_param[tech, yr] * m.production

            # Fuel and Material Costs based on selection
            for f in m.fuels:
                total_cost += m.fuel_cost_param[f, yr] * m.production * m.fuel_select[f, yr]
            for mat in m.materials:
                total_cost += m.material_cost_param[mat, yr] * m.production * m.material_select[mat, yr]
        return total_cost

    model.objective = Objective(rule=total_cost_rule, sense=minimize)

    # --- 4) Fix Technology for the Initial Year (2025) ---
    def fix_technology_for_year(model, fixed_year=2025, baseline_tech=None):
        if baseline_tech is None:
            raise ValueError("Baseline technology must be specified.")

        print(f"Fixing technology for year {fixed_year} to {baseline_tech}")

        def fix_tech_rule(m, tech):
            if tech == baseline_tech:
                return m.active_technology[tech, fixed_year] == 1
            else:
                return m.active_technology[tech, fixed_year] == 0

        # Create a unique name for the constraint to avoid conflicts
        setattr(model, f"FixTechnologyConstraint_{fixed_year}", Constraint(model.technologies, rule=fix_tech_rule))

    # Call the function to fix technology for 2025
    fix_technology_for_year(model, fixed_year=initial_year, baseline_tech=baseline_tech)

    return model


# Main script to load data, loop over each furnace site, and solve
file_path = 'database/steel_data.xlsx'
data = load_data(file_path)

solver = SolverFactory('glpk')  # or another solver

results_dict = {}

for system_name in data['baseline'].index:
    print(f"\n=== Solving for furnace site: {system_name} ===")

    # Extract the row (Series) for the current furnace site
    baseline_row = data['baseline'].loc[system_name]

    try:
        # 1) Build the model
        m = build_model_for_system(system_name, baseline_row, data)

        # 2) Optionally, inspect the model
        # m.pprint()

        # 3) Solve the model
        result = solver.solve(m, tee=True)

        # 4) Check solver status
        if result.solver.status == 'ok' and result.solver.termination_condition == 'optimal':
            # Gather results for this system
            production_value = pyo.value(m.production)  # From the model's Param

            # Fuel consumption data
            fuel_data = []
            for yr in m.years:
                for f in m.fuels:
                    if pyo.value(m.fuel_select[f, yr]) > 0.5:
                        fuel_data.append({
                            "Year": yr,
                            "Fuel": f,
                            "Consumption (tons)": pyo.value(m.fuel_consumption[f, yr])
                        })

            # Technology changes data
            technology_changes = []
            for yr in m.years:
                for tech in m.technologies:
                    if pyo.value(m.replace[tech, yr]) > 0.5:
                        technology_changes.append({
                            "Year": yr,
                            "Action": "Replace",
                            "Technology": tech
                        })
                    if pyo.value(m.renew[tech, yr]) > 0.5:
                        technology_changes.append({
                            "Year": yr,
                            "Action": "Renew",
                            "Technology": tech
                        })

            # Active technologies data
            active_technologies = []
            for yr in m.years:
                for tech in m.technologies:
                    if pyo.value(m.active_technology[tech, yr]) > 0.5:
                        active_technologies.append({
                            "Year": yr,
                            "Active Technology": tech
                        })

            # Save results
            results_dict[system_name] = {
                "Production": production_value,
                "Fuel Consumption": fuel_data,
                "Technology Changes": technology_changes,
                "Active Technologies": active_technologies
            }

            # --- Debugging: Inspect Technology Status for 2025 ---
            print("\n--- Technology Status for 2025 ---")
            for tech in m.technologies:
                active_val = pyo.value(m.active_technology[tech, 2025])
                replace_val = pyo.value(m.replace[tech, 2025])
                renew_val = pyo.value(m.renew[tech, 2025])
                print(f"  Technology {tech}: Active = {active_val}, Replace = {replace_val}, Renew = {renew_val}")

            # --- Debugging: Verify Replace and Renew Variables ---
            print("\n--- Replace and Renew Variables ---")
            for yr in m.years:
                for tech in m.technologies:
                    replace_val = pyo.value(m.replace[tech, yr])
                    renew_val = pyo.value(m.renew[tech, yr])
                    print(f"Year {yr}, Tech {tech}: Replace = {replace_val}, Renew = {renew_val}")

        else:
            print(f"Solver failed for {system_name}. Status: {result.solver.status}, Condition: {result.solver.termination_condition}")

    except Exception as e:
        print(f"An error occurred for {system_name}: {e}")

    finally:
        # Delete the model to free memory and prevent variable name conflicts
        del m

# Display results for all systems
for system_name, results in results_dict.items():
    print(f"\n=== Results for {system_name} ===")
    print(f"Production: {results['Production']} tons")
    print("\nFuel Consumption:")
    for fc in results['Fuel Consumption']:
        print(f"  Year {fc['Year']}: {fc['Fuel']} - {fc['Consumption (tons)']} tons")

    print("\nTechnology Changes:")
    if results['Technology Changes']:
        for tc in results['Technology Changes']:
            print(f"  Year {tc['Year']}: {tc['Action']} - {tc['Technology']}")
    else:
        print("  No technology changes.")

    print("\nActive Technologies:")
    for at in results['Active Technologies']:
        print(f"  Year {at['Year']}: {at['Active Technology']}")
