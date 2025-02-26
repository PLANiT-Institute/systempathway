from pyomo.environ import value
import os
from datetime import datetime
import pandas as pd

def export_results_enhanced(model, annual_global_capex, annual_global_renewal_cost,
                            annual_global_opex, annual_global_total_emissions,
                            annual_global_fuel_consumption, annual_global_material_consumption,
                            annual_global_tech_adoption,
                            output_dir='results', filename_base='model_results',
                            export_csv=True):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    excel_filename = f"{filename_base}_{timestamp}.xlsx"
    excel_path = os.path.join(output_dir, excel_filename)

    with pd.ExcelWriter(excel_path) as writer:
        for sys in model.systems:
            short_sys = sys.replace("yang ", "yang").replace(" ", "")[:10]
            yearly_metrics, fuel_consumption_table, material_consumption_table, technology_statuses = [], [], [], []
            baseline_tech = model.baseline_technology[sys]
            introduced_year = model.introduced_year_param[sys]
            lifespan = model.lifespan_param[baseline_tech]

            for yr in model.years:
                capex_cost = sum(model.capex_param[tech, yr] * value(model.replace_prod_active[sys, tech, yr])
                                 for tech in model.technologies)
                if yr == min(model.years) and baseline_tech in model.technologies:
                    capex_adjustment = (model.capex_param[baseline_tech, yr] *
                                        ((lifespan - (yr - introduced_year)) / lifespan) *
                                        value(model.production[sys, yr]))
                    capex_cost += capex_adjustment

                renewal_cost = sum(model.renewal_param[tech, yr] * value(model.renew_prod_active[sys, tech, yr])
                                   for tech in model.technologies)
                opex_cost = sum(model.opex_param[tech, yr] * value(model.prod_active[sys, tech, yr])
                                for tech in model.technologies)
                total_emissions = sum(value(model.emission_by_tech[sys, tech, yr])
                                      for tech in model.technologies)

                fuel_consumption = {fuel: value(model.fuel_consumption[sys, fuel, yr]) for fuel in model.fuels}
                material_consumption = {mat: value(model.material_consumption[sys, mat, yr]) for mat in model.materials}

                yearly_metrics.append({"Year": yr, "CAPEX": capex_cost, "Renewal Cost": renewal_cost,
                                       "OPEX": opex_cost, "Total Emissions": total_emissions})
                fuel_consumption_table.append({"Year": yr, **fuel_consumption})
                material_consumption_table.append({"Year": yr, **material_consumption})
                for tech in model.technologies:
                    technology_statuses.append({
                        "Year": yr, "Technology": tech,
                        "Continue": value(model.continue_technology[sys, tech, yr]),
                        "Replace": value(model.replace[sys, tech, yr]),
                        "Renew": value(model.renew[sys, tech, yr]),
                        "Active": value(model.active_technology[sys, tech, yr])
                    })

            pd.DataFrame(yearly_metrics).set_index("Year").to_excel(writer, sheet_name=f'{short_sys}_Costs')
            pd.DataFrame(fuel_consumption_table).set_index("Year").to_excel(writer, sheet_name=f'{short_sys}_Fuel')
            pd.DataFrame(material_consumption_table).set_index("Year").to_excel(writer, sheet_name=f'{short_sys}_Mat')
            pd.DataFrame(technology_statuses).to_excel(writer, sheet_name=f'{short_sys}_Tech', index=False)

        # Global Summary (Enhanced)
        annual_summary = [
            {"Year": yr, "Total CAPEX": annual_global_capex[yr], "Total Renewal Cost": annual_global_renewal_cost[yr],
             "Total OPEX": annual_global_opex[yr],
             "Total Cost": (annual_global_capex[yr] + annual_global_renewal_cost[yr] + annual_global_opex[yr]),
             "Total Emissions": annual_global_total_emissions[yr],
             **{f"Fuel Consumption ({fuel})": annual_global_fuel_consumption[yr][fuel] for fuel in model.fuels},
             **{f"Material Consumption ({mat})": annual_global_material_consumption[yr][mat] for mat in model.materials},
             **{f"Tech Adoption ({tech})": annual_global_tech_adoption[yr][tech] for tech in model.technologies}}
            for yr in sorted(model.years)
        ]
        pd.DataFrame(annual_summary).set_index("Year").to_excel(writer, sheet_name='Global_Summary')

    print(f"\n=== Results exported to Excel: {excel_path} ===\n")

    if export_csv:
        csv_dir = os.path.join(output_dir, f"{filename_base}_{timestamp}_csv")
        os.makedirs(csv_dir, exist_ok=True)
        for sys in model.systems:
            short_sys = sys.replace("yang ", "yang").replace(" ", "")[:10]
            pd.DataFrame(yearly_metrics).set_index("Year").to_csv(os.path.join(csv_dir, f'{short_sys}_Costs.csv'))
            pd.DataFrame(fuel_consumption_table).set_index("Year").to_csv(os.path.join(csv_dir, f'{short_sys}_Fuel.csv'))
            pd.DataFrame(material_consumption_table).set_index("Year").to_csv(os.path.join(csv_dir, f'{short_sys}_Mat.csv'))
            pd.DataFrame(technology_statuses).to_csv(os.path.join(csv_dir, f'{short_sys}_Tech.csv'), index=False)
        pd.DataFrame(annual_summary).set_index("Year").to_csv(os.path.join(csv_dir, 'Global_Summary.csv'))
        print(f"\n=== Results also exported as CSV to folder: {csv_dir} ===\n")