from pyomo.environ import (
    ConcreteModel, Var, NonNegativeReals, Binary, Param,
    Objective, Constraint, Set, minimize, value, Any
)
import pandas as pd

def build_unified_model(data, **kwargs):
    carbonprice_include = kwargs.get('carbonprice_include', False)
    max_renew = kwargs.get('max_renew', 10)
    allow_replace_same_technology = kwargs.get('allow_replace_same_technology', False)

    model = ConcreteModel()

    # Define Sets
    model.systems = Set(initialize=data['baseline'].index.tolist())
    model.technologies = Set(initialize=data['technology'].index.tolist())
    model.fuels = Set(initialize=data['fuel_cost'].index.tolist())
    model.materials = Set(initialize=data['material_cost'].index.tolist())
    model.years = Set(initialize=sorted([int(yr) for yr in data['capex'].columns.tolist()]))

    # Baseline Parameters
    baseline_fuels_data = {sys: row['fuels'] for sys, row in data['baseline'].iterrows()}
    baseline_fuel_shares_data = {sys: row['fuel_shares'] for sys, row in data['baseline'].iterrows()}
    baseline_materials_data = {sys: row['materials'] for sys, row in data['baseline'].iterrows()}
    baseline_material_shares_data = {sys: row['material_shares'] for sys, row in data['baseline'].iterrows()}

    model.baseline_fuels = Param(model.systems, initialize=baseline_fuels_data, within=Any)
    model.baseline_fuel_shares = Param(model.systems, initialize=baseline_fuel_shares_data, within=Any)
    model.baseline_materials = Param(model.systems, initialize=baseline_materials_data, within=Any)
    model.baseline_material_shares = Param(model.systems, initialize=baseline_material_shares_data, within=Any)
    model.baseline_production = Param(model.systems, initialize=data['baseline']['production'].to_dict(), within=NonNegativeReals)

    # Other Parameters
    model.carbonprice_param = Param(model.years, initialize=lambda m, yr: data['carbonprice'].loc['global', yr], default=0.0)
    model.capex_param = Param(model.technologies, model.years, initialize=lambda m, tech, yr: data['capex'].loc[tech, yr], default=0.0)
    model.opex_param = Param(model.technologies, model.years, initialize=lambda m, tech, yr: data['opex'].loc[tech, yr], default=0.0)
    model.renewal_param = Param(model.technologies, model.years, initialize=lambda m, tech, yr: data['renewal'].loc[tech, yr], default=0.0)
    model.fuel_cost_param = Param(model.fuels, model.years, initialize=lambda m, f, yr: data['fuel_cost'].loc[f, yr], default=0.0)
    model.fuel_eff_param = Param(model.fuels, model.years, initialize=lambda m, f, yr: data['fuel_efficiency'].loc[f, yr], default=0.0)
    model.fuel_emission = Param(model.fuels, model.years, initialize=lambda m, f, yr: data['fuel_emission'].loc[f, yr], default=0.0)
    model.material_cost_param = Param(model.materials, model.years, initialize=lambda m, mat, yr: data['material_cost'].loc[mat, yr], default=0.0)
    model.material_eff_param = Param(model.materials, model.years, initialize=lambda m, mat, yr: data['material_efficiency'].loc[mat, yr], default=0.0)
    model.material_emission = Param(model.materials, model.years, initialize=lambda m, mat, yr: data['material_emission'].loc[mat, yr], default=0.0)
    model.production_param = Param(model.systems, initialize=data['baseline']['production'].to_dict(), default=0)
    model.lifespan_param = Param(model.technologies, initialize=lambda m, tech: data['technology'].loc[tech, 'lifespan'], default=0)
    model.introduced_year_param = Param(model.systems, initialize=data['baseline']['introduced_year'].to_dict(), default=0)
    model.technology_ei = Param(model.technologies, model.years, initialize=lambda m, tech, yr: data['technology_ei'].loc[tech, yr], default=1.0)
    model.emission_limit = Param(model.years, initialize=lambda m, yr: data['emission'].loc['global', yr], default=0)
    model.technology_introduction = Param(model.technologies, initialize=lambda m, tech: data['technology'].loc[tech, 'introduction'], default=0)
    model.baseline_technology = Param(model.systems, initialize=lambda m, sys: data['baseline'].loc[sys, 'technology'], within=model.technologies)
    model.max_renew = Param(initialize=max_renew)

    # Decision Variables
    model.replace = Var(model.systems, model.technologies, model.years, domain=Binary, initialize=0)
    model.active_technology = Var(model.systems, model.technologies, model.years, domain=Binary, initialize=0)
    model.continue_technology = Var(model.systems, model.technologies, model.years, domain=Binary, initialize=0)
    model.fuel_select = Var(model.systems, model.fuels, model.years, domain=Binary, initialize=0)
    model.material_select = Var(model.systems, model.materials, model.years, domain=Binary, initialize=0)
    model.production = Var(model.systems, model.years, domain=NonNegativeReals, initialize=0)
    model.fuel_consumption = Var(model.systems, model.fuels, model.years, domain=NonNegativeReals, initialize=0)
    model.material_consumption = Var(model.systems, model.materials, model.years, domain=NonNegativeReals, initialize=0)
    model.emission_by_tech = Var(model.systems, model.technologies, model.years, domain=NonNegativeReals, initialize=0)
    model.prod_active = Var(model.systems, model.technologies, model.years, domain=NonNegativeReals, initialize=0)
    model.replace_prod_active = Var(model.systems, model.technologies, model.years, domain=NonNegativeReals, initialize=0)
    model.renew_prod_active = Var(model.systems, model.technologies, model.years, domain=NonNegativeReals, initialize=0)
    model.activation_change = Var(model.systems, model.technologies, model.years, domain=Binary, initialize=0)
    model.renew = Var(model.systems, model.technologies, model.years, domain=Binary)
    model.total_fuel_consumption = Var(model.systems, model.years, within=NonNegativeReals)
    model.total_material_consumption = Var(model.systems, model.years, within=NonNegativeReals)

    # Constraints
    def emission_by_tech_rule(m, sys, tech, yr):
        return m.emission_by_tech[sys, tech, yr] == (
            m.technology_ei[tech, yr] * (
                sum(m.fuel_emission[f, yr] * m.fuel_consumption[sys, f, yr] for f in m.fuels) +
                sum(m.material_emission[mat, yr] * m.material_consumption[sys, mat, yr] for mat in m.materials)
            )
        )
    model.emission_by_tech_constraint = Constraint(model.systems, model.technologies, model.years, rule=emission_by_tech_rule)

    if not carbonprice_include:
        def emission_limit_rule(m, yr):
            return sum(m.emission_by_tech[sys, tech, yr] for sys in m.systems for tech in m.technologies) <= m.emission_limit[yr]
        model.emission_limit_constraint = Constraint(model.years, rule=emission_limit_rule)

    def technology_activation_rule(m, sys, yr):
        return sum(m.active_technology[sys, tech, yr] for tech in m.technologies) == 1
    model.technology_activation_constraint = Constraint(model.systems, model.years, rule=technology_activation_rule)

    def baseline_technology_first_year_rule(m, sys, tech, yr):
        if yr == min(m.years) and tech == m.baseline_technology[sys]:
            return m.continue_technology[sys, tech, yr] == 1
        return Constraint.Skip
    model.baseline_technology_first_year_constraint = Constraint(model.systems, model.technologies, model.years, rule=baseline_technology_first_year_rule)

    def baseline_technology_first_year_rule2(m, sys, tech, yr):
        if yr == min(m.years) and tech == m.baseline_technology[sys]:
            return m.renew[sys, tech, yr] + m.replace[sys, tech, yr] == 0
        return Constraint.Skip
    model.baseline_technology_first_year_constraint2 = Constraint(model.systems, model.technologies, model.years, rule=baseline_technology_first_year_rule2)

    def non_baseline_technologies_first_year_rule(m, sys, tech, yr):
        if yr == min(m.years) and tech != m.baseline_technology[sys]:
            return (m.continue_technology[sys, tech, yr] + m.replace[sys, tech, yr] + m.renew[sys, tech, yr] + m.active_technology[sys, tech, yr]) == 0
        return Constraint.Skip
    model.non_baseline_technologies_first_year_constraint = Constraint(model.systems, model.technologies, model.years, rule=non_baseline_technologies_first_year_rule)

    def hard_baseline_fuel_rule(m, sys, f, yr):
        if yr == min(m.years):
            return m.fuel_select[sys, f, yr] == (1 if f in m.baseline_fuels[sys] else 0)
        return Constraint.Skip
    model.hard_baseline_fuel_constraint = Constraint(model.systems, model.fuels, model.years, rule=hard_baseline_fuel_rule)

    def hard_baseline_material_rule(m, sys, mat, yr):
        if yr == min(m.years):
            return m.material_select[sys, mat, yr] == (1 if mat in m.baseline_materials[sys] else 0)
        return Constraint.Skip
    model.hard_baseline_material_constraint = Constraint(model.systems, model.materials, model.years, rule=hard_baseline_material_rule)

    def baseline_fuel_share_rule(m, sys, fuel, yr):
        if yr == min(m.years) and fuel in m.baseline_fuels[sys]:
            idx = m.baseline_fuels[sys].index(fuel)
            return m.fuel_consumption[sys, fuel, yr] == (
                m.baseline_fuel_shares[sys][idx] * m.baseline_production[sys] * m.fuel_eff_param[fuel, yr]
            )
        return Constraint.Skip
    model.baseline_fuel_share_constraint = Constraint(model.systems, model.fuels, model.years, rule=baseline_fuel_share_rule)

    def baseline_material_share_rule(m, sys, mat, yr):
        if yr == min(m.years) and mat in m.baseline_materials[sys]:
            idx = m.baseline_materials[sys].index(mat)
            return m.material_consumption[sys, mat, yr] == (
                m.baseline_material_shares[sys][idx] * m.baseline_production[sys] * m.material_eff_param[mat, yr]
            )
        return Constraint.Skip
    model.baseline_material_share_constraint = Constraint(model.systems, model.materials, model.years, rule=baseline_material_share_rule)

    if not allow_replace_same_technology:
        sorted_years = sorted(model.years)
        prev_year = {sorted_years[i]: sorted_years[i-1] for i in range(1, len(sorted_years))}
        def no_replace_with_self_rule(m, sys, tech, yr):
            if yr in prev_year:
                return m.replace[sys, tech, yr] + m.active_technology[sys, tech, prev_year[yr]] <= 1
            return Constraint.Skip
        model.no_replace_with_self_constraint = Constraint(model.systems, model.technologies, model.years, rule=no_replace_with_self_rule)

    def renew_limit_rule(m, sys, tech):
        return sum(m.renew[sys, tech, yr] for yr in m.years) <= m.max_renew
    model.renew_limit_constraint = Constraint(model.systems, model.technologies, rule=renew_limit_rule)

    def define_activation_change_rule(m, sys, tech, yr):
        if yr > min(m.years):
            return m.activation_change[sys, tech, yr] >= m.active_technology[sys, tech, yr] - m.active_technology[sys, tech, yr - 1]
        return Constraint.Skip
    model.define_activation_change_constraint = Constraint(model.systems, model.technologies, model.years, rule=define_activation_change_rule)

    def enforce_replace_on_activation_rule(m, sys, tech, yr):
        if yr > min(m.years):
            return m.replace[sys, tech, yr] >= m.activation_change[sys, tech, yr]
        return Constraint.Skip
    model.enforce_replace_on_activation_constraint = Constraint(model.systems, model.technologies, model.years, rule=enforce_replace_on_activation_rule)

    def enforce_replacement_or_renewal_years_rule(m, sys, tech, yr):
        introduced_year = m.introduced_year_param[sys]
        lifespan = m.lifespan_param[tech]
        if yr > introduced_year and (yr - introduced_year) % lifespan != 0:
            return m.replace[sys, tech, yr] + m.renew[sys, tech, yr] == 0
        return Constraint.Skip
    model.enforce_replacement_or_renewal_years_constraint = Constraint(model.systems, model.technologies, model.years, rule=enforce_replacement_or_renewal_years_rule)

    def enforce_no_continuation_in_replacement_years_rule(m, sys, tech, yr):
        introduced_year = m.introduced_year_param[sys]
        lifespan = m.lifespan_param[tech]
        if yr > introduced_year and (yr - introduced_year) % lifespan == 0:
            return m.continue_technology[sys, tech, yr] == 0
        return Constraint.Skip
    model.enforce_no_continuation_in_replacement_years_constraint = Constraint(model.systems, model.technologies, model.years, rule=enforce_no_continuation_in_replacement_years_rule)

    def exclusivity_rule(m, sys, tech, yr):
        return m.continue_technology[sys, tech, yr] + m.replace[sys, tech, yr] + m.renew[sys, tech, yr] <= 1
    model.exclusivity_rule = Constraint(model.systems, model.technologies, model.years, rule=exclusivity_rule)

    def active_technology_rule(m, sys, tech, yr):
        return m.active_technology[sys, tech, yr] == (
            m.continue_technology[sys, tech, yr] + m.replace[sys, tech, yr] + m.renew[sys, tech, yr]
        )
    model.active_technology_constraint = Constraint(model.systems, model.technologies, model.years, rule=active_technology_rule)

    def single_active_technology_rule(m, sys, yr):
        return sum(m.active_technology[sys, tech, yr] for tech in m.technologies) == 1
    model.single_active_technology_constraint = Constraint(model.systems, model.years, rule=single_active_technology_rule)

    def introduction_year_constraint_rule(m, sys, tech, yr):
        if yr < m.technology_introduction[tech]:
            return m.replace[sys, tech, yr] + m.continue_technology[sys, tech, yr] + m.renew[sys, tech, yr] == 0
        return Constraint.Skip
    model.introduction_year_constraint = Constraint(model.systems, model.technologies, model.years, rule=introduction_year_constraint_rule)

    def minimum_production_rule(m, sys, yr):
        return m.production[sys, yr] >= m.production_param[sys]
    model.minimum_production_constraint = Constraint(model.systems, model.years, rule=minimum_production_rule)

    def fuel_production_constraint_rule(m, sys, yr):
        return m.production[sys, yr] == sum(
            m.fuel_consumption[sys, fuel, yr] / m.fuel_eff_param[fuel, yr] for fuel in m.fuels
        )
    model.fuel_production_constraint = Constraint(model.systems, model.years, rule=fuel_production_constraint_rule)

    def fuel_selection_rule(m, sys, yr):
        return sum(m.fuel_select[sys, fuel, yr] for fuel in m.fuels) >= 1
    model.fuel_selection_constraint = Constraint(model.systems, model.years, rule=fuel_selection_rule)

    def total_fuel_consumption_rule(m, sys, yr):
        return m.total_fuel_consumption[sys, yr] == sum(m.fuel_consumption[sys, fuel, yr] for fuel in m.fuels)
    model.total_fuel_consumption_constraint = Constraint(model.systems, model.years, rule=total_fuel_consumption_rule)

    M_fuel = max(model.production_param.values()) * max(model.fuel_eff_param.values())
    def fuel_max_share_constraint_rule(m, sys, tech, f, yr):
        if yr > min(m.years):
            max_share = data['fuel_max_ratio'].get((tech, f), 0)
            return m.fuel_consumption[sys, f, yr] <= (
                max_share * m.total_fuel_consumption[sys, yr] + M_fuel * (1 - m.active_technology[sys, tech, yr])
            )
        return Constraint.Skip
    model.fuel_max_share_constraint = Constraint(model.systems, model.technologies, model.fuels, model.years, rule=fuel_max_share_constraint_rule)

    def fuel_min_share_constraint_rule(m, sys, tech, f, yr):
        introduction_year = data['fuel_introduction'].loc[f]
        if yr < introduction_year:
            return m.fuel_consumption[sys, f, yr] == 0
        min_share = data['fuel_min_ratio'].get((tech, f), 0)
        return m.fuel_consumption[sys, f, yr] >= (
            min_share * m.total_fuel_consumption[sys, yr] - M_fuel * (1 - m.active_technology[sys, tech, yr])
        )
    model.fuel_min_share_constraint = Constraint(model.systems, model.technologies, model.fuels, model.years, rule=fuel_min_share_constraint_rule)

    def material_production_constraint_rule(m, sys, yr):
        return m.production[sys, yr] == sum(
            m.material_consumption[sys, mat, yr] / m.material_eff_param[mat, yr] for mat in m.materials
        )
    model.material_production_constraint = Constraint(model.systems, model.years, rule=material_production_constraint_rule)

    def material_selection_rule(m, sys, yr):
        return sum(m.material_select[sys, mat, yr] for mat in m.materials) >= 1
    model.material_selection_constraint = Constraint(model.systems, model.years, rule=material_selection_rule)

    def total_material_consumption_rule(m, sys, yr):
        return m.total_material_consumption[sys, yr] == sum(m.material_consumption[sys, mat, yr] for mat in m.materials)
    model.total_material_consumption_constraint = Constraint(model.systems, model.years, rule=total_material_consumption_rule)

    M_mat = max(model.production_param.values()) * max(model.material_eff_param.values())
    def material_max_share_constraint_rule(m, sys, tech, mat, yr):
        if yr > min(m.years):
            max_share = data['material_max_ratio'].get((tech, mat), 0)
            return m.material_consumption[sys, mat, yr] <= (
                max_share * m.total_material_consumption[sys, yr] + M_mat * (1 - m.active_technology[sys, tech, yr])
            )
        return Constraint.Skip
    model.material_max_share_constraint = Constraint(model.systems, model.technologies, model.materials, model.years, rule=material_max_share_constraint_rule)

    def material_min_share_constraint_rule(m, sys, tech, mat, yr):
        introduction_year = data['material_introduction'].loc[mat]
        if yr < introduction_year:
            return m.material_consumption[sys, mat, yr] == 0
        min_share = data['material_min_ratio'].get((tech, mat), 0)
        return m.material_consumption[sys, mat, yr] >= (
            min_share * m.total_material_consumption[sys, yr] - M_mat * (1 - m.active_technology[sys, tech, yr])
        )
    model.material_min_share_constraint = Constraint(model.systems, model.technologies, model.materials, model.years, rule=material_min_share_constraint_rule)

    def prod_active_limit_rule(m, sys, tech, yr):
        return m.prod_active[sys, tech, yr] <= m.production[sys, yr]
    model.prod_active_limit_constraint = Constraint(model.systems, model.technologies, model.years, rule=prod_active_limit_rule)

    def prod_active_binary_rule(m, sys, tech, yr):
        return m.prod_active[sys, tech, yr] <= m.active_technology[sys, tech, yr] * M_fuel
    model.prod_active_binary_constraint = Constraint(model.systems, model.technologies, model.years, rule=prod_active_binary_rule)

    def prod_active_lower_rule(m, sys, tech, yr):
        return m.prod_active[sys, tech, yr] >= m.production[sys, yr] - M_fuel * (1 - m.active_technology[sys, tech, yr])
    model.prod_active_lower_constraint = Constraint(model.systems, model.technologies, model.years, rule=prod_active_lower_rule)

    def replace_prod_active_limit_rule(m, sys, tech, yr):
        return m.replace_prod_active[sys, tech, yr] <= m.production[sys, yr]
    model.replace_prod_active_limit_constraint = Constraint(model.systems, model.technologies, model.years, rule=replace_prod_active_limit_rule)

    def replace_prod_active_binary_rule(m, sys, tech, yr):
        return m.replace_prod_active[sys, tech, yr] <= m.replace[sys, tech, yr] * M_fuel
    model.replace_prod_active_binary_constraint = Constraint(model.systems, model.technologies, model.years, rule=replace_prod_active_binary_rule)

    def replace_prod_active_lower_rule(m, sys, tech, yr):
        return m.replace_prod_active[sys, tech, yr] >= m.production[sys, yr] - M_fuel * (1 - m.replace[sys, tech, yr])
    model.replace_prod_active_lower_constraint = Constraint(model.systems, model.technologies, model.years, rule=replace_prod_active_lower_rule)

    def renew_prod_active_limit_rule(m, sys, tech, yr):
        return m.renew_prod_active[sys, tech, yr] <= m.production[sys, yr]
    model.renew_prod_active_limit_constraint = Constraint(model.systems, model.technologies, model.years, rule=renew_prod_active_limit_rule)

    def renew_prod_active_binary_rule(m, sys, tech, yr):
        return m.renew_prod_active[sys, tech, yr] <= m.renew[sys, tech, yr] * M_fuel
    model.renew_prod_active_binary_constraint = Constraint(model.systems, model.technologies, model.years, rule=renew_prod_active_binary_rule)

    def renew_prod_active_lower_rule(m, sys, tech, yr):
        return m.renew_prod_active[sys, tech, yr] >= m.production[sys, yr] - M_fuel * (1 - m.renew[sys, tech, yr])
    model.renew_prod_active_lower_constraint = Constraint(model.systems, model.technologies, model.years, rule=renew_prod_active_lower_rule)

    # Objective Function
    def total_cost_rule(m):
        total_cost = sum(
            sum(
                (m.capex_param[tech, yr] * m.replace_prod_active[sys, tech, yr] +
                 m.renewal_param[tech, yr] * m.renew_prod_active[sys, tech, yr] +
                 m.opex_param[tech, yr] * m.prod_active[sys, tech, yr])
                for tech in m.technologies
            ) +
            sum(m.fuel_cost_param[fuel, yr] * m.fuel_consumption[sys, fuel, yr] for fuel in m.fuels) +
            sum(m.material_cost_param[mat, yr] * m.material_consumption[sys, mat, yr] for mat in m.materials)
            for sys in m.systems for yr in m.years
        )
        if carbonprice_include:
            carbon_cost = sum(
                m.carbonprice_param[yr] * sum(m.emission_by_tech[sys, tech, yr] for tech in m.technologies)
                for sys in m.systems for yr in m.years
            )
            total_cost += carbon_cost
        return total_cost
    model.total_cost = Objective(rule=total_cost_rule, sense=minimize)

    return model

# Note: build_model_for_system is not used in main, so omitted for brevity