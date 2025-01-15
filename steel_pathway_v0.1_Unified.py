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
    data['emission'] = pd.read_excel(file_path, sheet_name='emission', index_col=0)
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
    data['technology_fuel_pairs'] = pd.read_excel(file_path, sheet_name='technology_fuel_pairs') \
        .groupby('technology')['fuel'].apply(list).to_dict()

    # Import and structure fuel max ratios
    technology_fuel_pairs_df = pd.read_excel(file_path, sheet_name='technology_fuel_pairs')
    data['fuel_max_ratios'] = technology_fuel_pairs_df.set_index(['technology', 'fuel'])['max'].to_dict()

    # Import and group Technology-Material Pairs
    data['technology_material_pairs'] = pd.read_excel(file_path, sheet_name='technology_material_pairs') \
        .groupby('technology')['material'].apply(list).to_dict()

    # Import and structure material max ratios
    technology_material_pairs_df = pd.read_excel(file_path, sheet_name='technology_material_pairs')
    data['material_max_ratios'] = technology_material_pairs_df.set_index(['technology', 'material'])['max'].to_dict()

    # Restructure the data into a dictionary
    data['material_max_ratios'] = technology_material_pairs_df.set_index(['technology', 'material'])['max'].to_dict()

    data['technology_introduction'] = pd.read_excel(file_path, sheet_name='technology', index_col=0)['introduction'].to_dict()

    # Load emission-related data
    data['emission_system'] = pd.read_excel(file_path, sheet_name='emission_system', index_col=0)
    data['fuel_emission'] = pd.read_excel(file_path, sheet_name='fuel_emission', index_col=0)
    data['material_emission'] = pd.read_excel(file_path, sheet_name='material_emission', index_col=0)
    data['technology_ei'] = pd.read_excel(file_path, sheet_name='technology_ei', index_col=0)

    return data


