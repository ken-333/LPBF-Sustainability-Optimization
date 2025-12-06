from pyomo.environ import *
from pyaugmecon import PyAugmecon
import pandas as pd

# ==========================================
# the first part: define the LPBF-Sustainability-Optimization model
# ==========================================
def create_lpbf_model():
    model = ConcreteModel()

    # 1. define the layer thickness (μm)
    LT_val = 100
    
    #物理常量
    rho_steel = 7.70  # 0 is the nominal density of SS-CX (7.70 g/cm3)
    
    #碳排放因子
    EF_powder = 1.45  # in the paper, we use the value of 1.45 kg CO2e/kg powder for stainless steel powder(SS-CX) production
    EF_elec = 0.5366  # in the paper, we use the value of 0.5366 kg CO2e/kWh for electricity generation in China

    #成本参数 (unit : Yuan)   
    Price_power = 1.336   # electricity price (Yuan/kWh) in 2020 in China
    Price_powder = 210    # stainless steel powder price (Yuan/kg) in 2020 in China
    Price_gas = 53        # shielding gas (Argon) price (Yuan/kg) in 2020 in China

    # 假设设备折旧 + 人工的综合费率 (估算值，基于 Table 9 和公式)
    # 为了简化线性模型，我们假设每小时的机器+人工成本是固定的
    # 这里假设为 C_hour (Yuan/hour)，你可以根据实际情况调整
    C_hour = 150.0

    # --------------------------------------------------
    # 2. define the decision variables (P, V, H)
    # --------------------------------------------------
    model.P = Var(within=NonNegativeReals, bounds=(385, 460), doc="Laser Power (W)")  # 激光功率 P (W)
    model.V = Var(within=NonNegativeReals, bounds=(700, 1150), doc="Scanning Speed (mm/s)")  # 扫描速度 V (mm/s)
    model.H = Var(within=NonNegativeReals, bounds=(90, 115), doc ="Hatch Spacing (μm)")  # 扫描间距 H (μm)

    # --------------------------------------------------
    # 3. 定义辅助表达式 (为了写公式方便)
    # --------------------------------------------------
    # 能量密度 ED = P / (V * H * LT)
    # 注意单位换算: V(mm/s), H(um), LT(um)
    # H_mm = H * 1e-3, LT_mm = LT * 1e-3
    # 这是一个非线性项，Gurobi 需要开启 NonConvex 参数才能处理

    def ed_rule(m):
        # 分母: V * (H/1000) * (LT/1000)
        return m.P / (m.V * (m.H * 1e-3) * (LT_val * 1e-3))
    model.ED = Expression(rule=ed_rule)

    # 打印时间 (Time to build 1 cm^3 or similar unit)
    # 生产率 Rate (mm^3/s) = V * H * LT
    def build_rate_rule(m):
        return m.V * (m.H * 1e-3) * (LT_val * 1e-3)
    model.BuildRate = Expression(rule=build_rate_rule)

    # --------------------------------------------------
    # 4. 定义约束 (致密度 > 99%)
    # --------------------------------------------------
    # 使用你提供的线性回归系数 (Linear Main Effects) [Source: 193 & Table 4]
    # Density = Intercept + c1*P + c2*V + c3*H + c4*LT + c5*ED
    # 注意：这里包含了 ED，这会引入非线性。如果想纯线性，可以暂时忽略 ED 项，
    # 但根据你的公式，ED 影响很大，所以我们保留它，交给 Gurobi 处理。
    def density_constraint_rule(m):
        predicted_RD = (
            136.59848 
            + 0.094923 * m.P 
            - 0.028654 * m.V 
            - 0.201185 * m.H 
            - 0.108546 * LT_val 
            - 0.524864 * m.ED  # 非线性项
        )
        return predicted_RD >= 99.5
    model.C_Density = Constraint(rule=density_constraint_rule)

    # --------------------------------------------------
    # 5. 定义目标函数 (Objectives)
    # --------------------------------------------------
    
    # --- 目标 1: 最小化碳排放 (Carbon) ---
    # Carbon = (粉末排放) + (电力排放)
    # 考虑打印 1 cm3 (1000 mm3) 的体积
    def obj_carbon_rule(m):
        vol_mm3 = 1000.0
        # 粉末质量 (kg) = Vol * density / 利用率(假设0.87)
        mass_powder_kg = (vol_mm3 * 1e-3) * (rho_steel / 1000.0) / 0.87
        carbon_powder = mass_powder_kg * EF_powder
        
        # 打印时间 (hour) = Volume / Rate / 3600
        time_h = (vol_mm3 / m.BuildRate) / 3600.0
        # 耗电量 (kWh) = (P/1000) * time_h
        energy_kwh = (m.P / 1000.0) * time_h
        carbon_elec = energy_kwh * EF_elec
        
        return carbon_powder + carbon_elec
    
    # 设为最小化
    model.Obj_Carbon = Objective(rule=obj_carbon_rule, sense=minimize)


    # --- 目标 2: 最小化成本 (Cost) ---
    # Cost = 机器人工费 + 粉末费 + 电费 + 气体费
    def obj_cost_rule(m):
        vol_mm3 = 1000.0
        time_h = (vol_mm3 / m.BuildRate) / 3600.0
        
        cost_machine = time_h * C_hour
        
        mass_powder_kg = (vol_mm3 * 1e-3) * (rho_steel / 1000.0) / 0.87
        cost_powder = mass_powder_kg * Price_powder
        
        energy_kwh = (m.P / 1000.0) * time_h
        cost_elec = energy_kwh * Price_power
        
        # 气体费 (假设每小时消耗固定体积 V_gas_flow)
        # 这里简化处理，假设每小时气体成本 10元
        cost_gas = time_h * 10.0 
        
        return cost_machine + cost_powder + cost_elec + cost_gas
        
    # 设为最小化
    model.Obj_Cost = Objective(rule=obj_cost_rule, sense=minimize)


    # --- 目标 3: 最大化生产效率 (Efficiency) ---
    # Efficiency = BuildRate
    # 原题是最大化，转为 最小化 (-BuildRate)
    def obj_eff_rule(m):
        return -1 * m.BuildRate
        
    model.Obj_Efficiency = Objective(rule=obj_eff_rule, sense=minimize)


    # --------------------------------------------------
    # 6. 注册目标列表
    # --------------------------------------------------
    model.obj_list = ObjectiveList()
    model.obj_list.add(expr=model.Obj_Carbon.expr, sense=minimize)
    model.obj_list.add(expr=model.Obj_Cost.expr, sense=minimize)
    model.obj_list.add(expr=model.Obj_Efficiency.expr, sense=minimize)

    # 初始停用
    for o in range(len(model.obj_list)):
        model.obj_list[o + 1].deactivate()

    return model


