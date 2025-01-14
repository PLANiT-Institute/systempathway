import pandas as pd
from pyomo.environ import (
    ConcreteModel, Var, NonNegativeReals, Binary, Param,
    Objective, Constraint, SolverFactory, Set, minimize
)

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


def build_model_for_system(system_name, baseline_row, data):
    """
    Build a Pyomo optimization model for a single furnace site (system),
    ensuring that the initial year maintains the baseline technology
    and is excluded from the optimization years.
    """
    model = ConcreteModel()

    # Define sets from the loaded data
    model.technologies = Set(initialize=data['technology'].index.tolist())
    model.fuels = Set(initialize=data['fuel_cost'].index.tolist())
    model.materials = Set(initialize=data['material_cost'].index.tolist())

    # Exclude 2025 from the optimization years
    all_years = sorted([int(yr) for yr in data['capex'].columns.tolist()])
    initial_year = 2025  # Fixed baseline year
    # optimization_years = [yr for yr in all_years if yr != initial_year]
    optimization_years = all_years
    model.years = Set(initialize=optimization_years)

    # Parameters from the baseline
    production = baseline_row['production']
    introduced_year = baseline_row['introduced_year']
    baseline_tech = baseline_row['technology']

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

    # Decision variable for continuing the same technology
    model.continue_technology = Var(
        model.technologies, model.years,
        domain=Binary,
        doc="1 if the technology is continued from the previous year, else 0"
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
    # Adjust the definition of active_technology to include introduced_year
    model.active_technology = Var(
        model.technologies, model.years | {introduced_year},  # Include introduced_year
        domain=Binary,
        doc="1 if technology is active in a given year, else 0"
    )

    # Define lifespan as a parameter
    model.lifespan_param = Param(
        model.technologies,
        initialize=lambda m, tech: data['technology'].loc[tech, 'lifespan'],
        default=0
    )
    # Constraints

    def hard_baseline_fuel_rule(m, f, yr):
        if yr == 2025:  # Lock the fuel selection for the initial year
            baseline_fuel = baseline_row['fuel']
            if f == baseline_fuel:
                return m.fuel_select[f, yr] == 1  # Must use the baseline fuel
            else:
                return m.fuel_select[f, yr] == 0  # Other fuels cannot be selected
        return Constraint.Skip

    model.hard_baseline_fuel_constraint = Constraint(
        model.fuels, model.years, rule=hard_baseline_fuel_rule
    )

    def first_year_constraint(m, tech, yr):

        # First year: Only baseline technology can continue
        if yr == min(m.years):
            if tech == baseline_tech:
                return m.continue_technology[tech, yr] == 1
            else:
                return m.continue_technology[tech, yr] + m.replace[tech, yr] + m.renew[tech, yr] == 0

        return Constraint.Skip

    model.first_year_constraint = Constraint(model.technologies, model.years, rule=first_year_constraint)

    def enforce_continuation_before_lifespan(m, tech, yr):
        introduced_year = baseline_row['introduced_year']
        lifespan = m.lifespan_param[tech]
        end_of_lifespan = introduced_year + lifespan

        # From first year to end_of_lifespan - 1: Continuation only
        if min(m.years) < yr < end_of_lifespan:
            if tech == baseline_tech:
                return m.continue_technology[tech, yr] == 1
            else:
                return m.continue_technology[tech, yr] + m.replace[tech, yr] + m.renew[tech, yr] == 0
        return Constraint.Skip

    model.enforce_continuation_before_lifespan_constraint = Constraint(
        model.technologies, model.years, rule=enforce_continuation_before_lifespan
    )

    # If a technology is continued, it must have been active in the previous year
    def continuity_active_rule(m, tech, yr):
        if yr > min(m.years):  # Skip the first year
            return m.continue_technology[tech, yr] <= m.active_technology[tech, yr - 1]
        return Constraint.Skip

    model.continuity_active_constraint = Constraint(
        model.technologies, model.years, rule=continuity_active_rule
    )

    def active_technology_rule(m, tech, yr):
        introduced_year = baseline_row['introduced_year']
        lifespan = m.lifespan_param[tech]
        end_of_lifespan = introduced_year + lifespan

        # Before the end of the lifespan, active technology is determined by continuation
        if min(m.years) < yr < end_of_lifespan:
            return m.active_technology[tech, yr] == m.continue_technology[tech, yr]

        # At the end of the lifespan, active technology is determined by replacement or renewal
        if yr == end_of_lifespan:
            return m.active_technology[tech, yr] == m.replace[tech, yr] + m.renew[tech, yr]

        return Constraint.Skip

    model.active_technology_constraint = Constraint(
        model.technologies, model.years, rule=active_technology_rule
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
        return production == sum(
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

    # Objective function with levelized capex and opex
    def total_cost_rule(m):
        return sum(
            sum(
                # Capex (levelized) for all active technologies
                m.capex_param[tech, yr] * production * m.active_technology[tech, yr]
                # Opex for all active technologies
                + m.opex_param[tech, yr] * production * m.active_technology[tech, yr]
                # Renewal costs
                + m.renewal_param[tech, yr] * production * m.renew[tech, yr]
                # Fuel costs
                + sum(
                    m.fuel_cost_param[f, yr] * production * m.fuel_select[f, yr]
                    for f in m.fuels
                )
                # Material costs
                + sum(
                    m.material_cost_param[mat, yr] * production * m.material_select[mat, yr]
                    for mat in m.materials
                )
                for tech in m.technologies
            )
            for yr in m.years
        )

    model.objective = Objective(rule=total_cost_rule, sense=minimize)

    return model

# -------------------------------------------------------------------------
# Main script to load data, loop over each furnace site, and solve
file_path = 'database/steel_data.xlsx'
data = load_data(file_path)

solver = SolverFactory('glpk')  # or another solver

results_dict = {}

for system_name in data['baseline'].index:
    print(f"\n=== Solving for furnace site: {system_name} ===")

    # Extract the row (Series) for the current furnace site
    baseline_row = data['baseline'].loc[system_name]

    # 1) Build the model
    m = build_model_for_system(system_name, baseline_row, data)

    # 2) Solve the model
    result = solver.solve(m, tee=True)

    if result.solver.status == 'ok' and result.solver.termination_condition == 'optimal':
        # Gather results for this system
        production_value = baseline_row['production']  # From the baseline_row

        # Fuel consumption data
        fuel_data = []
        for yr in m.years:
            for f in m.fuels:
                if m.fuel_select[f, yr].value > 0.5:
                    fuel_data.append({
                        "Year": yr,
                        "Fuel": f,
                        "Consumption (tons)": m.fuel_consumption[f, yr].value
                    })

        # Technology changes data
        technology_changes = []

        for yr in m.years:
            active_technology = None

            # Check if any replacement occurs in this year
            for tech in m.technologies:
                if m.replace[tech, yr].value > 0.5:
                    active_technology = tech
                    break  # Only one replacement can happen per year

            # If no replacement occurred, the baseline technology remains active
            if not active_technology:
                for tech in m.technologies:
                    if m.active_technology[tech, yr].value > 0.5:
                        active_technology = tech
                        break

            # Add the active technology for the year
            if active_technology:
                technology_changes.append({
                    "Year": yr,
                    "Technology": active_technology
                })

        # Save results
        results_dict[system_name] = {
            "Production": production_value,
            "Fuel Consumption": fuel_data,
            "Technology Changes": technology_changes
        }

    else:
        print(f"Solver failed for {system_name}. Status: {result.solver.status}, Condition: {result.solver.termination_condition}")
#
# Display results for all systems
for system_name, results in results_dict.items():
    print(f"\n=== Results for {system_name} ===")
    print(f"Production: {results['Production']} tons")
    print("\nFuel Consumption:")
    for fc in results['Fuel Consumption']:
        print(f"  Year {fc['Year']}: {fc['Fuel']} - {fc['Consumption (tons)']} tons")

    print("\nTechnology Changes:")
    for tc in results['Technology Changes']:
        print(f"  Year {tc['Year']}: {tc['Technology']}")