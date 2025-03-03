from pyomo.environ import (
    ConcreteModel, Var, NonNegativeReals, Binary, Param,
    Objective, Constraint, SolverFactory, Set, minimize, value, Any
)
import pandas as pd


def build_model_for_system(system_name, baseline_row, data, **kwargs):
    """
    Build a Pyomo optimization model for a single furnace site (system),
    ensuring that the initial year maintains the baseline technology
    and is excluded from the optimization years.
    """

    carbonprice_include = kwargs.get('carbonprice_include', False)
    max_renew = kwargs.get('max_renew', 10)
    allow_replace_same_technology = kwargs.get('allow_replace_same_technology', False)

    model = ConcreteModel()

    # Define Big-M parameter
    Big_M = 1e6  # Adjust this value based on your problem scale

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

    # Extract multi-fuel and multi-material data

    baseline_fuels = baseline_row['fuels']
    baseline_fuel_shares = baseline_row['fuel_shares']
    baseline_materials = baseline_row['materials']
    baseline_material_shares = baseline_row['material_shares']

    # Parameters
    model.capex_param = Param(model.technologies, model.years,initialize=lambda m, tech, yr: data['capex'].loc[tech, yr], default=0.0)
    model.opex_param = Param(model.technologies, model.years, initialize=lambda m, tech, yr: data['opex'].loc[tech, yr],default=0.0)
    model.renewal_param = Param(model.technologies, model.years,initialize=lambda m, tech, yr: data['renewal'].loc[tech, yr], default=0.0)
    model.fuel_cost_param = Param(model.fuels, model.years, initialize=lambda m, f, yr: data['fuel_cost'].loc[f, yr],default=0.0)
    model.fuel_eff_param = Param(model.fuels, model.years,initialize=lambda m, f, yr: data['fuel_efficiency'].loc[f, yr], default=0.0)
    model.material_cost_param = Param(model.materials, model.years,initialize=lambda m, mat, yr: data['material_cost'].loc[mat, yr], default=0.0)
    model.material_eff_param = Param(model.materials, model.years,initialize=lambda m, mat, yr: data['material_efficiency'].loc[mat, yr],default=0.0)
    model.carbonprice_param = Param(model.years, initialize=lambda m, yr: data['carbonprice'].loc['global', yr], default=0.0)

    # Parameters for Lifespan and Introduction Year
    model.lifespan_param = Param(model.technologies,initialize=lambda m, tech: data['technology'].loc[tech, 'lifespan'], default=0)
    model.introduced_year_param = Param(initialize=lambda m: introduced_year)
    model.max_renew = Param(initialize=max_renew)  # Example value; set as needed

    # Calculate spent_years from baseline
    baseline_spent_years = initial_year - baseline_row['introduced_year']
    model.spent_years = Var(model.years, within=NonNegativeReals)
    model.lifespan_completion = Var(model.technologies, model.years, domain=Binary)  # For lifespan completion

    # **Emission Parameters with Yearly Dimensions**
    model.fuel_emission = Param(model.fuels, model.years,initialize=lambda m, f, yr: data['fuel_emission'].loc[f, yr],default=0.0)
    model.material_emission = Param(model.materials, model.years,initialize=lambda m, mat, yr: data['material_emission'].loc[mat, yr],default=0.0)
    model.technology_ei = Param(model.technologies, model.years,initialize=lambda m, tech, yr: data['technology_ei'].loc[tech, yr],default=1.0)
    model.emission_limit = Param(model.years,initialize=lambda m, yr: data['emission_system'].loc[system_name, yr],default=1e9)
    # Parameters for maximum fuel and material ratios
    model.fuel_max_ratio = Param(model.technologies, model.fuels,initialize=lambda m, tech, fuel: data['fuel_max_ratio'].get((tech, fuel), 0),default=0.0)
    model.fuel_min_ratio = Param(model.technologies, model.fuels,initialize=lambda m, tech, fuel: data['fuel_min_ratio'].get((tech, fuel), 0),default=0.0)

    model.material_max_ratio = Param(model.technologies, model.materials,initialize=lambda m, tech, mat: data['material_max_ratio'].get((tech, mat), 0),default=0.0)

    # **Variables**
    model.material_consumption = Var(model.materials, model.years, domain=NonNegativeReals)
    model.emission_by_tech = Var(model.technologies, model.years, domain=NonNegativeReals)

    # Decision Variables
    model.fuel_select = Var(model.fuels, model.years, domain=Binary)
    model.material_select = Var(model.materials, model.years, domain=Binary)
    model.continue_technology = Var(model.technologies, model.years, domain=Binary)
    model.replace = Var(model.technologies, model.years, domain=Binary)
    model.renew = Var(model.technologies, model.years, domain=Binary)
    model.fuel_consumption = Var(model.fuels, model.years, domain=NonNegativeReals)
    model.active_technology = Var(model.technologies, model.years | {introduced_year}, domain=Binary)
    model.activation_change = Var(model.technologies, model.years, domain=Binary)


    # Total fuel consumption variable for each year
    model.total_fuel_consumption = Var(model.years, within=NonNegativeReals)
    model.total_material_consumption = Var(model.years, within=NonNegativeReals)

    """
    First year rule
    """
    # Constraint: Ensure baseline technology is active and continued in the first year
    def baseline_technology_first_year_rule(m, tech, yr):
        if yr == min(m.years) and tech == baseline_tech:
            return m.continue_technology[tech, yr] == 1
        return Constraint.Skip

    model.baseline_technology_first_year_constraint = Constraint(
        model.technologies, model.years, rule=baseline_technology_first_year_rule
    )

    def baesline_technology_first_year_rule2(m, tech, yr):
        if yr == min(m.years) and tech == baseline_tech:
            return m.renew[tech, yr] + m.replace[tech, yr] == 0
        return Constraint.Skip

    model.baesline_technology_first_year_constraint2 = Constraint(
        model.technologies, model.years, rule=baesline_technology_first_year_rule2
    )

    # Constraint: Ensure all non-baseline technologies are inactive in the first year
    def non_baseline_technologies_first_year_rule(m, tech, yr):
        if yr == min(m.years) and tech != baseline_tech:
            return (
                m.continue_technology[tech, yr] +
                m.replace[tech, yr] +
                m.renew[tech, yr] +
                m.active_technology[tech, yr]
            ) == 0
        return Constraint.Skip

    model.non_baseline_technologies_first_year_constraint = Constraint(
        model.technologies, model.years, rule=non_baseline_technologies_first_year_rule
    )

    # Ensure fuel selection matches the baseline fuels for the baseline year
    def hard_baseline_fuel_rule(m, f, yr):
        if yr == min(m.years):  # baseline year
            if f in baseline_fuels:
                # Ensure the fuel is selected in the baseline year if it's in the baseline fuels
                return m.fuel_select[f, yr] == 1
            else:
                # Ensure fuels not in the baseline are not selected
                return m.fuel_select[f, yr] == 0
        return Constraint.Skip

    model.hard_baseline_fuel_constraint = Constraint(
        model.fuels, model.years, rule=hard_baseline_fuel_rule
    )

    # Enforce baseline fuel shares
    def baseline_fuel_share_rule(m, fuel, yr):
        if yr == min(m.years) and fuel in baseline_fuels:
            # Fuel consumption must match the baseline share when the baseline tech is active
            return (m.fuel_consumption[fuel, yr] ==
                    baseline_fuel_shares[baseline_fuels.index(fuel)]
                    * production * m.fuel_eff_param[fuel, yr])
        return Constraint.Skip

    model.baseline_fuel_share_constraint = Constraint(
        model.fuels, model.years, rule=baseline_fuel_share_rule
    )

    # Ensure material selection matches the baseline materials for the baseline year
    def hard_baseline_material_rule(m, mat, yr):
        if yr == min(m.years):  # baseline year
            if mat in baseline_materials:
                # Ensure the material is selected in the baseline year if it's in the baseline materials
                return m.material_select[mat, yr] == 1
            else:
                # Ensure materials not in the baseline are not selected
                return m.material_select[mat, yr] == 0
        return Constraint.Skip

    model.hard_baseline_material_constraint = Constraint(
        model.materials, model.years, rule=hard_baseline_material_rule
    )

    # Enforce baseline material shares
    def baseline_material_share_rule(m, mat, yr):
        if yr == min(m.years) and mat in baseline_materials:
            # Material consumption must match the baseline share when the baseline tech is active
            return (m.material_consumption[mat, yr] == baseline_material_shares[baseline_materials.index(mat)]
                    * production * m.material_eff_param[mat, yr])
        return Constraint.Skip

    model.baseline_material_share_constraint = Constraint(
        model.materials, model.years, rule=baseline_material_share_rule
    )

    """
    Renewal Rule
    """

    def define_activation_change_rule(m, tech, yr):
        if yr > min(m.years):
            # activation_change = 1 if tech becomes active in yr from inactive in yr-1
            return m.activation_change[tech, yr] >= m.active_technology[tech, yr] - m.active_technology[tech, yr - 1]
        return Constraint.Skip

    model.define_activation_change_constraint = Constraint(
        model.technologies, model.years, rule=define_activation_change_rule
    )

    def enforce_replace_on_activation_rule(m, tech, yr):
        if yr > min(m.years):
            # If a technology becomes active, replace must be 1
            return m.replace[tech, yr] >= m.activation_change[tech, yr]
        return Constraint.Skip

    model.enforce_replace_on_activation_constraint = Constraint(
        model.technologies, model.years, rule=enforce_replace_on_activation_rule
    )

    def enforce_replacement_or_renewal_years_rule(m, tech, yr):
        introduced_year = m.introduced_year_param
        lifespan = m.lifespan_param[tech]
        if yr > introduced_year and (yr - introduced_year) % lifespan != 0:
            return m.replace[tech, yr] + m.renew[tech, yr] == 0
        return Constraint.Skip

    model.enforce_replacement_or_renewal_years_constraint = Constraint(
        model.technologies, model.years, rule=enforce_replacement_or_renewal_years_rule
    )

    def enforce_no_continuation_in_replacement_years_rule(m, tech, yr):
        introduced_year = m.introduced_year_param
        lifespan = m.lifespan_param[tech]
        if yr > introduced_year and (yr - introduced_year) % lifespan == 0:
            return m.continue_technology[tech, yr] == 0
        return Constraint.Skip
    model.enforce_no_continuation_in_replacement_years_constraint = Constraint(
        model.technologies, model.years, rule=enforce_no_continuation_in_replacement_years_rule
    )

    """
    Other baseline constraints
    """
    def exclusivity_rule(m, tech, yr):
        # Only one of continue, replace, or renew can be 1
        return m.continue_technology[tech, yr] + m.replace[tech, yr] + m.renew[tech, yr] <= 1

    model.exclusivity_rule = Constraint(model.technologies, model.years, rule=exclusivity_rule)

    # Define the constraint based on the allow_replace_same_technology flag
    def active_technology_rule(m, tech, yr):
        return m.active_technology[tech, yr] == (
                m.continue_technology[tech, yr] +
                m.replace[tech, yr] +
                m.renew[tech, yr]
        )

    # Apply the constraint to the model
    model.active_technology_constraint = Constraint(
        model.technologies,
        model.years,
        rule=active_technology_rule
    )

    # **Additional Constraint: Prevent Replacing a Technology with Itself**
    if not allow_replace_same_technology:
        # Constraint: If replace[tech, yr] == 1, then active_technology[tech, yr] == 0
        # This ensures that a technology cannot be replaced by itself
        def no_replace_with_self_rule(m, tech, yr):
            if yr > min(m.years):
                return m.replace[tech, yr] + m.active_technology[tech, yr-1] <= 1
            return Constraint.Skip

        model.no_replace_with_self_constraint = Constraint(
            model.technologies,
            model.years,
            rule=no_replace_with_self_rule
        )

    def single_active_technology_rule(m, yr):
        # Ensure only one technology is active in a given year
        return sum(m.active_technology[tech, yr] for tech in m.technologies) == 1

    model.single_active_technology_constraint = Constraint(
        model.years, rule=single_active_technology_rule
    )

    def introduction_year_constraint_rule(m, tech, yr):
        introduction_year = data['technology_introduction'][tech]
        if yr < introduction_year:
            return m.replace[tech, yr] + m.continue_technology[tech, yr] + m.renew[tech, yr] == 0
        return Constraint.Skip

    model.introduction_year_constraint = Constraint(model.technologies, model.years, rule=introduction_year_constraint_rule)

    def renew_limit_rule(m, tech):
        return sum(m.renew[tech, yr] for yr in m.years) <= m.max_renew

    model.renew_limit_constraint = Constraint(model.technologies, rule=renew_limit_rule)


    """
    Constraints for Fuel
    """
    def fuel_production_constraint_rule(m, yr):
        return production == sum(
            m.fuel_consumption[fuel, yr] / m.fuel_eff_param[fuel, yr] for fuel in m.fuels
        )

    model.fuel_production_constraint = Constraint(model.years, rule=fuel_production_constraint_rule)

    def fuel_selection_rule(m, yr):
        return sum(m.fuel_select[fuel, yr] for fuel in m.fuels) >= 1

    model.fuel_selection_constraint = Constraint(model.years, rule=fuel_selection_rule)

    # Rule to calculate total fuel consumption
    def total_fuel_consumption_rule(m, yr):
        return m.total_fuel_consumption[yr] == sum(
            m.fuel_consumption[f, yr] for f in m.fuels
        )

    # Add the total fuel consumption constraint
    model.total_fuel_consumption_constraint = Constraint(
        model.years, rule=total_fuel_consumption_rule
    )

    # Rule for maximum fuel share constraint
    def fuel_max_share_constraint_rule(m, tech, f, yr):
        if yr > min(m.years):
            # Get the maximum allowable share for the (technology, fuel) combination
            max_share = data['fuel_max_ratio'].get((tech, f), 0)

            # Constrain fuel consumption using Big-M reformulation
            return m.fuel_consumption[f, yr] <= (
                    max_share * m.total_fuel_consumption[yr] + Big_M * (1 - m.active_technology[tech, yr])
            )
        return Constraint.Skip

    # Add the constraint for all technologies, fuels, and years
    model.fuel_max_share_constraint = Constraint(
        model.technologies, model.fuels, model.years, rule=fuel_max_share_constraint_rule
    )

    def fuel_min_share_constraint_rule(m, tech, f, yr):
        introduction_year = data['fuel_introduction'].loc[f]
        if yr < introduction_year:
            # Can't use f, so skip or force consumption = 0
            return m.fuel_consumption[f, yr] == 0
        else:
            # If the technology is active, enforce the min share
            min_share = data['fuel_min_ratio'].get((tech, f), 0)
            return m.fuel_consumption[f, yr] >= (
                    min_share * m.total_fuel_consumption[yr]
                    - Big_M * (1 - m.active_technology[tech, yr])
            )
    model.fuel_min_share_constraint = Constraint(
        model.technologies, model.fuels, model.years, rule=fuel_min_share_constraint_rule
    )


    """
    Constraints for Materials
    """

    # **Material Production Constraint**
    def material_production_constraint_rule(m, yr):
        return production == sum(
            m.material_consumption[mat, yr] / m.material_eff_param[mat, yr] for mat in m.materials
        )
    model.material_production_constraint = Constraint(model.years, rule=material_production_constraint_rule)

    # **Material Selection Constraint**
    def material_selection_rule(m, yr):
        return sum(m.material_select[mat, yr] for mat in m.materials) >= 1
    model.material_selection_constraint = Constraint(model.years, rule=material_selection_rule)

    def total_material_consumption_rule(m, yr):
        return m.total_material_consumption[yr] == sum(
            m.material_consumption[mat, yr] for mat in m.materials
        )

    model.total_material_consumption_constraint = Constraint(
        model.years, rule=total_material_consumption_rule
    )

    # Define the material max share constraint with Big-M reformulation
    def material_max_share_constraint_rule(m, tech, mat, yr):
        if yr > min(m.years):
            max_share = data['material_max_ratio'].get((tech, mat), 0)

            # Constrain material consumption using Big-M reformulation
            return m.material_consumption[mat, yr] <= (
                    max_share * m.total_material_consumption[yr] + Big_M * (1 - m.active_technology[tech, yr])
            )
        return Constraint.Skip

    # Apply the constraint for all technologies, materials, and years
    model.material_max_share_constraint = Constraint(
        model.technologies, model.materials, model.years, rule=material_max_share_constraint_rule
    )

    def material_min_share_constraint_rule(m, tech, mat, yr):
        introduction_year = data['material_introduction'].loc[mat]
        if yr < introduction_year:
            # Can't use f, so skip or force consumption = 0
            return m.material_consumption[mat, yr] == 0
        else:
            # If the technology is active, enforce the min share
            min_share = data['material_min_ratio'].get((tech, mat), 0)
            return m.material_consumption[mat, yr] >= (
                    min_share * m.total_material_consumption[yr]
                    - Big_M * (1 - m.active_technology[tech, yr])
            )
    model.material_min_share_constraint = Constraint(
        model.technologies, model.materials, model.years, rule=material_min_share_constraint_rule
    )
    """
    Objective Function
    """

    def total_cost_rule(m):
        total_cost = sum(
            sum(
                # CAPEX: Only applied if the technology is replaced
                (m.capex_param[tech, yr] * m.replace[tech, yr] * production +
                 # Year 0 CAPEX adjustment for baseline tech
                 (m.capex_param[tech, yr] * ((m.lifespan_param[tech] - (yr - baseline_row['introduced_year'])) /
                                             m.lifespan_param[tech]) * production
                  if yr == min(m.years) and tech == baseline_tech else 0)) +
                # Renewal Cost: Only applied if the technology is renewed
                m.renewal_param[tech, yr] * m.renew[tech, yr] * production +
                # OPEX: Always applied for active technologies
                m.opex_param[tech, yr] * m.active_technology[tech, yr] * production
                for tech in m.technologies
            ) +
            # Fuel Cost: Calculated for each fuel based on its consumption
            sum(m.fuel_cost_param[fuel, yr] * m.fuel_consumption[fuel, yr] for fuel in m.fuels) +
            # Material Cost: Calculated for each material based on its consumption
            sum(m.material_cost_param[mat, yr] * m.material_consumption[mat, yr] for mat in m.materials)
            for yr in m.years
        )

        # Add carbon price if the flag is enabled
        if carbonprice_include:
            carbon_cost = sum(
                m.carbonprice_param[yr] * sum(m.emission_by_tech[tech, yr] for tech in m.technologies)
                for yr in m.years
            )
            total_cost += carbon_cost

        return total_cost

    model.total_cost = Objective(rule=total_cost_rule, sense=minimize)

    return model

