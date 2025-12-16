import numpy as np          # in order to handle numerical arrays
from scipy.optimize import differential_evolution, minimize     #导入两个优化器   differential_evolution：全局随机搜索（不需要梯度）minimize：局部优化器接口（用 SLSQP 支持约束）
import physics_model   # from layer 1 my physics engine evaluating Cost/Carbon/Efficiency/RD/ED

class HycridSolver:
    """
    Layer 3: 战术执行层 (Tactical Layer)
    
    职责：
    1. 接收 Layer 2 (总指挥) 下达的战略指令：主目标是谁？约束条件是什么？
    2. 执行 H-DE 混合策略：
       - Phase 1 (Global Exploration): 使用差分进化 (DE) 在松弛约束下寻找潜力区域。
       - Phase 2 (Local Refinement): 使用梯度算法 (SLSQP) 进行精确修整，确保满足硬约束。
    3. 返回最终的物理结果给 Layer 2。
    """
    
    def __init__(self,lt_val):
        """
        初始化求解器，绑定当前的工艺层厚。
        """
        self.lt = lt_val  #保存当前层厚，后续每次评估性能都用这个 LT。
        # 工艺参数边界: Power (W)-P, Speed (mm/s)-V, Hatch (um)-H
        self.bounds = [(385, 460), (700, 1150), (90, 115)]
        # 为什么必须有 bounds：1.DE 需要边界才能采样种群  2.SLSQP 用 bounds 限制变量可行域（物理/设备范围）

    def _get_all_metrics(self, x):
        """
        辅助函数：调用 Layer 1 的物理模型，计算所有指标。
        """
        Cost, Carbon, RD, ED = physics_model.predict_performance(x, self.lt)
        
        # 计算效率 (Volumetric Build Rate)
        # 单位换算: V(mm/s) * H(um->mm) * LT(um->mm) = mm^3/s
        efficiency = x[1] * (x[2] / 1000.0) * (self.lt / 1000.0)
        
        return {
            'Cost': Cost,
            'Carbon': Carbon,
            'Efficiency': efficiency,
            'RD': RD,
            'ED': ED
        }
    
    def solve(self, primary_obj_name, constraint_map):
        """
        执行混合求解的核心接口。
        
        :param primary_obj_name: 当前优化的主目标 (e.g., 'Cost')
        :param constraint_map: 当前的约束条件字典 (e.g., {'Carbon': 10.0})
        :return: 结果字典 或 None
        """
        # ==========================================================
        # Phase 1: Global Exploration (DE with Relaxed Constraints)
        # ==========================================================
        def relaxed_objective(x):
            metrics = self._get_all_metrics(x)

            # 1. 获取主目标值 (如果是 Max 问题则取反)
            score = metrics[primary_obj_name]
            if primary_obj_name == 'Efficiency':
             score = -score
        
            PENALTY = 1e6

            # 2. 物理约束松弛 (Relaxation Strategy)
            # 创新点：只要求 99.0%，保护种群多样性
            if metrics['RD'] < 99.0:
              score += PENALTY * (99.0 - metrics['RD'])**2

            # ED 约束 (30-80)
            if metrics['ED'] < 30.0: 
               score += PENALTY * (30.0 - metrics['ED'])**2
            elif metrics['ED'] < 80.0:
               score += PENALTY * (metrics['ED'] - 80.0)**2

            # 3. AUGMECON 动态约束
            # 根据总指挥下达的 epsilon 进行惩罚
            for c_name, c_limit in constraint_map.items():
               val = metrics[c_name]
               # Min目标 > Limit 则罚; Max目标 < Limit 则罚
               if c_name in ['Cost', 'Carbon']: #Min 类型
                  if val > c_limit:
                     score += PENALTY * (val - c_limit)**2
               elif c_name == 'Efficiency':  # Max 类型
                  if val < c_limit:
                     score += PENALTY * (c_limit - val)**2
            
            return score
        
        # 运行 DE
        de_res = differential_evolution(
           relaxed_objective, # 我的“目标+罚函数”
           self.bounds,       # 变量范围
           strategy= 'best1bin', # 经典稳健策略
           maxiter=50,         # 粗搜阶段不需要太久，主要找 basin
           popsize=20,         # 种群大一点提高全局探索能力（更稳，但慢）
           seed= 42            # 保证可复现（论文必须强调 reproducibility）
        )
        
        if not de_res.success:
           return None  # DE 都失败了，直接放弃
        
        # ==========================================================
        # Phase 2: Local Refinement (SLSQP with Strict Constraints)
        # ==========================================================

        # 1. 定义 SLSQP 目标函数 (纯净版，无罚函数)
        def exact_objective(x):
           metrics = self._get_all_metrics(x)
           val = metrics[promary_obj_name]
           return -val if primary_obj_name == 'Efficiency' else val
        
        # 2. 定义严格约束 (Constraints for SLSQP)
        # 格式: fun(x) >= 0
        cons = []

        # [A] 物理硬约束 (严格恢复到 99.5%)
        cons.append({'type':'ineq', 'fun': lambda x: self._get_all_metrics(x)['RD'] - 99.5})  #RD ≥ 99.5
        cons.append({'type': 'ineq', 'fun': lambda x: self._get_all_metrics(x)['ED'] - 30.0})  #ED ≥ 30
        cons.append({'type': 'ineq', 'fun': lambda x: 80.0 - self._get_all_metrics(x)['ED']})  #ED ≤ 80

        # [B] AUGMECON 动态约束
        for c_name, c_limit in constraint_map.items():
           if c_name in ['Cost', 'Carbon']:
              # limit - val >= 0 (即 val <= limit)
              cons.append({'type': 'ineq', 'fun': lambda x, n=c_name, l=c_limit: l - self._get_all_metrics(x)[n]})
           elif c_name == 'Efficiency':
              # val - limit >= 0 (即 val >= limit)
              cons.append({'type': 'ineq', 'fun': lambda x, n=c_name, l=c_limit: self._get_all_metrics(x)[n] - l})

        #运行 SLSQP (从 DE 的结果出发) 
        slsqp_res = minimize(       #SLSQP 是局部算法，需要初值；DE 给了一个“已经在好区域”的点
           exact_objective,
           x0=de_res.x,
           bounds=self.bounds,         #bounds 保证不出物理范围
           constraints=cons,           #constraints 强制满足硬约束（RD≥99.5, ED窗口, ε约束）
           method='SLSQP',
           options={'ftol': 1e-4, 'disp': False}   #ftol 控制收敛精度
        )

        # ==========================================================
        # 3. 结果验证与打包
        # ==========================================================

        # 优先使用精修后的解，如果精修失败，检查 DE 原解是否碰巧合格
        final_x = slsqp_res.x if slsqp_res.success else de_res.x
        final_metrics = self._get_all_metrics(final_x)

        #最终严格检查 (Strict Feasibility Check)
        is_feasible = True

        # 检查物理约束
        if final_metrics['RD'] < 99.49:
           is_feasible = False   # 允许微小误差
        if not (30.00 <= final_metrics['ED'] <= 80.0):
           is_feasible = False

        #检查 AUGMECON 约束
        for c_name, c_limit in constraint_map.items():
           val = final_metrics[c_name]
           if c_name in ['Cost', 'Carbon']:
              if val > c_limit + 0.05: is_feasible = False
           elif c_name == 'Efficiency':
              if val < c_limit - 0.001: is_feasible = False

        if is_feasible:
            # 返回 Layer 2 需要的完整数据包
            return {
                'is_feasible': True,
                'x': final_x,
                **final_metrics  # 解包所有指标 (Cost, Carbon, etc.)
            }
        else:
            return None
  



                     
                    
                



            


        

