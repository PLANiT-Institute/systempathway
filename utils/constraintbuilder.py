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

    # Similarly for feedstocks:
    def active_feedstock_upper_rule(m, sys, tech, fs, yr):
        return m.active_feedstock_consumption[sys, tech, fs, yr] <= m.feedstock_consumption[sys, fs, yr]

    model.active_feedstock_upper_constraint = Constraint(
        model.systems, model.technologies, model.feedstocks, model.years,
        rule=active_feedstock_upper_rule
    )

    def active_feedstock_tech_rule(m, sys, tech, fs, yr):
        return m.active_feedstock_consumption[sys, tech, fs, yr] <= BIG_M * m.active_technology[sys, tech, yr]

    model.active_feedstock_tech_constraint = Constraint(
        model.systems, model.technologies, model.feedstocks, model.years,
        rule=active_feedstock_tech_rule
    )

    def active_feedstock_lower_rule(m, sys, tech, fs, yr):
        return m.active_feedstock_consumption[sys, tech, fs, yr] >= (
                m.feedstock_consumption[sys, fs, yr] - BIG_M * (1 - m.active_technology[sys, tech, yr])
        )

    model.active_feedstock_lower_constraint = Constraint(
        model.systems, model.technologies, model.feedstocks, model.years,
        rule=active_feedstock_lower_rule
    )

    def emission_by_tech_rule(m, sys, tech, yr):
        return m.emission_by_tech[sys, tech, yr] == (
                m.technology_ei[tech, yr] * (
                sum(m.fuel_emission[f, yr] * m.active_fuel_consumption[sys, tech, f, yr] for f in m.fuels) +
                sum(m.feedstock_emission[fs, yr] * m.active_feedstock_consumption[sys, tech, fs, yr] for fs in
                    m.feedstocks)
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

    def hard_baseline_feedstock_rule(m, sys, fs, yr):
        if yr == min(m.years):  # Baseline year
            if fs in m.baseline_feedstocks[sys]:
                # Ensure baseline fuels are selected
                return m.feedstock_select[sys, fs, yr] == 1
            else:
                # Ensure non-baseline fuels are not selected
                return m.feedstock_select[sys, fs, yr] == 0
        return Constraint.Skip


    model.hard_baseline_feedstock_constraint = Constraint(
        model.systems, model.feedstocks, model.years,
        rule=hard_baseline_feedstock_rule
    )

    def baseline_fuel_share_rule(m, sys, fuel, yr):
            """Enforce that in the baseline year, each system's fuel consumption
            fsches baseline production × share × fuel intensity."""

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

    def baseline_feedstock_share_rule(m, sys, fs, yr):
        """Enforce that in the baseline year, each system's feedstock consumption
        fsches baseline production × feedstock share × (optionally) feedstock intensity."""

        # Only apply in the baseline year(s); skip for others
        if yr == min(m.years) and fs in m.baseline_feedstocks[sys]:
            # Find the correct index for this feedstock
            idx = m.baseline_feedstocks[sys].index(fs)

            # If you do NOT have a separate 'feedstock_eff_param', remove it from the formula
            return (
                    m.feedstock_consumption[sys, fs, yr] ==
                    m.baseline_feedstock_shares[sys][idx]
                    * m.baseline_production[sys]
                    * m.feedstock_eff_param[fs, yr]
            )
        else:
            return Constraint.Skip

    model.baseline_feedstock_share_constraint = Constraint(
        model.systems,
        model.feedstocks,
        model.years,
        rule=baseline_feedstock_share_rule
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

    return model

def feedstock_constraints(model, data):

    # 4.6. Material Constraints
    M_fs = max(model.production_param.values()) * max(model.feedstock_eff_param.values())  # Adjust based on the problem scale

    # 4.6.0. Material Production Constraint
    def feedstock_production_constraint_rule(m, sys, yr):
        return m.production[sys, yr] == sum(
            m.feedstock_consumption[sys, fs, yr] / m.feedstock_eff_param[fs, yr] for fs in m.feedstocks
        )

    model.feedstock_production_constraint = Constraint(model.systems, model.years,
                                                      rule=feedstock_production_constraint_rule)

    def feedstock_selection_rule(m, sys, yr):
        return sum(m.feedstock_select[sys, fs, yr] for fs in m.feedstocks) >= 1

    model.feedstock_selection_constraint = Constraint(model.systems, model.years, rule=feedstock_selection_rule)

    # 1. Total Material Consumption for Each System
    def total_feedstock_consumption_rule(m, sys, yr):
        # Total feedstock consumption per system for each year
        return m.total_feedstock_consumption[sys, yr] == sum(
            m.feedstock_consumption[sys, fs, yr] for fs in m.feedstocks
        )

    model.total_feedstock_consumption_constraint = Constraint(
        model.systems, model.years, rule=total_feedstock_consumption_rule
    )

    # 5. Maximum Material Share Constraint
    def feedstock_max_share_constraint_rule(m, sys, tech, fs, yr):
        if yr > min(m.years):

            # Get the maximum allowable share for the (technology, feedstock) combination
            max_share = data['feedstock_max_ratio'].get((tech, fs), 0)
            return m.feedstock_consumption[sys, fs, yr] <= (
                    max_share * m.total_feedstock_consumption[sys, yr] + M_fs * (1 - m.active_technology[sys, tech, yr])
            )
        else:
            return Constraint.Skip

    model.feedstock_max_share_constraint = Constraint(
        model.systems, model.technologies, model.feedstocks, model.years, rule=feedstock_max_share_constraint_rule
    )

    def feedstock_min_share_constraint_rule(m, sys, tech, fs, yr):
        # Pull the introduction year from your data
        introduction_year = data['feedstock_introduction'].loc[fs]

        # For years before introduction, force zero consumption
        if yr < introduction_year:
            return m.feedstock_consumption[sys, fs, yr] == 0

        # For introduced feedstocks, apply the min-share logic
        min_share = data['feedstock_min_ratio'].get((tech, fs), 0)

        # M_fs is your chosen "big M" for feedstocks; you already define it above.
        # The constraint says: if technology (sys, tech) is active,
        # feedstock_consumption >= min_share * total_feedstock_consumption
        # Otherwise, it can be relaxed by up to M_fs if the tech is not active.
        return m.feedstock_consumption[sys, fs, yr] >= (
                min_share * m.total_feedstock_consumption[sys, yr]
                - M_fs * (1 - m.active_technology[sys, tech, yr])
        )

    model.feedstock_min_share_constraint = Constraint(
        model.systems, model.technologies, model.feedstocks, model.years,
        rule=feedstock_min_share_constraint_rule
    )

    return model

def active_technology_constraints(model):

    M_fuel = max(model.production_param.values()) * max(model.fuel_eff_param.values())  # Adjust based on the problem scale

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

def lifespan_constraints(model):
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

    return model
