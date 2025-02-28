from pyomo.environ import (Objective, minimize)

def objectivefucntion(model, **kwargs):

    carbonprice_include = kwargs.get('carbonprice_include', False)

    def total_cost_rule(m):
        """
        Calculate the total cost, optionally including the carbon cost.
        """
        # Base cost components
        total_cost = sum(
            sum(
                # CAPEX, Renewal, and OPEX costs using auxiliary variables for linearity
                (model.capex_param[tech, yr] * model.replace_prod_active[sys, tech, yr] +
                 model.renewal_param[tech, yr] * model.renew_prod_active[sys, tech, yr] +
                 model.opex_param[tech, yr] * model.prod_active[sys, tech, yr])
                for tech in model.technologies
            ) +
            # Fuel costs
            sum(model.fuel_cost_param[fuel, yr] * model.fuel_consumption[sys, fuel, yr] for fuel in model.fuels) +
            # Material costs
            sum(model.feedstock_cost_param[fs, yr] * model.feedstock_consumption[sys, fs, yr] for fs in model.feedstocks)
            for sys in model.systems for yr in model.years
        )
    
        # Add carbon price cost if the flag is enabled
        if carbonprice_include:
            carbon_cost = sum(
                model.carbonprice_param[yr] * sum(
                    model.emission_by_tech[sys, tech, yr] for tech in model.technologies
                )
                for sys in model.systems for yr in model.years
            )
            total_cost += carbon_cost
    
        return total_cost
    
    
    model.total_cost = Objective(rule=total_cost_rule, sense=minimize)
    
    return model