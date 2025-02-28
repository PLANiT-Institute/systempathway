from pyomo.environ import (Var, NonNegativeReals, Binary, Param,Set, Any)

def build_parameters(model, data, **kwargs):

    max_renew = kwargs.get('max_renew', 10)

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

    return model
