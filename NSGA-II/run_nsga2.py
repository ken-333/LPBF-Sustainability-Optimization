import pandas as pd
import numpy as np
from nsga2.problem import Problem
from nsga2.evolution import Evolution
import physics_model  # 导入你的物理模型

# ==========================================
# 1. 定义问题类 (适配你的 NSGA-II 库)
# ==========================================
class LPBFProblem(Problem):
    def __init__(self, lt_val):
        self.lt = lt_val
        
        # 定义变量范围 [(min, max), ...]
        # P: 385-460, V: 700-1150, H: 90-115
        vars_bounds = [(385, 460), (700, 1150), (90, 115)]
        
        # 将三个目标函数打包成列表
        # 注意：这里传递的是方法对象 (self.obj_...)
        objs = [self.obj_cost, self.obj_carbon, self.obj_efficiency]
        
        # 初始化父类
        # 注意：这个库的 Problem 类不接受 num_of_constraints
        super().__init__(objectives=objs, 
                         num_of_variables=3, 
                         variables_range=vars_bounds, 
                         expand=False) # expand=False 表示传入的是列表 [P,V,H]

    # --- 辅助函数：统一计算物理指标和罚分 ---
    def _calc_physics(self, features):
        P, V, H = features[0], features[1], features[2]
        
        # 1. 调用物理模型
        try:
            Cost, Carbon, RD, ED = physics_model.predict_performance([P, V, H], self.lt)
        except:
            return 1e9, 1e9, 0, 0 # 出错返回巨大代价
            
        # 2. 计算效率
        Efficiency = V * (H / 1000.0) * (self.lt / 1000.0)
        
        # 3. 计算罚分 (Penalty)
        penalty = 0
        # 致密度硬约束 RD >= 99.5
        if RD < 99.5:
            penalty += 1e6 + (99.5 - RD) * 1e6
        # 能量密度约束
        if not (30 <= ED <= 80):
            penalty += 1e6
            
        return Cost, Carbon, Efficiency, penalty

    # --- 目标函数 1: Cost (Min) ---
    def obj_cost(self, features):
        Cost, Carbon, Efficiency, penalty = self._calc_physics(features)
        return Cost + penalty

    # --- 目标函数 2: Carbon (Min) ---
    def obj_carbon(self, features):
        Cost, Carbon, Efficiency, penalty = self._calc_physics(features)
        return Carbon + penalty

    # --- 目标函数 3: Efficiency (Max -> Min) ---
    def obj_efficiency(self, features):
        Cost, Carbon, Efficiency, penalty = self._calc_physics(features)
        return -Efficiency + penalty  # 取负数因为 NSGA-II 默认求最小

# ==========================================
# 2. 主运行函数
# ==========================================
def run_baseline():
    print("🚀 启动 NSGA-II 基准对比测试 (适配版)...")
    
    all_results = []
    
    for lt in [80, 100, 120]:
        print(f"\n正在计算 LT = {lt} µm ...")
        
        # 实例化问题
        problem = LPBFProblem(lt)
        
        # 配置进化参数
        # num_of_generations: 迭代次数
        # num_of_individuals: 种群大小
        evo = Evolution(problem, num_of_generations=200, num_of_individuals=100)
        
        # 开始跑
        best_inds = evo.evolve()
        
        print(f"  -> 进化完成，找到 {len(best_inds)} 个解")
        
        # 提取有效数据
        valid_count = 0
        for ind in best_inds:
            P, V, H = ind.features
            
            # 重新计算真实指标 (不带罚分)
            Cost, Carbon, RD, ED = physics_model.predict_performance([P, V, H], lt)
            Efficiency = V * (H / 1000.0) * (lt / 1000.0)
            
            # 只保存合格的解 (RD >= 99.45)
            if RD >= 99.45:
                all_results.append({
                    'LT_um': lt,
                    'P_W': P,
                    'V_mm_s': V,
                    'H_um': H,
                    'Cost': Cost,
                    'Carbon': Carbon,
                    'Efficiency': Efficiency,
                    'RD': RD,
                    'Method': 'NSGA-II'
                })
                valid_count += 1
        
        print(f"  -> 其中有效合格解 (RD>=99.45): {valid_count} 个")

    # ==========================================
    # 3. 导出 CSV
    # ==========================================
    if len(all_results) > 0:
        df = pd.DataFrame(all_results)
        cols = ['LT_um', 'P_W', 'V_mm_s', 'H_um', 'Cost', 'Carbon', 'Efficiency', 'RD', 'Method']
        df = df[cols]
        
        output_file = 'results_nsga2.csv'
        df.to_csv(output_file, index=False)
        print(f"\n✅ 成功! 结果已保存为 '{output_file}'")
    else:
        print("\n❌ 警告: NSGA-II 未找到任何合格解。")

if __name__ == "__main__":
    run_baseline()