import numpy as np
import pandas as pd
from scipy.optimize import minimize
import time
import warnings

# 忽略不必要的数学警告
warnings.filterwarnings("ignore")

class LPBFConfig:
    """
    配置类：存储所有物理常数、价格参数和碳排放因子。
    数据来源：论文手稿及补充材料。
    """
    def __init__(self):
        # --- 1. 物理参数 ---
        self.rho_steel = 7.70      # 密度 (g/cm3)
        self.eta_powder = 0.87     # 粉末利用率 (87%)
        
        # --- 2. 碳排放因子 (Carbon Factors) ---
        self.EF_powder = 1.45      # 不锈钢粉末 (kg CO2e/kg)
        self.EF_elec = 0.5366      # 中国电力 (kg CO2e/kWh)
        
        # --- 3. 成本参数 (Cost Parameters, Unit: CNY) ---
        self.price_power = 1.336   # 电费 (Yuan/kWh)
        self.price_powder = 210.0  # 粉末 (Yuan/kg)
        self.price_gas = 53.0      # 保护气 (Yuan/m3) - 需换算或按小时估算
        self.C_hour = 150.0        # 机器折旧+人工综合费率 (Yuan/hour)
        
        # --- 4. 变量边界 (Constraints) ---
        # [P_min, P_max], [V_min, V_max], [H_min, H_max]
        self.bounds = [
            (385, 460),    # Power (W)
            (700, 1150),   # Velocity (mm/s)
            (90, 115)      # Hatch Spacing (um)
        ]
        
        # 离散的层厚选项 (um)
        self.LT_options = [80, 100, 120]

class ProcessModel:
    """
    过程模型类：封装非线性回归方程和三个目标函数的计算逻辑。
    """
    def __init__(self, config):
        self.cfg = config

    def predict_density(self, x, LT):
        """
        非线性回归模型：预测致密度 (Relative Density)
        输入 x: [P, V, H]
        输入 LT: 固定层厚
        """
        P, V, H = x
        
        # 计算能量密度 ED (J/mm^3)
        # 注意单位换算：V(mm/s), H(um)->mm, LT(um)->mm
        # ED = P / (V * H * LT)
        H_mm = H * 1e-3
        LT_mm = LT * 1e-3
        ED = P / (V * H_mm * LT_mm)
        
        # --- 【关键】这里填入你 Design-Expert 的回归系数 ---
        # 你的公式中有二次项和交叉项，这里必须完整复现
        # 示例系数（请务必用论文里的真实系数替换！）
        # RD = Intercept + c1*P + c2*V + ... + c_sq*P^2 + ...
        
        # 假设公式结构如下 (请根据 manuscript2025714.docx 修正系数):
        RD = (
            136.59848 
            + 0.094923 * P 
            - 0.028654 * V 
            - 0.201185 * H 
            - 0.108546 * LT 
            - 0.524864 * ED  # ED本身是非线性的
            # + ... (把剩下的平方项和交叉项补全)
        )
        return RD

    def calculate_objectives(self, x, LT):
        """
        计算三个目标函数值
        返回: [Carbon, Cost, Efficiency]
        """
        P, V, H = x
        
        # 辅助计算：建造速率 (Build Rate, mm^3/s)
        # Rate = V * H * LT
        build_rate = V * (H * 1e-3) * (LT * 1e-3) 
        
        # 设定计算基准：打印 1 cm^3 (1000 mm^3)
        vol_mm3 = 1000.0
        time_h = (vol_mm3 / build_rate) / 3600.0  # 所需时间 (小时)
        
        # --- Obj 1: Carbon Emission (kg CO2) ---
        # 材料碳: 体积 * 密度 * (1/利用率) * 因子
        mass_kg = (vol_mm3 * 1e-3) * (self.cfg.rho_steel * 1e-3) # g -> kg 修正
        # 注意：rho_steel 是 7.7 g/cm3 = 7.7e-3 kg/cm3. 
        # 上面 vol 是 1 cm3. 所以 mass = 7.7e-3 kg.
        mass_powder_consumed = 7.7e-3 / self.cfg.eta_powder
        carbon_mat = mass_powder_consumed * self.cfg.EF_powder
        
        # 能源碳: 功率(kW) * 时间(h) * 因子
        energy_kwh = (P / 1000.0) * time_h
        carbon_eng = energy_kwh * self.cfg.EF_elec
        
        f_carbon = carbon_mat + carbon_eng
        
        # --- Obj 2: Production Cost (CNY) ---
        cost_mat = mass_powder_consumed * self.cfg.price_powder
        cost_elec = energy_kwh * self.cfg.price_power
        cost_machine = time_h * self.cfg.C_hour
        # 气体成本简化：假设每小时 10 元
        cost_gas = time_h * 10.0
        
        f_cost = cost_mat + cost_elec + cost_machine + cost_gas
        
        # --- Obj 3: Efficiency (Max Build Rate) ---
        # 优化器默认求最小，所以返回 -BuildRate
        # 但这里为了物理意义清晰，先返回正值，优化器里再取负
        f_eff = build_rate
        
        return np.array([f_carbon, f_cost, f_eff])

