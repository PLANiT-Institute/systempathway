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

    return model

def baseline_constraints(model):
    # Get the first year of the model
    first_year = min(model.years)
    
    # Ensure baseline technology is active and continued in the first year
    def baseline_technology_first_year_rule(m, sys, tech, yr):
        # Only apply if capacity is positive in the first year
        if yr == first_year and tech == m.baseline_technology[sys] and m.capacity_plan[sys, yr] > 0:
            return m.continue_technology[sys, tech, yr] == 1
        return Constraint.Skip

    model.baseline_technology_first_year_constraint = Constraint(
        model.systems, model.technologies, model.years, rule=baseline_technology_first_year_rule
    )

    def baseline_technology_first_year_rule2(m, sys, tech, yr):
        # Only apply if capacity is positive in the first year
        if yr == first_year and tech == m.baseline_technology[sys] and m.capacity_plan[sys, yr] > 0:
            return m.renew[sys, tech, yr] + m.replace[sys, tech, yr] == 0
        return Constraint.Skip

    model.baseline_technology_first_year_constraint2 = Constraint(
        model.systems, model.technologies, model.years, rule=baseline_technology_first_year_rule2
    )

    # Ensure all non-baseline technologies are inactive in the first year
    def non_baseline_technologies_first_year_rule(m, sys, tech, yr):
        # Only apply if capacity is positive in the first year
        if yr == first_year and tech != m.baseline_technology[sys] and m.capacity_plan[sys, yr] > 0:
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
        # Only apply if capacity is positive in the first year
        if yr == first_year and m.capacity_plan[sys, yr] > 0:  # Baseline year
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
        # Only apply if capacity is positive in the first year
        if yr == first_year and m.capacity_plan[sys, yr] > 0:  # Baseline year
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
            matches baseline production × share × fuel intensity."""

            # Only apply if capacity is positive in the first year
            if yr == first_year and fuel in m.baseline_fuels[sys] and m.capacity_plan[sys, yr] > 0:
                # Find the correct index for this fuel in baseline_fuels
                idx = m.baseline_fuels[sys].index(fuel)

                # Calculate target value
                share = m.baseline_fuel_shares[sys][idx]
                target = share * m.production[sys, yr] * m.fuel_eff_param[fuel, yr]
                
                # Return only the lower bound constraint, the upper bound will be in a separate constraint
                return m.fuel_consumption[sys, fuel, yr] >= 0.95 * target
            else:
                return Constraint.Skip

    model.baseline_fuel_share_constraint = Constraint(
        model.systems, model.fuels, model.years,
        rule=baseline_fuel_share_rule
    )
    
    # Add upper bound for fuel share as a separate constraint
    def baseline_fuel_share_upper_rule(m, sys, fuel, yr):
        """Enforce upper bound for baseline fuel consumption."""
        if yr == first_year and fuel in m.baseline_fuels[sys] and m.capacity_plan[sys, yr] > 0:
            idx = m.baseline_fuels[sys].index(fuel)
            share = m.baseline_fuel_shares[sys][idx]
            target = share * m.production[sys, yr] * m.fuel_eff_param[fuel, yr]
            
            return m.fuel_consumption[sys, fuel, yr] <= 1.05 * target
        else:
            return Constraint.Skip
            
    model.baseline_fuel_share_upper_constraint = Constraint(
        model.systems, model.fuels, model.years,
        rule=baseline_fuel_share_upper_rule
    )

    def baseline_feedstock_share_rule(m, sys, fs, yr):
        """Enforce that in the baseline year, each system's feedstock consumption
        matches baseline production × feedstock share × (optionally) feedstock intensity."""

        # Only apply if capacity is positive in the first year
        if yr == first_year and fs in m.baseline_feedstocks[sys] and m.capacity_plan[sys, yr] > 0:
            # Find the correct index for this feedstock
            idx = m.baseline_feedstocks[sys].index(fs)

            # Calculate target value
            share = m.baseline_feedstock_shares[sys][idx]
            target = share * m.production[sys, yr] * m.feedstock_eff_param[fs, yr]
            
            # Return only the lower bound constraint
            return m.feedstock_consumption[sys, fs, yr] >= 0.95 * target
        else:
            return Constraint.Skip

    model.baseline_feedstock_share_constraint = Constraint(
        model.systems,
        model.feedstocks,
        model.years,
        rule=baseline_feedstock_share_rule
    )
    
    # Add upper bound for feedstock share as a separate constraint
    def baseline_feedstock_share_upper_rule(m, sys, fs, yr):
        """Enforce upper bound for baseline feedstock consumption."""
        if yr == first_year and fs in m.baseline_feedstocks[sys] and m.capacity_plan[sys, yr] > 0:
            idx = m.baseline_feedstocks[sys].index(fs)
            share = m.baseline_feedstock_shares[sys][idx]
            target = share * m.production[sys, yr] * m.feedstock_eff_param[fs, yr]
            
            return m.feedstock_consumption[sys, fs, yr] <= 1.05 * target
        else:
            return Constraint.Skip
            
    model.baseline_feedstock_share_upper_constraint = Constraint(
        model.systems,
        model.feedstocks,
        model.years,
        rule=baseline_feedstock_share_upper_rule
    )

    return model

def fuel_constraints(model, data):

    # 4.5. Fuel Constraints
    def fuel_production_constraint_rule(m, sys, yr):
        # Only apply if system has positive capacity
        if m.capacity_plan[sys, yr] > 0:
            return m.production[sys, yr] == sum(
                m.fuel_consumption[sys, fuel, yr] / m.fuel_eff_param[fuel, yr] for fuel in m.fuels
            )
        return Constraint.Skip

    model.fuel_production_constraint = Constraint(model.systems, model.years, rule=fuel_production_constraint_rule)

    def fuel_selection_rule(m, sys, yr):
        # Only apply if system has positive capacity
        if m.capacity_plan[sys, yr] > 0:
            return sum(m.fuel_select[sys, fuel, yr] for fuel in m.fuels) >= 1
        return Constraint.Skip

    model.fuel_selection_constraint = Constraint(model.systems, model.years, rule=fuel_selection_rule)


    def total_fuel_consumption_rule(m, sys, yr):
        # Only apply if system has positive capacity
        if m.capacity_plan[sys, yr] > 0:
            # Total fuel consumption per system for each year
            return m.total_fuel_consumption[sys, yr] == sum(
                m.fuel_consumption[sys, fuel, yr] for fuel in m.fuels
            )
        else:
            # If no capacity, ensure total fuel consumption is zero
            return m.total_fuel_consumption[sys, yr] == 0

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
    # Get limited technologies if provided
    limited_technologies = kwargs.get('limited_technologies', {'BF-BOF': 2, 'EAF': 4})
    
    # Print the technologies in model to help debug
    print("Available technologies in model:", list(model.technologies))
    
    # Apply technology usage constraints if limited_technologies is not empty
    if limited_technologies:
        model = technology_usage_constraints(model, limited_technologies=limited_technologies)

    # Add capacity constraint as a minimum requirement (as per requirements)
    def capacity_constraint_rule(m, sys, yr):
        # If a capacity is specified, enforce it as a minimum
        if m.capacity_plan[sys, yr] > 0:
            return m.production[sys, yr] >= m.capacity_plan[sys, yr]
        else:
            # If no capacity is specified, production must be zero
            return m.production[sys, yr] == 0
    
    model.capacity_constraint = Constraint(
        model.systems, model.years, rule=capacity_constraint_rule
    )
    
    # Add maximum production constraint to prevent unrealistically high production
    def maximum_production_rule(m, sys, yr):
        if m.capacity_plan[sys, yr] > 0:
            # Set max production to a reasonable multiple of minimum (e.g., 1.5x)
            return m.production[sys, yr] <= 1.5 * m.capacity_plan[sys, yr]
        return Constraint.Skip
    
    model.maximum_production_constraint = Constraint(
        model.systems, model.years, rule=maximum_production_rule
    )
    
    # Constraint to enforce system activation based on capacity - with more flexibility
    def system_activation_rule(m, sys, yr):
        # A system is active in years where its capacity is greater than zero
        if m.capacity_plan[sys, yr] > 0:
            # At least one technology must be active (but allow more for transition years)
            return sum(m.active_technology[sys, tech, yr] for tech in m.technologies) >= 1
        else:
            # No technology should be active if capacity is zero
            return sum(m.active_technology[sys, tech, yr] for tech in m.technologies) == 0
    
    model.system_activation_constraint = Constraint(
        model.systems, model.years, rule=system_activation_rule
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
            if yr in prev_year and prev_year[yr] in m.years:
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
        if yr > min(m.years) and yr-1 in m.years:
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

    # Allow no more than one active technology per system per year if capacity > 0
    def single_active_technology_rule(m, sys, yr):
        if m.capacity_plan[sys, yr] > 0:
            # Ensure only one technology is active in a given year per system
            return sum(m.active_technology[sys, tech, yr] for tech in m.technologies) <= 1
        return Constraint.Skip

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

    return model

def lifespan_constraints(model):
    def enforce_replacement_or_renewal_years_rule(m, sys, tech, yr):
        # Skip if capacity is zero for this system in this year
        if m.capacity_plan[sys, yr] <= 0:
            return Constraint.Skip
            
        # Get first year of model time horizon
        first_year = min(m.years)
        
        # Skip for the first year or if previous year is not in model.years
        if yr == first_year or yr-1 not in m.years:
            return Constraint.Skip
            
        introduced_year = m.introduced_year_param[sys]
        lifespan = m.lifespan_param[tech]
        
        # Handle division by zero
        if lifespan == 0:
            return Constraint.Skip
            
        if yr > introduced_year and (yr - introduced_year) % lifespan == 0:
            return m.replace[sys, tech, yr] + m.renew[sys, tech, yr] == m.active_technology[sys, tech, yr-1]
        return Constraint.Skip

    model.enforce_replacement_or_renewal_years_constraint = Constraint(
        model.systems, model.technologies, model.years, rule=enforce_replacement_or_renewal_years_rule
    )

    def enforce_no_continuation_in_replacement_years_rule(m, sys, tech, yr):
        # Skip if capacity is zero for this system in this year
        if m.capacity_plan[sys, yr] <= 0:
            return Constraint.Skip
            
        introduced_year = m.introduced_year_param[sys]
        lifespan = m.lifespan_param[tech]
        
        # Handle division by zero
        if lifespan == 0:
            return Constraint.Skip
            
        if yr > introduced_year and (yr - introduced_year) % lifespan == 0:
            return m.continue_technology[sys, tech, yr] == 0
        return Constraint.Skip

    model.enforce_no_continuation_in_replacement_years_constraint = Constraint(
        model.systems, model.technologies, model.years, rule=enforce_no_continuation_in_replacement_years_rule
    )

    return model

def technology_usage_constraints(model, limited_technologies=None):
    """
    Add constraints to limit the number of facilities using specific technologies.
    
    Parameters:
    -----------
    model : Pyomo model
        The optimization model
    limited_technologies : dict
        A dictionary with technology names as keys and maximum allowed facilities as values.
        Example: {'FX': 2, 'EAF': 2}
    
    Returns:
    --------
    model : Pyomo model
        The model with technology usage constraints added
    """
    if not limited_technologies:
        return model
    
    first_year = min(model.years)
    
    for tech, max_facilities in limited_technologies.items():
        if tech not in model.technologies:
            print(f"Warning: Technology '{tech}' not found in model technologies. Skipping constraint.")
            continue
            
        def tech_usage_limit_rule(m, tech=tech, max_facilities=max_facilities, yr=None):
            """Limit the number of facilities using the specified technology in a given year"""
            if yr is None:
                return Constraint.Skip
                
            # Only apply limit in years after the first year to avoid baseline conflicts
            if yr > first_year:
                return sum(m.active_technology[sys, tech, yr] for sys in m.systems) <= max_facilities
            return Constraint.Skip
        
        constraint_name = f"max_{tech}_facilities_constraint"
        setattr(model, constraint_name, Constraint(model.years, rule=lambda m, yr, t=tech, mf=max_facilities: 
                                                   tech_usage_limit_rule(m, t, mf, yr)))
    
    return model
