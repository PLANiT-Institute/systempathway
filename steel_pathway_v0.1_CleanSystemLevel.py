import pandas as pd
from pyomo.environ import (
    ConcreteModel, Var, NonNegativeReals, Binary, Param,
    Objective, Constraint, SolverFactory, Set, minimize, ConstraintList
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

    # Load material-related data
    data['material_cost'] = pd.read_excel(file_path, sheet_name='material_cost', index_col=0)
    data['material_efficiency'] = pd.read_excel(file_path, sheet_name='material_efficiency', index_col=0)

    # Load financial data
    data['capex'] = pd.read_excel(file_path, sheet_name='capex', index_col=0)
    data['opex'] = pd.read_excel(file_path, sheet_name='opex', index_col=0)
    data['renewal'] = pd.read_excel(file_path, sheet_name='renewal', index_col=0)

    # # Import and group Technology-Fuel Pairs
    # data['technology_fuel_pairs'] = pd.read_excel(file_path, sheet_name='technology_fuel_pairs') \
    #     .groupby('technology')['fuel'].apply(list).to_dict()

    # Import and structure fuel max ratios
    technology_fuel_pairs_df = pd.read_excel(file_path, sheet_name='technology_fuel_pairs')
    data['technology_fuel_pairs'] = technology_fuel_pairs_df.groupby('technology')['fuel'].apply(list).to_dict()
    data['fuel_max_ratio'] = technology_fuel_pairs_df.set_index(['technology', 'fuel'])['max'].to_dict()
    data['fuel_min_ratio'] = technology_fuel_pairs_df.set_index(['technology', 'fuel'])['min'].to_dict()

    # Import and group Technology-Material Pairs
    technology_material_pairs_df = pd.read_excel(file_path, sheet_name='technology_material_pairs')
    data['technology_material_pairs'] = technology_material_pairs_df.groupby('technology')['material'].apply(list).to_dict()
    data['material_max_ratio'] = technology_material_pairs_df.set_index(['technology', 'material'])['max'].to_dict()
    data['material_min_ratio'] = technology_material_pairs_df.set_index(['technology', 'material'])['min'].to_dict()

    data['technology_introduction'] = pd.read_excel(file_path, sheet_name='technology', index_col=0)['introduction'].to_dict()

    # Load emission-related data
    data['emission_system'] = pd.read_excel(file_path, sheet_name='emission_system', index_col=0)
    data['fuel_emission'] = pd.read_excel(file_path, sheet_name='fuel_emission', index_col=0)
    data['material_emission'] = pd.read_excel(file_path, sheet_name='material_emission', index_col=0)
    data['technology_ei'] = pd.read_excel(file_path, sheet_name='technology_ei', index_col=0)

    return data


def build_model_for_system(system_name, baseline_row, data):
    """
    Build a Pyomo optimization model for a single furnace site (system),
    ensuring that the initial year maintains the baseline technology
    and is excluded from the optimization years.
    """
    model = ConcreteModel()

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

    # Parameters
    model.capex_param = Param(model.technologies, model.years,initialize=lambda m, tech, yr: data['capex'].loc[tech, yr], default=0.0)
    model.opex_param = Param(model.technologies, model.years, initialize=lambda m, tech, yr: data['opex'].loc[tech, yr],default=0.0)
    model.renewal_param = Param(model.technologies, model.years,initialize=lambda m, tech, yr: data['renewal'].loc[tech, yr], default=0.0)
    model.fuel_cost_param = Param(model.fuels, model.years, initialize=lambda m, f, yr: data['fuel_cost'].loc[f, yr],default=0.0)
    model.fuel_eff_param = Param(model.fuels, model.years,initialize=lambda m, f, yr: data['fuel_efficiency'].loc[f, yr], default=0.0)
    model.material_cost_param = Param(model.materials, model.years,initialize=lambda m, mat, yr: data['material_cost'].loc[mat, yr], default=0.0)
    model.material_eff_param = Param(model.materials, model.years,initialize=lambda m, mat, yr: data['material_efficiency'].loc[mat, yr],default=0.0)

    # Decision Variables
    model.fuel_select = Var(model.fuels, model.years, domain=Binary)
    model.material_select = Var(model.materials, model.years, domain=Binary)
    model.continue_technology = Var(model.technologies, model.years, domain=Binary)
    model.replace = Var(model.technologies, model.years, domain=Binary)
    model.renew = Var(model.technologies, model.years, domain=Binary)
    model.fuel_consumption = Var(model.fuels, model.years, domain=NonNegativeReals)
    model.active_technology = Var(model.technologies, model.years | {introduced_year}, domain=Binary)
    model.activation_change = Var(model.technologies, model.years, domain=Binary)

    # Parameters for Lifespan and Introduction Year
    model.lifespan_param = Param(model.technologies,initialize=lambda m, tech: data['technology'].loc[tech, 'lifespan'], default=0)
    model.introduced_year_param = Param(initialize=lambda m: introduced_year)

    # **Emission Parameters with Yearly Dimensions**
    model.fuel_emission = Param(model.fuels, model.years,initialize=lambda m, f, yr: data['fuel_emission'].loc[f, yr],default=0.0)
    model.material_emission = Param(model.materials, model.years,initialize=lambda m, mat, yr: data['material_emission'].loc[mat, yr],default=0.0)
    model.technology_ei = Param(model.technologies, model.years,initialize=lambda m, tech, yr: data['technology_ei'].loc[tech, yr],default=1.0)
    model.emission_limit = Param(model.years,initialize=lambda m, yr: data['emission_system'].loc[system_name, yr],default=1e9)

    # **Variables**
    model.material_consumption = Var(model.materials, model.years, domain=NonNegativeReals)
    model.emission_by_tech = Var(model.technologies, model.years, domain=NonNegativeReals)

    # Parameters for maximum fuel and material ratios
    # Initialize fuel max ratio parameter
    model.fuel_max_ratio = Param(
        model.technologies, model.fuels,
        initialize=lambda m, tech, fuel: data['fuel_max_ratio'].get((tech, fuel), 0),
        default=0.0
    )

    # Initialize material max ratio parameter
    model.material_max_ratio = Param(
        model.technologies, model.materials,
        initialize=lambda m, tech, mat: data['material_max_ratio'].get((tech, mat), 0),
        default=0.0
    )

    """
    Emission Constraints
    """

    def emission_by_tech_rule(m, tech, yr):
        return m.emission_by_tech[tech, yr] ==(
            m.technology_ei[tech, yr] * (
                    sum(m.fuel_emission[f, yr] * m.fuel_consumption[f, yr] for f in m.fuels) +
                    sum(m.material_emission[mat, yr] * m.material_consumption[mat, yr] for mat in m.materials)
            )
        )

    model.emission_by_tech_constraint = Constraint(model.technologies, model.years, rule=emission_by_tech_rule)

    # Total Emission Constraint per Year
    def total_emission_limit_rule(m, yr):
        return sum(
            m.emission_by_tech[tech, yr] for tech in m.technologies
        ) <= m.emission_limit[yr]

    model.total_emission_limit_constraint = Constraint(model.years, rule=total_emission_limit_rule)

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

    def hard_baseline_fuel_rule(m, f, yr):
        if yr == min(m.years):  # Lock the fuel selection for the initial year
            baseline_fuel = baseline_row['fuel']
            if f == baseline_fuel:
                return m.fuel_select[f, yr] == 1  # Must use the baseline fuel
            else:
                return m.fuel_select[f, yr] == 0  # Other fuels cannot be selected
        return Constraint.Skip

    model.hard_baseline_fuel_constraint = Constraint(
        model.fuels, model.years, rule=hard_baseline_fuel_rule
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

    def active_technology_rule(m, tech, yr):
        # A technology is active if it is continued, replaced, or renewed
        return m.active_technology[tech, yr] == m.continue_technology[tech, yr] + m.replace[tech, yr] + m.renew[
            tech, yr]

    model.active_technology_constraint = Constraint(model.technologies, model.years, rule=active_technology_rule)

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

    # Total fuel consumption variable for each year
    model.total_fuel_consumption = Var(model.years, within=NonNegativeReals)

    # Rule to calculate total fuel consumption
    def total_fuel_consumption_rule(m, yr):
        return m.total_fuel_consumption[yr] == sum(
            m.fuel_consumption[f, yr] for f in m.fuels
        )

    # Add the total fuel consumption constraint
    model.total_fuel_consumption_constraint = Constraint(
        model.years, rule=total_fuel_consumption_rule
    )

    # Define Big-M parameter
    Big_M = 1e6  # Adjust this value based on your problem scale

    # Rule for maximum fuel share constraint
    def fuel_max_share_constraint_rule(m, tech, f, yr):
        # Get the maximum allowable share for the (technology, fuel) combination
        max_share = data['fuel_max_ratio'].get((tech, f), 0)

        # Constrain fuel consumption using Big-M reformulation
        return m.fuel_consumption[f, yr] <= (
                max_share * m.total_fuel_consumption[yr] + Big_M * (1 - m.active_technology[tech, yr])
        )

    # Add the constraint for all technologies, fuels, and years
    model.fuel_max_share_constraint = Constraint(
        model.technologies, model.fuels, model.years, rule=fuel_max_share_constraint_rule
    )

    # # May not need
    #
    # def fuel_consumption_limit_rule(m, f, yr):
    #     return m.fuel_consumption[f, yr] <= m.fuel_select[f, yr] * m.fuel_eff_param[f, yr] * production
    #
    # model.fuel_consumption_limit_constraint = Constraint(
    #     model.fuels, model.years, rule=fuel_consumption_limit_rule
    # )
    #
    # # Define the material min share constraint with Big-M reformulation
    # def fuel_min_share_constraint_rule(m, tech, f, yr):
    #     min_share = data['fuel_min_ratio'].get((tech, f), 0)
    #
    #     # Constrain material consumption to meet minimum share
    #     return m.fuel_consumption[f, yr] >= (
    #             min_share * m.total_fuel_consumption[yr] - Big_M * (1 - m.active_technology[tech, yr])
    #     )
    #
    # # Apply the constraint for all technologies, materials, and years
    # model.fuel_min_share_constraint = Constraint(
    #     model.technologies, model.fuels, model.years, rule=fuel_min_share_constraint_rule
    # )
    #
    # def technology_fuel_link_rule(m, yr, tech):
    #     compatible_fuels = data['technology_fuel_pairs'].get(tech, [])
    #     # If a technology is active, at least one of its compatible fuels must be selected
    #     return sum(m.fuel_select[f, yr] for f in compatible_fuels) >= m.active_technology[tech, yr]
    #
    # model.technology_fuel_link_constraint = Constraint(
    #     model.years, model.technologies, rule=technology_fuel_link_rule
    # )

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

    # Define Big-M parameter
    Big_M = 1e6  # Adjust this value based on the scale of your problem

    # Define the material max share constraint with Big-M reformulation
    def material_max_share_constraint_rule(m, tech, mat, yr):
        max_share = data['material_max_ratio'].get((tech, mat), 0)

        # Constrain material consumption using Big-M reformulation
        return m.material_consumption[mat, yr] <= (
                max_share * m.total_material_consumption[yr] + Big_M * (1 - m.active_technology[tech, yr])
        )

    # Apply the constraint for all technologies, materials, and years
    model.material_max_share_constraint = Constraint(
        model.technologies, model.materials, model.years, rule=material_max_share_constraint_rule
    )

    # May not need
    # # Define the material min share constraint with Big-M reformulation
    # def material_min_share_constraint_rule(m, tech, mat, yr):
    #     min_share = data['material_min_ratio'].get((tech, mat), 0)
    #
    #     # Constrain material consumption to meet minimum share
    #     return m.material_consumption[mat, yr] >= (
    #             min_share * m.total_material_consumption[yr] - Big_M * (1 - m.active_technology[tech, yr])
    #     )
    #
    # # Apply the constraint for all technologies, materials, and years
    # model.material_min_share_constraint = Constraint(
    #     model.technologies, model.materials, model.years, rule=material_min_share_constraint_rule
    # )
    # # **Technology-Material Link Constraint**
    # def technology_material_link_rule(m, yr, tech):
    #     compatible_materials = data['technology_material_pairs'].get(tech, [])
    #     # If a technology is active, at least one of its compatible materials must be selected
    #     return sum(m.material_select[mat, yr] for mat in compatible_materials) >= m.active_technology[tech, yr]
    #
    # model.technology_material_link_constraint = Constraint(
    #     model.years, model.technologies, rule=technology_material_link_rule
    # )
    #
    # # **Material Consumption Limit Constraint**
    # def material_consumption_limit_rule(m, mat, yr):
    #     return (
    #         m.material_consumption[mat, yr]
    #         <= m.material_select[mat, yr] * m.material_eff_param[mat, yr] * production
    #     )
    # model.material_consumption_limit_constraint = Constraint(
    #     model.materials, model.years, rule=material_consumption_limit_rule
    # )
    #
    #
    # # Total material consumption variable for each year
    # model.total_material_consumption = Var(model.years, within=NonNegativeReals)
    """
    Objective Function
    """

    def total_cost_rule(m):
        return sum(
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

    model.total_cost = Objective(rule=total_cost_rule, sense=minimize)

    return model


# Load data
file_path = 'database/steel_data.xlsx'
data = load_data(file_path)
solver = SolverFactory('glpk')
results_dict = {}
for system_name in data['baseline'].index:
    print(f"\n=== Solving for furnace site: {system_name} ===")

    baseline_row = data['baseline'].loc[system_name]

    # Build and solve the model
    model = build_model_for_system(system_name, baseline_row, data)
    result = solver.solve(model, tee=True)

    if result.solver.status == 'ok' and result.solver.termination_condition == 'optimal':
        print(f"\n=== Results for {system_name} ===")
        production_value = baseline_row['production']

        yearly_metrics = []
        fuel_consumption_table = []
        material_consumption_table = []

        for yr in model.years:
            # Calculate costs
            capex_cost = sum(
                model.capex_param[tech, yr] * model.replace[tech, yr].value * production_value
                for tech in model.technologies
            )

            # Adjust CAPEX for the first year and baseline technology
            if yr == min(model.years):
                capex_cost += model.capex_param[baseline_row['technology'], yr] * (
                    model.lifespan_param[baseline_row['technology']] - (yr - baseline_row['introduced_year'])
                ) / model.lifespan_param[baseline_row['technology']] * production_value

            renewal_cost = sum(
                model.renewal_param[tech, yr] * model.renew[tech, yr].value * production_value
                for tech in model.technologies
            )
            opex_cost = sum(
                model.opex_param[tech, yr] * model.active_technology[tech, yr].value * production_value
                for tech in model.technologies
            )

            # Calculate emissions
            total_emissions = sum(
                model.emission_by_tech[tech, yr].value for tech in model.technologies
            )

            # Calculate fuel consumption
            fuel_consumption = {
                fuel: model.fuel_consumption[fuel, yr].value for fuel in model.fuels
            }

            # Calculate material consumption
            material_consumption = {
                mat: model.material_consumption[mat, yr].value for mat in model.materials
            }

            # Add yearly data
            yearly_metrics.append({
                "Year": yr,
                "CAPEX": capex_cost,
                "Renewal Cost": renewal_cost,
                "OPEX": opex_cost,
                "Total Emissions": total_emissions
            })

            # Add to fuel and material consumption tables
            fuel_consumption_table.append({"Year": yr, **fuel_consumption})
            material_consumption_table.append({"Year": yr, **material_consumption})

        # Convert costs to DataFrame
        costs_df = pd.DataFrame(yearly_metrics).set_index("Year")
        print("\n=== Costs and Emissions by Year ===")
        print(costs_df)

        # Convert fuel and material consumption to DataFrames
        fuel_df = pd.DataFrame(fuel_consumption_table).set_index("Year")
        material_df = pd.DataFrame(material_consumption_table).set_index("Year")

        print("\n=== Fuel Consumption by Year ===")
        print(fuel_df)

        print("\n=== Material Consumption by Year ===")
        print(material_df)

        # Extract technology statuses
        technology_statuses = []
        for yr in model.years:
            for tech in model.technologies:
                technology_statuses.append({
                    "Year": yr,
                    "Technology": tech,
                    "Continue": model.continue_technology[tech, yr].value,
                    "Replace": model.replace[tech, yr].value,
                    "Renew": model.renew[tech, yr].value,
                    "Active": model.active_technology[tech, yr].value
                })

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

    else:
        print(
            f"Solver failed for {system_name}. Status: {result.solver.status}, Condition: {result.solver.termination_condition}")

