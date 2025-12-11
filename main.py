import pandas as pd # for data handling in order to store results and exchange to excel
from  pyaugmecon import PyAugmecon
import config as cfg
from model_builder import create_lpbf_model

def run_optimization():
    all_raw_results = []  # List to store raw Pareto results for all layer thicknesses
  
    print(">>> Start LPBF Multi-objective Optimization <<<")
    for lt_val in [80, 100, 120]: #Loop over each layer thickness. Each value is sent into the optimization process.
        print(f"\n[Status] Optimizing for Layer Thickness = {lt_val} um ...")
        
        #1. create Model Factory
        # PyAugmecon 需要一个无参数的函数来创建模型
        # 我们用 lambda 表达式把当前的 lt_val "固化" 进去
        model_instance = create_lpbf_model(lt_val)
        # why use lambda here? 
        # PyAugmecon(model_factory, ...) 要求第一个参数是一个函数，而不是一个模型对象。
        # 如果我们直接写 create_lpbf_model(80)，它会立即执行并返回一个模型对象，这会报错。
        # 写成 lambda: create_lpbf_model(80)，相当于把函数“打包”好交给求解器，求解器想什么时候调用就什么时候调用。

        #2. setup PyAugmecon optimizer
        opts = {
            'log_name': f'log_lt_{lt_val}', # log file name
            'grid_points': 2,               # number of grid points in each objective
            'solver_name': 'gurobi',        # choose Gurobi as the solver
             # 【关键】传递给 Gurobi 的参数
            'solver_opts': cfg.SOLVER_OPTS  # 包含 {'NonConvex': 2}
        }

        #3. create optimizer object
        try:
            solver = PyAugmecon(model_instance, opts)
            solver.solve()
        except Exception as e:
            print(f"[Error] Optimization failed for Layer Thickness = {lt_val} um. Error: {e}")
            continue

        #4. retrieve results
        # 获取所有帕托最优的目标函数值组合 (列表的元组)
        pareto_objectives = solver.get_pareto_solutions() # get all pareto solutions

        print(f" -> Found {len(pareto_objectives)} pareto solutions. ")

        for obj_vals in pareto_objectives:
            # obj_vals 是一个元组: (Cost, Carbon, Efficiency)
            # 注意: PyAugmecon 内部是最大化，所以 Cost 和 Carbon 可能是负数
            # 我们在 model_builder 里已经乘了 -1，这里拿到的就是负值

            # 获取对应的决策变量 (P, V, H)
            # 返回的是一个字典: {'P': Series, 'V': Series...}
            
            dec_vars = solver.get_decision_variables(obj_vals)

            def safe_get(possible_names):
                for name in possible_names:
                    if name in dec_vars:
                        val = dec_vars[name]
                        return val.iloc[0] if hasattr(val, 'iloc') else val
                available_keys = list(dec_vars.keys())
                raise KeyError(f"无法找到变量 {possible_names}。当前可用变量名: {available_keys}")

            try:
                p_val = safe_get(['Power_W', 'P'])      
                v_val = safe_get(['Speed_mm_s', 'V'])   
                h_val = safe_get(['Hatch_um', 'H'])     
            except KeyError as e:
                print(f"[Warning] 跳过无效解: {e}")
                continue

            # 存储结果
            record = {
                'LT_um': lt_val,
                'P_W': p_val,
                'V_mm_s': v_val,
                'H_um': h_val,

                # 还原目标函数值 (取绝对值还原为正数)
                'Obj_Cost': -1 * obj_vals[0],   # 因为我们在 model_builder 乘了 -1
                'Obj_Carbon': -1 * obj_vals[1], # 同上
                'Obj_Efficiency': obj_vals[2]   # 本身就是最大化，不用变
            }
            all_raw_results.append(record)
    
    # 5. 初步保存
    print("\n[Status] Optimization finished. Saving raw results...")
    df_raw = pd.DataFrame(all_raw_results)

    # 保存到 Excel 方便查看 (中间存档)
    df_raw.to_excel("raw_pareto_results.xlsx", index=False)

    return all_raw_results

if __name__ == "__main__":
    # 测试运行
    results = run_optimization()
    print(f"Total solutions collected: {len(results)}")