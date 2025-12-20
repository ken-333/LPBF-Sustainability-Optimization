import pandas as pd
import numpy as np
from scipy.optimize import differential_evolution
import config as cfg
import test_new  # 确保这里导入的是修改后返回 (Cost, Carbon, RD, ED) 的 test.py

# ==========================================
# 移植部分 A: 目标函数构建 (对应 pyaugmecon/model.py 的 convert_prob)
# ==========================================
def hybrid_objective_function(x, lt_val, eps_carbon):
    """
    逻辑移植：将多目标转化为单目标+罚函数
    对应原库：model.obj_list[1].expr += ... slack ...
    """
    # 1. 物理计算 (黑盒替代 Pyomo)
    Cost, Carbon, RD, ED = test_new.predict_performance(x, lt_val)
    
    # 2. 基础目标
    final_score = Cost
    
    # 3. 罚函数 (替代 Gurobi 的硬约束)
    PENALTY = 1e6 
    
    # 物理约束
    if RD < 99.5: final_score += PENALTY * (99.5 - RD) ** 2
    if ED < 30.0: final_score += PENALTY * (30.0 - ED) ** 2
    elif ED > 80.0: final_score += PENALTY * (ED - 80.0) ** 2

    # AUGMECON 核心约束 (Carbon <= epsilon)
    if Carbon > eps_carbon:
        final_score += PENALTY * (Carbon - eps_carbon) ** 2
        
    return final_score

# ==========================================
# 移植部分 B: 求解流程控制 (对应 pyaugmecon/solver_process.py)
# ==========================================
def run_optimization():
    print(">>> 启动 DE-AUGMECON-R (逻辑移植版) <<<")
    
    all_results = []
    bounds = [(385, 460), (700, 1150), (90, 115)]
    
    for lt_val in [80, 100, 120]:
        print(f"\n{'='*40}")
        print(f"正在优化层厚: {lt_val} um")
        print(f"{'='*40}")
        
        # --- 1. 网格初始化 (对应 model.py 的 find_obj_range) ---
        # 设定 Carbon 的搜索范围 (Payoff Table 的上下界)
        min_c, max_c = 5.0, 15.0  
        grid_points = 20
        step = (max_c - min_c) / (grid_points - 1) # 计算步长
        
        print(f"  网格范围: [{min_c}, {max_c}], 步长: {step:.4f}")
        
        # 初始化循环变量
        current_eps = max_c  # 从最宽松的约束开始
        
        # --- 2. 主循环 (对应 solver_process.py 的 run 方法) ---
        while current_eps >= min_c - 1e-6:
            print(f"  > 约束 Epsilon (Carbon <= {current_eps:.4f}) ...", end="")
            
            # --- 求解 (替代 model.solve) ---
            result = differential_evolution(
                func=hybrid_objective_function,
                bounds=bounds,
                args=(lt_val, current_eps),
                strategy='best1bin',
                maxiter=100,
                popsize=15,
                tol=0.01,
                seed=42 # 保证复现性
            )
            
            # 提取真实物理值
            if result.success:
                best_x = result.x
                real_cost, real_c, real_rd, real_ed = test_new.predict_performance(best_x, lt_val)
                
                # 判断可行性 (替代 model.is_infeasible)
                # 允许微小误差 (罚函数特性)
                is_feasible = (real_rd >= 99.45) and (real_c <= current_eps + 0.1) and (30 <= real_ed <= 80)
            else:
                is_feasible = False

            # --- 3. 核心逻辑分支 (复刻 solver_process.py 的跳转逻辑) ---
            
            if is_feasible:
                # 成功找到解
                print(f" 成功! [Cost: {real_cost:.2f}, C_real: {real_c:.2f}]")
                
                # 保存数据
                vol_rate = best_x[1] * best_x[2] * lt_val * 1e-6
                record = {
                    'LT_um': lt_val,
                    'P_W': best_x[0], 'V_mm_s': best_x[1], 'H_um': best_x[2],
                    'Obj_Cost': real_cost, 'Obj_Carbon': real_c,
                    'Obj_Efficiency': vol_rate, 'RD_Predicted': real_rd,
                    'ED_J_mm3': real_ed
                }
                all_results.append(record)
                
                # [核心移植] 旁路跳跃 (Bypass Logic)
                # 原库逻辑：slack = round(model.slack_val); jump = int(slack / step)
                # 移植逻辑：直接用真实值计算下一个网格点
                
                slack = current_eps - real_c
                
                # 如果有显著松弛 (Slack > Step)，说明中间的网格点被“跨越”了
                if slack > step:
                    skipped_steps = int(slack / step)
                    print(f"    >>> [AUGMECON-R] Slack={slack:.4f}. 跳过 {skipped_steps} 个冗余网格点 (Bypass).")
                
                # 更新下一个 epsilon：直接设为 "实际值 - step"
                # 这等效于原库的 jump 逻辑
                current_eps = real_c - step
                
            else:
                # [核心移植] 早退机制 (Early Exit)
                # 原库逻辑：if early_exit and is_infeasible: break/continue
                print(f" 失败 (RD={real_rd:.2f}%). [Early Exit] 停止当前层厚搜索.")
                break # 直接退出 while 循环，不再尝试更严格的约束

    # ==========================================
    # 结果保存 (复用原 post_process 接口)
    # ==========================================
    if all_results:
        df = pd.DataFrame(all_results)
        df = df.drop_duplicates(subset=['Obj_Cost', 'Obj_Carbon'])
        output_file = "hybrid_pareto_results.xlsx"
        df.to_excel(output_file, index=False)
        print(f"\n>>> 优化完成！共找到 {len(df)} 个有效解。结果已保存至 {output_file}")
    else:
        print("\n>>> 警告：未找到任何可行解。")

if __name__ == "__main__":
    run_optimization()