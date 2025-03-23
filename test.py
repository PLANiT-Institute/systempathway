from pyomo.environ import *
from pyomo.opt import SolverFactory

solver = SolverFactory("highs", executable="/opt/anaconda3/envs/pyomo/bin/highs")
print(solver.available())  # Should be True