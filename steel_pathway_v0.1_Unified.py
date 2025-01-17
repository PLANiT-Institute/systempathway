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
    data['carbonprice'] = pd.read_excel(file_path, sheet_name='carbonprice', index_col=0)

    # Load technology emission intensities and pairings
    data['technology_ei'] = pd.read_excel(file_path, sheet_name='technology_ei', index_col=0)
    data['technology_fuel_pairs'] = pd.read_excel(file_path, sheet_name='technology_fuel_pairs').groupby('technology')['fuel'].apply(list).to_dict()
    data['technology_material_pairs'] = \
pd.read_excel(file_path, sheet_name='technology_material_pairs').groupby('technology')['material'].apply(list).to_dict()
    data['technology_introduction'] = pd.read_excel(file_path, sheet_name='technology', index_col=0)[
        'introduction'].to_dict()
    technology_fuel_pairs_df = pd.read_excel(file_path, sheet_name='technology_fuel_pairs')

    data['fuel_max_ratio'] = technology_fuel_pairs_df.set_index(['technology', 'fuel'])['max'].to_dict()
    data['fuel_min_ratio'] = technology_fuel_pairs_df.set_index(['technology', 'fuel'])['min'].to_dict()
    technology_material_pairs_df = pd.read_excel(file_path, sheet_name='technology_material_pairs')

    data['material_max_ratio'] = technology_material_pairs_df.set_index(['technology', 'material'])['max'].to_dict()
    data['material_min_ratio'] = technology_material_pairs_df.set_index(['technology', 'material'])['min'].to_dict()


    return data