def build_unified_model(data):
    """
    Build a Pyomo optimization model for a single furnace site (system),
    ensuring that the initial year maintains the baseline technology
    and is excluded from the optimization years.
    """
    model = ConcreteModel()
    BIG_M = 1e9
    # Unified Sets
    model.systems = Set(initialize=data['baseline'].index.tolist())
    model.technologies = Set(initialize=data['technology'].index.tolist())
    model.fuels = Set(initialize=data['fuel_cost'].index.tolist())
    model.materials = Set(initialize=data['material_cost'].index.tolist())
    model.years = Set(initialize=sorted([int(yr) for yr in data['capex'].columns.tolist()]))

    # Exclude 2025 from the optimization years
    all_years = sorted([int(yr) for yr in data['capex'].columns.tolist()])
    initial_year = 2025  # Fixed baseline year
    optimization_years = all_years
    model.years = Set(initialize=optimization_years)
    # Parameters from the baseline

    introduced_year_data = data['baseline']['introduced_year'].to_dict()

    # Parameters
    model.capex_param = Param(model.technologies, model.years,initialize=lambda m, tech, yr: data['capex'].loc[tech, yr], default=0.0)
    model.opex_param = Param(model.technologies, model.years, initialize=lambda m, tech, yr: data['opex'].loc[tech, yr],default=0.0)
    model.renewal_param = Param(model.technologies, model.years,initialize=lambda m, tech, yr: data['renewal'].loc[tech, yr], default=0.0)
    model.fuel_cost_param = Param(model.fuels, model.years, initialize=lambda m, f, yr: data['fuel_cost'].loc[f, yr],default=0.0)
    model.fuel_eff_param = Param(model.fuels, model.years,initialize=lambda m, f, yr: data['fuel_efficiency'].loc[f, yr], default=0.0)
    model.material_cost_param = Param(model.materials, model.years,initialize=lambda m, mat, yr: data['material_cost'].loc[mat, yr], default=0.0)
    model.material_eff_param = Param(model.materials, model.years,initialize=lambda m, mat, yr: data['material_efficiency'].loc[mat, yr],default=0.0)
    # Parameters for Lifespan and Introduction Year
    model.lifespan_param = Param(model.technologies,initialize=lambda m, tech: data['technology'].loc[tech, 'lifespan'], default=0)
    model.introduced_year_param = Param(model.systems,initialize=lambda m, sys: introduced_year_data[sys])
    # **Emission Parameters with Yearly Dimensions**
    model.fuel_emission = Param(model.fuels, model.years,initialize=lambda m, f, yr: data['fuel_emission'].loc[f, yr],default=0.0)
    model.material_emission = Param(model.materials, model.years,initialize=lambda m, mat, yr: data['material_emission'].loc[mat, yr],default=0.0)
    model.technology_ei = Param(model.technologies, model.years,initialize=lambda m, tech, yr: data['technology_ei'].loc[tech, yr],default=1.0)
    # Define emission_limit as a parameter indexed only by years
    model.emission_limit = Param(model.years,initialize=lambda m, yr: data['emission'].loc['global', yr], default=0)
    # Parameters for maximum fuel and material ratios
    # Initialize fuel max ratio parameter
    model.fuel_max_ratio = Param(model.technologies, model.fuels,initialize=lambda m, tech, fuel: data['fuel_max_ratios'].get((tech, fuel), 0),default=0.0)
    model.material_max_ratio = Param(model.technologies, model.materials,initialize=lambda m, tech, mat: data['material_max_ratios'].get((tech, mat), 0),default=0.0)
    model.technology_introduction = Param(model.technologies,initialize=lambda m, tech: data['technology'].loc[tech, 'introduction'],default=0)  # Provide a default value for technologies with no introduction year)
    model.fuel_eff_param = Param(model.fuels, model.years,initialize=lambda m, f, yr: data['fuel_efficiency'].loc[f, yr],default=1.0)

    model.production = Var(model.systems, model.years, domain=NonNegativeReals)
    model.fuel_select = Var(model.systems, model.fuels, model.years, domain=Binary)
    model.material_select = Var(model.systems, model.materials, model.years, domain=Binary)
    model.active_technology = Var(model.systems, model.technologies, model.years, domain=Binary)
    model.replace = Var(model.systems, model.technologies, model.years, domain=Binary)
    model.renew = Var(model.systems, model.technologies, model.years, domain=Binary)
    model.continue_technology = Var(model.systems, model.technologies, model.years, domain=Binary)
    model.fuel_consumption = Var(model.systems, model.fuels, model.years, domain=NonNegativeReals)
    model.material_consumption = Var(model.systems, model.materials, model.years, domain=NonNegativeReals)
    model.emission_by_tech = Var(model.systems, model.technologies, model.years, domain=NonNegativeReals)

    # Constraints

    """
    Global constriants
    """

    def global_emission_limit_rule(m, yr):
        return sum(
            m.emission_by_tech[sys, tech, yr]
            for sys in m.systems
            for tech in m.technologies
        ) <= m.emission_limit[yr]

    model.global_emission_limit_constraint = Constraint(model.years, rule=global_emission_limit_rule)

    # Each system must have exactly one active technology per year
    def one_active_technology_rule(m, sys, yr):
        return sum(m.active_technology[sys, tech, yr] for tech in m.technologies) == 1

    model.one_active_technology_constraint = Constraint(
        model.systems, model.years, rule=one_active_technology_rule)

    """
    Emission Constraints (Unified Model)
    """

    def emission_by_tech_rule(m, sys, tech, yr):
        return m.emission_by_tech[sys, tech, yr] == (
                m.technology_ei[tech, yr] * (
                sum(m.fuel_emission[f, yr] * m.fuel_consumption[sys, f, yr] for f in m.fuels) +
                sum(m.material_emission[mat, yr] * m.material_consumption[sys, mat, yr] for mat in m.materials)
        )
        )

    model.emission_by_tech_constraint = Constraint(model.systems, model.technologies, model.years,
                                                   rule=emission_by_tech_rule)

    # Total Emission Constraint per Year (System-Wide)
    def total_emission_limit_rule(m, yr):
        return sum(
            m.emission_by_tech[sys, tech, yr] for sys in m.systems for tech in m.technologies
        ) <= m.emission_limit[yr]

    model.total_emission_limit_constraint = Constraint(model.years, rule=total_emission_limit_rule)


    """
    Other baseline constraints (Unified Model)
    """

    def hard_baseline_fuel_rule(m, sys, f, yr):
        if yr == 2025:  # Lock the fuel selection for the initial year
            baseline_fuel = data['baseline'].loc[sys, 'fuel']
            if f == baseline_fuel:
                return m.fuel_select[sys, f, yr] == 1  # Must use the baseline fuel
            else:
                return m.fuel_select[sys, f, yr] == 0  # Other fuels cannot be selected
        return Constraint.Skip

    model.hard_baseline_fuel_constraint = Constraint(
        model.systems, model.fuels, model.years, rule=hard_baseline_fuel_rule
    )

    def first_year_constraint(m, sys, tech, yr):
        # First year: Only baseline technology can continue
        if yr == min(m.years):
            baseline_tech = data['baseline'].loc[sys, 'technology']
            if tech == baseline_tech:
                return m.continue_technology[sys, tech, yr] == 1
            else:
                return m.continue_technology[sys, tech, yr] + m.replace[sys, tech, yr] + m.renew[sys, tech, yr] == 0
        return Constraint.Skip

    model.first_year_constraint = Constraint(model.systems, model.technologies, model.years, rule=first_year_constraint)

    def enforce_continuation_before_lifespan(m, sys, tech, yr):
        introduced_year = data['baseline'].loc[sys, 'introduced_year']
        lifespan = m.lifespan_param[tech]
        end_of_lifespan = introduced_year + lifespan

        # From first year to end_of_lifespan - 1: Continuation only
        if min(m.years) < yr < end_of_lifespan:
            baseline_tech = data['baseline'].loc[sys, 'technology']
            if tech == baseline_tech:
                return m.continue_technology[sys, tech, yr] == 1
            else:
                return m.continue_technology[sys, tech, yr] + m.replace[sys, tech, yr] + m.renew[sys, tech, yr] == 0
        return Constraint.Skip

    model.enforce_continuation_before_lifespan_constraint = Constraint(
        model.systems, model.technologies, model.years, rule=enforce_continuation_before_lifespan
    )

    # If a technology is continued, it must have been active in the previous year
    def continuity_active_rule(m, sys, tech, yr):
        if yr > min(m.years):  # Skip the first year
            return m.continue_technology[sys, tech, yr] <= m.active_technology[sys, tech, yr - 1]
        return Constraint.Skip

    model.continuity_active_constraint = Constraint(
        model.systems, model.technologies, model.years, rule=continuity_active_rule
    )

    def enforce_exclusivity_rule(m, sys, tech, yr):
        return m.replace[sys, tech, yr] + m.renew[sys, tech, yr] + m.continue_technology[sys, tech, yr] <= 1

    model.enforce_exclusivity = Constraint(model.systems, model.technologies, model.years, rule=enforce_exclusivity_rule)

    def active_technology_rule(m, sys, tech, yr):
        lifespan = m.lifespan_param[tech]
        introduced_year = data['baseline'].loc[sys, 'introduced_year']
        end_of_lifespan = introduced_year + lifespan

        # Determine replacement/renewal years
        if (yr - introduced_year) % lifespan == 0 and (yr - introduced_year) >= lifespan:
            # At replacement/renewal years
            return m.active_technology[sys, tech, yr] == m.replace[sys, tech, yr] + m.renew[sys, tech, yr]

        elif yr > introduced_year:
            # Before or after replacement/renewal years
            return m.active_technology[sys, tech, yr] == m.continue_technology[sys, tech, yr]

        return Constraint.Skip  # Skip years outside the modeling range

    model.active_technology_constraint = Constraint(
        model.systems, model.technologies, model.years, rule=active_technology_rule
    )

    def same_technology_renewal_rule(m, sys, tech, yr):
        if yr > min(m.years):  # Skip the first year
            # If the technology was active in the previous year, it cannot be replaced but must be renewed
            return m.replace[sys, tech, yr] <= 1 - m.active_technology[sys, tech, yr - 1]
        return Constraint.Skip

    model.same_technology_renewal_constraint = Constraint(
        model.systems, model.technologies, model.years, rule=same_technology_renewal_rule
    )

    def introduction_year_constraint_rule(m, sys, tech, yr):
        introduction_year = m.technology_introduction[tech]
        if yr < introduction_year:
            return m.replace[sys, tech, yr] + m.continue_technology[sys, tech, yr] + m.renew[sys, tech, yr] == 0
        return Constraint.Skip

    model.introduction_year_constraint = Constraint(
        model.systems, model.technologies, model.years, rule=introduction_year_constraint_rule
    )

    # h. Production constraint
    def production_constraint_rule(m, sys, yr):
        return m.production[sys, yr] == sum(
            m.fuel_consumption[sys, f, yr] / m.fuel_eff_param[f, yr]
            for f in m.fuels
        )

    model.production_constraint = Constraint(model.systems, model.years, rule=production_constraint_rule)

    """
    Constraints for Fuel (Unified Model)
    """

    # Production Alignment with Fuel Consumption
    def fuel_production_constraint_rule(m, sys, yr):
        return m.production[sys, yr] == sum(
            m.fuel_consumption[sys, f, yr] * m.fuel_eff_param[f, yr]
            for f in m.fuels
        )

    model.fuel_production_constraint = Constraint(model.systems, model.years, rule=fuel_production_constraint_rule)

    # Ensure Exactly One Fuel Is Selected Per Year
    def fuel_selection_rule(m, sys, yr):
        return sum(m.fuel_select[sys, f, yr] for f in m.fuels) == 1

    model.fuel_selection_constraint = Constraint(model.systems, model.years, rule=fuel_selection_rule)

    # Fuel Consumption Limits for Selected Fuels
    def fuel_consumption_limit_rule(m, sys, f, yr):
        return m.fuel_consumption[sys, f, yr] <= m.fuel_select[sys, f, yr] * m.production[sys, yr]

    model.fuel_consumption_limit_constraint = Constraint(
        model.systems, model.fuels, model.years, rule=fuel_consumption_limit_rule
    )

    # Fuel-Technology Compatibility
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

    """
    Constraints for Materials (Unified Model)
    """

    # Material Consumption Alignment with Production
    def material_production_constraint_rule(m, sys, yr):
        # Production is matched to the sum of material consumption adjusted by efficiency
        return m.production[sys, yr] == sum(
            m.material_consumption[sys, mat, yr] * m.material_eff_param[mat, yr]
            for mat in m.materials
        )

    model.material_production_constraint = Constraint(model.systems, model.years,
                                                      rule=material_production_constraint_rule)

    # Ensure at least one material is selected per year
    def material_selection_rule(m, sys, yr):
        return sum(m.material_select[sys, mat, yr] for mat in m.materials) == 1

    model.material_selection_constraint = Constraint(model.systems, model.years, rule=material_selection_rule)

    # Material Consumption Limits for Selected Materials
    def material_consumption_limit_rule(m, sys, mat, yr):
        return m.material_consumption[sys, mat, yr] <= m.material_select[sys, mat, yr] * BIG_M

    model.material_consumption_limit_constraint = Constraint(
        model.systems, model.materials, model.years, rule=material_consumption_limit_rule
    )

    # Material-Technology Compatibility
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

    """
    Objective Function
    """
    # Auxiliary Variable
    model.production_active = Var(model.systems, model.technologies, model.years, domain=NonNegativeReals)

    # Objective Function
    def total_cost_rule(m):
        return sum(
            m.production_active[sys, tech, yr] * (m.capex_param[tech, yr] + m.opex_param[tech, yr])
            + m.renewal_param[tech, yr] * m.renew[sys, tech, yr]
            + sum(m.fuel_cost_param[f, yr] * m.fuel_select[sys, f, yr] for f in m.fuels)
            + sum(m.material_cost_param[mat, yr] * m.material_select[sys, mat, yr] for mat in m.materials)
            for sys in m.systems
            for tech in m.technologies
            for yr in m.years
        )

    model.objective = Objective(rule=total_cost_rule, sense=minimize)

    # Linearized Constraints for production_active
    def production_active_constraint_upper(m, sys, tech, yr):
        return m.production_active[sys, tech, yr] <= m.production[sys, yr]

    def production_active_constraint_binary(m, sys, tech, yr):
        return m.production_active[sys, tech, yr] <= BIG_M * m.active_technology[sys, tech, yr]

    def production_active_constraint_nonnegativity(m, sys, tech, yr):
        return m.production_active[sys, tech, yr] >= 0

    model.production_active_constraint_upper = Constraint(
        model.systems, model.technologies, model.years, rule=production_active_constraint_upper
    )
    model.production_active_constraint_binary = Constraint(
        model.systems, model.technologies, model.years, rule=production_active_constraint_binary
    )
    model.production_active_constraint_nonnegativity = Constraint(
        model.systems, model.technologies, model.years, rule=production_active_constraint_nonnegativity
    )


    return model


