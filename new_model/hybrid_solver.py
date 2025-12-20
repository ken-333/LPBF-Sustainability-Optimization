import numpy as np          
from scipy.optimize import differential_evolution, minimize     
import physics_model   

class HybridSolver:
    """
    Layer 3: 战术执行层 (Tactical Layer)
    """
    
    def __init__(self, lt_val):   # 将lt分成3组单独运行
        self.lt = lt_val  
        # 工艺参数边界: Power (W)-P, Speed (mm/s)-V, Hatch (um)-H
        self.bounds = [(385, 460), (700, 1150), (90, 115)]

    def _get_all_metrics(self, x):
        """
        辅助函数：只计算基础物理指标，不计算复合指标(PRI)
        """
        Cost, Carbon, RD, ED = physics_model.predict_performance(x, self.lt)
        
        # 计算效率
        efficiency = x[1] * (x[2] / 1000.0) * (self.lt / 1000.0)
        
        return {
            'Cost': Cost,
            'Carbon': Carbon,
            'Efficiency': efficiency,
            'RD': RD,
            'ED': ED
            # 注意：这里没有 Quality_Robustness，必须在外面手动算！
        }
    
    def solve(self, primary_obj_name, constraint_map):
        # ==========================================================
        # Phase 1: 定义目标函数
        # ==========================================================
        def relaxed_objective(x):
            metrics = self._get_all_metrics(x)
            rd_pred = metrics['RD']
            ed_val = metrics['ED']
            
            # 实时计算 PRI 用于优化引导
            quality_loss = (100.0 - rd_pred) ** 2
            stability_penalty = ((ed_val - 50.0) / 20.0) ** 2
            pri_val = quality_loss + 1.0 * stability_penalty   # 👉 PRI 不是物理模型给的，是你人为设计的“质量 + 稳定性综合指标”

            violation = 0.0   #如果 x 完全合格 → violation 还是 0  只要有一条不合格 → violation 就开始累加
            # 1. 物理底线
            if rd_pred < 99.5: violation += (99.5 - rd_pred) * 1e6
            
            # 2. 动态约束检查
            if 'Carbon' in constraint_map and metrics['Carbon'] > constraint_map['Carbon']:
                violation += (metrics['Carbon'] - constraint_map['Carbon']) * 1e5   # 这里罚得比 RD 轻（1e5 vs 1e6）
            if 'Efficiency' in constraint_map and metrics['Efficiency'] < constraint_map['Efficiency']:
                violation += (constraint_map['Efficiency'] - metrics['Efficiency']) * 1e5
            if 'Quality_Robustness' in constraint_map and pri_val > constraint_map['Quality_Robustness']:
                violation += (pri_val - constraint_map['Quality_Robustness']) * 1e5

            if violation > 0: return 1e9 + violation
            else: return metrics['Cost'] / 4.0
            # 情况A：不合格，返回一个 极其巨大的数。“这玩意太烂了，别选”
            # 情况 B：完全合格  RD ≥ 99.5，Carbon / Efficiency / PRI 都满足 ε 约束。 这时才开始比较 Cost
            # Cost 只有在“活下来以后”才有资格被比较

        # ==========================================================
        # Phase 2: 执行优化 (DE -> SLSQP)
        # ==========================================================
        # 1. 全局搜索
        de_res = differential_evolution(
            relaxed_objective, self.bounds, strategy='best1bin', 
            maxiter=50, popsize=20, tol=1e-4, mutation=(0.5, 1.0), 
            recombination=0.7, seed=42
        )
        
        # 2. 局部精修
        slsqp_res = minimize(
            relaxed_objective, x0=de_res.x, bounds=self.bounds, 
            method='SLSQP', tol=1e-6, options={'maxiter': 50}
        )

        # ==========================================================
        # Phase 3: 结果打包与验证 (死磕 KeyError)
        # ==========================================================

        # --- A. 尝试使用 SLSQP 的结果 ---
        final_x = slsqp_res.x
        final_metrics = self._get_all_metrics(final_x)

        # 🟢 [强制补全 1]：必须立刻计算 PRI 并塞入字典
        q_loss = (100.0 - final_metrics['RD']) ** 2
        s_loss = ((final_metrics['ED'] - 50.0) / 20.0) ** 2
        final_pri = q_loss + 1.0 * s_loss
        
        final_metrics['Quality_Robustness'] = final_pri # <--- 关键赋值

        # 验证可行性
        is_feasible = True
        if final_metrics['RD'] < 99.45: is_feasible = False 

        # 循环检查约束 (现在字典里肯定有 key 了)
        for c_name, c_limit in constraint_map.items():
            val = final_metrics[c_name] # 这里不会再报错了
            if c_name == 'Carbon' and val > c_limit + 1e-3: is_feasible = False
            if c_name == 'Efficiency' and val < c_limit - 1e-3: is_feasible = False
            if c_name == 'Quality_Robustness' and val > c_limit + 1e-3: is_feasible = False

        # --- B. 回退策略 (如果 SLSQP 失败，尝试用 DE 的结果) ---
        if not is_feasible:
             # 重新提取 DE 的指标
             de_metrics = self._get_all_metrics(de_res.x)
             
             # 🟢 [强制补全 2]：DE 的字典也必须补全 PRI！
             de_q = (100.0 - de_metrics['RD'])**2
             de_s = ((de_metrics['ED']-50)/20)**2
             de_pri = de_q + 1.0 * de_s
             
             de_metrics['Quality_Robustness'] = de_pri # <--- 漏了这里就会在下面报错

             # 验证 DE 可行性
             de_feasible = True
             if de_metrics['RD'] < 99.45: de_feasible = False
             
             for c_name, c_limit in constraint_map.items():
                 # 这里的 constraint_map 包含 Quality_Robustness
                 # 所以 de_metrics 必须有这个 key
                 val = de_metrics[c_name] 
                 if c_name == 'Carbon' and val > c_limit + 1e-3: de_feasible = False
                 if c_name == 'Efficiency' and val < c_limit - 1e-3: de_feasible = False
                 if c_name == 'Quality_Robustness' and val > c_limit + 1e-3: de_feasible = False
             
             # 如果 DE 可行，就用 DE 的结果替换
             if de_feasible:
                 final_x = de_res.x
                 final_metrics = de_metrics
                 is_feasible = True

        # --- C. 返回最终结果 ---
        if is_feasible:
            return {
                'is_feasible': True,
                'Cost': final_metrics['Cost'],
                'Carbon': final_metrics['Carbon'],
                'Efficiency': final_metrics['Efficiency'],
                'Quality_Robustness': final_metrics['Quality_Robustness'], # 确保这里也能取到
                'RD': final_metrics['RD'],
                'ED': final_metrics['ED'],
                'P_W': final_x[0],
                'V_mm_s': final_x[1],
                'H_um': final_x[2],
            }
        else:
            return None