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

    # Load technology emission intensities and pairings
    data['technology_ei'] = pd.read_excel(file_path, sheet_name='technology_ei', index_col=0)
    data['technology_fuel_pairs'] = pd.read_excel(file_path, sheet_name='technology_fuel_pairs').groupby('technology')[
        'fuel'].apply(list).to_dict()
    data['technology_material_pairs'] = \
        pd.read_excel(file_path, sheet_name='technology_material_pairs').groupby('technology')['material'].apply(
            list).to_dict()
    data['technology_introduction'] = pd.read_excel(file_path, sheet_name='technology', index_col=0)[
        'introduction'].to_dict()

    return data

def build_unified_model(data):
    """
    Build a unified Pyomo optimization model that includes all systems and global emission constraints.
    """
    model = ConcreteModel()

    # Sets
    model.systems = Set(initialize=data['baseline'].index.tolist())
    model.technologies = Set(initialize=data['technology'].index.tolist())
    model.fuels = Set(initialize=data['fuel_cost'].index.tolist())
    model.materials = Set(initialize=data['material_cost'].index.tolist())

    # Define all years
    all_years = sorted([int(yr) for yr in data['capex'].columns.tolist()])
    model.years = Set(initialize=all_years)
    initial_year = 2025  # Fixed baseline year

    # Parameters
    # Financial Parameters
    model.capex = Param(model.technologies, model.years, initialize=lambda m, tech, yr: data['capex'].loc[tech, yr], default=0.0)
    model.opex = Param(model.technologies, model.years, initialize=lambda m, tech, yr: data['opex'].loc[tech, yr], default=0.0)
    model.renewal = Param(model.technologies, model.years, initialize=lambda m, tech, yr: data['renewal'].loc[tech, yr], default=0.0)

    # Emission Parameters
    model.technology_ei = Param(model.technologies, model.years, initialize=lambda m, tech, yr: data['technology_ei'].loc[tech, yr], default=1.0)
    model.global_emission_limit = Param(model.years, initialize=lambda m, yr: data['emission'].loc['emission', yr], default=1e9)

    # Fuel Parameters
    model.fuel_cost = Param(model.fuels, model.years, initialize=lambda m, f, yr: data['fuel_cost'].loc[f, yr], default=0.0)
    model.fuel_efficiency = Param(model.fuels, model.years, initialize=lambda m, f, yr: data['fuel_efficiency'].loc[f, yr], default=0.0)
    model.fuel_emission = Param(model.fuels, model.years, initialize=lambda m, f, yr: data['fuel_emission'].loc[f, yr], default=0.0)

    # Material Parameters
    model.material_cost = Param(model.materials, model.years, initialize=lambda m, mat, yr: data['material_cost'].loc[mat, yr], default=0.0)
    model.material_efficiency = Param(model.materials, model.years, initialize=lambda m, mat, yr: data['material_efficiency'].loc[mat, yr], default=0.0)
    model.material_emission = Param(model.materials, model.years, initialize=lambda m, mat, yr: data['material_emission'].loc[mat, yr], default=0.0)

    # Decision Variables
    model.fuel_select = Var(model.systems, model.fuels, model.years, domain=Binary)
    model.material_select = Var(model.systems, model.materials, model.years, domain=Binary)
    model.continue_technology = Var(model.systems, model.technologies, model.years, domain=Binary)
    model.replace = Var(model.systems, model.technologies, model.years, domain=Binary)
    model.renew = Var(model.systems, model.technologies, model.years, domain=Binary)
    model.fuel_consumption = Var(model.systems, model.fuels, model.years, domain=NonNegativeReals)
    model.material_consumption = Var(model.systems, model.materials, model.years, domain=NonNegativeReals)
    model.active_technology = Var(model.systems, model.technologies, model.years, domain=Binary)

    # Emission Variables
    model.system_emission = Var(model.systems, model.years, domain=NonNegativeReals)
    model.total_emissions = Var(model.years, domain=NonNegativeReals)

    # Objective Function: Minimize Total Cost Across All Systems
    def total_cost_rule(m):
        return sum(
            sum(
                m.capex[tech, yr] * m.active_technology[sys, tech, yr]
                + m.opex[tech, yr] * m.active_technology[sys, tech, yr]
                + m.renewal[tech, yr] * m.renew[sys, tech, yr]
                + sum(m.fuel_cost[f, yr] * m.fuel_consumption[sys, f, yr] for f in m.fuels)
                + sum(m.material_cost[mat, yr] * m.material_consumption[sys, mat, yr] for mat in m.materials)
                for tech in m.technologies
            )
            for sys in m.systems for yr in m.years
        )

    model.objective = Objective(rule=total_cost_rule, sense=minimize)

    # Constraints
    def fuel_selection_rule(m, sys, yr):
        return sum(m.fuel_select[sys, f, yr] for f in m.fuels) == 1

    model.fuel_selection_constraint = Constraint(model.systems, model.years, rule=fuel_selection_rule)

    def material_selection_rule(m, sys, yr):
        return sum(m.material_select[sys, mat, yr] for mat in m.materials) == 1

    model.material_selection_constraint = Constraint(model.systems, model.years, rule=material_selection_rule)

    def production_constraint_rule(m, sys, yr):
        production = data['baseline'].loc[sys, 'production']
        return sum(m.fuel_consumption[sys, f, yr] / m.fuel_efficiency[f, yr] for f in m.fuels) == production

    model.production_constraint = Constraint(model.systems, model.years, rule=production_constraint_rule)

    def active_technology_rule(m, sys, tech, yr):
        return m.active_technology[sys, tech, yr] == m.continue_technology[sys, tech, yr] + m.replace[sys, tech, yr] + m.renew[sys, tech, yr]

    model.active_technology_constraint = Constraint(model.systems, model.technologies, model.years, rule=active_technology_rule)

    def system_emission_rule(m, sys, yr):
        return m.system_emission[sys, yr] == sum(
            m.technology_ei[tech, yr] * (
                sum(m.fuel_emission[f, yr] * m.fuel_consumption[sys, f, yr] for f in m.fuels) +
                sum(m.material_emission[mat, yr] * m.material_consumption[sys, mat, yr] for mat in m.materials)
            )
            for tech in m.technologies
        )

    model.system_emission_constraint = Constraint(model.systems, model.years, rule=system_emission_rule)

    def total_emission_rule(m, yr):
        return m.total_emissions[yr] == sum(m.system_emission[sys, yr] for sys in m.systems)

    model.total_emission_constraint = Constraint(model.years, rule=total_emission_rule)

    def global_emission_limit_rule(m, yr):
        return m.total_emissions[yr] <= m.global_emission_limit[yr]

    model.global_emission_limit_constraint = Constraint(model.years, rule=global_emission_limit_rule)

    return model