# main function for unified model
# Load data
# Load data
file_path = "database/steel_data.xlsx"
data = load_data(file_path)

# Build and solve the model
model = build_unified_model(data)
solver = SolverFactory("glpk")
result = solver.solve(model, tee=False)


# Check solver status
if result.solver.status == 'ok' and result.solver.termination_condition == 'optimal':
    results_dict = {}

    for system_name in model.systems:
        production_value = data['baseline'].loc[system_name, 'production']

        # Extract fuel consumption
        fuel_data = [
            {
                "Year": yr,
                "Fuel": f,
                "Consumption (tons)": model.fuel_consumption[system_name, f, yr].value
            }
            for yr in model.years
            for f in model.fuels
            if model.fuel_select[system_name, f, yr].value > 0.5
        ]

        # Extract material consumption
        material_data = [
            {
                "Year": yr,
                "Material": mat,
                "Consumption (tons)": model.material_consumption[system_name, mat, yr].value,
                "Share": model.material_consumption[system_name, mat, yr].value / production_value
            }
            for yr in model.years
            for mat in model.materials
            if model.material_consumption[system_name, mat, yr].value > 0
        ]

        # Extract technology changes
        technology_changes = [
            {
                "Year": yr,
                "Technology": next(
                    (tech for tech in model.technologies if model.active_technology[system_name, tech, yr].value > 0.5),
                    "None"
                ),
                "Status": (
                    "replace" if any(model.replace[system_name, tech, yr].value > 0.5 for tech in model.technologies) else
                    "renew" if any(model.renew[system_name, tech, yr].value > 0.5 for tech in model.technologies) else
                    "continue" if any(model.continue_technology[system_name, tech, yr].value > 0.5 for tech in model.technologies) else
                    "inactive"
                )
            }
            for yr in model.years
        ]

        # Extract emissions
        emissions_results = []
        for yr in model.years:
            total_emission = sum(
                model.emission_by_tech[system_name, tech, yr].value
                for tech in model.technologies
                if model.emission_by_tech[system_name, tech, yr].value is not None
            )
            emission_limit = data['emission'].loc['global', yr]
            emissions_results.append({
                "Year": yr,
                "Total Emissions": total_emission,
                "Emission Limit": emission_limit
            })
            print(f"Total Emissions for {system_name} in {yr}: {total_emission} <= Limit: {emission_limit}")

        # Store results
        results_dict[system_name] = {
            "Production": production_value,
            "Fuel Consumption": fuel_data,
            "Material Consumption": material_data,
            "Technology Changes": technology_changes,
            "Emissions": emissions_results
        }

    # Display results
    for system_name, results in results_dict.items():
        print(f"\n=== Results for {system_name} ===")
        print(f"Production: {results['Production']} tons")

        print("\nFuel Consumption:")
        for fc in results['Fuel Consumption']:
            print(f"  Year {fc['Year']}: {fc['Fuel']} - {fc['Consumption (tons)']} energy unit")

        print("\nMaterial Consumption:")
        for mc in results['Material Consumption']:
            print(f"  Year {mc['Year']}: {mc['Material']} - {mc['Consumption (tons)']} tons, Share: {mc['Share']:.2%}")

        print("\nTechnology Changes:")
        for tc in results['Technology Changes']:
            print(f"  Year {tc['Year']}: {tc['Technology']} ({tc['Status']})")

        print("\nEmissions:")
        for emission in results['Emissions']:
            print(f"  Year {emission['Year']}: {emission['Total Emissions']} <= Limit: {emission['Emission Limit']}")
else:
    print(f"Solver failed. Status: {result.solver.status}, Condition: {result.solver.termination_condition}")

