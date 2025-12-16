import pandas as pd
import os

# ============================================================
# 导入我们刚刚构建的 Layer 2 和 Layer 3
# ============================================================
from augmecon_r import AugmeconRGamsStyle  # Layer 2: 总指挥
from hybrid_solver import HycridSolver     # Layer 3: 特种部队 (H-DE 实现)
import post_process                        # Layer 4: 后处理 (画图/排序)

# ============================================================
# 配置区域
# ============================================================
#定义优化目标及方向
# 注意：第一个目标 ('Cost') 将被作为主目标 (Primary Objective)
# 后面的目标 ('Carbon') 将被作为 epsilon 约束目标
OBJECTIVE_CONFIG = {
    'Cost': {'type': 'min'}, # 成本：越低越好
    'Carbon': {'type': 'min'}, # 碳排放：越低越好
    'Efficiency': {'type': 'max'} # 效率：越高越好
}

# 网格密度 (决定帕累托前沿的精细度)
GRID_POINTS = 20

def run_pipeline():
    print(f"{'='*60}")
    print(f"🚀 启动 H-DE-AUGMECON-R 优化流程")
    print(f"🎯 优化目标: {list(OBJECTIVE_CONFIG.keys())}")
    print(f"⚙️  网格密度: {GRID_POINTS}")
    print(f"{'='*60}")

    all_layer_results = []

    # 遍历不同的工艺层厚
    for lt in [80, 100, 120]:
        print(f"\n\n>>> 正在处理层厚: {lt} um ...")

        # ---------------------------------------------------------
        # Step 1: 组建特种部队 (Layer 3)
        # ---------------------------------------------------------
        # 实例化混合求解器，注入当前层厚参数
        solver = HycridSolver(lt_val = lt)

        # ---------------------------------------------------------
        # Step 2: 派遣总指挥 (Layer 2)
        # ---------------------------------------------------------
        # 实例化 GAMS 风格控制器，注入求解器和目标配置
        controller = AugmeconRGamsStyle(
            solver_handler = solver,
            objective_config = OBJECTIVE_CONFIG,
            grid_points = GRID_POINTS
        )

        # ---------------------------------------------------------
        # Step 3: 执行任务 (Run)
        # ---------------------------------------------------------
        try:
            # 这一步会自动执行 Payoff Table 计算 -> 网格生成 -> 循环求解
            df_res = controller.run()

            if not df_res.emoty:
                # 标记当前层厚
                df_res['LT_um'] = lt #因为 solver 层厚是固定的，但 controller.run() 的结果里不一定带 LT。

                # 整理列顺序 (让 Excel 好看一点)
                cols_order = ['LT_um', 'P_W', 'V_mm_s', 'H_um', 
                              'Cost', 'Carbon', 'Efficiency', 
                              'RD', 'ED', 'is_feasible']
                
                # 只保留存在的列
                cols_to_keep = [c for c in cols_order if c in df_res.columns]  # c 只是程序员随便起的一个变量名，本身没有任何特殊含义。在这里代表column
                df_res = df_res[cols_to_keep]

                all_layer_results.append(df_res)                                # append() 函数用于向列表的末尾添加新元素
                print(f"✅ 层厚 {lt} um 完成，找到 {len(df_res)} 个帕累托解。")
            else:
                print(f"⚠️ 层厚 {lt} um 未找到可行解。")

        except Exception as e:
            print(f"❌ 层厚 {lt} um 处理时发生错误: {e}")
            import traceback
            traceback.print_exc()

    # ---------------------------------------------------------
    # Step 4: 汇总与后处理 (Layer 4)
    # ---------------------------------------------------------
    if all_layer_results:
        print(f"\n{'='*60}")
        print("💾 正在保存最终结果...")

        # 合并所有层厚的结果
        final_df = pd.concat(all_layer_results, ignore_index=True)    #pd.concat(...) 把列表里的所有 DataFrame，像“竖着叠表格”一样拼成一个大表   ignore_index=True ：自动重新编号 index

        # 保存原始数据
        output_file = "final_pareto_results.xlsx"
        final_df.to_excel(output_file, index=False)    #把这个大表 final_df 保存成一个 Excel 文件。 index=False：将index删掉，没用
        print(f"📄 结果已保存至: {os.path.abspath(output_file)}")


        # 调用后处理模块 (TOPSIS 排序 + 画图)
        # 假设 post_process.py 里有相应的处理逻辑，或者你可以直接在这里写
        # 这里我们简单调用 post_process 的逻辑 (如果有封装好的函数)
        # 如果没有，你可以直接用 Excel 进行分析，或者在这里补充 TOPSIS 代码
        print("\n📊 统计信息:")

        print(final_df.groupby('LT_um')[['Cost', 'Carbon']].describe())
    else:
        print("\n❌ 整个流程未找到任何有效解，请检查约束条件或物理模型。")

if __name__ == "__main__":
    run_pipeline()







                