class AugmeconRSolver:
    """
    算法核心类：实现 AUGMECON-R 算法逻辑。
    Reference: Bouaziz et al. (2023)
    """
    def __init__(self, config, model):
        self.cfg = config
        self.model = model
        self.payoff_table = None
        self.obj_ranges = None
        
        # --- 【修复】添加缺失的变量初始化 ---
        self.payoff_min = None
        self.payoff_max = None
        self.ranges = None
        
    def _optimize_single_obj(self, LT, obj_index):
        """
        单目标优化辅助函数（用于构建 Payoff Table）
        obj_index: 0=Carbon(Min), 1=Cost(Min), 2=Eff(Max)
        """
        def objective(x):
            objs = self.model.calculate_objectives(x, LT)
            if obj_index == 2: # 效率要最大化，转最小化
                return -objs[2]
            return objs[obj_index]
        
        # 约束：致密度 >= 99.5
        cons = [{'type': 'ineq', 'fun': lambda x: self.model.predict_density(x, LT) - 99.5}]
        
        res = minimize(
            objective, 
            x0=[400, 900, 100], # 初始猜测
            bounds=self.cfg.bounds,
            constraints=cons,
            method='SLSQP',
            options={'ftol': 1e-4}
        )
        return res

    def build_payoff_table(self):
        """
        第一步：构建支付表，确定目标函数的取值范围 (Range)。
        """
        print("正在构建 Payoff Table (确定搜索边界)...")
        # 存储所有情况下的极值：[Min_Carbon, Max_Carbon], [Min_Cost, Max_Cost], [Min_Eff, Max_Eff]
        # 由于我们有不同的 LT，我们需要遍历所有 LT 找到全局的最优和最差边界
        
        global_min = [np.inf, np.inf, np.inf] # 理想点
        global_max = [-np.inf, -np.inf, -np.inf] # 纳什点
        
        for LT in self.cfg.LT_options:
            # 分别单目标优化三个指标
            for i in range(3):
                res = self._optimize_single_obj(LT, i)
                if res.success:
                    # 计算该点对应的三个目标值
                    current_objs = self.model.calculate_objectives(res.x, LT)
                    
                    # 更新全局边界
                    for j in range(3):
                        if current_objs[j] < global_min[j]: global_min[j] = current_objs[j]
                        if current_objs[j] > global_max[j]: global_max[j] = current_objs[j]
        
        self.payoff_min = np.array(global_min)
        self.payoff_max = np.array(global_max)
        self.ranges = self.payoff_max - self.payoff_min
        
        # 防止 Range 为 0 (数值稳定性)
        self.ranges[self.ranges == 0] = 1e-6
        
        print(f"碳排放范围: {self.payoff_min[0]:.4f} - {self.payoff_max[0]:.4f}")
        print(f"成本范围:   {self.payoff_min[1]:.4f} - {self.payoff_max[1]:.4f}")
        print(f"效率范围:   {self.payoff_min[2]:.4f} - {self.payoff_max[2]:.4f}")

    def solve(self, grid_points=10):
        """
        第二步：执行 AUGMECON-R 双层循环
        主目标：Carbon (Min)
        约束目标2：Cost (Min) -> e_cost
        约束目标3：Efficiency (Max) -> e_eff
        """
        if self.payoff_min is None:
            self.build_payoff_table()
            
        pareto_front = []
        
        # 生成网格 (从最差到最好)
        # Cost (Min): 上限从 Max 降到 Min
        grid_cost = np.linspace(self.payoff_max[1], self.payoff_min[1], grid_points)
        # Eff (Max): 下限从 Min 升到 Max
        grid_eff = np.linspace(self.payoff_min[2], self.payoff_max[2], grid_points)
        
        total_steps = len(self.cfg.LT_options) * grid_points * grid_points
        step_count = 0
        
        print(f"\n开始双层循环优化 (Total steps: {total_steps})...")
        
        # 遍历层厚 (离散变量外循环)
        for LT in self.cfg.LT_options:
            # 遍历 Cost 约束
            for e_cost in grid_cost:
                # 遍历 Efficiency 约束
                for e_eff in grid_eff:
                    step_count += 1
                    
                    # === 核心：定义 AUGMECON-R 的增强目标函数 ===
                    def augmented_objective(aug_vars):
                        # aug_vars = [P, V, H, s_cost, s_eff]
                        x_process = aug_vars[:3]
                        s_cost = aug_vars[3]
                        s_eff = aug_vars[4]
                        
                        objs = self.model.calculate_objectives(x_process, LT)
                        f_carbon = objs[0]
                        
                        # 目标：最小化 Carbon - epsilon * (归一化松弛变量)
                        # 归一化很重要，让松弛变量的权重一致
                        eps = 1e-3
                        reward = eps * (s_cost/self.ranges[1] + s_eff/self.ranges[2])
                        return f_carbon - reward

                    # === 定义约束 ===
                    # 变量边界: P, V, H, s_cost, s_eff
                    # s 变量必须 >= 0
                    aug_bounds = self.cfg.bounds + [(0, None), (0, None)]
                    
                    cons = [
                        # 1. 成本约束 (等式): Cost + s_cost = e_cost
                        {'type': 'eq', 'fun': lambda x: 
                         self.model.calculate_objectives(x[:3], LT)[1] + x[3] - e_cost},
                        
                        # 2. 效率约束 (等式): Eff - s_eff = e_eff
                        # 注意：Eff是越大越好，所以是 Eff - s = 下限
                        {'type': 'eq', 'fun': lambda x: 
                         self.model.calculate_objectives(x[:3], LT)[2] - x[4] - e_eff},
                        
                        # 3. 致密度约束 (不等式): Density >= 99.5
                        {'type': 'ineq', 'fun': lambda x: 
                         self.model.predict_density(x[:3], LT) - 99.5}
                    ]
                    
                    # === 求解 ===
                    # 初始猜测
                    x0 = [420, 900, 100, 1.0, 1.0]
                    
                    res = minimize(
                        augmented_objective, x0, 
                        method='SLSQP', bounds=aug_bounds, constraints=cons,
                        options={'disp': False}
                    )
                    
                    if res.success:
                        # 记录有效解
                        sol = res.x[:3]
                        final_objs = self.model.calculate_objectives(sol, LT)
                        density = self.model.predict_density(sol, LT)
                        
                        result_row = {
                            'LayerThickness': LT,
                            'Power': sol[0],
                            'Velocity': sol[1],
                            'HatchSpacing': sol[2],
                            'Carbon': final_objs[0],
                            'Cost': final_objs[1],
                            'Efficiency': final_objs[2],
                            'Density': density,
                            'Grid_Cost': e_cost,
                            'Grid_Eff': e_eff
                        }
                        pareto_front.append(result_row)
                        
                        # (可选) 这里可以加入 Bouaziz 论文中的 "Early Exit" 或 "Bypass" 逻辑
                        # 如果松弛变量很大，可以跳过后续几个网格以加速
        
        return pd.DataFrame(pareto_front)

# ==========================================
# 主程序入口
# ==========================================
if __name__ == "__main__":
    # 1. 初始化
    config = LPBFConfig()
    model = ProcessModel(config)
    solver = AugmeconRSolver(config, model)
    
    # 2. 运行优化
    # grid_points 建议设为 10-20 用于生成高质量 Pareto 前沿
    start_time = time.time()
    results_df = solver.solve(grid_points=12) 
    end_time = time.time()
    
    print(f"\n优化完成！耗时: {end_time - start_time:.2f} 秒")
    print(f"共找到 {len(results_df)} 个潜在 Pareto 解")
    
    # 3. 数据清洗 (去除重复解和被支配解)
    # 简单去重
    results_df = results_df.round(4).drop_duplicates(subset=['Carbon', 'Cost', 'Efficiency'])
    
    # 4. 保存结果
    results_df.to_excel("Pareto_Optimization_Results.xlsx", index=False)
    print("结果已保存至 'Pareto_Optimization_Results.xlsx'")
    
    # 打印前几行看看
    print(results_df.head())