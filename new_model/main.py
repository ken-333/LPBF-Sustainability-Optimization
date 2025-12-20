import pandas as pd
import os

# ============================================================
# 导入我们刚刚构建的 Layer 2 和 Layer 3
# ============================================================
from augmecon_r import AugmeconRGamsStyle  # Layer 2: 总指挥
from hybrid_solver import HybridSolver     # Layer 3: 特种部队 (H-DE 实现)
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
    'Efficiency': {'type': 'max'}, # 效率：越高越好
    'Quality_Robustness': {'type': 'min'}  #工艺鲁棒性/PRI (Min) -> 越小代表质量越好且越稳
}

# 网格密度 (决定帕累托前沿的精细度)
GRID_POINTS = 5

def run_pipeline():
    print(f"{'='*60}")
    print(f"🚀 启动 H-DE-AUGMECON-R (4-Objective Path A) 优化流程")
    print(f"🎯 主目标 (Primary): Cost")
    print(f"⛓️  约束目标 (Constraints): Carbon, Efficiency, Quality_Robustness")
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
        solver = HybridSolver(lt_val = lt)

        # ---------------------------------------------------------
        # Step 2: 派遣总指挥 (Layer 2)
        # ---------------------------------------------------------
        # 实例化 GAMS 风格控制器，注入求解器和目标配置
        controller = AugmeconRGamsStyle(
            solver_handler = solver,
            objective_config = OBJECTIVE_CONFIG,
            grid_points = GRID_POINTS
        )

        # 1. 计算支付表 (确定 4 个目标的物理边界)
        print(f"  [Step 1] 计算支付表 (Payoff Table)...")
        controller.calculate_payoff_table()
        
        # 2. 执行核心循环 (切片扫描)
        print(f"  [Step 2] 开始多目标扫描 (Grid Search)...")
        df_res = controller.solve()

        if not df_res.empty:
            df_res['LT_um'] = lt
            
            # 这里的列名处理要小心，确保包含所有4个目标
            cols_to_keep = ['P_W', 'V_mm_s', 'H_um', 'LT_um', 
                            'RD', 'ED', 'is_feasible',
                            'Cost', 'Carbon', 'Efficiency', 'Quality_Robustness']
            
            # 防御性编程：只保留存在的列
            cols_to_keep = [c for c in cols_to_keep if c in df_res.columns]
            df_res = df_res[cols_to_keep]

            all_layer_results.append(df_res)
            print(f"✅ 层厚 {lt} um 完成，找到 {len(df_res)} 个帕累托解。")
        else:
            print(f"⚠️ 层厚 {lt} um 未找到可行解。")

    # ---------------------------------------------------------
    # Step 4: 汇总与后处理 (Layer 4)
    # ---------------------------------------------------------
    if all_layer_results:
        print(f"\n{'='*60}")
        print("💾 正在保存最终结果...")

        # 合并所有层厚的结果
        final_df = pd.concat(all_layer_results, ignore_index=True)    #pd.concat(...) 把列表里的所有 DataFrame，像“竖着叠表格”一样拼成一个大表   ignore_index=True ：自动重新编号 index

        # 保存原始数据
        output_file = "raw_pareto_results.xlsx"
        final_df.to_excel(output_file, index=False)    #把这个大表 final_df 保存成一个 Excel 文件。 index=False：将index删掉，没用
        print(f"📄 结果已保存至: {os.path.abspath(output_file)}")
        # 调用后处理 (需要修改 post_process 支持 4 目标)
        post_process.run_topsis_standard(final_df)
    else:
        print("❌ 未找到任何解，请检查约束是否过严。")

if __name__ == "__main__":
    run_pipeline()







                












