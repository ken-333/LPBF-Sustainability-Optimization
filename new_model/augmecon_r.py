import numpy as np
import pandas as pd
import time

class AugmeconRGamsStyle:
    """
    Python implementation that strictly mirrors the GAMS logic of AUGMECON-R.
    创新改进: 
    1. 引入代理回退策略 (Surrogate Fallback Strategy) 处理极端物理约束下的边界计算。
    2. 引入容错跳过机制 (Fault-Tolerant Skipping) 处理网格中的无解点。
    """
    
    def __init__(self, solver_handler, objective_config, grid_points=20):
        self.solver = solver_handler
        self.obj_config = objective_config
        self.grid_points = grid_points
        
        self.obj_names = list(objective_config.keys())
        self.primary_obj = self.obj_names[0]       # e.g., 'Cost'
        self.constrained_objs = self.obj_names[1:] # e.g., ['Carbon', 'Efficiency']
        self.n_constr = len(self.constrained_objs)
        
        self.payoff_table = pd.DataFrame(index=self.obj_names, columns=self.obj_names)
        self.ranges = {} 
        self.grids = {} 

    def calculate_payoff_table(self):
        """
        Phase 1: 计算支付表 (Payoff Table) - 确定帕累托前沿的边界
        
        【算法创新点 1：代理回退策略】
        当求解器无法找到某个目标（如 Carbon）的独立极值点时（通常是因为掉进了 RD < 99.5% 的物理深坑），
        本算法会自动在已有的最优解（如 Cost 的最优解）中寻找“物理代理”。
        原理：Cost 和 Carbon 高度正相关，Cost 的最优参数通常也是 Carbon 在可行域内的最优参数。
        """
        print(f"\n  [AUGMECON-R] Constructing Payoff Table (Robust Mode)...")
        
        # 用于存储每个目标优化后的最佳解，作为“解库”
        best_solutions = {} 
        
        # 1. 依次优化每个目标
        for primary in self.obj_names:
            print(f"    -> Optimizing {primary}...", end="")
            
            # 尝试调用求解器 (Layer 3)
            res = self.solver.solve(primary, {})
            
            if res is not None:
                # ✅ 情况 A: 成功找到解 (标准情况)
                val = res[primary]
                print(f" Done. Ideal={val:.4f}")
                best_solutions[primary] = res
                
                # 记录到支付表
                for col in self.obj_names:
                    self.payoff_table.loc[primary, col] = res[col]
            else:
                # ⚠️ 情况 B: 求解失败 (通常发生在 80um 下的 Carbon)
                # 触发代理策略：去“解库”里找替补
                print(f" [Warning] Strict constraints met. Applying Surrogate Strategy...", end="")
                
                found_fallback = False
                # 初始化比较基准 (如果是 Min 目标，初始设为无穷大；Max 设为无穷小)
                best_fallback_val = float('inf') if self.obj_config[primary]['type']=='min' else float('-inf')
                best_fallback_res = None
                fallback_source = ""
                
                # 遍历之前已经算出来的解 (比如 Cost 的解)
                for existing_name, existing_res in best_solutions.items():
                    current_val = existing_res[primary] # 看这个解在当前目标(Carbon)下的表现
                    
                    # 判断是否是更好的替补
                    is_better = False
                    if self.obj_config[primary]['type'] == 'min':
                        if current_val < best_fallback_val: is_better = True
                    else:
                        if current_val > best_fallback_val: is_better = True
                        
                    if is_better:
                        best_fallback_val = current_val
                        best_fallback_res = existing_res
                        fallback_source = existing_name
                        found_fallback = True
                
                if found_fallback:
                    print(f" Solved using {fallback_source}'s proxy. Val={best_fallback_val:.4f}")
                    # 使用替补结果填表
                    best_solutions[primary] = best_fallback_res
                    for col in self.obj_names:
                        self.payoff_table.loc[primary, col] = best_fallback_res[col]
                else:
                    # ❌ 情况 C: 彻底无解 (连 Cost 都算不出来，说明物理模型或约束有问题)
                    print(" Failed!")
                    raise RuntimeError(f"Critical Error: No feasible region found even for {primary} (and no proxy available).")

        # 2. 计算 Nadir (最差值) 和 Ideal (理想值)
        self.nadir_point = {}
        self.ideal_point = {}
        
        for obj in self.obj_names:
            col_values = self.payoff_table[obj].values
            if self.obj_config[obj]['type'] == 'min':
                self.ideal_point[obj] = min(col_values)
                self.nadir_point[obj] = max(col_values)
            else:
                self.ideal_point[obj] = max(col_values)
                self.nadir_point[obj] = min(col_values)
                
        # 3. 设置网格范围
        self.setup_grid_ranges()

    def setup_grid_ranges(self):
        """生成网格切分点"""
        for obj in self.constrained_objs:
            mn = min(self.payoff_table[obj])
            mx = max(self.payoff_table[obj])
            
            # 防御性编程：防止最大最小值极其接近导致除以零 (比如 Cost 和 Carbon 的解完全重合)
            if abs(mx - mn) < 1e-6:
                if self.obj_config[obj]['type'] == 'min':
                    mx = mn + 1e-3 # 人为拓宽一点点
                else:
                    mn = mx - 1e-3
            
            r = mx - mn
            self.ranges[obj] = {'min': mn, 'max': mx, 'range': r}
            
            # 生成网格点
            if self.obj_config[obj]['type'] == 'min':
                # Min目标：从 Max 降到 Min (逐步收紧约束)
                step = r / self.grid_points
                self.grids[obj] = [mx - k * step for k in range(self.grid_points + 1)]
            else:
                # Max目标：从 Min 升到 Max
                step = r / self.grid_points
                self.grids[obj] = [mn + k * step for k in range(self.grid_points + 1)]
            
            self.ranges[obj]['step'] = step
            # print(f"    -> Grid {obj}: [{self.grids[obj][0]:.4f} ... {self.grids[obj][-1]:.4f}] (Step={step:.4f})")

    def solve(self):
        """
        Phase 2: 执行 AUGMECON-R 主循环 (Strict Mode)
        集成两大加速引擎：
        1. Slack Jump: 容易满足时，大步跳跃。
        2. Early Exit: 发现无解时，直接熔断退出，不再纠缠。
        """
        if not self.grids: self.calculate_payoff_table()
        
        print(f"\n  [AUGMECON-R] Starting Main Loop (Strict & Fast)...")
        
        posg = [0] * self.n_constr 
        maxg = [self.grid_points] * self.n_constr
        all_solutions = []
        infeas_count = 0
        iter_count = 0
        
        while True:
            iter_count += 1
            
            # 1. 构建约束
            current_constraints = {}
            for i, obj in enumerate(self.constrained_objs):
                idx = posg[i]
                val = self.grids[obj][idx]
                current_constraints[obj] = val
            
            # 2. 求解
            res = self.solver.solve(self.primary_obj, current_constraints)
            
            # 默认只走一步
            active_jump = 1
            remaining_steps = maxg[-1] - posg[-1]
            
            if res is not None:
                # ✅ [Case A] 找到解 -> 尝试利用 Slack 跳跃
                res['is_feasible'] = True
                all_solutions.append(res)
                
                innermost_obj = self.constrained_objs[-1]
                eps_val = current_constraints[innermost_obj]
                achieved = res[innermost_obj]
                step = self.ranges[innermost_obj]['step']
                
                if step > 1e-12:
                    # 计算松弛量
                    if self.obj_config[innermost_obj]['type'] == 'min':
                        slack = eps_val - achieved  # Min目标: 限值 - 实际
                    else:
                        slack = achieved - eps_val  # Max目标: 实际 - 限值
                    
                    if slack < 0: slack = 0
                    
                    # 🚀 核心加速 1: 只要有富余，就跳！
                    jump = int(slack / step)
                    # jump+1 代表直接跳到“下一个可能不满足”的未知区域
                    active_jump = max(1, min(jump + 1, remaining_steps + 1))
                    
                    if active_jump > 1:
                        # 打印一下让你看着爽
                        # print(f"    >> 🚀 Jump! Skipped {active_jump-1} grids (Slack={slack:.4f})")
                        pass

            else:
                # ❌ [Case B] 无解 -> 触发熔断机制 (Early Exit)
                infeas_count += 1
                
                # 🚀 核心加速 2: 既然当前宽松条件都无解，后面更严的肯定无解
                # 直接跳过这一整行内层循环！
                active_jump = remaining_steps + 1
                # print(f"    >> 🛑 Infeasible. Early exit inner loop.")

            # 3. 更新索引 (递归进位)
            innermost_idx = self.n_constr - 1
            current_dim = innermost_idx
            
            posg[current_dim] += active_jump
            
            # 处理进位
            while current_dim >= 0:
                if posg[current_dim] > maxg[current_dim]:
                    if current_dim == 0:
                        print(f"\n  [AUGMECON-R] Loop Finished.")
                        print(f"  -> Valid Solutions: {len(all_solutions)}")
                        print(f"  -> Infeasible/Skipped: {infeas_count} (Actual calls)")
                        return pd.DataFrame(all_solutions)
                    
                    posg[current_dim] = 0
                    current_dim -= 1
                    posg[current_dim] += 1
                else:
                    break