def build_unified_model(data, **kwargs):
    """
    Get kwargs
    """
    carbonprice_include = kwargs.get('carbonprice_include', False)
    max_renew = kwargs.get('max_renew', 10)
    allow_replace_same_technology = kwargs.get('allow_replace_same_technology', False)

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


    # Extract and structure multi-fuel data by system and technology
    baseline_fuels_data = {
        sys: row['fuels']
        for sys, row in data['baseline'].iterrows()
    }
    baseline_fuel_shares_data = {
        sys: row['fuel_shares']
        for sys, row in data['baseline'].iterrows()
    }

    # Similarly, for materials
    baseline_materials_data = {
        sys: row['materials']
        for sys, row in data['baseline'].iterrows()
    }
    baseline_material_shares_data = {
        sys: row['material_shares']
        for sys, row in data['baseline'].iterrows()
    }

    # Define parameters for baseline fuels and materials
    model.baseline_fuels = Param(model.systems, initialize=baseline_fuels_data, within=Any)
    model.baseline_fuel_shares = Param(model.systems, initialize=baseline_fuel_shares_data, within=Any)
    model.baseline_materials = Param(model.systems, initialize=baseline_materials_data, within=Any)
    model.baseline_material_shares = Param(model.systems, initialize=baseline_material_shares_data, within=Any)

    baseline_production_data = {
        sys: baseline_row['production'] for sys, baseline_row in data['baseline'].iterrows()
    }
    model.baseline_production = Param(model.systems, initialize=baseline_production_data, within=NonNegativeReals)


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


    # --------------------------
    # 3. Define Decision Variables
    # --------------------------
    # Binary Variables
    model.replace = Var(model.systems, model.technologies, model.years, domain=Binary, initialize=0)
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

    model.renew = Var(model.systems, model.technologies, model.years, domain=Binary)
    model.max_renew = Param(initialize=max_renew)  # Example value; set as needed

    # 1. Total Fuel Consumption for Each System
    model.total_fuel_consumption = Var(model.systems, model.years, within=NonNegativeReals)
    model.total_material_consumption = Var(model.systems, model.years, within=NonNegativeReals)
    # --------------------------
    # 4. Define Constraints
    # --------------------------


    """
    Emission Constraints
    """
    # # 4.1. Emission Constraints

    # Auxiliary variables to capture consumption only if the tech is active
    model.active_fuel_consumption = Var(
        model.systems, model.technologies, model.fuels, model.years,
        domain=NonNegativeReals
    )
    model.active_material_consumption = Var(
        model.systems, model.technologies, model.materials, model.years,
        domain=NonNegativeReals
    )

    BIG_M = 1e15  # Adjust based on your data scale

    # 1) If tech is active, let active_fuel_consumption track fuel_consumption
    #    If tech is inactive, force it to be zero
    def active_fuel_upper_rule(m, sys, tech, f, yr):
        return m.active_fuel_consumption[sys, tech, f, yr] <= m.fuel_consumption[sys, f, yr]

    model.active_fuel_upper_constraint = Constraint(
        model.systems, model.technologies, model.fuels, model.years,
        rule=active_fuel_upper_rule
    )

    def active_fuel_tech_rule(m, sys, tech, f, yr):
        return m.active_fuel_consumption[sys, tech, f, yr] <= BIG_M * m.active_technology[sys, tech, yr]

    model.active_fuel_tech_constraint = Constraint(
        model.systems, model.technologies, model.fuels, model.years,
        rule=active_fuel_tech_rule
    )

    # (Optional) Lower bound so that if tech is active, active_fuel_consumption ≈ fuel_consumption
    def active_fuel_lower_rule(m, sys, tech, f, yr):
        return m.active_fuel_consumption[sys, tech, f, yr] >= (
                m.fuel_consumption[sys, f, yr] - BIG_M * (1 - m.active_technology[sys, tech, yr])
        )

    model.active_fuel_lower_constraint = Constraint(
        model.systems, model.technologies, model.fuels, model.years,
        rule=active_fuel_lower_rule
    )

    # Similarly for materials:
    def active_material_upper_rule(m, sys, tech, mat, yr):
        return m.active_material_consumption[sys, tech, mat, yr] <= m.material_consumption[sys, mat, yr]

    model.active_material_upper_constraint = Constraint(
        model.systems, model.technologies, model.materials, model.years,
        rule=active_material_upper_rule
    )

    def active_material_tech_rule(m, sys, tech, mat, yr):
        return m.active_material_consumption[sys, tech, mat, yr] <= BIG_M * m.active_technology[sys, tech, yr]

    model.active_material_tech_constraint = Constraint(
        model.systems, model.technologies, model.materials, model.years,
        rule=active_material_tech_rule
    )

    def active_material_lower_rule(m, sys, tech, mat, yr):
        return m.active_material_consumption[sys, tech, mat, yr] >= (
                m.material_consumption[sys, mat, yr] - BIG_M * (1 - m.active_technology[sys, tech, yr])
        )

    model.active_material_lower_constraint = Constraint(
        model.systems, model.technologies, model.materials, model.years,
        rule=active_material_lower_rule
    )

    def emission_by_tech_rule(m, sys, tech, yr):
        return m.emission_by_tech[sys, tech, yr] == (
                m.technology_ei[tech, yr] * (
                sum(m.fuel_emission[f, yr] * m.active_fuel_consumption[sys, tech, f, yr] for f in m.fuels) +
                sum(m.material_emission[mat, yr] * m.active_material_consumption[sys, tech, mat, yr] for mat in
                    m.materials)
        )
        )

    model.emission_by_tech_constraint = Constraint(
        model.systems, model.technologies, model.years,
        rule=emission_by_tech_rule
    )

    def emission_limit_rule(m, yr):
        return sum(
            m.emission_by_tech[sys, tech, yr]
            for sys in m.systems
            for tech in m.technologies
        ) <= m.emission_limit[yr]

    if not carbonprice_include:
        model.emission_limit_constraint = Constraint(
            model.years, rule=emission_limit_rule
        )

    # def emission_by_tech_rule(m, sys, tech, yr):
    #     # if yr == min(m.years):
    #     #     return Constraint.Skip
    #     # else:
    #     return m.emission_by_tech[sys, tech, yr] == (
    #         m.technology_ei[tech, yr] * (
    #             sum(m.fuel_emission[f, yr] * m.fuel_consumption[sys, f, yr] for f in m.fuels) +
    #             sum(m.material_emission[mat, yr] * m.material_consumption[sys, mat, yr] for mat in m.materials)
    #         )
    #     )
    #
    # model.emission_by_tech_constraint = Constraint(model.systems, model.technologies, model.years,
    #                                                rule=emission_by_tech_rule)
    #
    # def emission_limit_rule(m, yr):
    #     # if yr == min(m.years):
    #     #     return Constraint.Skip
    #     # else:
    #     return sum(
    #         m.emission_by_tech[sys, tech, yr] for sys in m.systems for tech in m.technologies) <= \
    #         m.emission_limit[yr]
    #
    # if carbonprice_include == False:
    #     model.emission_limit_constraint = Constraint(model.years, rule=emission_limit_rule)

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

    def hard_baseline_fuel_rule(m, sys, f, yr):
        if yr == min(m.years):  # Baseline year
            if f in m.baseline_fuels[sys]:
                # Ensure baseline fuels are selected
                return m.fuel_select[sys, f, yr] == 1
            else:
                # Ensure non-baseline fuels are not selected
                return m.fuel_select[sys, f, yr] == 0
        return Constraint.Skip

    model.hard_baseline_fuel_constraint = Constraint(
        model.systems, model.fuels, model.years, rule=hard_baseline_fuel_rule
    )

    def hard_baseline_material_rule(m, sys, mat, yr):
        if yr == min(m.years):  # Baseline year
            if mat in m.baseline_materials[sys]:
                # Ensure baseline fuels are selected
                return m.material_select[sys, mat, yr] == 1
            else:
                # Ensure non-baseline fuels are not selected
                return m.material_select[sys, mat, yr] == 0
        return Constraint.Skip


    model.hard_baseline_material_constraint = Constraint(
        model.systems, model.materials, model.years,
        rule=hard_baseline_material_rule
    )

    def baseline_fuel_share_rule(m, sys, fuel, yr):
            """Enforce that in the baseline year, each system's fuel consumption
            matches baseline production × share × fuel efficiency."""

            # Only apply in the baseline year(s); skip for other years if you have multiple
            if yr == min(m.years) and fuel in m.baseline_fuels[sys]:
                # Find the correct index for this fuel in baseline_fuels
                idx = m.baseline_fuels[sys].index(fuel)

                return m.fuel_consumption[sys, fuel, yr] == (
                        m.baseline_fuel_shares[sys][idx]
                        * m.baseline_production[sys]
                        * m.fuel_eff_param[fuel, yr]
                )
            else:
                return Constraint.Skip

    model.baseline_fuel_share_constraint = Constraint(
        model.systems, model.fuels, model.years,
        rule=baseline_fuel_share_rule
    )

    def baseline_material_share_rule(m, sys, mat, yr):
        """Enforce that in the baseline year, each system's material consumption
        matches baseline production × material share × (optionally) material efficiency."""

        # Only apply in the baseline year(s); skip for others
        if yr == min(m.years) and mat in m.baseline_materials[sys]:
            # Find the correct index for this material
            idx = m.baseline_materials[sys].index(mat)

            # If you do NOT have a separate 'material_eff_param', remove it from the formula
            return (
                    m.material_consumption[sys, mat, yr] ==
                    m.baseline_material_shares[sys][idx]
                    * m.baseline_production[sys]
                    * m.material_eff_param[mat, yr]
            )
        else:
            return Constraint.Skip

    model.baseline_material_share_constraint = Constraint(
        model.systems,
        model.materials,
        model.years,
        rule=baseline_material_share_rule
    )

    # **Additional Constraint: Prevent Replacing a Technology with Itself**

    if not allow_replace_same_technology:
        # Define a sorted list of years and create a mapping to previous years
        sorted_years = sorted(model.years)
        prev_year = {}
        for i in range(1, len(sorted_years)):
            prev_year[sorted_years[i]] = sorted_years[i - 1]

        # Constraint: If replace[sys, tech, yr] == 1, then active_technology[sys, tech, yr-1] == 0
        # This ensures that a technology cannot be replaced by itself
        def no_replace_with_self_rule(m, sys, tech, yr):
            if yr in prev_year:
                return m.replace[sys, tech, yr] + m.active_technology[sys, tech, prev_year[yr]] <= 1
            return Constraint.Skip

        model.no_replace_with_self_constraint = Constraint(
            model.systems,
            model.technologies,
            model.years,
            rule=no_replace_with_self_rule
        )

    def renew_limit_rule(m, sys, tech):
        return sum(m.renew[sys, tech, yr] for yr in m.years) <= m.max_renew

    model.renew_limit_constraint = Constraint(model.systems,
                                              model.technologies, rule=renew_limit_rule)


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
        if yr > min(m.years):
            # Get the maximum allowable share for the (technology, fuel) combination
            max_share = data['fuel_max_ratio'].get((tech, f), 0)
            return m.fuel_consumption[sys, f, yr] <= (
                    max_share * m.total_fuel_consumption[sys, yr] + M_fuel * (1 - m.active_technology[sys, tech, yr])
            )
        else:
            return Constraint.Skip

    model.fuel_max_share_constraint = Constraint(
        model.systems, model.technologies, model.fuels, model.years, rule=fuel_max_share_constraint_rule
    )

    def fuel_min_share_constraint_rule(m, sys, tech, f, yr):
        # Look up the introduction year for this fuel
        introduction_year = data['fuel_introduction'].loc[f]

        # If we're before the introduction year, enforce zero consumption
        if yr < introduction_year:
            return m.fuel_consumption[sys, f, yr] == 0

        # Otherwise, apply the minimum-share constraint
        min_share = data['fuel_min_ratio'].get((tech, f), 0)
        return m.fuel_consumption[sys, f, yr] >= (
                min_share * m.total_fuel_consumption[sys, yr]
                - M_fuel * (1 - m.active_technology[sys, tech, yr])
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
        if yr > min(m.years):

            # Get the maximum allowable share for the (technology, material) combination
            max_share = data['material_max_ratio'].get((tech, mat), 0)
            return m.material_consumption[sys, mat, yr] <= (
                    max_share * m.total_material_consumption[sys, yr] + M_mat * (1 - m.active_technology[sys, tech, yr])
            )
        else:
            return Constraint.Skip

    model.material_max_share_constraint = Constraint(
        model.systems, model.technologies, model.materials, model.years, rule=material_max_share_constraint_rule
    )

    def material_min_share_constraint_rule(m, sys, tech, mat, yr):
        # Pull the introduction year from your data
        introduction_year = data['material_introduction'].loc[mat]

        # For years before introduction, force zero consumption
        if yr < introduction_year:
            return m.material_consumption[sys, mat, yr] == 0

        # For introduced materials, apply the min-share logic
        min_share = data['material_min_ratio'].get((tech, mat), 0)

        # M_mat is your chosen "big M" for materials; you already define it above.
        # The constraint says: if technology (sys, tech) is active,
        # material_consumption >= min_share * total_material_consumption
        # Otherwise, it can be relaxed by up to M_mat if the tech is not active.
        return m.material_consumption[sys, mat, yr] >= (
                min_share * m.total_material_consumption[sys, yr]
                - M_mat * (1 - m.active_technology[sys, tech, yr])
        )

    model.material_min_share_constraint = Constraint(
        model.systems, model.technologies, model.materials, model.years,
        rule=material_min_share_constraint_rule
    )

    # # 6. Minimum Material Share Constraint
    # def material_min_share_constraint_rule(m, sys, tech, mat, yr):
    #     if yr > min(m.years):
    #
    #         # Get the minimum allowable share for the (technology, material) combination
    #         min_share = data['material_min_ratio'].get((tech, mat), 0)
    #         return m.material_consumption[sys, mat, yr] >= (
    #                 min_share * m.total_material_consumption[sys, yr] -
    #                 M_mat * (1 - m.active_technology[sys, tech, yr])
    #         )
    #     else:
    #         return Constraint.Skip
    #
    # model.material_min_share_constraint = Constraint(
    #     model.systems, model.technologies, model.materials, model.years, rule=material_min_share_constraint_rule
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