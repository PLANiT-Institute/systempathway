from pyomo.environ import (Constraint)

def emission_constraints(model,**kwargs):

    carbonprice_include = kwargs.get('carbonprice_include', False)

    BIG_M = max(model.production_param.values()) * max(model.fuel_eff_param.values())

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

    # def technology_activation_rule(m, sys, yr):
    #     return sum(m.active_technology[sys, tech, yr] for tech in m.technologies) == 1

    # model.technology_activation_constraint = Constraint(model.systems, model.years, rule=technology_activation_rule)

    return model

def baseline_constraints(model):
    # Ensure baseline technology is active and continued in the first year
    def baseline_technology_first_year_rule(m, sys, tech, yr):
        if yr == min(m.years) and tech == m.baseline_technology[sys]:
            # 만약 첫 해의 생산량이 0이면 스킵
            if m.production_param[sys, yr] == 0:
                return Constraint.Skip
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
    # --------------------------------------
    # 4.5.1 Production = sum of active fuel usage (by tech)
    # --------------------------------------
    def fuel_production_constraint_rule(m, sys, yr):
        """
        Production of system 'sys' at year 'yr' equals the sum of
        active fuel consumption for all technologies, adjusted by fuel efficiency.
        """
        return (
            m.production[sys, yr]
            == sum(
                m.active_fuel_consumption[sys, tech, f, yr] / m.fuel_eff_param[f, yr]
                for tech in m.technologies
                for f in m.fuels
            )
        )

    model.fuel_production_constraint = Constraint(
        model.systems, model.years,
        rule=fuel_production_constraint_rule
    )

    # --------------------------------------
    # 4.5.2 System-level fuel consumption = sum of tech-level consumption
    # --------------------------------------
    def fuel_system_sum_rule(m, sys, f, yr):
        """
        The system-level fuel consumption = sum of the tech-level active fuel consumption.
        This ensures that if a technology isn't valid for 'f', it remains 0.
        """
        return m.fuel_consumption[sys, f, yr] == sum(
            m.active_fuel_consumption[sys, tech, f, yr]
            for tech in m.technologies
        )

    model.fuel_system_sum_constraint = Constraint(
        model.systems, model.fuels, model.years,
        rule=fuel_system_sum_rule
    )

    # --------------------------------------
    # 4.5.3 Restrict usage if (tech, fuel) not allowed
    # --------------------------------------
    def restrict_fuel_usage_rule(m, sys, tech, f, yr):
        """
        If fuel 'f' is NOT in data['technology_fuel_pairs'][tech],
        force active_fuel_consumption[sys, tech, f, yr] == 0.
        """
        valid_fuels = data['technology_fuel_pairs']  # dict: { 'BF-BOF': ['Coal_BB',...], ... }
        if f not in valid_fuels[tech]:
            return m.active_fuel_consumption[sys, tech, f, yr] == 0
        return Constraint.Skip

    model.restrict_fuel_usage_constraint = Constraint(
        model.systems, model.technologies, model.fuels, model.years,
        rule=restrict_fuel_usage_rule
    )

    # --------------------------------------
    # 4.5.4 At least one fuel selected per system-year
    # --------------------------------------
    def fuel_selection_rule(m, sys, yr):
        return sum(m.fuel_select[sys, fuel, yr] for fuel in m.fuels) >= 1

    model.fuel_selection_constraint = Constraint(
        model.systems, model.years,
        rule=fuel_selection_rule
    )

    # --------------------------------------
    # 4.5.5 Summation of total fuel consumption
    # --------------------------------------
    def total_fuel_consumption_rule(m, sys, yr):
        return m.total_fuel_consumption[sys, yr] == sum(
            m.fuel_consumption[sys, fuel, yr] for fuel in m.fuels
        )

    model.total_fuel_consumption_constraint = Constraint(
        model.systems, model.years,
        rule=total_fuel_consumption_rule
    )

    # --------------------------------------
    # 4.5.6 Max/min share constraints (optional)
    # --------------------------------------
    M_fuel = max(model.production_param.values()) * max(model.fuel_eff_param.values())

    def fuel_max_share_constraint_rule(m, sys, tech, f, yr):
        if yr > min(m.years) and (tech, f) in data['fuel_max_ratio']:
            max_share = data['fuel_max_ratio'][(tech, f)]
            return m.fuel_consumption[sys, f, yr] <= (
                max_share * m.total_fuel_consumption[sys, yr]
                + M_fuel * (1 - m.active_technology[sys, tech, yr])
            )
        return Constraint.Skip

    model.fuel_max_share_constraint = Constraint(
        model.systems, model.technologies, model.fuels, model.years,
        rule=fuel_max_share_constraint_rule
    )

    def fuel_min_share_constraint_rule(m, sys, tech, f, yr):
        if yr > min(m.years) and (tech, f) in data['fuel_min_ratio']:
            intro_year = data['fuel_introduction'].loc[f]
            if yr < intro_year:
                return m.fuel_consumption[sys, f, yr] == 0

            min_share = data['fuel_min_ratio'][(tech, f)]
            return m.fuel_consumption[sys, f, yr] >= (
                min_share * m.total_fuel_consumption[sys, yr]
                - M_fuel * (1 - m.active_technology[sys, tech, yr])
            )
        return Constraint.Skip

    model.fuel_min_share_constraint = Constraint(
        model.systems, model.technologies, model.fuels, model.years,
        rule=fuel_min_share_constraint_rule
    )

    return model


