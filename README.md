# Steel Industry Decarbonization Optimization Model (MACC Steel)

This project implements a comprehensive optimization model for analyzing technology pathways and their associated costs for decarbonizing the steel industry. The model uses linear programming to find optimal technology adoption strategies while minimizing total system costs and evaluating emission reduction potential.

## Overview

The Steel Industry Decarbonization Optimization Model is designed to:
- Optimize technology replacement and renewal decisions across multiple steel production systems
- Calculate marginal abatement costs (MACC) for different decarbonization pathways
- Analyze fuel and feedstock consumption patterns under different scenarios
- Evaluate the economic and environmental impacts of various steel production technologies

## Input Data Structure

The model requires an Excel file with multiple sheets containing the following data:

### Required Sheets and Data Formats

#### 1. `baseline` Sheet
- **Index**: System names (steel production facilities/sites)
- **Columns**:
  - `technology`: Current baseline technology (string)
  - `fuel`: Comma-separated list of fuels used (string)
  - `fuel_share`: Comma-separated list of fuel consumption shares (numeric, 0-1)
  - `feedstock`: Comma-separated list of feedstocks used (string)
  - `feedstock_share`: Comma-separated list of feedstock consumption shares (numeric, 0-1)
  - `production`: Annual production capacity (numeric, units: tons/year)
  - `introduced_year`: Year when baseline technology was introduced (integer)

#### 2. `technology` Sheet
- **Index**: Technology names
- **Columns**:
  - `lifespan`: Technology lifespan (integer, years)
  - `introduction`: Year when technology becomes available (integer)
  - `availability`: Comma-separated allowed actions: 'replace', 'renew', 'continue' (string)

#### 3. Cost Data Sheets
All cost sheets have technologies/fuels/feedstocks as index and years as columns.

- **`capex`**: Capital expenditures ($/unit capacity)
- **`opex`**: Operating expenditures ($/unit production/year)
- **`renewal`**: Renewal costs ($/unit capacity)
- **`fuel_cost`**: Fuel costs ($/unit fuel)
- **`feedstock_cost`**: Feedstock costs ($/unit feedstock)

#### 4. Intensity Data Sheets
- **`fuel_intensity`**: Fuel consumption per unit production (fuel units/production unit)
- **`feedstock_intensity`**: Feedstock consumption per unit production (feedstock units/production unit)

#### 5. Emission Data Sheets
- **`fuel_emission`**: Emission factors for fuels (tCO2e/fuel unit)
- **`feedstock_emission`**: Emission factors for feedstocks (tCO2e/feedstock unit)
- **`technology_ei`**: Technology-specific emission intensities (tCO2e/production unit)
- **`emission`**: Global emission limits by year (tCO2e/year)

#### 6. Technology-Fuel/Feedstock Pairing Sheets
- **`technology_fuel_pairs`**: Defines which fuels each technology can use
  - Columns: `technology`, `fuel`, `min` (minimum ratio), `max` (maximum ratio)
- **`technology_feedstock_pairs`**: Defines which feedstocks each technology can use
  - Columns: `technology`, `feedstock`, `min` (minimum ratio), `max` (maximum ratio)

#### 7. Additional Data Sheets
- **`production`**: Production targets by system and year (tons/year)
- **`carbonprice`**: Carbon pricing by year ($/tCO2e)
- **`fuel_introduction`**: Year when fuels become available
- **`feedstock_introduction`**: Year when feedstocks become available

## Algorithm Description

### Mathematical Formulation

The model is formulated as a mixed-integer linear programming (MILP) problem using the Pyomo optimization framework.

#### Decision Variables
- **Binary Variables**:
  - `replace[sys, tech, year]`: Technology replacement decisions
  - `active_technology[sys, tech, year]`: Technology activity status
  - `continue_technology[sys, tech, year]`: Technology continuation decisions
  - `renew[sys, tech, year]`: Technology renewal decisions
  - `fuel_select[sys, fuel, year]`: Fuel selection decisions
  - `feedstock_select[sys, feedstock, year]`: Feedstock selection decisions

- **Continuous Variables**:
  - `production[sys, year]`: Production levels (tons/year)
  - `fuel_consumption[sys, fuel, year]`: Fuel consumption (fuel units/year)
  - `feedstock_consumption[sys, feedstock, year]`: Feedstock consumption (feedstock units/year)
  - `emission_by_tech[sys, tech, year]`: Emissions by technology (tCO2e/year)

