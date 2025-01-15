import pandas as pd
from pyomo.environ import (
    ConcreteModel, Var, NonNegativeReals, Binary, Param,
    Objective, Constraint, SolverFactory, Set, minimize, ConstraintList
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
    data['fuel_emission'] = pd.read_excel(file_path, sheet_name='fuel_emission', index_col=0)

    # Load material-related data
    data['material_cost'] = pd.read_excel(file_path, sheet_name='material_cost', index_col=0)
    data['material_efficiency'] = pd.read_excel(file_path, sheet_name='material_efficiency', index_col=0)
    data['material_emission'] = pd.read_excel(file_path, sheet_name='material_emission', index_col=0)

    # Load financial data
    data['capex'] = pd.read_excel(file_path, sheet_name='capex', index_col=0)
    data['opex'] = pd.read_excel(file_path, sheet_name='opex', index_col=0)
    data['renewal'] = pd.read_excel(file_path, sheet_name='renewal', index_col=0)
    data['emission'] = pd.read_excel(file_path, sheet_name='emission', index_col=0)

    # Load technology emission intensities and pairings
    data['technology_ei'] = pd.read_excel(file_path, sheet_name='technology_ei', index_col=0)
    data['technology_fuel_pairs'] = pd.read_excel(file_path, sheet_name='technology_fuel_pairs').groupby('technology')[
        'fuel'].apply(list).to_dict()
    data['technology_material_pairs'] = \
    pd.read_excel(file_path, sheet_name='technology_material_pairs').groupby('technology')['material'].apply(
        list).to_dict()
    data['technology_introduction'] = pd.read_excel(file_path, sheet_name='technology', index_col=0)[
        'introduction'].to_dict()

    return data


def build_unified_model(data):
    """
    Build a unified Pyomo optimization model that includes all systems and global emission constraints.
    """
    model = ConcreteModel()

    # Sets
    model.systems = Set(initialize=data['baseline'].index.tolist())
    model.technologies = Set(initialize=data['technology'].index.tolist())
    model.fuels = Set(initialize=data['fuel_cost'].index.tolist())
    model.materials = Set(initialize=data['material_cost'].index.tolist())

    # Define all years from the data
    all_years = sorted([int(yr) for yr in data['capex'].columns.tolist()])
    initial_year = 2025  # Fixed baseline year
    model.years = Set(initialize=all_years)

    # Parameters
    # Financial Parameters
    model.capex = Param(model.technologies, model.years, initialize=lambda m, tech, yr: data['capex'].loc[tech, yr],
                        default=0.0)
    model.opex = Param(model.technologies, model.years, initialize=lambda m, tech, yr: data['opex'].loc[tech, yr],
                       default=0.0)
    model.renewal = Param(model.technologies, model.years, initialize=lambda m, tech, yr: data['renewal'].loc[tech, yr],
                          default=0.0)

    # Emission Intensity
    model.technology_ei = Param(model.technologies, model.years,
                                initialize=lambda m, tech, yr: data['technology_ei'].loc[tech, yr], default=1.0)

    # Fuel Parameters
    model.fuel_cost = Param(model.fuels, model.years, initialize=lambda m, f, yr: data['fuel_cost'].loc[f, yr],
                            default=0.0)
    model.fuel_efficiency = Param(model.fuels, model.years,
                                  initialize=lambda m, f, yr: data['fuel_efficiency'].loc[f, yr], default=0.0)
    model.fuel_emission = Param(model.fuels, model.years, initialize=lambda m, f, yr: data['fuel_emission'].loc[f, yr],
                                default=0.0)

    # Material Parameters
    model.material_cost = Param(model.materials, model.years,
                                initialize=lambda m, mat, yr: data['material_cost'].loc[mat, yr], default=0.0)
    model.material_efficiency = Param(model.materials, model.years,
                                      initialize=lambda m, mat, yr: data['material_efficiency'].loc[mat, yr],
                                      default=0.0)
    model.material_emission = Param(model.materials, model.years,
                                    initialize=lambda m, mat, yr: data['material_emission'].loc[mat, yr], default=0.0)

    # Technology-Fuel and Technology-Material Pairs
    data['technology_fuel_pairs'] = data['technology_fuel_pairs']  # Already loaded as a dict
    data['technology_material_pairs'] = data['technology_material_pairs']  # Already loaded as a dict

    # Global Emission Limits
    model.global_emission_limit = Param(model.years, initialize=lambda m, yr: data['emission'].loc['emission', yr],
                                        default=1e9)

    # Decision Variables
    # For each system
    model.fuel_select = Var(model.systems, model.fuels, model.years, domain=Binary)
    model.material_select = Var(model.systems, model.materials, model.years, domain=Binary)
    model.continue_technology = Var(model.systems, model.technologies, model.years, domain=Binary)
    model.replace = Var(model.systems, model.technologies, model.years, domain=Binary)
    model.renew = Var(model.systems, model.technologies, model.years, domain=Binary)
    model.fuel_consumption = Var(model.systems, model.fuels, model.years, domain=NonNegativeReals)
    model.active_technology = Var(model.systems, model.technologies, model.years, domain=Binary)

    # Emission Variables
    model.system_emission = Var(model.systems, model.years, domain=NonNegativeReals)

    # Auxiliary Variables for Linearization
    model.fuel_consumption_active = Var(model.systems, model.technologies, model.fuels, model.years,
                                        domain=NonNegativeReals)
    model.material_emission_active = Var(model.systems, model.technologies, model.materials, model.years,
                                         domain=NonNegativeReals)

    # Global Total Emissions
    model.total_emissions = Var(model.years, within=NonNegativeReals)

    # Objective Function: Minimize Total Cost Across All Systems
    def total_cost_rule(m):
        return sum(
            sum(
                m.capex[tech, yr] * m.active_technology[sys, tech, yr]
                + m.opex[tech, yr] * m.active_technology[sys, tech, yr]
                + m.renewal[tech, yr] * m.renew[sys, tech, yr]
                + sum(m.fuel_cost[f, yr] * m.fuel_select[sys, f, yr] for f in m.fuels)
                + sum(m.material_cost[mat, yr] * m.material_select[sys, mat, yr] for mat in m.materials)
                for tech in m.technologies
            )
            for sys in m.systems for yr in m.years
        )

    model.objective = Objective(rule=total_cost_rule, sense=minimize)

    # Constraints
    # 1. For each system and year, exactly one fuel and one material must be selected
    def fuel_selection_rule(m, sys, yr):
        return sum(m.fuel_select[sys, f, yr] for f in m.fuels) == 1

    model.fuel_selection_constraint = Constraint(model.systems, model.years, rule=fuel_selection_rule)

    def material_selection_rule(m, sys, yr):
        return sum(m.material_select[sys, mat, yr] for mat in m.materials) == 1

    model.material_selection_constraint = Constraint(model.systems, model.years, rule=material_selection_rule)

    # 2. Production Constraint for Each System and Year
    def production_constraint_rule(m, sys, yr):
        production = data['baseline'].loc[sys, 'production']
        return sum(m.fuel_consumption[sys, f, yr] / m.fuel_efficiency[f, yr] for f in m.fuels) == production

    model.production_constraint = Constraint(model.systems, model.years, rule=production_constraint_rule)

    # 3. Link Fuel Consumption and Selection
    M_BIG = 1e6  # A large number to link binary and continuous variables
    model.fuel_consumption_active = Var(model.systems, model.fuels, model.years, domain=NonNegativeReals)

    def fuel_consumption_limit_rule(m, sys, f, yr):
        return m.fuel_consumption[sys, f, yr] <= m.fuel_select[sys, f, yr] * M_BIG

    model.fuel_consumption_limit_constraint = Constraint(model.systems, model.fuels, model.years,
                                                         rule=fuel_consumption_limit_rule)

    # 4. Technology Continuity and Lifecycle Constraints
    for sys in model.systems:
        baseline_row = data['baseline'].loc[sys]
        baseline_tech = baseline_row['technology']
        introduced_year = baseline_row['introduced_year']
        lifespan = data['technology'].loc[baseline_tech, 'lifespan']
        end_of_lifespan = introduced_year + lifespan

        for yr in model.years:
            # First Year Constraints
            if yr == initial_year:
                for tech in model.technologies:
                    if tech == baseline_tech:
                        model.continue_technology[sys, tech, yr].fix(1)
                        model.replace[sys, tech, yr].fix(0)
                        model.renew[sys, tech, yr].fix(0)
                        model.active_technology[sys, tech, yr].fix(1)
                    else:
                        model.continue_technology[sys, tech, yr].fix(0)
                        model.replace[sys, tech, yr].fix(0)
                        model.renew[sys, tech, yr].fix(0)
                        model.active_technology[sys, tech, yr].fix(0)

            # Enforce Continuation Before Lifespan Ends
            if initial_year < yr < end_of_lifespan:
                for tech in model.technologies:
                    if tech == baseline_tech:
                        model.continue_technology[sys, tech, yr].fix(1)
                        model.replace[sys, tech, yr].fix(0)
                        model.renew[sys, tech, yr].fix(0)
                        model.active_technology[sys, tech, yr].fix(1)
                    else:
                        model.continue_technology[sys, tech, yr].fix(0)
                        model.replace[sys, tech, yr].fix(0)
                        model.renew[sys, tech, yr].fix(0)
                        model.active_technology[sys, tech, yr].fix(0)

    # 5. Active Technology Definition
    def active_technology_rule(m, sys, tech, yr):
        return m.active_technology[sys, tech, yr] == m.continue_technology[sys, tech, yr] + m.replace[sys, tech, yr] + \
            m.renew[sys, tech, yr]

    model.active_technology_constraint = Constraint(model.systems, model.technologies, model.years,
                                                    rule=active_technology_rule)

    # 6. Technology-Fuel and Technology-Material Pairing
    def fuel_technology_link_rule(m, sys, f, yr):
        compatible_techs = [
            tech for tech in m.technologies if f in data['technology_fuel_pairs'].get(tech, [])
        ]
        return sum(m.active_technology[sys, tech, yr] for tech in compatible_techs) >= m.fuel_select[sys, f, yr]

    model.fuel_technology_link_constraint = Constraint(model.systems, model.fuels, model.years,
                                                       rule=fuel_technology_link_rule)

    def material_technology_link_rule(m, sys, mat, yr):
        compatible_techs = [
            tech for tech in m.technologies if mat in data['technology_material_pairs'].get(tech, [])
        ]
        return sum(m.active_technology[sys, tech, yr] for tech in compatible_techs) >= m.material_select[sys, mat, yr]

    model.material_technology_link_constraint = Constraint(model.systems, model.materials, model.years,
                                                           rule=material_technology_link_rule)

    # 7. Auxiliary Constraints for Linearization
    # Fuel Consumption Active Constraints
    model.fuel_consumption_active_constraints = ConstraintList()
    for sys in model.systems:
        for tech in model.technologies:
            for f in model.fuels:
                for yr in model.years:
                    model.fuel_consumption_active_constraints.add(
                        model.fuel_consumption_active[sys, tech, f, yr] <= model.fuel_consumption[sys, f, yr]
                    )
                    model.fuel_consumption_active_constraints.add(
                        model.fuel_consumption_active[sys, tech, f, yr] <= M_BIG * model.active_technology[
                            sys, tech, yr]
                    )
                    model.fuel_consumption_active_constraints.add(
                        model.fuel_consumption_active[sys, tech, f, yr] >= model.fuel_consumption[
                            sys, f, yr] - M_BIG * (1 - model.active_technology[sys, tech, yr])
                    )
                    model.fuel_consumption_active_constraints.add(
                        model.fuel_consumption_active[sys, tech, f, yr] >= 0
                    )

    # Material Emission Active Constraints
    model.material_emission_active_constraints = ConstraintList()
    for sys in model.systems:
        for tech in model.technologies:
            for mat in model.materials:
                for yr in model.years:
                    emission_value = (data['baseline'].loc[sys, 'production'] / model.material_efficiency[mat, yr]) * \
                                     model.material_emission[mat, yr]
                    model.material_emission_active_constraints.add(
                        model.material_emission_active[sys, tech, mat, yr] <= emission_value
                    )
                    model.material_emission_active_constraints.add(
                        model.material_emission_active[sys, tech, mat, yr] <= M_BIG * model.active_technology[
                            sys, tech, yr]
                    )
                    model.material_emission_active_constraints.add(
                        model.material_emission_active[sys, tech, mat, yr] >= emission_value - M_BIG * (
                                    1 - model.active_technology[sys, tech, yr])
                    )
                    model.material_emission_active_constraints.add(
                        model.material_emission_active[sys, tech, mat, yr] >= 0
                    )

    # 8. Emission Calculation Constraint
    def system_emission_rule(m, sys, yr):
        return m.system_emission[sys, yr] == sum(
            m.technology_ei[tech, yr] * (
                    sum(m.fuel_consumption_active[sys, tech, f, yr] * m.fuel_emission[f, yr] for f in m.fuels) +
                    sum(m.material_emission_active[sys, tech, mat, yr] for mat in m.materials)
            )
            for tech in m.technologies
        )

    model.system_emission_constraint = Constraint(model.systems, model.years, rule=system_emission_rule)

    # 9. Global Emission Aggregation
    def total_emission_rule(m, yr):
        return m.total_emissions[yr] == sum(m.system_emission[sys, yr] for sys in m.systems)

    model.total_emission_constraint = Constraint(model.years, rule=total_emission_rule)

    # 10. Global Emission Limits
    def global_emission_limit_rule(m, yr):
        return m.total_emissions[yr] <= m.global_emission_limit[yr]

    model.global_emission_limit_constraint = Constraint(model.years, rule=global_emission_limit_rule)

    return model


def main():
    # Load data
    file_path = '../database/steel_data.xlsx'
    data = load_data(file_path)

    # Build unified model
    model = build_unified_model(data)

    # Choose solver
    solver = SolverFactory('glpk')  # Ensure GLPK is installed

    # Solve the model
    result = solver.solve(model, tee=True)

    # Check solver status
    if (result.solver.status == 'ok') and (result.solver.termination_condition == 'optimal'):
        print("Solver found an optimal solution.\n")
    else:
        print(f"Solver status: {result.solver.status}")
        print(f"Termination condition: {result.solver.termination_condition}")
        return

    # Extract and display results
    results_dict = {}
    for sys in model.systems:
        production = data['baseline'].loc[sys, 'production']
        fuel_consumption = [
            {
                "Year": yr,
                "Fuel": f,
                "Consumption (tons)": model.fuel_consumption[sys, f, yr].value
            }
            for yr in model.years
            for f in model.fuels
            if model.fuel_select[sys, f, yr].value > 0.5
        ]

        technology_changes = [
            {
                "Year": yr,
                "Technology": tech,
                "Status": (
                    "replace" if model.replace[sys, tech, yr].value > 0.5 else
                    "renew" if model.renew[sys, tech, yr].value > 0.5 else
                    "continue" if model.continue_technology[sys, tech, yr].value > 0.5 else
                    "none"
                )
            }
            for yr in model.years
            for tech in model.technologies
            if (model.replace[sys, tech, yr].value > 0.5 or
                model.renew[sys, tech, yr].value > 0.5 or
                model.continue_technology[sys, tech, yr].value > 0.5)
        ]

        emissions = [
            {
                "Year": yr,
                "Emission (tons CO2eq)": model.system_emission[sys, yr].value
            }
            for yr in model.years
        ]

        results_dict[sys] = {
            "Production": production,
            "Fuel Consumption": fuel_consumption,
            "Technology Changes": technology_changes,
            "Emissions": emissions
        }

    # Display results
    for sys, results in results_dict.items():
        print(f"\n=== Results for {sys} ===")
        print(f"Production: {results['Production']} tons")

        print("\nFuel Consumption:")
        for fc in results['Fuel Consumption']:
            print(f"  Year {fc['Year']}: {fc['Fuel']} - {fc['Consumption (tons)']} tons")

        print("\nTechnology Changes:")
        for tc in results['Technology Changes']:
            print(f"  Year {tc['Year']}: {tc['Technology']} ({tc['Status']})")

        print("\nEmissions:")
        for em in results['Emissions']:
            print(f"  Year {em['Year']}: {em['Emission (tons CO2eq)']} tons")

    # Calculate and display total emissions across all systems
    total_emissions_by_year = {yr: model.total_emissions[yr].value for yr in model.years}

    print("\n=== Total System-Wide Emissions ===")
    for yr, total_emission in total_emissions_by_year.items():
        print(f"Year {yr}: {total_emission} tons CO2eq")


if __name__ == "__main__":
    main()
