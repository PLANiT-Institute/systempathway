from pyomo.environ import (ConcreteModel, Objective, Constraint, minimize)
import pandas as pd
import importlib
import utils.parameterbuilder as _param
import utils.constraintbuilder as _const
import utils.objectivefunctionbuilder as _objf

importlib.reload(_param)
importlib.reload(_const)
importlib.reload(_objf)

def build_unified_model(data, **kwargs):

    """
    Build the unified Pyomo model.
    """

    model = ConcreteModel()

    model = _param.build_parameters(model, data, **kwargs)
    model = _objf.objectivefucntion(model, **kwargs)
    model = _const.emission_constraints(model, **kwargs)
    model = _const.baseline_constraints(model)
    model = _const.fuel_constraints(model, data)
    model = _const.feedstock_constraints(model, data)
    model = _const.active_technology_constraints(model)
    model = _const.lifespan_constraints(model)
    model = _const.other_constraints(model, **kwargs)
    model = _const.max_count_constraints(model, data, **kwargs)

    return model