#### Objective Function
Minimize total system cost comprising:
1. **CAPEX**: Capital expenditures for new technology installations
2. **OPEX**: Annual operating expenses
3. **Fuel Costs**: Annual fuel expenditures
4. **Feedstock Costs**: Annual feedstock expenditures
5. **Renewal Costs**: Technology renewal expenses
6. **Carbon Costs** (optional): Carbon pricing costs based on emissions

#### Key Constraints
1. **Technology Lifecycle Constraints**: Enforce technology lifespan and replacement logic
2. **Production Balance**: Ensure production targets are met
3. **Fuel/Feedstock Balance**: Link technology choices with fuel/feedstock requirements
4. **Emission Constraints**: Enforce emission limits (if specified)
5. **Technology Availability**: Respect technology introduction years and allowed actions
6. **Resource Ratio Constraints**: Enforce min/max ratios for fuel/feedstock usage

### Solution Process

1. **Data Loading**: Parse Excel input file and structure data for optimization
2. **Model Building**: Construct Pyomo model with parameters, variables, and constraints
3. **Optimization**: Solve using linear programming solver (default: HiGHS)
4. **Results Processing**: Calculate comprehensive metrics including:
   - Annual costs by category (CAPEX, OPEX, fuel, feedstock)
   - Technology adoption patterns
   - Fuel and feedstock consumption
   - Emission reductions
   - Marginal abatement costs (MACC)

## Output Data Structure

The model generates comprehensive results saved to `results/Model_Output.xlsx` with multiple sheets:

### Summary Sheets
- **`Global Annual Summary`**: Aggregated annual metrics across all systems
- **`Discounted Costs`**: Present value calculations with discount rates
- **`Unit Costs and MAC`**: Per-unit costs and marginal abatement costs
- **`Technology Production Share`**: Technology mix analysis

### System-Level Sheets
For each production system:
- **`{System}_CostsEmissions`**: Annual costs and emissions
- **`{System}_Fuel`**: Fuel consumption by year
- **`{System}_Feedstock`**: Feedstock consumption by year
- **`{System}_Tech`**: Technology status (active, replaced, renewed)
- **`{System}_Tech_Production`**: Production allocation by technology

### Key Output Metrics and Units

#### Cost Metrics
- **Total CAPEX**: Capital expenditures ($/year)
- **Total OPEX**: Operating expenditures ($/year)
- **Fuel Costs**: Annual fuel expenses ($/year)
- **Feedstock Costs**: Annual feedstock expenses ($/year)
- **Discounted Costs**: Present value using 2% discount rate ($/year)
- **Unit Costs**: Cost per unit of production ($/ton)

#### Environmental Metrics
- **Total Emissions**: Greenhouse gas emissions (tCO2e/year)
- **Emission Reductions**: Reduction from baseline (tCO2e/year)
- **Emissions Intensity**: Emissions per unit production (tCO2e/ton)

#### Economic Analysis
- **Marginal Abatement Cost (MACC)**: Cost per unit emission reduction ($/tCO2e)
- **Annualized CAPEX**: CAPEX distributed over technology lifetime ($/year)
- **Technology Adoption Rates**: Share of production by technology (%)

## Data Preparation Guidelines

### Input Data Requirements
1. **Consistency**: Ensure all sheets use consistent system, technology, fuel, and feedstock names
2. **Completeness**: All required data points must be present for the analysis period
3. **Units**: Maintain consistent units across all data sheets
4. **Time Series**: Data should cover the full analysis period with annual resolution

### Data Validation
- Verify that fuel/feedstock shares sum to 1.0 for each system
- Ensure technology introduction years are consistent with availability
- Check that min/max ratios in pairing sheets are feasible (min ≤ max)
- Validate that emission factors and intensities are non-negative

## Model Configuration

### Key Parameters
- **Solver**: Default uses HiGHS (open-source linear programming solver)
- **Carbon Pricing**: Optional inclusion of carbon costs in objective function
- **Maximum Renewals**: Limit on number of technology renewals (default: 10)
- **Technology Replacement**: Option to allow same-technology replacements
- **Discount Rates**: 2% for CAPEX/OPEX, 2% for fuel/feedstock costs

### Usage Example
```python
from main_v2 import main

# Run optimization with custom parameters
results = main(
    file_path="database/Steel Data Mar 10.xlsx",
    solver_selection='appsi_highs',
    carboprice_include=False,
    max_renew=10,
    allow_replace_same_technology=False
)
```

This model provides a comprehensive framework for analyzing steel industry decarbonization pathways, supporting strategic decision-making for technology investments and policy development.