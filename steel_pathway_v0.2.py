from pyomo.environ import (
    ConcreteModel, Var, NonNegativeReals, Binary, Param,
    Objective, Constraint, SolverFactory, Set, ConstraintList, minimize
)

def build_model_for_system(system_name, baseline_row, data):
    """
    Build a Pyomo optimization model for a single furnace site (system),
    ensuring that every replacement or renewal enforces a continuation period.
    """
    model = ConcreteModel()

    # Define sets from the loaded data
    model.technologies = Set(initialize=data['technology'].index.tolist())
    model.fuels = Set(initialize=data['fuel_cost'].index.tolist())
    model.materials = Set(initialize=data['material_cost'].index.tolist())

    # Define all years
    all_years = sorted([int(yr) for yr in data['capex'].columns.tolist()])
    initial_year = 2025  # Fixed baseline year
    optimization_years = all_years  # Including the initial year
    model.years = Set(initialize=optimization_years)

    # Parameters from the baseline
    production = baseline_row['production']
    baseline_tech = baseline_row['technology']
    baseline_fuel = baseline_row['fuel']
    introduced_year = baseline_row['introduced_year']

    # Parameters
    model.capex_param = Param(
        model.technologies, model.years,
        initialize=lambda m, tech, yr: data['capex'].loc[tech, yr],
        default=0.0
    )
    model.opex_param = Param(
        model.technologies, model.years,
        initialize=lambda m, tech, yr: data['opex'].loc[tech, yr],
        default=0.0
    )
    model.renewal_param = Param(
        model.technologies, model.years,
        initialize=lambda m, tech, yr: data['renewal'].loc[tech, yr],
        default=0.0
    )
    model.fuel_cost_param = Param(
        model.fuels, model.years,
        initialize=lambda m, f, yr: data['fuel_cost'].loc[f, yr],
        default=0.0
    )
    model.fuel_eff_param = Param(
        model.fuels, model.years,
        initialize=lambda m, f, yr: data['fuel_efficiency'].loc[f, yr],
        default=0.0
    )
    model.material_cost_param = Param(
        model.materials, model.years,
        initialize=lambda m, mat, yr: data['material_cost'].loc[mat, yr],
        default=0.0
    )
    model.material_eff_param = Param(
        model.materials, model.years,
        initialize=lambda m, mat, yr: data['material_efficiency'].loc[mat, yr],
        default=0.0
    )

    # Decision variables
    model.fuel_select = Var(
        model.fuels, model.years,
        domain=Binary,
        doc="1 if fuel is selected in a given year, else 0"
    )
    model.material_select = Var(
        model.materials, model.years,
        domain=Binary,
        doc="1 if material is selected in a given year, else 0"
    )

    # Decision variables for technology management
    model.continue_technology = Var(
        model.technologies, model.years,
        domain=Binary,
        doc="1 if the technology is continued from the previous year, else 0"
    )
    model.replace = Var(
        model.technologies, model.years,
        domain=Binary,
        doc="1 if technology is replaced in a given year, else 0"
    )
    model.renew = Var(
        model.technologies, model.years,
        domain=Binary,
        doc="1 if the technology is renewed in a given year, else 0"
    )

    model.fuel_consumption = Var(
        model.fuels, model.years,
        domain=NonNegativeReals,
        doc="Amount of fuel consumed in a given year"
    )

    # Active technology variable
    model.active_technology = Var(
        model.technologies, model.years,
        domain=Binary,
        doc="1 if technology is active in a given year, else 0"
    )

    # Define lifespan as a parameter
    model.lifespan_param = Param(
        model.technologies,
        initialize=lambda m, tech: data['technology'].loc[tech, 'lifespan'],
        default=0
    )

    # Constraints

    # 1. Hard Baseline Fuel Constraint
    def hard_baseline_fuel_rule(m, f, yr):
        if yr == initial_year:  # Lock the fuel selection for the initial year
            if f == baseline_fuel:
                return m.fuel_select[f, yr] == 1  # Must use the baseline fuel
            else:
                return m.fuel_select[f, yr] == 0  # Other fuels cannot be selected
        return Constraint.Skip

    model.hard_baseline_fuel_constraint = Constraint(
        model.fuels, model.years, rule=hard_baseline_fuel_rule
    )

    # 2. First Year Constraint: Only baseline technology can continue
    def first_year_constraint(m, tech, yr):
        # First year: Only baseline technology can continue
        if yr == initial_year:
            if tech == baseline_tech:
                return m.continue_technology[tech, yr] == 1
            else:
                return m.continue_technology[tech, yr] + m.replace[tech, yr] + m.renew[tech, yr] == 0
        return Constraint.Skip

    model.first_year_constraint = Constraint(model.technologies, model.years, rule=first_year_constraint)

    # 3. Enforce Continuation Before Initial Lifespan Ends
    def enforce_continuation_before_lifespan(m, tech, yr):
        lifespan = m.lifespan_param[tech]
        end_of_initial_lifespan = introduced_year + lifespan

        # From initial_year to end_of_initial_lifespan - 1: Continuation only
        if initial_year < yr < end_of_initial_lifespan:
            if tech == baseline_tech:
                return m.continue_technology[tech, yr] == 1
            else:
                return m.continue_technology[tech, yr] + m.replace[tech, yr] + m.renew[tech, yr] == 0
        return Constraint.Skip

    model.enforce_continuation_before_lifespan_constraint = Constraint(
        model.technologies, model.years, rule=enforce_continuation_before_lifespan
    )

    # 4. Continuity Active Constraint
    def continuity_active_rule(m, tech, yr):
        if yr > initial_year:  # Skip the first year
            return m.continue_technology[tech, yr] <= m.active_technology[tech, yr - 1]
        return Constraint.Skip

    model.continuity_active_constraint = Constraint(
        model.technologies, model.years, rule=continuity_active_rule
    )

    # 5. Active Technology Constraint
    def active_technology_rule(m, tech, yr):
        # Active if continued, replaced, or renewed
        return m.active_technology[tech, yr] == m.continue_technology[tech, yr] + m.replace[tech, yr] + m.renew[tech, yr]

    model.active_technology_constraint = Constraint(
        model.technologies, model.years, rule=active_technology_rule
    )

    # 6. Introduction Year Constraint
    def introduction_year_constraint_rule(m, tech, yr):
        introduction_year = data['technology_introduction'].get(tech, initial_year)
        if yr < introduction_year:
            return m.replace[tech, yr] == 0
        return Constraint.Skip

    model.introduction_year_constraint = Constraint(
        model.technologies, model.years, rule=introduction_year_constraint_rule
    )

    # 7. Ensure Only One Fuel is Selected Each Year
    def fuel_selection_rule(m, yr):
        return sum(m.fuel_select[f, yr] for f in m.fuels) == 1

    model.fuel_selection_constraint = Constraint(model.years, rule=fuel_selection_rule)

    # 8. Ensure Only One Material is Selected Each Year
    def material_selection_rule(m, yr):
        return sum(m.material_select[mat, yr] for mat in m.materials) == 1

    model.material_selection_constraint = Constraint(model.years, rule=material_selection_rule)

    # 9. Production Constraint
    def production_constraint_rule(m, yr):
        return production == sum(
            m.fuel_consumption[f, yr] / m.fuel_eff_param[f, yr] for f in m.fuels
        )

    model.production_constraint = Constraint(model.years, rule=production_constraint_rule)

    # 10. Link Fuel Consumption and Selection
    M_BIG = 1e6  # A large number to link binary and continuous variables

    def fuel_consumption_limit_rule(m, f, yr):
        return m.fuel_consumption[f, yr] <= m.fuel_select[f, yr] * M_BIG

    model.fuel_consumption_limit_constraint = Constraint(
        model.fuels, model.years, rule=fuel_consumption_limit_rule
    )

    # 11. Technology-Fuel Pairing Constraint
    def fuel_technology_link_rule(m, yr, f):
        compatible_replacements = [
            tech for tech in m.technologies if f in data['technology_fuel_pairs'].get(tech, [])
        ]
        return sum(m.replace[tech, yr] for tech in compatible_replacements) >= m.fuel_select[f, yr]

    model.fuel_technology_link_constraint = Constraint(
        model.years, model.fuels, rule=fuel_technology_link_rule
    )

    # 12. Technology-Material Pairing Constraint
    def material_technology_link_rule(m, yr, mat):
        compatible_replacements = [
            tech for tech in m.technologies if mat in data['technology_material_pairs'].get(tech, [])
        ]
        return sum(m.replace[tech, yr] for tech in compatible_replacements) >= m.material_select[mat, yr]

    model.material_technology_link_constraint = Constraint(
        model.years, model.materials, rule=material_technology_link_rule
    )

    # -----------------------------------------
    # New Constraints: Lifespan Continuation (Constraints 13-15)
    # -----------------------------------------

    # 13. Continuation Constraint: If replace or renew in yr, then continue for next 'lifespan' years
    # This ensures that if a technology is replaced or renewed in year 'yr', it continues for 'lifespan' years thereafter
    model.lifespan_continuation_constraints = ConstraintList()

    for tech in model.technologies:
        lifespan = model.lifespan_param[tech]
        for yr in model.years:
            for l in range(1, lifespan + 1):
                future_yr = yr + l
                if future_yr in model.years:
                    # If replace or renew in yr, then continue in future_yr
                    model.lifespan_continuation_constraints.add(
                        model.continue_technology[tech, future_yr] >= m.replace[tech, yr] + m.renew[tech, yr]
                    )

    # 14. Replacement/Renewal Block Constraint: During continuation period, no replace or renew
    # This prevents any replace or renew actions during the continuation period enforced by the above constraints
    model.replacement_block_constraints = ConstraintList()

    for tech in model.technologies:
        lifespan = model.lifespan_param[tech]
        for yr in model.years:
            for l in range(1, lifespan + 1):
                prev_yr = yr - l
                if prev_yr in model.years:
                    # If replace or renew occurred in prev_yr, then no replace or renew in yr
                    model.replacement_block_constraints.add(
                        model.replace[tech, yr] + model.renew[tech, yr] <= 1 - (model.replace[tech, prev_yr] + model.renew[tech, prev_yr])
                    )

    # (Optional) 15. Ensure Only One Technology is Active Each Year
    # Uncomment this section if only one technology can be active per year
    # def single_active_technology_rule(m, yr):
    #     return sum(m.active_technology[tech, yr] for tech in m.technologies) == 1
    #
    # model.single_active_technology_constraint = Constraint(model.years, rule=single_active_technology_rule)

    # -----------------------------------------
    # Objective function with levelized capex and opex
    # -----------------------------------------
    def total_cost_rule(m):
        return sum(
            sum(
                # Capex (levelized) for all active technologies
                m.capex_param[tech, yr] * production * m.active_technology[tech, yr]
                # Opex for all active technologies
                + m.opex_param[tech, yr] * production * m.active_technology[tech, yr]
                # Renewal costs
                + m.renewal_param[tech, yr] * production * m.renew[tech, yr]
                # Fuel costs
                + sum(
                    m.fuel_cost_param[f, yr] * production * m.fuel_select[f, yr]
                    for f in m.fuels
                )
                # Material costs
                + sum(
                    m.material_cost_param[mat, yr] * production * m.material_select[mat, yr]
                    for mat in m.materials
                )
                for tech in m.technologies
            )
            for yr in m.years
        )

    model.objective = Objective(rule=total_cost_rule, sense=minimize)

    return model


