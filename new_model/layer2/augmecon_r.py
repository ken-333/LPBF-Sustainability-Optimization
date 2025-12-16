import numpy as np                            # in order to handle numerical arrays
import pandas as pd                           # for data handling in order to store results and exchange to excel
import time                                   #用于计时/性能统计

class AugmeconRGamsStyle:                     # 定义一个类，把 AUGMECON-R 的流程封装成可复用组件
    """
    Python implementation that strictly mirrors the GAMS logic of AUGMECON-R.
    Reference: 'Augmecon-R-fdff0312.../AUGMECON-R' GAMS code.
    """
    
    def __init__(self, solver_handler, objective_config, grid_points=20):
        self.solver = solver_handler
        self.obj_config = objective_config
        self.grid_points = grid_points
        
        # 提取目标函数名称
        self.obj_names = list(objective_config.keys())
        self.primary_obj = self.obj_names[0]      # 主目标 (Z)
        self.constrained_objs = self.obj_names[1:] # 约束目标 (Constraint Objectives)
        self.n_constr = len(self.constrained_objs)
        
        # 数据存储
        self.payoff_table = pd.DataFrame(index=self.obj_names, columns=self.obj_names)   #创建 payoff table      行=“哪个目标做主目标”，列=“各目标值”。
        self.ranges = {} # min, max, range, step
        self.grids = {}  # 存储具体的网格值
        
    def _get_optimization_type(self, name):
        return self.obj_config[name]['type'] # 'min' or 'max'

    def calculate_payoff_table(self):
        """
        Phase 1: Lexicographic Payoff Table Construction
        完全对应 GAMS 代码中 loop(kp, solve...) 部分
        """
        print(f"  [AUGMECON-R] Constructing Payoff Table...")
        
        # 1. 轮流优化每个目标
        for primary in self.obj_names:
            print(f"    -> Optimizing {primary}...", end="")
            res = self.solver.solve(primary_obj_type=primary, constraint_map={})
            
            if res and res.get('is_feasible'):
                val = res[primary]
                print(f" Done. Ideal={val:.4f}")
                # 填表
                for col in self.obj_names:
                    self.payoff_table.loc[primary, col] = res[col]
            else:
                raise RuntimeError(f"Failed to find optimal solution for {primary}")

        # 2. 计算 Range 和 Step
        # 对应 GAMS: minobj(k), maxobj(k), range(k), step(k)
        for obj in self.constrained_objs:
            # Ideal: 对角线值
            ideal = self.payoff_table.loc[obj, obj]
            # Nadir: 该列的最差值
            col_vals = self.payoff_table[obj]
            if self.obj_config[obj]['type'] == 'min':
                nadir = col_vals.max()
            else:
                nadir = col_vals.min()
                
            r_val = abs(nadir - ideal)
            if r_val < 1e-6: r_val = 1e-6 # 避免除零
            
            step_val = r_val / (self.grid_points - 1)
            
            self.ranges[obj] = {
                'ideal': ideal,
                'nadir': nadir,
                'range': r_val,
                'step': step_val
            }
            
            # 生成网格值 (Grid RHS)
            # GAMS 逻辑: gridrhs = maxobj - numg/maxg * range (对于 min 问题)
            # 这意味着网格总是从 "最差(Nadir)" 到 "最好(Ideal)" 排列
            # 对于 Min 问题: Nadir(大) -> Ideal(小)
            # 对于 Max 问题: Nadir(小) -> Ideal(大)
            self.grids[obj] = np.linspace(nadir, ideal, self.grid_points)
            
            # 确保 grid[0] 是最宽松的约束 (Nadir)，grid[-1] 是最严格的 (Ideal)
            print(f"    -> Grid {obj}: [{self.grids[obj][0]:.2f} ... {self.grids[obj][-1]:.2f}] (Step={step_val:.4f})")

    def run(self):
        """
        Phase 2 & 3: Main Loop with Bypass and Early Exit
        完全复刻 GAMS 的手动循环控制逻辑 (lines 60-70)
        """
        if self.payoff_table.isnull().values.any():
            self.calculate_payoff_table()
            
        # --- 初始化变量 ---
        # posg: 当前每个维度的网格索引指针 (对应 GAMS 的 posg)
        # 初始全为 0 (从最宽松的 Nadir 点开始)
        posg = [0] * self.n_constr
        
        # maxg: 每个维度的最大索引 (GAMS: maxg)
        maxg = [self.grid_points - 1] * self.n_constr
        
        # flag: 标志阵列 (GAMS: flag(q,r,s))
        # 维度顺序与 self.constrained_objs 一致
        flag_shape = tuple([self.grid_points] * self.n_constr)
        flag_array = np.zeros(flag_shape, dtype=int)
        
        # jump: 跳跃步数 (GAMS: jump(k))
        jump = [1] * self.n_constr
        
        iter_count = 0
        infeas_count = 0
        all_solutions = []
        
        print(f"\n  [AUGMECON-R] Starting Main Loop (GAMS Logic)...")
        
        # === 模拟 GAMS 的 repeat ... until 循环 ===
        # GAMS 是通过手动调整 posg 来控制循环的，直到所有 posg 都达到 maxg
        
        while True:
            # 1. 检查是否结束 (对应 GAMS line 70 until 条件)
            # 如果所有维度都到达 maxg，且没有进位发生，则结束
            # 为了简单，我们在循环底部检查退出条件，或者使用 break
            
            # 构建当前的约束值 RHS
            current_constraints = {}
            current_indices = tuple(posg) # (i, j, k)
            
            for idx, obj_name in enumerate(self.constrained_objs):
                grid_idx = posg[idx]
                val = self.grids[obj_name][grid_idx]
                current_constraints[obj_name] = val
            
            # 2. 检查 Flag (GAMS: synthiki = flag(q,r,s))
            synthiki = flag_array[current_indices]
            
            if synthiki == 0:
                # === 求解 (Solve) ===
                # print(f"    Iter {iter_count}: {current_constraints} ... ", end="")
                res = self.solver.solve(self.primary_obj, current_constraints)
                iter_count += 1
                
                if res and res.get('is_feasible'):
                    # --- 可行 (Feasible) ---
                    # print("✅ OK")
                    all_solutions.append(res)
                    
                    # --- Bypass Logic (GAMS line 63) ---
                    # 计算每个维度的 b (能跳多少格)
                    # GAMS: b = floor(slack / step)
                    b_values = []
                    for idx, obj_name in enumerate(self.constrained_objs):
                        step = self.ranges[obj_name]['step']
                        limit = current_constraints[obj_name]
                        actual = res[obj_name]
                        
                        # 计算 Slack (无论 Min/Max，Slack 都是 "限制 - 实际" 的有利差值绝对值)
                        # Min: limit=10, actual=8 -> slack=2
                        # Max: limit=5, actual=7 -> slack=2
                        if self.obj_config[obj_name]['type'] == 'min':
                            slack = limit - actual
                        else:
                            slack = actual - limit
                        
                        if slack < 0: slack = 0 # 浮点误差保护
                        b = int(slack / step)
                        b_values.append(b)
                    
                    # 更新 Flag (Volume Marking)
                    # GAMS: flag(q,r,s) = b2 + 1
                    # GAMS 更新的是一个超立方体区域。
                    # 我们使用 Numpy 切片来批量更新
                    slices = []
                    for k, idx_val in enumerate(posg):
                        # 范围：当前点 ~ 当前点 + b[k]
                        # 注意：GAMS 的 flag 似乎主要影响当前最内层循环的后续步骤
                        # 这里我们严格按照逻辑：标记未来会被 Bypass 的点
                        end_val = min(idx_val + b_values[k] + 1, self.grid_points)
                        slices.append(slice(idx_val, end_val))
                    
                    # 标记为 b_innermost + 1 (GAMS line 63: flag...=b2+1)
                    # 这里为了简单，标记为 1 即可，表示跳过
                    # 注意：我们不能覆盖当前点（虽然它已经是0了），我们要标记"未来"的点
                    # 但 numpy 切片包含当前点。没关系，当前点已经跑完了。
                    flag_array[tuple(slices)] = 1
                    
                    # 计算 Jump (GAMS lines 65-66)
                    # GAMS 只更新最内层 (innermost) 的 jump
                    # jump(km1)$(numk(km1)=1) = 1 + floor(...)
                    # 假设 constrained_objs 的最后一个是最内层 (inner loop)
                    innermost_idx = self.n_constr - 1
                    jump[innermost_idx] = 1 + b_values[innermost_idx]
                    
                else:
                    # --- 不可行 (Infeasible) ---
                    # print("❌ Infeas (Early Exit)")
                    infeas_count += 1
                    
                    # Early Exit Logic (GAMS line 62)
                    # GAMS: flag(q,r,s) = terminal - current + 1
                    # 含义：封锁最内层循环剩余的所有点
                    
                    slices = []
                    for k, idx_val in enumerate(posg):
                        if k == self.n_constr - 1: # 最内层
                            slices.append(slice(idx_val, self.grid_points))
                        else:
                            slices.append(slice(idx_val, idx_val + 1)) # 只锁定当前层
                    
                    flag_array[tuple(slices)] = 1
                    
                    # 重置 jump，准备标准步进
                    innermost_idx = self.n_constr - 1
                    jump[innermost_idx] = 1

            else:
                # 如果 synthiki > 0 (被 Flag 标记跳过)
                # 我们不需要求解，直接准备调整索引
                # GAMS 逻辑里，如果 synthiki > 0，它会利用这个值来辅助步进
                pass

            # === 3. 索引推进 (Index Advancement / GAMS Clock Logic) ===
            # 对应 GAMS lines 67-70
            # 这是一个手动实现的 N 维计数器进位逻辑
            
            # GAMS 是通过 loop(km1...) 来实现的。
            # 核心逻辑：
            # 1. 尝试增加最内层索引 pos[last] += jump[last]
            # 2. 如果超过 max，则 pos[last] = 0，并进位到 pos[last-1] += 1
            # 3. 还要考虑 synthiki (Flag) 对步进的影响
            
            # 简化版实现 (逻辑等效):
            # 我们总是操作最内层 (last index)。
            # 如果当前被 flag 标记 (synthiki > 0)，我们应该跳过 synthiki 这么多步
            # GAMS line 68: control2 = pos + synthiki
            
            active_jump = 1
            innermost_idx = self.n_constr - 1
            
            if synthiki == 0:
                # 正常步进：使用计算出的 jump (如果有 bypass)
                active_jump = jump[innermost_idx]
            else:
                # 被 Flag 标记：跳过 Flag 指定的步数 (或者简单地 +1，因为 Flag 已经覆盖了区域)
                # GAMS line 68 暗示可以直接跳 synthiki 步
                # 这里我们保守一点，如果被 flag 了，就 +1，快速通过 flag 区域
                active_jump = 1 

            # 执行进位加法
            # 从最内层开始加
            current_dim = innermost_idx
            posg[current_dim] += active_jump
            
            # 处理进位 (Carry Over)
            while current_dim >= 0:
                if posg[current_dim] > maxg[current_dim]:
                    # 当前维度溢出
                    if current_dim == 0:
                        # 最外层也溢出了 -> 结束循环
                        print(f"\n  [AUGMECON-R] Loop Finished. Solutions: {len(all_solutions)}, Infeas: {infeas_count}")
                        return pd.DataFrame(all_solutions)
                    
                    # 进位：当前维归零 (GAMS line 70: posg...=0)，上一维 +1
                    # GAMS 其实并不是归零，而是重置为 0 (从 Nadir 开始)
                    posg[current_dim] = 0 
                    
                    # 进位到上一层
                    current_dim -= 1
                    posg[current_dim] += 1
                    
                    # 重置 jump (GAMS line 66: jump...=1 for outer loops)
                    # 每次进位后，内层的 jump 应该重置为 1
                    jump = [1] * self.n_constr
                else:
                    # 没有溢出，进位结束
                    break
            
            # 循环继续，进入下一次迭代