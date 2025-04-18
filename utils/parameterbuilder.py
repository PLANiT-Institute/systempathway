from pyomo.environ import (
    Var, NonNegativeReals, Binary, Param, Set, Any
)

def build_parameters(model, data, **kwargs):

    max_renew = kwargs.get('max_renew', 10)

    # Define Sets
    model.systems = Set(initialize=data['baseline'].index.tolist())
    model.technologies = Set(initialize=data['technology'].index.tolist())
    model.fuels = Set(initialize=data['fuel_cost'].index.tolist())
    model.feedstocks = Set(initialize=data['feedstock_cost'].index.tolist())
    model.years = Set(initialize=sorted([int(yr) for yr in data['capex'].columns.tolist()]))

    # Baseline Parameters
    baseline_fuels_data = {sys: row['fuels'] for sys, row in data['baseline'].iterrows()}
    baseline_fuel_shares_data = {sys: row['fuel_shares'] for sys, row in data['baseline'].iterrows()}
    baseline_feedstocks_data = {sys: row['feedstocks'] for sys, row in data['baseline'].iterrows()}
    baseline_feedstock_shares_data = {sys: row['feedstock_shares'] for sys, row in data['baseline'].iterrows()}

    model.baseline_fuels = Param(model.systems, initialize=baseline_fuels_data, within=Any)
    model.baseline_fuel_shares = Param(model.systems, initialize=baseline_fuel_shares_data, within=Any)
    model.baseline_feedstocks = Param(model.systems, initialize=baseline_feedstocks_data, within=Any)
    model.baseline_feedstock_shares = Param(model.systems, initialize=baseline_feedstock_shares_data, within=Any)
    model.baseline_production = Param(model.systems, initialize=data['baseline']['production'].to_dict(), within=NonNegativeReals)
    model.production_param = Param(model.systems, model.years, initialize=data["production"].stack().to_dict(), default=0.0)

    # Other Parameters
    model.carbonprice_param = Param(model.years, initialize=lambda m, yr: data['carbonprice'].loc['global', yr], default=0.0)
    model.capex_param = Param(model.technologies, model.years, initialize=lambda m, tech, yr: data['capex'].loc[tech, yr], default=0.0)
    model.opex_param = Param(model.technologies, model.years, initialize=lambda m, tech, yr: data['opex'].loc[tech, yr], default=0.0)
    model.renewal_param = Param(model.technologies, model.years, initialize=lambda m, tech, yr: data['renewal'].loc[tech, yr], default=0.0)
    model.fuel_cost_param = Param(model.fuels, model.years, initialize=lambda m, f, yr: data['fuel_cost'].loc[f, yr], default=0.0)
    model.fuel_eff_param = Param(model.fuels, model.years, initialize=lambda m, f, yr: data['fuel_intensity'].loc[f, yr], default=0.0)
    model.fuel_emission = Param(model.fuels, model.years, initialize=lambda m, f, yr: data['fuel_emission'].loc[f, yr], default=0.0)
    model.feedstock_cost_param = Param(model.feedstocks, model.years, initialize=lambda m, fs, yr: data['feedstock_cost'].loc[fs, yr], default=0.0)
    model.feedstock_eff_param = Param(model.feedstocks, model.years, initialize=lambda m, fs, yr: data['feedstock_intensity'].loc[fs, yr], default=0.0)
    model.feedstock_emission = Param(model.feedstocks, model.years, initialize=lambda m, fs, yr: data['feedstock_emission'].loc[fs, yr], default=0.0)

    model.lifespan_param = Param(model.technologies, initialize=lambda m, tech: data['technology'].loc[tech, 'lifespan'], default=0)
    model.introduced_year_param = Param(model.systems, initialize=data['baseline']['introduced_year'].to_dict(), default=0)
    model.technology_ei = Param(model.technologies, model.years, initialize=lambda m, tech, yr: data['technology_ei'].loc[tech, yr], default=1.0)
    model.emission_limit = Param(model.years, initialize=lambda m, yr: data['emission'].loc['global', yr], default=0)
    model.technology_introduction = Param(model.technologies, initialize=lambda m, tech: data['technology'].loc[tech, 'introduction'], default=0)
    model.baseline_technology = Param(model.systems, initialize=lambda m, sys: data['baseline'].loc[sys, 'technology'], within=model.technologies)
    model.max_renew = Param(initialize=max_renew)

    # ✨ NEW: Define a param to store 'availability' for each tech (list of allowed actions).
    # e.g. {'BF-BOF': ['replace','renew','continue'], 'BF-BOF-FX': ['renew','continue'], ...}
    # We'll store it as `within=Any` because it's a list of strings.
    model.technology_availability = Param(
        model.technologies,
        initialize=data['technology_availability'],
        within=Any
    )

    # Decision Variables
    model.replace = Var(model.systems, model.technologies, model.years, domain=Binary, initialize=0)
    model.active_technology = Var(model.systems, model.technologies, model.years, domain=Binary, initialize=0)
    model.continue_technology = Var(model.systems, model.technologies, model.years, domain=Binary, initialize=0)
    model.fuel_select = Var(model.systems, model.fuels, model.years, domain=Binary, initialize=0)
    model.feedstock_select = Var(model.systems, model.feedstocks, model.years, domain=Binary, initialize=0)
    model.production = Var(model.systems, model.years, domain=NonNegativeReals, initialize=0)
    model.fuel_consumption = Var(model.systems, model.fuels, model.years, domain=NonNegativeReals, initialize=0)
    model.feedstock_consumption = Var(model.systems, model.feedstocks, model.years, domain=NonNegativeReals, initialize=0)
    model.emission_by_tech = Var(model.systems, model.technologies, model.years, domain=NonNegativeReals, initialize=0)
    model.prod_active = Var(model.systems, model.technologies, model.years, domain=NonNegativeReals, initialize=0)
    model.replace_prod_active = Var(model.systems, model.technologies, model.years, domain=NonNegativeReals, initialize=0)
    model.renew_prod_active = Var(model.systems, model.technologies, model.years, domain=NonNegativeReals, initialize=0)
    model.activation_change = Var(model.systems, model.technologies, model.years, domain=Binary, initialize=0)
    model.renew = Var(model.systems, model.technologies, model.years, domain=Binary)
    model.total_fuel_consumption = Var(model.systems, model.years, within=NonNegativeReals)
    model.total_feedstock_consumption = Var(model.systems, model.years, within=NonNegativeReals)

    model.active_fuel_consumption = Var(model.systems, model.technologies, model.fuels, model.years, domain=NonNegativeReals)
    model.active_feedstock_consumption = Var(model.systems, model.technologies, model.feedstocks, model.years, domain=NonNegativeReals)

    model.active_if_started = Var(model.systems, model.technologies, model.years, model.years, domain=Binary)

    return model