def build_unified_model(data, **kwargs):
    """
    Get kwargs
    """
    carbonprice_include = kwargs.get('carbonprice_include', True)

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

    model.carbonprice_param = Param(model.years,
                                    initialize=lambda m, yr: data['carbonprice'].loc['global', yr],
                                    default=0.0)


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

    def emission_limit_rule(m, yr):
        return sum(
            m.emission_by_tech[sys, tech, yr] for sys in m.systems for tech in m.technologies) <= \
            m.emission_limit[yr]

    if carbonprice_include == False:
        model.emission_limit_constraint = Constraint(model.years, rule=emission_limit_rule)

    def technology_activation_rule(m, sys, yr):
        return sum(m.active_technology[sys, tech, yr] for tech in m.technologies) == 1

    model.technology_activation_constraint = Constraint(model.systems, model.years, rule=technology_activation_rule)

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

    """
    Fuel Constraints
    """

    # 4.5. Fuel Constraints
    def fuel_production_constraint_rule(m, sys, yr):
        return m.production[sys, yr] == sum(
            m.fuel_consumption[sys, fuel, yr] / m.fuel_eff_param[fuel, yr] for fuel in m.fuels
        )

    model.fuel_production_constraint = Constraint(model.systems, model.years, rule=fuel_production_constraint_rule)

    def fuel_selection_rule(m, sys, yr):
        return sum(m.fuel_select[sys, fuel, yr] for fuel in m.fuels) >= 1

    model.fuel_selection_constraint = Constraint(model.systems, model.years, rule=fuel_selection_rule)

    # 1. Total Fuel Consumption for Each System
    model.total_fuel_consumption = Var(model.systems, model.years, within=NonNegativeReals)

    def total_fuel_consumption_rule(m, sys, yr):
        # Total fuel consumption per system for each year
        return m.total_fuel_consumption[sys, yr] == sum(
            m.fuel_consumption[sys, fuel, yr] for fuel in m.fuels
        )

    model.total_fuel_consumption_constraint = Constraint(
        model.systems, model.years, rule=total_fuel_consumption_rule
    )

    M_fuel = max(model.production_param.values()) * max(model.fuel_eff_param.values())  # Adjust based on the problem scale

    # 5. Maximum Fuel Share Constraint

    def fuel_max_share_constraint_rule(m, sys, tech, f, yr):
        # Get the maximum allowable share for the (technology, fuel) combination
        max_share = data['fuel_max_ratio'].get((tech, f), 0)
        return m.fuel_consumption[sys, f, yr] <= (
                max_share * m.total_fuel_consumption[sys, yr] + M_fuel * (1 - m.active_technology[sys, tech, yr])
        )

    model.fuel_max_share_constraint = Constraint(
        model.systems, model.technologies, model.fuels, model.years, rule=fuel_max_share_constraint_rule
    )

    # # 4. Fuel Consumption Limit
    # def fuel_consumption_limit_rule(m, sys, f, yr):
    #     return m.fuel_consumption[sys, f, yr] <= M_fuel * m.fuel_select[sys, f, yr]
    #
    # model.fuel_consumption_limit_constraint = Constraint(model.systems, model.fuels, model.years,
    #                                                      rule=fuel_consumption_limit_rule)
    #
    # model.fuel_consumption_limit_constraint = Constraint(
    #     model.systems, model.fuels, model.years, rule=fuel_consumption_limit_rule
    # )
    # 6. Minimum Fuel Share Constraint
    def fuel_min_share_constraint_rule(m, sys, tech, f, yr):
        # Get the minimum allowable share for the (technology, fuel) combination
        min_share = data['fuel_min_ratio'].get((tech, f), 0)
        return m.fuel_consumption[sys, f, yr] >= (
                min_share * m.total_fuel_consumption[sys, yr] - M_fuel * (1 - m.active_technology[sys, tech, yr])
        )

    model.fuel_min_share_constraint = Constraint(
        model.systems, model.technologies, model.fuels, model.years, rule=fuel_min_share_constraint_rule
    )

    """
    Material Constraints
    """

    # 4.6. Material Constraints
    M_mat = max(model.production_param.values()) * max(model.material_eff_param.values())  # Adjust based on the problem scale

    # 4.6.0. Material Production Constraint
    def material_production_constraint_rule(m, sys, yr):
        return m.production[sys, yr] == sum(
            m.material_consumption[sys, mat, yr] / m.material_eff_param[mat, yr] for mat in m.materials
        )

    model.material_production_constraint = Constraint(model.systems, model.years,
                                                      rule=material_production_constraint_rule)

    def material_selection_rule(m, sys, yr):
        return sum(m.material_select[sys, mat, yr] for mat in m.materials) >= 1

    model.material_selection_constraint = Constraint(model.systems, model.years, rule=material_selection_rule)

    # 1. Total Material Consumption for Each System
    model.total_material_consumption = Var(model.systems, model.years, within=NonNegativeReals)

    def total_material_consumption_rule(m, sys, yr):
        # Total material consumption per system for each year
        return m.total_material_consumption[sys, yr] == sum(
            m.material_consumption[sys, mat, yr] for mat in m.materials
        )

    model.total_material_consumption_constraint = Constraint(
        model.systems, model.years, rule=total_material_consumption_rule
    )

    # 5. Maximum Material Share Constraint
    def material_max_share_constraint_rule(m, sys, tech, mat, yr):
        # Get the maximum allowable share for the (technology, material) combination
        max_share = data['material_max_ratio'].get((tech, mat), 0)
        return m.material_consumption[sys, mat, yr] <= (
                max_share * m.total_material_consumption[sys, yr] + M_mat * (1 - m.active_technology[sys, tech, yr])
        )

    model.material_max_share_constraint = Constraint(
        model.systems, model.technologies, model.materials, model.years, rule=material_max_share_constraint_rule
    )

    # 6. Minimum Material Share Constraint
    def material_min_share_constraint_rule(m, sys, tech, mat, yr):
        # Get the minimum allowable share for the (technology, material) combination
        min_share = data['material_min_ratio'].get((tech, mat), 0)
        return m.material_consumption[sys, mat, yr] >= (
                min_share * m.total_material_consumption[sys, yr] - M_mat * (1 - m.active_technology[sys, tech, yr])
        )

    model.material_min_share_constraint = Constraint(
        model.systems, model.technologies, model.materials, model.years, rule=material_min_share_constraint_rule
    )

    # # 4. Material Consumption Limit
    # def material_consumption_limit_rule(m, sys, mat, yr):
    #     # Material consumption is limited by material selection
    #     return m.material_consumption[sys, mat, yr] <= M_mat * m.material_select[sys, mat, yr]
    #
    # model.material_consumption_limit_constraint = Constraint(
    #     model.systems, model.materials, model.years, rule=material_consumption_limit_rule
    # )

    """
    Objective Function
    """

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
        """
        Calculate the total cost, optionally including the carbon cost.
        """
        # Base cost components
        total_cost = sum(
            sum(
                # CAPEX, Renewal, and OPEX costs using auxiliary variables for linearity
                (m.capex_param[tech, yr] * m.replace_prod_active[sys, tech, yr] +
                 m.renewal_param[tech, yr] * m.renew_prod_active[sys, tech, yr] +
                 m.opex_param[tech, yr] * m.prod_active[sys, tech, yr])
                for tech in m.technologies
            ) +
            # Fuel costs
            sum(m.fuel_cost_param[fuel, yr] * m.fuel_consumption[sys, fuel, yr] for fuel in m.fuels) +
            # Material costs
            sum(m.material_cost_param[mat, yr] * m.material_consumption[sys, mat, yr] for mat in m.materials)
            for sys in m.systems for yr in m.years
        )

        # Add carbon price cost if the flag is enabled
        if carbonprice_include:
            carbon_cost = sum(
                m.carbonprice_param[yr] * sum(
                    m.emission_by_tech[sys, tech, yr] for tech in m.technologies
                )
                for sys in m.systems for yr in m.years
            )
            total_cost += carbon_cost

        return total_cost

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

