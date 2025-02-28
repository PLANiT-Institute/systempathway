from pyomo.environ import (Constraint)

def emission_constraints(model,**kwargs):

    carbonprice_include = kwargs.get('carbonprice_include', False)

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

    def technology_activation_rule(m, sys, yr):
        return sum(m.active_technology[sys, tech, yr] for tech in m.technologies) == 1

    model.technology_activation_constraint = Constraint(model.systems, model.years, rule=technology_activation_rule)

    return model

def baseline_constraints(model):
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

    return model

def fuel_constraints(model, data):

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


    return model

def feedstock_constraints(model, data):

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

    return model

def other_constraints(model, **kwargs):

    allow_replace_same_technology = kwargs.get('allow_replace_same_technology', False)

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

    return model