# -------------------------------------------------------------------------
# Main script to load data, loop over each furnace site, and solve
file_path = 'database/steel_data.xlsx'
data = load_data(file_path)

solver = SolverFactory('glpk')  # or another solver

results_dict = {}

for system_name in data['baseline'].index:
    print(f"\n=== Solving for furnace site: {system_name} ===")

    # Extract the row (Series) for the current furnace site
    baseline_row = data['baseline'].loc[system_name]

    # 1) Build the model
    m = build_model_for_system(system_name, baseline_row, data)

    # 2) Solve the model
    result = solver.solve(m, tee=True)

    if result.solver.status == 'ok' and result.solver.termination_condition == 'optimal':
        # Gather results for this system
        production_value = baseline_row['production']  # From the baseline_row

        # Fuel consumption data
        fuel_data = []
        for yr in m.years:
            for f in m.fuels:
                if m.fuel_select[f, yr].value > 0.5:
                    fuel_data.append({
                        "Year": yr,
                        "Fuel": f,
                        "Consumption (tons)": m.fuel_consumption[f, yr].value
                    })

        # Technology changes data
        technology_changes = []

        for yr in m.years:
            active_technology = None

            # Check if any replacement occurs in this year
            for tech in m.technologies:
                if m.replace[tech, yr].value > 0.5:
                    active_technology = tech
                    break  # Only one replacement can happen per year

            # If no replacement occurred, the baseline technology remains active
            if not active_technology:
                for tech in m.technologies:
                    if m.active_technology[tech, yr].value > 0.5:
                        active_technology = tech
                        break

            # Add the active technology for the year
            if active_technology:
                technology_changes.append({
                    "Year": yr,
                    "Technology": active_technology
                })

        # Save results
        results_dict[system_name] = {
            "Production": production_value,
            "Fuel Consumption": fuel_data,
            "Technology Changes": technology_changes
        }

    else:
        print(f"Solver failed for {system_name}. Status: {result.solver.status}, Condition: {result.solver.termination_condition}")
#
# Display results for all systems
for system_name, results in results_dict.items():
    print(f"\n=== Results for {system_name} ===")
    print(f"Production: {results['Production']} tons")
    print("\nFuel Consumption:")
    for fc in results['Fuel Consumption']:
        print(f"  Year {fc['Year']}: {fc['Fuel']} - {fc['Consumption (tons)']} tons")

    print("\nTechnology Changes:")
    for tc in results['Technology Changes']:
        print(f"  Year {tc['Year']}: {tc['Technology']}")