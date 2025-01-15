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

    # Load material-related data
    data['material_cost'] = pd.read_excel(file_path, sheet_name='material_cost', index_col=0)
    data['material_efficiency'] = pd.read_excel(file_path, sheet_name='material_efficiency', index_col=0)

    # Load financial data
    data['capex'] = pd.read_excel(file_path, sheet_name='capex', index_col=0)
    data['opex'] = pd.read_excel(file_path, sheet_name='opex', index_col=0)
    data['renewal'] = pd.read_excel(file_path, sheet_name='renewal', index_col=0)

    # Import and group Technology-Fuel Pairs
    technology_fuel_pairs_df = pd.read_excel(file_path, sheet_name='technology_fuel_pairs')
    data['technology_fuel_pairs'] = technology_fuel_pairs_df.groupby('technology')['fuel'].apply(list).to_dict()
    data['fuel_max_ratios'] = technology_fuel_pairs_df.set_index(['technology', 'fuel'])['max'].to_dict()

    # Import and group Technology-Material Pairs
    technology_material_pairs_df = pd.read_excel(file_path, sheet_name='technology_material_pairs')
    data['technology_material_pairs'] = technology_material_pairs_df.groupby('technology')['material'].apply(
        list).to_dict()
    data['material_max_ratios'] = technology_material_pairs_df.set_index(['technology', 'material'])['max'].to_dict()

    data['technology_introduction'] = pd.read_excel(file_path, sheet_name='technology', index_col=0)[
        'introduction'].to_dict()

    # Load emission-related data
    data['emission_system'] = pd.read_excel(file_path, sheet_name='emission_system', index_col=0)
    data['fuel_emission'] = pd.read_excel(file_path, sheet_name='fuel_emission', index_col=0)
    data['material_emission'] = pd.read_excel(file_path, sheet_name='material_emission', index_col=0)
    data['technology_ei'] = pd.read_excel(file_path, sheet_name='technology_ei', index_col=0)

    # Load global emission limits (ensure 'global' row exists)
    data['emission'] = pd.read_excel(file_path, sheet_name='emission', index_col=0)

    # Verify 'global' row exists
    if 'global' not in data['emission'].index:
        raise ValueError("The 'emission' sheet must contain a row labeled 'global' with emission limits for each year.")

    return data


