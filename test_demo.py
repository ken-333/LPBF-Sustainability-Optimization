from pyomo.environ import *
from pyaugmecon import PyAugmecon
import pandas as pd

# ==========================================
# 第一部分：定义模型 (模仿 optimization_models.py)
# ==========================================
def create_test_model():
    """
    这是一个符合 PyAugmecon 标准格式的模型生成器函数。
    """
    model = ConcreteModel()

    # 1. 定义变量 (对应你的 P, V, H)
    # 这里我们定义 x1, x2 作为测试
    model.x1 = Var(within=NonNegativeReals, bounds=(0, 20))
    model.x2 = Var(within=NonNegativeReals, bounds=(0, 40))

    # 2. 定义约束 (对应你的致密度约束)
    def constraint_rule(m):
        return 5 * m.x1 + 4 * m.x2 <= 200
    model.C1 = Constraint(rule=constraint_rule)

    # 3. 定义目标函数 (对应你的 碳排放、成本、效率)
    # 注意：AUGMECON 内部逻辑基于“最小化”。
    # 如果原题是“最大化”，请加负号 (-) 变为最小化。
    
    # 目标1：最大化 x1  --> 变为 最小化 -x1
    def obj1_rule(m):
        return -1 * m.x1

    # 目标2：最大化 3x1 + 4x2 --> 变为 最小化 -(3x1 + 4x2)
    def obj2_rule(m):
        return -1 * (3 * m.x1 + 4 * m.x2)

    # ===================================================
    # 【关键步骤 1】必须使用 ObjectiveList
    # ===================================================
    model.obj_list = ObjectiveList()
    model.obj_list.add(expr=obj1_rule(model), sense=minimize)
    model.obj_list.add(expr=obj2_rule(model), sense=minimize)

    # ===================================================
    # 【关键步骤 2】初始化时必须“停用”所有目标
    # 作者的逻辑是：算法运行时会自己去根据需要激活某一个目标
    # 所以一开始要全部关掉，否则 Pyomo 会报错说有多个激活的目标
    # ===================================================
    for o in range(len(model.obj_list)):
        model.obj_list[o + 1].deactivate()

    return model

# ==========================================
# 第二部分：执行求解 (模仿 client.py)
# ==========================================
if __name__ == "__main__":
    # 1. 设置配置项 (opts)
    opts = {
        # 'grid_points': 网格密度。数字越大，解越密，算得越慢。
        # 对于你的科研，建议先设为 10 测试，正式跑设 20-50。
        "grid_points": 10,  
        
        # 'early_exit': 加速机制，遇到不可行解直接跳过
        "early_exit": True, 
        
        # 'solver_name': 指定求解器，你有 Gurobi 就填 gurobi
        "solver_name": "gurobi" 
    }

    print("正在初始化 PyAugmecon...")
    
    # 2. 实例化求解器
    # 注意：这里调用了上面的 create_test_model() 函数
    pyaugmecon = PyAugmecon(create_test_model(), opts)

    print("开始求解 Pareto 前沿...")
    
    # 3. 开始计算
    pyaugmecon.solve()

    # 4. 获取结果
    # get_pareto_solutions() 返回的是目标值的列表
    pareto_sols = pyaugmecon.get_pareto_solutions()
    
    print(f"\n计算完成！找到了 {len(pareto_sols)} 个最优解。\n")

    # 5. 整理并打印结果
    # 我们遍历每一个最优解，把它的变量值取出来
    results = []
    for sol_obj_values in pareto_sols:
        # 获取该解对应的决策变量 (x1, x2)
        dec_vars = pyaugmecon.get_decision_variables(sol_obj_values)
        
        # 还原目标值的正负号 (因为前面为了最小化加了负号)
        true_obj1 = -1 * sol_obj_values[0]
        true_obj2 = -1 * sol_obj_values[1]
        
        # 存入列表
        # 注意：作者返回的 decision_vars 是一个字典，值是 pandas Series
        # 我们用 .item() 取出里面的具体数值
        row = {
            "目标1 (x1)": true_obj1,
            "目标2 (Profit)": true_obj2,
            "变量 x1": dec_vars['x1'].item() if hasattr(dec_vars['x1'], 'item') else dec_vars['x1'],
            "变量 x2": dec_vars['x2'].item() if hasattr(dec_vars['x2'], 'item') else dec_vars['x2']
        }
        results.append(row)

    # 转为 DataFrame 显示
    df = pd.DataFrame(results)
    # 按目标1排序
    df = df.sort_values(by="目标1 (x1)")
    print(df)

    # 导出结果到 Excel
    # df.to_excel("my_test_results.xlsx", index=False)