def export_results_to_excel(model, annual_global_capex, annual_global_renewal_cost, annual_global_opex, annual_global_total_emissions):
    """
    Export detailed results to an Excel file with separate sheets for each furnace site
    and a summary sheet for annual global metrics.
    """
    with pd.ExcelWriter('model_results.xlsx') as writer:
        # Iterate over each system to create separate sheets
        for sys in model.systems:
            # Initialize lists to store yearly data
            yearly_metrics = []
            fuel_consumption_table = []
            material_consumption_table = []
            technology_statuses = []

            # Extract baseline technology information
            baseline_tech = data['baseline'].loc[sys, 'technology']
            introduced_year = data['baseline'].loc[sys, 'introduced_year']
            lifespan = model.lifespan_param[baseline_tech]

            for yr in model.years:
                # Calculate Costs
                capex_cost = sum(
                    model.capex_param[tech, yr] * value(model.replace_prod_active[sys, tech, yr])
                    for tech in model.technologies
                )

                if yr == min(model.years):
                    if baseline_tech in model.technologies:
                        capex_adjustment = model.capex_param[baseline_tech, yr] * (
                            (lifespan - (yr - introduced_year)) / lifespan
                        ) * value(model.production[sys, yr])
                        capex_cost += capex_adjustment
                    else:
                        print(f"Warning: Baseline technology '{baseline_tech}' not found in model.technologies for system '{sys}'.")

                renewal_cost = sum(
                    model.renewal_param[tech, yr] * value(model.renew_prod_active[sys, tech, yr])
                    for tech in model.technologies
                )

                opex_cost = sum(
                    model.opex_param[tech, yr] * value(model.prod_active[sys, tech, yr])
                    for tech in model.technologies
                )

                total_emissions = sum(
                    value(model.emission_by_tech[sys, tech, yr]) for tech in model.technologies
                )

                fuel_consumption = {
                    fuel: value(model.fuel_consumption[sys, fuel, yr]) for fuel in model.fuels
                }

                material_consumption = {
                    mat: value(model.material_consumption[sys, mat, yr]) for mat in model.materials
                }

                yearly_metrics.append({
                    "Year": yr,
                    "CAPEX": capex_cost,
                    "Renewal Cost": renewal_cost,
                    "OPEX": opex_cost,
                    "Total Emissions": total_emissions
                })

                fuel_consumption_table.append({"Year": yr, **fuel_consumption})
                material_consumption_table.append({"Year": yr, **material_consumption})

                for tech in model.technologies:
                    technology_statuses.append({
                        "Year": yr,
                        "Technology": tech,
                        "Continue": value(model.continue_technology[sys, tech, yr]),
                        "Replace": value(model.replace[sys, tech, yr]),
                        "Renew": value(model.renew[sys, tech, yr]),
                        "Active": value(model.active_technology[sys, tech, yr])
                    })

            # Convert Yearly Metrics to DataFrame
            costs_df = pd.DataFrame(yearly_metrics).set_index("Year")
            costs_df.to_excel(writer, sheet_name=f'{sys}_Costs_and_Emissions')

            # Convert Fuel Consumption to DataFrame
            fuel_df = pd.DataFrame(fuel_consumption_table).set_index("Year")
            fuel_df.to_excel(writer, sheet_name=f'{sys}_Fuel_Consumption')

            # Convert Material Consumption to DataFrame
            material_df = pd.DataFrame(material_consumption_table).set_index("Year")
            material_df.to_excel(writer, sheet_name=f'{sys}_Material_Consumption')

            # Convert Technology Statuses to DataFrame
            technology_df = pd.DataFrame(technology_statuses)
            technology_df.to_excel(writer, sheet_name=f'{sys}_Technology_Statuses', index=False)

        # Create a summary sheet for annual global metrics
        annual_summary = []
        for yr in sorted(model.years):
            total_cost = annual_global_capex[yr] + annual_global_renewal_cost[yr] + annual_global_opex[yr]
            annual_summary.append({
                "Year": yr,
                "Total CAPEX": annual_global_capex[yr],
                "Total Renewal Cost": annual_global_renewal_cost[yr],
                "Total OPEX": annual_global_opex[yr],
                "Total Cost": total_cost,
                "Total Emissions": annual_global_total_emissions[yr]
            })

        annual_summary_df = pd.DataFrame(annual_summary).set_index("Year")
        annual_summary_df.to_excel(writer, sheet_name='Annual_Global_Summary')