def build_unified_model(data):
    """
    Build a unified Pyomo optimization model that includes all furnace systems,
    applying system-wide emission limits.
    """
    model = ConcreteModel()

    # Define sets
    model.systems = Set(initialize=data['baseline'].index.tolist())
    model.technologies = Set(initialize=data['technology'].index.tolist())
    model.fuels = Set(initialize=data['fuel_cost'].index.tolist())
    model.materials = Set(initialize=data['material_cost'].index.tolist())

    # Define years
    all_years = sorted([int(yr) for yr in data['capex'].columns.tolist()])
    initial_year = 2025  # Fixed baseline year
    optimization_years = [yr for yr in all_years]  # Including initial year if needed
    model.years = Set(initialize=optimization_years)

    # Parameters
    # Financial Parameters
    model.capex_param = Param(model.technologies, model.years,
                              initialize=lambda m, tech, yr: data['capex'].loc[tech, yr], default=0.0)
    model.opex_param = Param(model.technologies, model.years, initialize=lambda m, tech, yr: data['opex'].loc[tech, yr],
                             default=0.0)
    model.renewal_param = Param(model.technologies, model.years,
                                initialize=lambda m, tech, yr: data['renewal'].loc[tech, yr], default=0.0)

    # Fuel Parameters
    model.fuel_cost_param = Param(model.fuels, model.years, initialize=lambda m, f, yr: data['fuel_cost'].loc[f, yr],
                                  default=0.0)
    model.fuel_eff_param = Param(model.fuels, model.years,
                                 initialize=lambda m, f, yr: data['fuel_efficiency'].loc[f, yr], default=0.0)

    # Material Parameters
    model.material_cost_param = Param(model.materials, model.years,
                                      initialize=lambda m, mat, yr: data['material_cost'].loc[mat, yr], default=0.0)
    model.material_eff_param = Param(model.materials, model.years,
                                     initialize=lambda m, mat, yr: data['material_efficiency'].loc[mat, yr],
                                     default=0.0)

    # Emission Parameters
    model.fuel_emission = Param(model.fuels, model.years, initialize=lambda m, f, yr: data['fuel_emission'].loc[f, yr],
                                default=0.0)
    model.material_emission = Param(model.materials, model.years,
                                    initialize=lambda m, mat, yr: data['material_emission'].loc[mat, yr], default=0.0)
    model.technology_ei = Param(model.technologies, model.years,
                                initialize=lambda m, tech, yr: data['technology_ei'].loc[tech, yr], default=1.0)

    # Global Emission Limits
    model.emission_limit = Param(
        model.years,
        initialize=lambda m, yr: data['emission'].loc['global', yr],
        default=1e9
    )

    # Technology-Fuel and Technology-Material Pairs
    model.fuel_max_ratio = Param(
        model.technologies, model.fuels,
        initialize=lambda m, tech, f: data['fuel_max_ratios'].get((tech, f), 0),
        default=0.0
    )
    model.material_max_ratio = Param(
        model.technologies, model.materials,
        initialize=lambda m, tech, mat: data['material_max_ratios'].get((tech, mat), 0),
        default=0.0
    )

    # Technology Introduction Years and Lifespans
    model.technology_introduction = Param(
        model.technologies,
        initialize=lambda m, tech: data['technology_introduction'][tech],
        default=initial_year
    )
    model.lifespan_param = Param(
        model.technologies,
        initialize=lambda m, tech: data['technology'].loc[tech, 'lifespan'],
        default=0
    )

    # Decision Variables
    model.fuel_select = Var(model.systems, model.fuels, model.years, domain=Binary)
    model.material_select = Var(model.systems, model.materials, model.years, domain=Binary)
    model.continue_technology = Var(model.systems, model.technologies, model.years, domain=Binary)
    model.replace = Var(model.systems, model.technologies, model.years, domain=Binary)
    model.renew = Var(model.systems, model.technologies, model.years, domain=Binary)
    model.fuel_consumption = Var(model.systems, model.fuels, model.years, domain=NonNegativeReals)
    model.material_consumption = Var(model.systems, model.materials, model.years, domain=NonNegativeReals)
    model.active_technology = Var(model.systems, model.technologies, model.years, domain=Binary)

    # Emission Variables
    model.emission_by_tech = Var(model.systems, model.technologies, model.years, domain=NonNegativeReals)

    # Production Parameters (assuming constant production per system)
    model.production = Param(
        model.systems,
        initialize=lambda m, s: data['baseline'].loc[s, 'production'],
        default=1.0
    )

    # Constraints

    # Emission Calculations per Technology and System
    def emission_by_tech_rule(m, system, tech, yr):
        return m.emission_by_tech[system, tech, yr] == (
                m.technology_ei[tech, yr] * (
                sum(m.fuel_emission[f, yr] * m.fuel_consumption[system, f, yr] for f in m.fuels) +
                sum(m.material_emission[mat, yr] * m.material_consumption[system, mat, yr] for mat in m.materials)
        )
        )

    model.emission_by_tech_constraint = Constraint(model.systems, model.technologies, model.years,
                                                   rule=emission_by_tech_rule)

    # Global Emission Limit per Year
    def total_global_emission_limit_rule(m, yr):
        return sum(
            m.emission_by_tech[system, tech, yr]
            for system in m.systems
            for tech in m.technologies
        ) <= m.emission_limit[yr]

    model.total_global_emission_limit_constraint = Constraint(model.years, rule=total_global_emission_limit_rule)

    # Technology Continuation and Replacement Constraints per System
    def first_year_constraint_rule(m, system, tech, yr):
        if yr == min(m.years):
            baseline_tech = data['baseline'].loc[system, 'technology']
            if tech == baseline_tech:
                return m.continue_technology[system, tech, yr] == 1
            else:
                return m.continue_technology[system, tech, yr] + m.replace[system, tech, yr] + m.renew[
                    system, tech, yr] == 0
        return Constraint.Skip

    model.first_year_constraint = Constraint(model.systems, model.technologies, model.years,
                                             rule=first_year_constraint_rule)

    def enforce_continuation_before_lifespan_rule(m, system, tech, yr):
        introduction_year = m.technology_introduction[tech]
        lifespan = m.lifespan_param[tech]
        end_of_lifespan = introduction_year + lifespan

        if introduction_year < yr < end_of_lifespan:
            baseline_tech = data['baseline'].loc[system, 'technology']
            if tech == baseline_tech:
                return m.continue_technology[system, tech, yr] == 1
            else:
                return m.continue_technology[system, tech, yr] + m.replace[system, tech, yr] + m.renew[
                    system, tech, yr] == 0
        return Constraint.Skip

    model.enforce_continuation_before_lifespan_constraint = Constraint(
        model.systems, model.technologies, model.years, rule=enforce_continuation_before_lifespan_rule
    )

    def continuity_active_rule(m, system, tech, yr):
        if yr > min(m.years):
            previous_year = yr - 1
            return m.continue_technology[system, tech, yr] <= m.active_technology[system, tech, previous_year]
        return Constraint.Skip

    model.continuity_active_constraint = Constraint(
        model.systems, model.technologies, model.years, rule=continuity_active_rule
    )

    def enforce_exclusivity_rule(m, system, tech, yr):
        return m.replace[system, tech, yr] + m.renew[system, tech, yr] + m.continue_technology[system, tech, yr] <= 1

    model.enforce_exclusivity = Constraint(model.systems, model.technologies, model.years,
                                           rule=enforce_exclusivity_rule)

    def active_technology_rule(m, system, tech, yr):
        lifespan = m.lifespan_param[tech]
        introduction_year = m.technology_introduction[tech]
        end_of_lifespan = introduction_year + lifespan

        if (yr - introduction_year) % lifespan == 0 and (yr - introduction_year) >= lifespan:
            return m.active_technology[system, tech, yr] == m.replace[system, tech, yr] + m.renew[system, tech, yr]
        elif yr > introduction_year:
            return m.active_technology[system, tech, yr] == m.continue_technology[system, tech, yr]
        return Constraint.Skip

    model.active_technology_constraint = Constraint(
        model.systems, model.technologies, model.years, rule=active_technology_rule
    )

    def same_technology_renewal_rule(m, system, tech, yr):
        if yr > min(m.years):
            return m.replace[system, tech, yr] <= 1 - m.active_technology[system, tech, yr - 1]
        return Constraint.Skip

    model.same_technology_renewal_constraint = Constraint(
        model.systems, model.technologies, model.years, rule=same_technology_renewal_rule
    )

    def introduction_year_constraint_rule(m, system, tech, yr):
        introduction_year = m.technology_introduction[tech]
        if yr < introduction_year:
            return m.replace[system, tech, yr] == 0
        return Constraint.Skip

    model.introduction_year_constraint = Constraint(
        model.systems, model.technologies, model.years, rule=introduction_year_constraint_rule
    )

    # Production Constraints per System and Year
    def production_constraint_rule(m, system, yr):
        return m.production[system] == sum(
            m.fuel_consumption[system, f, yr] / m.fuel_eff_param[f, yr] for f in m.fuels
        )

    model.production_constraint = Constraint(model.systems, model.years, rule=production_constraint_rule)

    # Fuel Constraints
    def fuel_selection_rule(m, system, yr):
        return sum(m.fuel_select[system, f, yr] for f in m.fuels) <= 3

    model.fuel_selection_constraint = Constraint(model.systems, model.years, rule=fuel_selection_rule)

    def fuel_consumption_limit_rule(m, system, f, yr):
        return m.fuel_consumption[system, f, yr] <= m.fuel_select[system, f, yr] * m.fuel_eff_param[f, yr] * \
            m.production[system]

    model.fuel_consumption_limit_constraint = Constraint(
        model.systems, model.fuels, model.years, rule=fuel_consumption_limit_rule
    )

    def fuel_technology_link_rule(m, system, f, yr):
        compatible_technologies = [
            tech for tech in m.technologies if f in data['technology_fuel_pairs'].get(tech, [])
        ]
        return sum(
            m.active_technology[system, tech, yr] for tech in compatible_technologies
        ) >= m.fuel_select[system, f, yr]

    model.fuel_technology_link_constraint = Constraint(
        model.systems, model.fuels, model.years, rule=fuel_technology_link_rule
    )

    # Material Constraints
    def material_selection_rule(m, system, yr):
        return sum(m.material_select[system, mat, yr] for mat in m.materials) <= 3

    model.material_selection_constraint = Constraint(model.systems, model.years, rule=material_selection_rule)

    def material_consumption_limit_rule(m, system, mat, yr):
        return m.material_consumption[system, mat, yr] <= m.material_select[system, mat, yr] * m.material_eff_param[
            mat, yr] * m.production[system]

    model.material_consumption_limit_constraint = Constraint(
        model.systems, model.materials, model.years, rule=material_consumption_limit_rule
    )

    def material_technology_link_rule(m, system, mat, yr):
        compatible_technologies = [
            tech for tech in m.technologies if mat in data['technology_material_pairs'].get(tech, [])
        ]
        return sum(
            m.active_technology[system, tech, yr] for tech in compatible_technologies
        ) >= m.material_select[system, mat, yr]

    model.material_technology_link_constraint = Constraint(
        model.systems, model.materials, model.years, rule=material_technology_link_rule
    )

    model.incompatible_fuel_technology_constraints = ConstraintList()

    for T in model.technologies:
        # Identify incompatible fuels for technology T
        compatible_fuels = set(data['technology_fuel_pairs'].get(T, []))
        incompatible_fuels = set(model.fuels) - compatible_fuels

        for F in incompatible_fuels:
            for S in model.systems:
                for Y in model.years:
                    # Add constraint: fuel_select + active_technology <=1
                    model.incompatible_fuel_technology_constraints.add(
                        model.fuel_select[S, F, Y] + model.active_technology[S, T, Y] <= 1
                    )

    # Objective Function: Minimize Total Cost Across All Systems and Years
    def total_cost_rule(m):
        return sum(
            sum(
                m.capex_param[tech, yr] * m.production[system] * m.active_technology[system, tech, yr]
                + m.opex_param[tech, yr] * m.production[system] * m.active_technology[system, tech, yr]
                + m.renewal_param[tech, yr] * m.production[system] * m.renew[system, tech, yr]
                + sum(
                    m.fuel_cost_param[f, yr] * m.production[system] * m.fuel_select[system, f, yr]
                    for f in m.fuels
                )
                + sum(
                    m.material_cost_param[mat, yr] * m.production[system] * m.material_select[system, mat, yr]
                    for mat in m.materials
                )
                for tech in m.technologies
            )
            for system in m.systems
            for yr in m.years
        )

    model.objective = Objective(rule=total_cost_rule, sense=minimize)

    return model