def feedstock_constraints(model, data):

    # 1) 생산량 = (기술별 feedstock 소모량 / 효율)의 합
    def feedstock_production_constraint_rule(m, sys, yr):
        return m.production[sys, yr] == sum(
            m.active_feedstock_consumption[sys, tech, fs, yr] / m.feedstock_eff_param[fs, yr]
            for tech in m.technologies
            for fs in m.feedstocks
        )

    model.feedstock_production_constraint = Constraint(
        model.systems, model.years,
        rule=feedstock_production_constraint_rule
    )

    # 2) 시스템 차원의 feedstock 소비량 = (기술별 소비량)의 합
    def feedstock_system_sum_rule(m, sys, fs, yr):
        return m.feedstock_consumption[sys, fs, yr] == sum(
            m.active_feedstock_consumption[sys, tech, fs, yr]
            for tech in m.technologies
        )

    model.feedstock_system_sum_constraint = Constraint(
        model.systems, model.feedstocks, model.years,
        rule=feedstock_system_sum_rule
    )

    # 3) (기술, feedstock) 조합이 유효하지 않으면 소비량 = 0
    def restrict_feedstock_usage_rule(m, sys, tech, fs, yr):
        valid_feedstocks = data['technology_feedstock_pairs']  # 예: {"BF-BOF": ["Iron ore_BB", "Scrap_BB"], ...}
        if fs not in valid_feedstocks[tech]:
            # 이 기술에 해당 원료(fs)는 사용 불가 → active_feedstock_consumption = 0
            return m.active_feedstock_consumption[sys, tech, fs, yr] == 0
        return Constraint.Skip

    model.restrict_feedstock_usage_constraint = Constraint(
        model.systems, model.technologies, model.feedstocks, model.years,
        rule=restrict_feedstock_usage_rule
    )

    # 4) 시스템별로 원료 선택이 최소 1개 이상? (선택적)
    def feedstock_selection_rule(m, sys, yr):
        return sum(m.feedstock_select[sys, fs, yr] for fs in m.feedstocks) >= 1

    model.feedstock_selection_constraint = Constraint(
        model.systems, model.years,
        rule=feedstock_selection_rule
    )

    # 5) 총원료 소비 (편의상 집계)
    def total_feedstock_consumption_rule(m, sys, yr):
        return m.total_feedstock_consumption[sys, yr] == sum(
            m.feedstock_consumption[sys, fs, yr] for fs in m.feedstocks
        )

    model.total_feedstock_consumption_constraint = Constraint(
        model.systems, model.years,
        rule=total_feedstock_consumption_rule
    )

    # 6) feedstock별 최대·최소 점유율 (필요에 따라 유지)
    M_fs = max(model.production_param.values()) * max(model.feedstock_eff_param.values())

    def feedstock_max_share_constraint_rule(m, sys, tech, fs, yr):
        if yr > min(m.years) and (tech, fs) in data['feedstock_max_ratio']:
            max_share = data['feedstock_max_ratio'][(tech, fs)]
            return m.feedstock_consumption[sys, fs, yr] <= (
                max_share * m.total_feedstock_consumption[sys, yr]
                + M_fs * (1 - m.active_technology[sys, tech, yr])
            )
        return Constraint.Skip

    model.feedstock_max_share_constraint = Constraint(
        model.systems, model.technologies, model.feedstocks, model.years,
        rule=feedstock_max_share_constraint_rule
    )

    def feedstock_min_share_constraint_rule(m, sys, tech, fs, yr):
        if yr > min(m.years) and (tech, fs) in data['feedstock_min_ratio']:
            intro_year = data['feedstock_introduction'].loc[fs]
            if yr < intro_year:
                return m.feedstock_consumption[sys, fs, yr] == 0

            min_share = data['feedstock_min_ratio'][(tech, fs)]
            return m.feedstock_consumption[sys, fs, yr] >= (
                min_share * m.total_feedstock_consumption[sys, yr]
                - M_fs * (1 - m.active_technology[sys, tech, yr])
            )
        return Constraint.Skip

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
        if m.production_param[sys, yr] == 0:
            # 생산 0이면 활성화 기술이 없어도 됨
            return Constraint.Skip
        else:
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

    def production_target_rule(m, sys, yr):
        return m.production[sys, yr] == m.production_param[sys, yr]

    model.production_target_constraint = Constraint(model.systems, model.years, rule=production_target_rule)



    def enforce_zero_production_inactive(m, sys, yr):
        if m.production_param[sys, yr] == 0:
            return sum(m.active_technology[sys, tech, yr] for tech in m.technologies) == 0
        return Constraint.Skip

    model.zero_production_inactive_constraint = Constraint(
        model.systems, model.years, rule=enforce_zero_production_inactive
    )

    def enforce_replace_when_inactive_to_active(m, sys, yr):
        # Skip first year (no previous year)
        if yr == min(m.years):
            return Constraint.Skip

        # 만약 작년(yr-1) 생산량이 0이었다면 => 시스템 비활성
        if m.production_param[sys, yr - 1] == 0:
            # 올해(yr)에 시스템이 활성화된다면 => sum(continue + renew) = 0
            # 즉 replace 외에는 안 됨.
            return sum(
                m.continue_technology[sys, tech, yr] + m.renew[sys, tech, yr]
                for tech in m.technologies
            ) == 0
        return Constraint.Skip

    model.replace_when_inactive_to_active_constraint = Constraint(
        model.systems, model.years, rule=enforce_replace_when_inactive_to_active
    )

    def fix_baseline_late_start_rule(m, sys, tech, yr):
        """
        If a system was inactive in (yr-1) and becomes active in yr,
        only the baseline technology can do replace=1, and all others must be 0.
        """
        # Skip the very first model year (no previous year to compare).
        if yr == min(m.years):
            return Constraint.Skip

        prev_year = yr - 1

        # Check if we have a "late start" at year Y:
        # i.e. production_param is 0 in year (Y-1) and > 0 in year Y.
        if (m.production_param[sys, prev_year] == 0) and (m.production_param[sys, yr] > 0):
            baseline_tech = m.baseline_technology[sys]
            if tech == baseline_tech:
                # The baseline tech must do replace=1
                return m.replace[sys, tech, yr] == 1
            else:
                # All other technologies must remain 0 in that year
                return (
                        m.replace[sys, tech, yr]
                        + m.renew[sys, tech, yr]
                        + m.continue_technology[sys, tech, yr]
                ) == 0
        return Constraint.Skip

    model.fix_baseline_late_start_constraint = Constraint(
        model.systems,
        model.technologies,
        model.years,
        rule=fix_baseline_late_start_rule
    )

    return model

def lifespan_constraints(model):
    def enforce_replacement_or_renewal_years_rule(m, sys, tech, yr):
        introduced_year = m.introduced_year_param[sys]
        lifespan = m.lifespan_param[tech]
        if (yr - introduced_year) >= 0 and (yr - introduced_year) % lifespan != 0:
            return m.replace[sys, tech, yr] + m.renew[sys, tech, yr] == 0
        return Constraint.Skip

    model.enforce_replacement_or_renewal_years_constraint = Constraint(
        model.systems, model.technologies, model.years, rule=enforce_replacement_or_renewal_years_rule
    )

    def enforce_no_continuation_in_replacement_years_rule(m, sys, tech, yr):
        introduced_year = m.introduced_year_param[sys]
        lifespan = m.lifespan_param[tech]
        if (yr - introduced_year) >= 0 and (yr - introduced_year) % lifespan == 0:
            return m.continue_technology[sys, tech, yr] == 0
        return Constraint.Skip

    model.enforce_no_continuation_in_replacement_years_constraint = Constraint(
        model.systems, model.technologies, model.years, rule=enforce_no_continuation_in_replacement_years_rule
    )

    return model