# ==========================================
# 第二部分：执行求解
# ==========================================
if __name__ == "__main__":
    # 配置求解器参数
    # 关键：因为公式里有 P/V 这种非线性项，必须告诉 Gurobi "NonConvex=2"
    solver_opts = {
        "NonConvex": 2,
        "MIPGap": 0.01
    }

    opts = {
        "grid_points": 10,   # 先用10个点测试
        "early_exit": True,
        "solver_name": "gurobi",
        "solver_opts": solver_opts # 传入 Gurobi 特殊配置
    }

    print("正在初始化 LPBF 优化模型...")
    model = create_lpbf_model()
    pyaugmecon = PyAugmecon(model, opts)

    print("开始求解 Pareto 前沿 (可能需要几分钟)...")
    try:
        pyaugmecon.solve()
        
        pareto_sols = pyaugmecon.get_pareto_solutions()
        print(f"\n计算完成！找到了 {len(pareto_sols)} 个最优解。\n")

        results = []
        for sol_obj_values in pareto_sols:
            dec_vars = pyaugmecon.get_decision_variables(sol_obj_values)
            
            # 还原真实值
            true_carbon = sol_obj_values[0]
            true_cost = sol_obj_values[1]
            true_eff = -1 * sol_obj_values[2] # 还原效率的正负号
            
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
        # 按效率排序
        df = df.sort_values(by="Efficiency (mm3/s)")
        print(df)
        
        # 导出
        df.to_excel("lpbf_optimization_results.xlsx", index=False)
        print("\n结果已保存至 lpbf_optimization_results.xlsx")

    except Exception as e:
        print(f"求解出错: {e}")
        print("提示: 请确保安装了 Gurobi 并且 License 有效。")