def extract_results(model, data):
    """
    Extract results from the unified model.
    """
    results_dict = {}
    for system in model.systems:
        production_value = data['baseline'].loc[system, 'production']

        # Extract fuel consumption
        fuel_data = [
            {
                "Year": yr,
                "Fuel": f,
                "Consumption (tons)": model.fuel_consumption[system, f, yr].value
            }
            for yr in model.years
            for f in model.fuels
            if model.fuel_select[system, f, yr].value > 0.5
        ]

        # Extract material consumption
        material_data = [
            {
                "Year": yr,
                "Material": mat,
                "Consumption (tons)": model.material_consumption[system, mat, yr].value,
                "Share": model.material_consumption[system, mat, yr].value / production_value
            }
            for yr in model.years
            for mat in model.materials
            if model.material_consumption[system, mat, yr].value > 0
        ]

        # Extract technology changes
        technology_changes = [
            {
                "Year": yr,
                "Technology": next(
                    (tech for tech in model.technologies if model.active_technology[system, tech, yr].value > 0.5),
                    "None"
                ),
                "Status": (
                    "replace" if any(model.replace[system, tech, yr].value > 0.5 for tech in model.technologies) else
                    "renew" if any(model.renew[system, tech, yr].value > 0.5 for tech in model.technologies) else
                    "continue" if any(
                        model.continue_technology[system, tech, yr].value > 0.5 for tech in model.technologies) else
                    "inactive"
                )
            }
            for yr in model.years
        ]

        # Extract Emissions per System
        emissions_results = [
            {
                "Year": yr,
                "Total Emissions": sum(
                    model.emission_by_tech[system, tech, yr].value
                    for tech in model.technologies
                    if model.emission_by_tech[system, tech, yr].value is not None
                ),
                "Emission Limit": data['emission'].loc['global', yr]
            }
            for yr in model.years
        ]

        # Store results
        results_dict[system] = {
            "Production": production_value,
            "Fuel Consumption": fuel_data,
            "Material Consumption": material_data,
            "Technology Changes": technology_changes,
            "Emissions": emissions_results
        }

    # Display global emissions
    print("\n=== Global Emissions ===")
    for yr in model.years:
        total_emission = sum(
            model.emission_by_tech[system, tech, yr].value
            for system in model.systems
            for tech in model.technologies
            if model.emission_by_tech[system, tech, yr].value is not None
        )
        emission_limit = data['emission'].loc['global', yr]
        print(f"Year {yr}: Total Emissions = {total_emission} <= Limit: {emission_limit}")

    return results_dict


