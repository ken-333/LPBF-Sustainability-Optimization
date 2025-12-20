from pyomo.environ import *
from pyaugmecon import PyAugmecon
import pandas as pd

# ==========================================
# 第一部分：定义 LPBF 模型 (终极修复版)
# ==========================================
def create_lpbf_model():
    model = ConcreteModel()

    # 1. 定义常数
    LT_val = 100.0  # 层厚 (μm)
    
    # 物理常量
    rho_steel = 7.70
    
    # 碳排放因子
    EF_powder = 1.45
    EF_elec = 0.5366

    # 成本参数
    Price_power = 1.336
    Price_powder = 210.0
    Price_gas = 53.0
    C_hour = 150.0

    # --------------------------------------------------
    # 2. 定义决策变量
    # --------------------------------------------------
    model.P = Var(within=NonNegativeReals, bounds=(385, 460), doc="Laser Power (W)")
    model.V = Var(within=NonNegativeReals, bounds=(700, 1150), doc="Scanning Speed (mm/s)")
    model.H = Var(within=NonNegativeReals, bounds=(90, 115), doc ="Hatch Spacing (μm)")

    # ==================================================
    # 【关键修复1】引入辅助变量，消除“除以变量”的操作
    # ==================================================
    model.VH = Var(within=NonNegativeReals, bounds=(60000, 140000))
    model.Inv_VH = Var(within=NonNegativeReals, bounds=(1e-6, 2e-5))

    # 约束：V * H == VH
    def vh_rule(m):
        return m.V * m.H == m.VH
    model.C_VH = Constraint(rule=vh_rule)

    # 约束：VH * Inv_VH == 1 (把除法变成乘法)
    def inv_vh_rule(m):
        return m.VH * m.Inv_VH == 1
    model.C_Inv_VH = Constraint(rule=inv_vh_rule)

    # --------------------------------------------------
    # 3. 重写辅助表达式
    # --------------------------------------------------
    # 变形后 ED = P * Inv_VH * (1 / (1e-6 * LT))
    coeff_ED = 1.0 / (1e-6 * LT_val)
    
    def ed_rule(m):
        return m.P * m.Inv_VH * coeff_ED
    model.ED = Expression(rule=ed_rule)

    # 生产率
    def build_rate_rule(m):
        return m.VH * LT_val * 1e-6
    model.BuildRate = Expression(rule=build_rate_rule)

    # --------------------------------------------------
    # 4. 定义约束 (致密度 > 99.5%)
    # --------------------------------------------------
    def density_constraint_rule(m):
        predicted_RD = (
            136.59848 
            + 0.094923 * m.P 
            - 0.028654 * m.V 
            - 0.201185 * m.H 
            - 0.108546 * LT_val 
            - 0.524864 * m.ED 
        )
        return predicted_RD >= 98.71
    model.C_Density = Constraint(rule=density_constraint_rule)

    # --------------------------------------------------
    # 5. 定义目标函数
    # --------------------------------------------------
    vol_mm3 = 1000.0
    coeff_Time = vol_mm3 / (LT_val * 1e-6 * 3600.0)
    
    # --- 目标 1: 最小化碳排放 ---
    def obj_carbon_rule(m):
        mass_powder_kg = (vol_mm3 * 1e-3) * (rho_steel / 1000.0) / 0.87
        carbon_powder = mass_powder_kg * EF_powder
        
        # P * 1e-3 * Time * EF_elec
        term_elec = (m.P * 1e-3) * (coeff_Time * m.Inv_VH) * EF_elec
        
        return carbon_powder + term_elec
    
    model.Obj_Carbon = Objective(rule=obj_carbon_rule, sense=minimize)
    # 【关键修复2】定义完立刻关掉！防止干扰 PyAugmecon
    model.Obj_Carbon.deactivate()

    # --- 目标 2: 最小化成本 ---
    def obj_cost_rule(m):
        time_expr = coeff_Time * m.Inv_VH
        
        cost_machine = time_expr * C_hour
        
        mass_powder_kg = (vol_mm3 * 1e-3) * (rho_steel / 1000.0) / 0.87
        cost_powder = mass_powder_kg * Price_powder
        
        cost_elec = (m.P * 1e-3) * time_expr * Price_power
        
        cost_gas = time_expr * 10.0 
        
        return cost_machine + cost_powder + cost_elec + cost_gas
        
    model.Obj_Cost = Objective(rule=obj_cost_rule, sense=minimize)
    # 【关键修复2】定义完立刻关掉！
    model.Obj_Cost.deactivate()

    # --- 目标 3: 最大化生产效率 (Min -VH) ---
    def obj_eff_rule(m):
        return -1 * m.VH * LT_val * 1e-6
        
    model.Obj_Efficiency = Objective(rule=obj_eff_rule, sense=minimize)
    # 【关键修复2】定义完立刻关掉！
    model.Obj_Efficiency.deactivate()

    # --------------------------------------------------
    # 6. 注册目标列表
    # --------------------------------------------------
    model.obj_list = ObjectiveList()
    # 即使上面deactivate了，这里添加expr依然有效，PyAugmecon会自己管理这个列表的激活状态
    model.obj_list.add(expr=model.Obj_Carbon.expr, sense=minimize)
    model.obj_list.add(expr=model.Obj_Cost.expr, sense=minimize)
    model.obj_list.add(expr=model.Obj_Efficiency.expr, sense=minimize)

    # 再次确认列表里的也是初始关闭的
    for o in range(len(model.obj_list)):
        model.obj_list[o + 1].deactivate()

    return model


# ==========================================
# 第二部分：执行求解
# ==========================================
if __name__ == "__main__":
    # 配置求解器参数
    solver_opts = {
        "NonConvex": 2,
        "MIPGap": 0.01
    }

    opts = {
        "grid_points": 10,
        "early_exit": True,
        "solver_name": "gurobi",
        "solver_opts": solver_opts
    }

    print("正在初始化 LPBF 优化模型 (修复双重目标激活问题)...")
    
    model = create_lpbf_model() 
    pyaugmecon = PyAugmecon(model, opts)

    print("开始求解 Pareto 前沿...")
    try:
        pyaugmecon.solve()
        
        pareto_sols = pyaugmecon.get_pareto_solutions()
        print(f"\n计算完成！找到了 {len(pareto_sols)} 个最优解。\n")

        results = []
        for sol_obj_values in pareto_sols:
            dec_vars = pyaugmecon.get_decision_variables(sol_obj_values)
            
            true_carbon = sol_obj_values[0]
            true_cost = sol_obj_values[1]
            true_eff = -1 * sol_obj_values[2]
            
            row = {
                "P (W)": dec_vars['P'].item(),
                "V (mm/s)": dec_vars['V'].item(),
                "H (um)": dec_vars['H'].item(),
                "Carbon (kgCO2)": true_carbon,
                "Cost (Yuan)": true_cost,
                "Efficiency (mm3/s)": true_eff
            }
            results.append(row)

        df = pd.DataFrame(results)
        df = df.sort_values(by="Efficiency (mm3/s)")
        print(df)
        
        df.to_excel("lpbf_optimization_results.xlsx", index=False)
        print("\n结果已保存至 lpbf_optimization_results.xlsx")

    except Exception as e:
        print(f"\n求解出错: {e}")
        import traceback
        traceback.print_exc()