from pyomo.environ import SolverFactory, value
import pandas as pd

def main(**kwargs):

    carbonprice_include = kwargs.get('carboprice_include', False)

    # --------------------------
    # 7. Load Data
    # --------------------------
    file_path = 'database/steel_data.xlsx'  # Update with your actual file path
    data = load_data(file_path)

    # --------------------------
    # 8. Build the Unified Model
    # --------------------------
    model = build_unified_model(data, carbonprice_include=carbonprice_include)

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
        return  # Exit the function as no solution exists
    else:
        # Something else is wrong
        print(f"\n=== Solver Status: {result.solver.status} ===\n")
        print(f"=== Termination Condition: {result.solver.termination_condition} ===\n")
        return  # Exit the function as the solution is not optimal

    # --------------------------
    # 11. Initialize Annual Global Metrics
    # --------------------------
    annual_global_capex = {yr: 0.0 for yr in model.years}
    annual_global_renewal_cost = {yr: 0.0 for yr in model.years}
    annual_global_opex = {yr: 0.0 for yr in model.years}
    annual_global_total_emissions = {yr: 0.0 for yr in model.years}

    # --------------------------
    # 12. Display and Collect Detailed Results
    # --------------------------
    for sys in model.systems:
        print(f"\n=== Results for Furnace Site: {sys} ===\n")

        # Initialize lists to store yearly data
        yearly_metrics = []
        fuel_consumption_table = []
        material_consumption_table = []
        technology_statuses = []

        # Extract baseline technology information
        baseline_tech = data['baseline'].loc[sys, 'technology']
        introduced_year = data['baseline'].loc[sys, 'introduced_year']
        lifespan = model.lifespan_param[baseline_tech]

        for yr in model.years:
            # Calculate Costs
            # CAPEX: Only applied if the technology is replaced
            capex_cost = sum(
                model.capex_param[tech, yr] * value(model.replace_prod_active[sys, tech, yr])
                for tech in model.technologies
            )

            # Adjust CAPEX for the first year and baseline technology
            if yr == min(model.years):
                if baseline_tech in model.technologies:
                    capex_adjustment = model.capex_param[baseline_tech, yr] * (
                        (lifespan - (yr - introduced_year)) / lifespan
                    ) * value(model.production[sys, yr])
                    capex_cost += capex_adjustment
                else:
                    print(f"Warning: Baseline technology '{baseline_tech}' not found in model.technologies for system '{sys}'.")

            # Renewal Cost: Only applied if the technology is renewed
            renewal_cost = sum(
                model.renewal_param[tech, yr] * value(model.renew_prod_active[sys, tech, yr])
                for tech in model.technologies
            )

            # OPEX: Always applied for active technologies
            opex_cost = sum(
                model.opex_param[tech, yr] * value(model.prod_active[sys, tech, yr])
                for tech in model.technologies
            )

            # Calculate Emissions
            total_emissions = sum(
                value(model.emission_by_tech[sys, tech, yr]) for tech in model.technologies
            )

            # Calculate Fuel Consumption
            fuel_consumption = {
                fuel: value(model.fuel_consumption[sys, fuel, yr]) for fuel in model.fuels
            }

            # Calculate Material Consumption
            material_consumption = {
                mat: value(model.material_consumption[sys, mat, yr]) for mat in model.materials
            }

            # Collect Yearly Metrics
            yearly_metrics.append({
                "Year": yr,
                "CAPEX": capex_cost,
                "Renewal Cost": renewal_cost,
                "OPEX": opex_cost,
                "Total Emissions": total_emissions
            })

            # Collect Fuel Consumption Data
            fuel_consumption_table.append({"Year": yr, **fuel_consumption})

            # Collect Material Consumption Data
            material_consumption_table.append({"Year": yr, **material_consumption})

            # Collect Technology Statuses
            for tech in model.technologies:
                technology_statuses.append({
                    "Year": yr,
                    "Technology": tech,
                    "Continue": value(model.continue_technology[sys, tech, yr]),
                    "Replace": value(model.replace[sys, tech, yr]),
                    "Renew": value(model.renew[sys, tech, yr]),
                    "Active": value(model.active_technology[sys, tech, yr])
                })

            # Accumulate Annual Global Metrics
            annual_global_capex[yr] += capex_cost
            annual_global_renewal_cost[yr] += renewal_cost
            annual_global_opex[yr] += opex_cost
            annual_global_total_emissions[yr] += total_emissions

        # Convert Yearly Metrics to DataFrame
        costs_df = pd.DataFrame(yearly_metrics).set_index("Year")
        print("=== Costs and Emissions by Year ===")
        print(costs_df)

        # Convert Fuel Consumption to DataFrame
        fuel_df = pd.DataFrame(fuel_consumption_table).set_index("Year")
        print("\n=== Fuel Consumption by Year ===")
        print(fuel_df)

        # Convert Material Consumption to DataFrame
        material_df = pd.DataFrame(material_consumption_table).set_index("Year")
        print("\n=== Material Consumption by Year ===")
        print(material_df)

        # Display Technology Statuses
        print("\n=== Technology Statuses ===")

        technology_df = pd.DataFrame(technology_statuses)

        # Filter rows where at least one status indicator is 1
        technology_df_filtered = technology_df[
            technology_df[['Active', 'Continue', 'Replace', 'Renew']].sum(axis=1) >= 1
            ]

        # Set MultiIndex if 'System' is available
        if 'System' in technology_df_filtered.columns:
            technology_df_filtered.set_index(['System', 'Year', 'Technology'], inplace=True)
        else:
            technology_df_filtered.set_index(['Year', 'Technology'], inplace=True)

        # Rearrange columns
        desired_columns = ['Continue', 'Replace', 'Renew', 'Active']
        technology_df_filtered = technology_df_filtered[desired_columns]

        # Display the DataFrame
        print("\n=== Technology Statuses ===\n")
        print(technology_df_filtered)
    # --------------------------
    # 13. Display Annual Global Metrics
    # --------------------------
    print("\n=== Annual Global Total Costs and Emissions ===")
    annual_summary = []
    for yr in sorted(model.years):
        total_cost = annual_global_capex[yr] + annual_global_renewal_cost[yr] + annual_global_opex[yr]
        annual_summary.append({
            "Year": yr,
            "Total CAPEX": annual_global_capex[yr],
            "Total Renewal Cost": annual_global_renewal_cost[yr],
            "Total OPEX": annual_global_opex[yr],
            "Total Cost": total_cost,
            "Total Emissions": annual_global_total_emissions[yr]
        })

    annual_summary_df = pd.DataFrame(annual_summary).set_index("Year")
    print(annual_summary_df)

    # --------------------------
    # 14. Export Results to Excel
    # --------------------------
    # export_results_to_excel(model, annual_global_capex, annual_global_renewal_cost, annual_global_opex, annual_global_total_emissions)
    # print("\n=== Results have been exported to 'model_results.xlsx' ===\n")

if __name__ == "__main__":
    main(carboprice_include=True)
