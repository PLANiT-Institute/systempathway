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

    # Define years
    all_years = sorted([int(yr) for yr in data['capex'].columns.tolist()])
    model.years = Set(initialize=all_years)

    # Parameters from the baseline
    production = baseline_row['production']
    baseline_tech = baseline_row['technology']

    # Define parameters
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
    model.lifespan_param = Param(
        model.technologies,
        initialize=lambda m, tech: data['technology'].loc[tech, 'lifespan'],
        default=0
    )

    # Decision variables
    model.fuel_select = Var(model.fuels, model.years, domain=Binary)
    model.material_select = Var(model.materials, model.years, domain=Binary)
    model.continue_technology = Var(model.technologies, model.years, domain=Binary)
    model.replace = Var(model.technologies, model.years, domain=Binary)
    model.renew = Var(model.technologies, model.years, domain=Binary)
    model.active_technology = Var(model.technologies, model.years, domain=Binary)
    model.fuel_consumption = Var(model.fuels, model.years, domain=NonNegativeReals)

    # Constraints
    def replace_or_renew_years_rule(m, tech, yr):
        introduced_year = data['technology_introduction'][tech]
        lifespan = m.lifespan_param[tech]

        if yr >= min(m.years):
            if (yr - introduced_year) % lifespan == 0 and (yr - introduced_year) >= lifespan:
                return m.replace[tech, yr] + m.renew[tech, yr] <= 1
            else:
                return m.replace[tech, yr] + m.renew[tech, yr] == 0
        return Constraint.Skip

    model.replace_or_renew_years_constraint = Constraint(
        model.technologies, model.years, rule=replace_or_renew_years_rule
    )

    def continuation_only_rule(m, tech, yr):
        introduced_year = data['technology_introduction'][tech]
        lifespan = m.lifespan_param[tech]

        if yr >= min(m.years):
            if (yr - introduced_year) % lifespan != 0 or (yr - introduced_year) < lifespan:
                return m.continue_technology[tech, yr] == 1
        return Constraint.Skip

    model.continuation_only_constraint = Constraint(
        model.technologies, model.years, rule=continuation_only_rule
    )

    def active_technology_rule(m, tech, yr):
        introduced_year = data['technology_introduction'][tech]
        lifespan = m.lifespan_param[tech]

        if (yr - introduced_year) % lifespan == 0 and (yr - introduced_year) >= lifespan:
            return m.active_technology[tech, yr] == m.replace[tech, yr] + m.renew[tech, yr]
        elif yr >= introduced_year:
            return m.active_technology[tech, yr] == m.continue_technology[tech, yr]
        return Constraint.Skip

    model.active_technology_constraint = Constraint(
        model.technologies, model.years, rule=active_technology_rule
    )

    def fuel_technology_link_rule(m, tech, f):
        if f not in data['technology_fuel_pairs'].get(tech, []):
            return sum(m.active_technology[tech, yr] for yr in m.years) == 0
        return Constraint.Skip

    model.fuel_technology_link_constraint = Constraint(
        model.technologies, model.fuels, rule=fuel_technology_link_rule
    )

    def material_technology_link_rule(m, tech, mat):
        if mat not in data['technology_material_pairs'].get(tech, []):
            return sum(m.active_technology[tech, yr] for yr in m.years) == 0
        return Constraint.Skip

    model.material_technology_link_constraint = Constraint(
        model.technologies, model.materials, rule=material_technology_link_rule
    )

    def total_cost_rule(m):
        return sum(
            sum(
                m.capex_param[tech, yr] * production * m.active_technology[tech, yr]
                + m.opex_param[tech, yr] * production * m.active_technology[tech, yr]
                + m.renewal_param[tech, yr] * production * m.renew[tech, yr]
                + sum(m.fuel_cost_param[f, yr] * production * m.fuel_select[f, yr] for f in m.fuels)
                + sum(m.material_cost_param[mat, yr] * production * m.material_select[mat, yr] for mat in m.materials)
                for tech in m.technologies
            )
            for yr in m.years
        )

    model.objective = Objective(rule=total_cost_rule, sense=minimize)

    return model

# Main script
file_path = 'database/steel_data.xlsx'
data = load_data(file_path)
solver = SolverFactory('glpk')

results_dict = {}

for system_name in data['baseline'].index:
    print(f"\n=== Solving for furnace site: {system_name} ===")
    baseline_row = data['baseline'].loc[system_name]
    m = build_model_for_system(system_name, baseline_row, data)
    result = solver.solve(m, tee=True)

    if result.solver.status == 'ok' and result.solver.termination_condition == 'optimal':
        print(f"Optimal solution found for {system_name}")

        # Extract results
        production_value = baseline_row['production']

        # Technology changes
        technology_changes = []
        for yr in m.years:
            active_technology = None
            for tech in m.technologies:
                if m.active_technology[tech, yr].value is not None and m.active_technology[tech, yr].value > 0.5:
                    active_technology = tech
                    break
            if active_technology:
                technology_changes.append({"Year": yr, "Technology": active_technology})

        # Fuel consumption
        fuel_data = []
        for yr in m.years:
            for f in m.fuels:
                if m.fuel_select[f, yr].value is not None and m.fuel_select[f, yr].value > 0.5:
                    fuel_data.append({
                        "Year": yr,
                        "Fuel": f,
                        "Consumption (tons)": m.fuel_consumption[f, yr].value if m.fuel_consumption[f, yr].value is not None else 0
                    })

        # Material consumption
        material_data = []
        for yr in m.years:
            for mat in m.materials:
                if m.material_select[mat, yr].value is not None and m.material_select[mat, yr].value > 0.5:
                    material_data.append({
                        "Year": yr,
                        "Material": mat,
                        "Consumption (tons)": production_value * m.material_eff_param[mat, yr]
                    })

        # Save results
        results_dict[system_name] = {
            "Production": production_value,
            "Technology Changes": technology_changes,
            "Fuel Consumption": fuel_data,
            "Material Consumption": material_data
        }

    else:
        print(f"Solver failed for {system_name}. Status: {result.solver.status}, Condition: {result.solver.termination_condition}")

# Display results
for system_name, results in results_dict.items():
    print(f"\n=== Results for {system_name} ===")
    print(f"Production: {results['Production']} tons\n")

    print("Technology Changes by Year:")
    for change in results['Technology Changes']:
        print(f"  Year {change['Year']}: {change['Technology']}")

    print("\nFuel Consumption by Year:")
    for fuel in results['Fuel Consumption']:
        print(f"  Year {fuel['Year']}: {fuel['Fuel']} - {fuel['Consumption (tons)']} tons")

    print("\nMaterial Consumption by Year:")
    for material in results['Material Consumption']:
        print(f"  Year {material['Year']}: {material['Material']} - {material['Consumption (tons)']} tons")