def main():
    # Load data
    file_path = 'database/steel_data.xlsx'
    data = load_data(file_path)
    solver = SolverFactory('glpk')

    # Build unified model
    model = build_unified_model(data)

    # Solve the model
    result = solver.solve(model, tee=True)

    # Check solver status
    if result.solver.status == 'ok' and result.solver.termination_condition == 'optimal':
        # Extract and store results
        results_dict = extract_results(model, data)

        # Display results for each system
        for system_name, results in results_dict.items():
            print(f"\n=== Results for {system_name} ===")
            print(f"Production: {results['Production']} tons")

            print("\nFuel Consumption:")
            for fc in results['Fuel Consumption']:
                print(f"  Year {fc['Year']}: {fc['Fuel']} - {fc['Consumption (tons)']} energy unit")

            print("\nMaterial Consumption:")
            for mc in results['Material Consumption']:
                print(
                    f"  Year {mc['Year']}: {mc['Material']} - {mc['Consumption (tons)']} tons, Share: {mc['Share']:.2%}")

            print("\nTechnology Changes:")
            for tc in results['Technology Changes']:
                print(f"  Year {tc['Year']}: {tc['Technology']} ({tc['Status']})")

            print("\nEmissions:")
            for emission in results['Emissions']:
                print(
                    f"  Year {emission['Year']}: {emission['Total Emissions']} <= Limit: {emission['Emission Limit']}")
    else:
        print(f"Solver failed. Status: {result.solver.status}, Condition: {result.solver.termination_condition}")


if __name__ == "__main__":
    main()
