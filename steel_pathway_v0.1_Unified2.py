import pandas as pd
from pyomo.environ import (
    ConcreteModel, Var, NonNegativeReals, Binary, Param,
    Objective, Constraint, SolverFactory, Set, minimize, value as pyomo_value
)
from pyomo.util.infeasible import log_infeasible_constraints


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
    Build the unified Pyomo model.
    """

    model = ConcreteModel()

    # --------------------------
    # 1. Define Sets
    # --------------------------
    model.systems = Set(initialize=data['baseline'].index.tolist())
    model.technologies = Set(initialize=data['technology'].index.tolist())
    model.fuels = Set(initialize=data['fuel_cost'].index.tolist())
    model.materials = Set(initialize=data['material_cost'].index.tolist())
    model.years = Set(initialize=sorted([int(yr) for yr in data['capex'].columns.tolist()]))

    # --------------------------
    # 2. Define Parameters
    # --------------------------
    # CAPEX, OPEX, Renewal
    model.capex_param = Param(model.technologies, model.years,
                              initialize=lambda m, tech, yr: data['capex'].loc[tech, yr],
                              default=0.0)
    model.opex_param = Param(model.technologies, model.years,
                             initialize=lambda m, tech, yr: data['opex'].loc[tech, yr],
                             default=0.0)
    model.renewal_param = Param(model.technologies, model.years,
                                initialize=lambda m, tech, yr: data['renewal'].loc[tech, yr],
                                default=0.0)

    # Fuel and Material Costs and Efficiencies
    model.fuel_cost_param = Param(model.fuels, model.years,
                                  initialize=lambda m, f, yr: data['fuel_cost'].loc[f, yr],
                                  default=0.0)
    model.fuel_eff_param = Param(model.fuels, model.years,
                                 initialize=lambda m, f, yr: data['fuel_efficiency'].loc[f, yr],
                                 default=0.0)
    model.fuel_emission = Param(model.fuels, model.years,
                                initialize=lambda m, f, yr: data['fuel_emission'].loc[f, yr],
                                default=0.0)

    model.material_cost_param = Param(model.materials, model.years,
                                      initialize=lambda m, mat, yr: data['material_cost'].loc[mat, yr],
                                      default=0.0)
    model.material_eff_param = Param(model.materials, model.years,
                                     initialize=lambda m, mat, yr: data['material_efficiency'].loc[mat, yr],
                                     default=0.0)
    model.material_emission = Param(model.materials, model.years,
                                    initialize=lambda m, mat, yr: data['material_emission'].loc[mat, yr],
                                    default=0.0)

    # Lifespan and Introduction Year
    production = data['baseline']['production'].to_dict()
    model.production_param = Param(model.systems,
                                   initialize=lambda m, sys: production[sys],
                                   default = 0)

    introduced_year_data = data['baseline']['introduced_year'].to_dict()
    model.lifespan_param = Param(model.technologies,
                                 initialize=lambda m, tech: data['technology'].loc[tech, 'lifespan'],
                                 default=0)
    model.introduced_year_param = Param(model.systems,
                                        initialize=lambda m, sys: introduced_year_data.get(sys, 0),
                                        default=0)

    # Emission Parameters
    model.technology_ei = Param(model.technologies, model.years,
                                initialize=lambda m, tech, yr: data['technology_ei'].loc[tech, yr],
                                default=1.0)
    model.emission_limit = Param(model.years,
                                 initialize=lambda m, yr: data['emission'].loc['global', yr],
                                 default=0)

    # Technology Introduction
    model.technology_introduction = Param(model.technologies,
                                          initialize=lambda m, tech: data['technology'].loc[tech, 'introduction'],
                                          default=0)

    # Baseline Technology and Fuel
    model.baseline_technology = Param(
        model.systems,
        initialize=lambda m, sys: data['baseline'].loc[sys, 'technology'],
        within=model.technologies
    )

    model.baseline_fuel = Param(
        model.systems,
        initialize=lambda m, sys: data['baseline'].loc[sys, 'fuel'],
        within=model.fuels
    )

    # --------------------------
    # 3. Define Decision Variables
    # --------------------------
    # Binary Variables
    model.replace = Var(model.systems, model.technologies, model.years, domain=Binary, initialize=0)
    model.renew = Var(model.systems, model.technologies, model.years, domain=Binary, initialize=0)
    model.active_technology = Var(model.systems, model.technologies, model.years, domain=Binary, initialize=0)
    model.continue_technology = Var(model.systems, model.technologies, model.years, domain=Binary, initialize=0)
    model.fuel_select = Var(model.systems, model.fuels, model.years, domain=Binary, initialize=0)
    model.material_select = Var(model.systems, model.materials, model.years, domain=Binary, initialize=0)

    # Continuous Variables
    model.production = Var(model.systems, model.years, domain=NonNegativeReals, initialize=0)
    model.fuel_consumption = Var(model.systems, model.fuels, model.years, domain=NonNegativeReals, initialize=0)
    model.material_consumption = Var(model.systems, model.materials, model.years, domain=NonNegativeReals, initialize=0)
    model.emission_by_tech = Var(model.systems, model.technologies, model.years, domain=NonNegativeReals, initialize=0)

    # Auxiliary Variables for Linearization
    model.prod_active = Var(model.systems, model.technologies, model.years, domain=NonNegativeReals, initialize=0)
    model.replace_prod_active = Var(model.systems, model.technologies, model.years, domain=NonNegativeReals, initialize=0)
    model.renew_prod_active = Var(model.systems, model.technologies, model.years, domain=NonNegativeReals, initialize=0)

    # Activation Change Variable
    model.activation_change = Var(
        model.systems, model.technologies, model.years,
        domain=Binary,
        initialize=0
    )

    # --------------------------
    # 4. Define Constraints
    # --------------------------

    # 4.1. Emission Constraints
    def emission_by_tech_rule(m, sys, tech, yr):
        return m.emission_by_tech[sys, tech, yr] == (
            m.technology_ei[tech, yr] * (
                sum(m.fuel_emission[f, yr] * m.fuel_consumption[sys, f, yr] for f in m.fuels) +
                sum(m.material_emission[mat, yr] * m.material_consumption[sys, mat, yr] for mat in m.materials)
            )
        )

    model.emission_by_tech_constraint = Constraint(model.systems, model.technologies, model.years,
                                                   rule=emission_by_tech_rule)

    def total_emission_limit_rule(m, yr):
        return sum(
            m.emission_by_tech[sys, tech, yr] for sys in m.systems for tech in m.technologies
        ) <= m.emission_limit[yr]

    model.total_emission_limit_constraint = Constraint(model.years, rule=total_emission_limit_rule)

    # 4.2. First Year Constraints
    # Ensure baseline technology is active and continued in the first year
    def baseline_technology_first_year_rule(m, sys, tech, yr):
        if yr == min(m.years) and tech == m.baseline_technology[sys]:
            return m.continue_technology[sys, tech, yr] == 1
        return Constraint.Skip

    model.baseline_technology_first_year_constraint = Constraint(
        model.systems, model.technologies, model.years, rule=baseline_technology_first_year_rule
    )

    def baseline_technology_first_year_rule2(m, sys, tech, yr):
        if yr == min(m.years) and tech == m.baseline_technology[sys]:
            return m.renew[sys, tech, yr] + m.replace[sys, tech, yr] == 0
        return Constraint.Skip

    model.baseline_technology_first_year_constraint2 = Constraint(
        model.systems, model.technologies, model.years, rule=baseline_technology_first_year_rule2
    )

    # Ensure all non-baseline technologies are inactive in the first year
    def non_baseline_technologies_first_year_rule(m, sys, tech, yr):
        if yr == min(m.years) and tech != m.baseline_technology[sys]:
            return (
                m.continue_technology[sys, tech, yr] +
                m.replace[sys, tech, yr] +
                m.renew[sys, tech, yr] +
                m.active_technology[sys, tech, yr]
            ) == 0
        return Constraint.Skip

    model.non_baseline_technologies_first_year_constraint = Constraint(
        model.systems, model.technologies, model.years, rule=non_baseline_technologies_first_year_rule
    )

    # Lock the fuel selection for the initial year
    def hard_baseline_fuel_rule(m, sys, f, yr):
        if yr == min(m.years):  # Lock the fuel selection for the initial year
            baseline_fuel = m.baseline_fuel[sys]
            if f == baseline_fuel:
                return m.fuel_select[sys, f, yr] == 1  # Must use the baseline fuel
            else:
                return m.fuel_select[sys, f, yr] == 0  # Other fuels cannot be selected
        return Constraint.Skip

    model.hard_baseline_fuel_constraint = Constraint(
        model.systems, model.fuels, model.years, rule=hard_baseline_fuel_rule
    )

    # 4.3. Renewal Constraints
    def define_activation_change_rule(m, sys, tech, yr):
        if yr > min(m.years):
            # activation_change = 1 if tech becomes active in yr from inactive in yr-1
            return m.activation_change[sys, tech, yr] >= m.active_technology[sys, tech, yr] - m.active_technology[sys, tech, yr - 1]
        return Constraint.Skip

    model.define_activation_change_constraint = Constraint(
        model.systems, model.technologies, model.years, rule=define_activation_change_rule
    )

    def enforce_replace_on_activation_rule(m, sys, tech, yr):
        if yr > min(m.years):
            # If a technology becomes active, replace must be 1
            return m.replace[sys, tech, yr] >= m.activation_change[sys, tech, yr]
        return Constraint.Skip

    model.enforce_replace_on_activation_constraint = Constraint(
        model.systems, model.technologies, model.years, rule=enforce_replace_on_activation_rule
    )

    def enforce_replacement_or_renewal_years_rule(m, sys, tech, yr):
        introduced_year = m.introduced_year_param[sys]
        lifespan = m.lifespan_param[tech]
        if yr > introduced_year and (yr - introduced_year) % lifespan != 0:
            return m.replace[sys, tech, yr] + m.renew[sys, tech, yr] == 0
        return Constraint.Skip

    model.enforce_replacement_or_renewal_years_constraint = Constraint(
        model.systems, model.technologies, model.years, rule=enforce_replacement_or_renewal_years_rule
    )

    def enforce_no_continuation_in_replacement_years_rule(m, sys, tech, yr):
        introduced_year = m.introduced_year_param[sys]
        lifespan = m.lifespan_param[tech]
        if yr > introduced_year and (yr - introduced_year) % lifespan == 0:
            return m.continue_technology[sys, tech, yr] == 0
        return Constraint.Skip

    model.enforce_no_continuation_in_replacement_years_constraint = Constraint(
        model.systems, model.technologies, model.years, rule=enforce_no_continuation_in_replacement_years_rule
    )

    # 4.4. Exclusivity Constraints
    def exclusivity_rule(m, sys, tech, yr):
        # Only one of continue, replace, or renew can be 1
        return m.continue_technology[sys, tech, yr] + m.replace[sys, tech, yr] + m.renew[sys, tech, yr] <= 1

    model.exclusivity_rule = Constraint(model.systems, model.technologies, model.years, rule=exclusivity_rule)

    def active_technology_rule(m, sys, tech, yr):
        # A technology is active if it is continued, replaced, or renewed
        return m.active_technology[sys, tech, yr] == (
                m.continue_technology[sys, tech, yr] + m.replace[sys, tech, yr] + m.renew[sys, tech, yr]
        )

    model.active_technology_constraint = Constraint(model.systems, model.technologies, model.years,
                                                    rule=active_technology_rule)

    def single_active_technology_rule(m, sys, yr):
        # Ensure only one technology is active in a given year per system
        return sum(m.active_technology[sys, tech, yr] for tech in m.technologies) == 1

    model.single_active_technology_constraint = Constraint(
        model.systems, model.years, rule=single_active_technology_rule
    )

    def introduction_year_constraint_rule(m, sys, tech, yr):
        introduction_year = m.technology_introduction[tech]
        if yr < introduction_year:
            return m.replace[sys, tech, yr] + m.continue_technology[sys, tech, yr] + m.renew[sys, tech, yr] == 0
        return Constraint.Skip

    model.introduction_year_constraint = Constraint(
        model.systems, model.technologies, model.years, rule=introduction_year_constraint_rule
    )

    # Example: Minimum production per system per year
    def minimum_production_rule(m, sys, yr):
        return m.production[sys, yr] >= m.production_param[sys]

    model.minimum_production_constraint = Constraint(model.systems, model.years, rule=minimum_production_rule)

    # 4.5. Fuel Constraints
    def fuel_production_constraint_rule(m, sys, yr):
        return m.production[sys, yr] == sum(
            m.fuel_consumption[sys, fuel, yr] / m.fuel_eff_param[fuel, yr] for fuel in m.fuels
        )

    model.fuel_production_constraint = Constraint(model.systems, model.years, rule=fuel_production_constraint_rule)

    def fuel_selection_rule(m, sys, yr):
        return sum(m.fuel_select[sys, fuel, yr] for fuel in m.fuels) == 1

    model.fuel_selection_constraint = Constraint(model.systems, model.years, rule=fuel_selection_rule)

    # Fuel-Technology Link Constraint
    def fuel_technology_link_rule(m, sys, yr, f):
        compatible_technologies = [
            tech for tech in m.technologies if f in data['technology_fuel_pairs'].get(tech, [])
        ]
        return sum(
            m.active_technology[sys, tech, yr] for tech in compatible_technologies
        ) >= m.fuel_select[sys, f, yr]

    model.fuel_technology_link_constraint = Constraint(
        model.systems, model.years, model.fuels, rule=fuel_technology_link_rule
    )

    # 4.6. Material Constraints
    # 4.6.1. Material Consumption Limit Constraints (Linearized with Big-M)
    # Define maximum possible material consumption based on production and efficiency
    # max_material_efficiency = max(data['material_efficiency'].max().max(), 1)  # Ensure at least 1 to prevent M=0
    # M_material = max_material_efficiency * max_production

    # 4.6. Material Constraints

    # 4.6.0. Material Production Constraint
    def material_production_constraint_rule(m, sys, yr):
        return m.production[sys, yr] == sum(
            m.material_consumption[sys, mat, yr] / m.material_eff_param[mat, yr] for mat in m.materials
        )

    model.material_production_constraint = Constraint(model.systems, model.years,
                                                      rule=material_production_constraint_rule)

    # 4.5. Fuel Constraints
    def material_production_constraint_rule(m, sys, yr):
        return m.production[sys, yr] == sum(
            m.material_consumption[sys, mat, yr] / m.material_eff_param[mat, yr] for mat in m.materials
        )

    model.material_production_constraint = Constraint(model.systems, model.years, rule=material_production_constraint_rule)

    def material_selection_rule(m, sys, yr):
        return sum(m.material_select[sys, mat, yr] for mat in m.materials) == 1

    model.material_selection_constraint = Constraint(model.systems, model.years, rule=material_selection_rule)

    # Material-Technology Link Constraint
    def material_technology_link_rule(m, sys, yr, mat):
        compatible_technologies = [
            tech for tech in m.technologies if mat in data['technology_material_pairs'].get(tech, [])
        ]
        return sum(
            m.active_technology[sys, tech, yr] for tech in compatible_technologies
        ) >= m.material_select[sys, mat, yr]

    model.material_technology_link_constraint = Constraint(
        model.systems, model.years, model.materials, rule=material_technology_link_rule
    )

    # 4.7. Linearization of Auxiliary Product Terms (prod_active, replace_prod_active, renew_prod_active)
    # Since active_technology, replace, renew are binary and production is continuous, linearize with Big-M

    M_fuel = max(model.production_param.values()) * max(model.fuel_eff_param.values())

    # 4.7.1. prod_active = production * active_technology
    def prod_active_limit_rule(m, sys, tech, yr):
        return m.prod_active[sys, tech, yr] <= m.production[sys, yr]

    model.prod_active_limit_constraint = Constraint(
        model.systems, model.technologies, model.years,
        rule=prod_active_limit_rule
    )

    def prod_active_binary_rule(m, sys, tech, yr):
        return m.prod_active[sys, tech, yr] <= m.active_technology[sys, tech, yr] * M_fuel

    model.prod_active_binary_constraint = Constraint(
        model.systems, model.technologies, model.years,
        rule=prod_active_binary_rule
    )

    def prod_active_lower_rule(m, sys, tech, yr):
        return m.prod_active[sys, tech, yr] >= m.production[sys, yr] - M_fuel * (1 - m.active_technology[sys, tech, yr])

    model.prod_active_lower_constraint = Constraint(
        model.systems, model.technologies, model.years,
        rule=prod_active_lower_rule
    )

    # 4.7.2. replace_prod_active = replace * production
    def replace_prod_active_limit_rule(m, sys, tech, yr):
        return m.replace_prod_active[sys, tech, yr] <= m.production[sys, yr]

    model.replace_prod_active_limit_constraint = Constraint(
        model.systems, model.technologies, model.years,
        rule=replace_prod_active_limit_rule
    )

    def replace_prod_active_binary_rule(m, sys, tech, yr):
        return m.replace_prod_active[sys, tech, yr] <= m.replace[sys, tech, yr] * M_fuel

    model.replace_prod_active_binary_constraint = Constraint(
        model.systems, model.technologies, model.years,
        rule=replace_prod_active_binary_rule
    )

    def replace_prod_active_lower_rule(m, sys, tech, yr):
        return m.replace_prod_active[sys, tech, yr] >= m.production[sys, yr] - M_fuel * (1 - m.replace[sys, tech, yr])

    model.replace_prod_active_lower_constraint = Constraint(
        model.systems, model.technologies, model.years,
        rule=replace_prod_active_lower_rule
    )

    # 4.7.3. renew_prod_active = renew * production
    def renew_prod_active_limit_rule(m, sys, tech, yr):
        return m.renew_prod_active[sys, tech, yr] <= m.production[sys, yr]

    model.renew_prod_active_limit_constraint = Constraint(
        model.systems, model.technologies, model.years,
        rule=renew_prod_active_limit_rule
    )

    def renew_prod_active_binary_rule(m, sys, tech, yr):
        return m.renew_prod_active[sys, tech, yr] <= m.renew[sys, tech, yr] * M_fuel

    model.renew_prod_active_binary_constraint = Constraint(
        model.systems, model.technologies, model.years,
        rule=renew_prod_active_binary_rule
    )

    def renew_prod_active_lower_rule(m, sys, tech, yr):
        return m.renew_prod_active[sys, tech, yr] >= m.production[sys, yr] - M_fuel * (1 - m.renew[sys, tech, yr])

    model.renew_prod_active_lower_constraint = Constraint(
        model.systems, model.technologies, model.years,
        rule=renew_prod_active_lower_rule
    )

    # --------------------------
    # 5. Define Objective Function
    # --------------------------
    def total_cost_rule(m):
        return sum(
            sum(
                # Use auxiliary variables for linearity
                (m.capex_param[tech, yr] * m.replace_prod_active[sys, tech, yr] +
                 m.renewal_param[tech, yr] * m.renew_prod_active[sys, tech, yr] +
                 m.opex_param[tech, yr] * m.prod_active[sys, tech, yr])
                for tech in m.technologies
            ) +
            # Linear fuel and material costs
            sum(m.fuel_cost_param[fuel, yr] * m.fuel_consumption[sys, fuel, yr] for fuel in m.fuels) +
            sum(m.material_cost_param[mat, yr] * m.material_consumption[sys, mat, yr] for mat in m.materials)
            for sys in m.systems for yr in m.years
        )

    model.total_cost = Objective(rule=total_cost_rule, sense=minimize)


    return model


def display_selected_technologies(model):
    print("\n=== Selected Technologies per System per Year ===\n")
    for sys in model.systems:
        for yr in model.years:
            selected_techs = []
            for tech in model.technologies:
                if pyomo_value(model.active_technology[sys, tech, yr]) > 0.5:
                    selected_techs.append(tech)
            techs_str = ', '.join(selected_techs) if selected_techs else 'None'
            print(f"System: {sys}, Year: {yr}, Technology: {techs_str}")


def display_selected_fuels(model):
    print("\n=== Selected Fuels per System per Year ===\n")
    for sys in model.systems:
        for yr in model.years:
            selected_fuels = []
            for fuel in model.fuels:
                if pyomo_value(model.fuel_select[sys, fuel, yr]) > 0.5:
                    selected_fuels.append(fuel)
            fuels_str = ', '.join(selected_fuels) if selected_fuels else 'None'
            print(f"System: {sys}, Year: {yr}, Fuel: {fuels_str}")


def display_selected_materials(model):
    print("\n=== Selected Materials per System per Year ===\n")
    for sys in model.systems:
        for yr in model.years:
            selected_mats = []
            for mat in model.materials:
                if pyomo_value(model.material_select[sys, mat, yr]) > 0.5:
                    selected_mats.append(mat)
            mats_str = ', '.join(selected_mats) if selected_mats else 'None'
            print(f"System: {sys}, Year: {yr}, Material: {mats_str}")


def display_production_levels(model):
    print("\n=== Production Levels per System per Year ===\n")
    for sys in model.systems:
        for yr in model.years:
            production = pyomo_value(model.production[sys, yr])
            print(f"System: {sys}, Year: {yr}, Production: {production}")


def display_total_cost(model):
    total_cost = pyomo_value(model.total_cost)
    print(f"\n=== Total Cost of the Solution: {total_cost} ===\n")


def export_results_to_excel(model):
    with pd.ExcelWriter('model_results.xlsx') as writer:
        # Selected Technologies
        records = []
        for sys in model.systems:
            for yr in model.years:
                for tech in model.technologies:
                    if pyomo_value(model.active_technology[sys, tech, yr]) > 0.5:
                        records.append({'System': sys, 'Year': yr, 'Technology': tech})
        df_tech = pd.DataFrame(records)
        df_tech.to_excel(writer, sheet_name='Selected Technologies', index=False)

        # Selected Fuels
        records = []
        for sys in model.systems:
            for yr in model.years:
                for fuel in model.fuels:
                    if pyomo_value(model.fuel_select[sys, fuel, yr]) > 0.5:
                        records.append({'System': sys, 'Year': yr, 'Fuel': fuel})
        df_fuel = pd.DataFrame(records)
        df_fuel.to_excel(writer, sheet_name='Selected Fuels', index=False)

        # Selected Materials
        records = []
        for sys in model.systems:
            for yr in model.years:
                for mat in model.materials:
                    if pyomo_value(model.material_select[sys, mat, yr]) > 0.5:
                        records.append({'System': sys, 'Year': yr, 'Material': mat})
        df_mat = pd.DataFrame(records)
        df_mat.to_excel(writer, sheet_name='Selected Materials', index=False)

        # Production Levels
        records = []
        for sys in model.systems:
            for yr in model.years:
                production = pyomo_value(model.production[sys, yr])
                records.append({'System': sys, 'Year': yr, 'Production': production})
        df_prod = pd.DataFrame(records)
        df_prod.to_excel(writer, sheet_name='Production Levels', index=False)

        # Total Cost
        total_cost = pyomo_value(model.total_cost)
        df_cost = pd.DataFrame([{'Total Cost': total_cost}])
        df_cost.to_excel(writer, sheet_name='Total Cost', index=False)

    print("\n=== Results have been exported to 'model_results.xlsx' ===\n")


def main():
    # --------------------------
    # 7. Load Data
    # --------------------------
    file_path = 'database/steel_data.xlsx'  # Update with your actual file path
    data = load_data(file_path)

    # --------------------------
    # 8. Build the Unified Model
    # --------------------------
    model = build_unified_model(data)

    # --------------------------
    # 9. Solve the Model
    # --------------------------
    solver = SolverFactory('glpk')  # Ensure GLPK is installed
    if not solver.available():
        raise RuntimeError("GLPK solver is not available. Please install it or choose another solver.")

    result = solver.solve(model, tee=True)

    # --------------------------
    # 10. Check Solver Status
    # --------------------------
    if (result.solver.status == 'ok') and (result.solver.termination_condition == 'optimal'):
        print("\n=== Solver found an optimal solution. ===\n")
    elif result.solver.termination_condition == 'infeasible':
        print("\n=== Solver found the model to be infeasible. ===\n")
        log_infeasible_constraints(model)
    else:
        # Something else is wrong
        print(f"\n=== Solver Status: {result.solver.status} ===\n")
        print(f"=== Termination Condition: {result.solver.termination_condition} ===\n")

    # --------------------------
    # 11. Display Results
    # --------------------------
    display_selected_technologies(model)
    display_selected_fuels(model)
    display_selected_materials(model)
    display_production_levels(model)
    display_total_cost(model)

    # --------------------------
    # 12. Export Results to Excel
    # --------------------------
    export_results_to_excel(model)


if __name__ == "__main__":
    main()