import pandas as pd                           # for data handling in order to store results and exchange to excel
import numpy as np                            # in order to handle numerical arrays
import matplotlib.pyplot as plt               # for plotting
from mpl_toolkits.mplot3d import Axes3D       # for 3D plotting
import os                                     #做文件/路径判断，比如 os.path.exists()


# import topsis module
try:
    from topsis import Topsis
except ImportError:
    print("[Error] topsis.py module not found. Please ensure it is in the same directory.")
    exit()


# ==========================================
# 1. 回归模型系数
# ==========================================
REG_COEFFS = {                                #regression coefficients for energy density calculation
    'Intercept': 136.59848,                   # 截距 (常数项)
    # --- 一次项 ---
    'P':0.094923,                             # 对应Power的系数
    'V':-0.028654,                            # 对应Speed的系数
    'H':-0.201185,                            # 对应Hatch的系数
    'LT':-0.108546,                           # 对应Layer Thickness的系数
    'ED':-0.524864,                           # 对应 Energy Density

    # --- 二次项 ---
    'P^2':  -0.000051,
    'V^2':  0.00000883923,
    'H^2':  0.000575,
    'ED^2': 0.002459,

    # --- 交互项 ---
    'P*V':   -0.000012,
    'P*H':   -0.000123,
    'P*ED':  -0.000122,
    'V*H':   0.000013,
    'V*ED':  0.000096,
    'H*ED':  0.000450
}

def calculate_rd_manual(row):
    # 1. 获取变量 (从优化结果的列名 P_W 等提取)
    P = row['P_W']
    V = row['V_mm_s']
    H = row['H_um']
    LT = row['LT_um']

    # 2. 计算 Energy Density (ED)
    # 公式: ED = P / (V * H * LT) * 10^6
    # 单位换算: V(mm/s), H(um=10^-3 mm), LT(um=10^-3 mm)
    if V * H * LT == 0: return 0  #是防止除 0 崩溃（虽然正常物理参数不会是 0）
    ED = P / (V * H * LT * 1e-6)

    # 3. 提取系数 (为了写公式方便)
    c = REG_COEFFS                #为了写公式方便，给字典起一个短名字 c

    # 4. 代入多项式公式 (Eq.2)
    # 这里的结构与 Design-Expert 里的公式一致
    rd_val = (
        c['Intercept'] +
        c['P']*P + c['V']*V + c['H']*H + c['LT']*LT + c['ED']*ED +
        c['P^2']*(P**2) + c['V^2']*(V**2) + c['H^2']*(H**2) + c['ED^2']*(ED**2) +
        c['P*V']*(P*V) + c['P*H']*(P*H) + c['P*ED']*(P*ED) +
        c['V*H']*(V*H) + c['V*ED']*(V*ED) + c['H*ED']*(H*ED)
    )

    # 物理截断：RD 最大 100% （如果回归稍微 overshoot（比如算出 100.2），就把它截断成 100）
    return min(rd_val, 100.0)


# ==========================================
# 2. 对接标准 TOPSIS 算法 (直接使用 topsis.py 模块)
# ==========================================
def run_topsis_standard(df):
    print("   -> 正在准备 TOPSIS 数据...")

    # 1. 构建评价矩阵 (只包含目标函数列)
    eval_matrix = df[['Obj_Cost', 'Obj_Carbon', 'Obj_Efficiency']].to_numpy(dtype=float)

    # 2. 定义权重 (根据重要性自行设定)
    weights = [0.4, 0.2, 0.4]  # 权重总和没有硬性要求，可以是任意正数

    # 3. 准备方向标准 (Criteria)
    # 根据 topsis.py 的逻辑 (step_4):
    # If criteria[i] is True/1 -> Maximize (越大越好)
    # If criteria[i] is False/0 -> Minimize (越小越好)
    # 我们的目标: Cost(Min), Carbon(Min), Efficiency(Max)
    criteria = [False, False, True]

    # 4. 创建 Topsis 对象
    try :
        t = Topsis(eval_matrix, weights, criteria)

        # 5. 执行计算步骤
        # 我们不直接调用 t.calc()，因为它会打印大量中间步骤，刷屏太乱。
        # 我们手动调用核心步骤即可：
        t.step_2() # 归一化
        t.step_3() # 加权
        t.step_4() # 确定理想解/负理想解
        t.step_5() # 计算距离
        t.step_6() # 计算相似度 (worst_similarity)

        # 6. 获取结果
        # worst_similarity 就是 TOPSIS 得分 (接近1为最优)
        return t.worst_similarity
    
    except Exception as e:
        print(f"❌ TOPSIS 计算出错: {e}")
        return np.zeros(len(df))
    

# ==========================================
# 3. 绘图与主流程（三维帕托图 + 最优解高亮）
# ==========================================
def plot_3d(df, best_sols):         # df：所有通过 RD 筛选、参加 TOPSIS 的解（很多点）, best_sols：TOPSIS 最优解（少量点）
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d') #111：表示“1 行 1 列中的第 1 个子图”，也就是只有一个大图  projection='3d'：告诉 Matplotlib 使用 3D 坐标轴（来自 Axes3D）。

    colors = {80: '#1f77b4', 100: '#2ca02c', 120: '#d62728'}  # 80 μm → 蓝色 100 μm → 绿色 120 μm → 红色
    markers = {80: 'o', 100: '^', 120: 's'}                          #80 μm → 圆点 o 100 μm → 三角形 ^ 120 μm → 方形 s


    for lt in [80, 100, 120]:
        sub = df[df['LT_um'] == lt]
        if sub.empty: continue
        ax.scatter(sub['Obj_Cost'], sub['Obj_Efficiency'], sub['Obj_Carbon'],
                   c=colors[lt], marker=markers[lt], label=rf'LT {lt} $\mu m$', s=40, alpha=0.6)
        

    if not best_sols.empty:
        ax.scatter(best_sols['Obj_Cost'], best_sols['Obj_Efficiency'], best_sols['Obj_Carbon'],
                   c='gold', s=200, marker='*', edgecolors='black', label='Best Solution', zorder=10)
        
    ax.set_xlabel('Cost (CNY)')
    ax.set_ylabel('Efficiency ($mm^3/s$)')
    ax.set_zlabel('Carbon ($kg CO_2$)')
    ax.legend()      # 显示图例 Best Solution and LT labels


    if not os.path.exists('results'): os.makedirs('results')
    plt.savefig('results/pareto_front_3d.png', dpi=300)
    print("✅ 3D 图已保存至 results/pareto_front_3d.png")
    plt.show()

def main():
    # 1. 读取数据
    files = ["raw_pareto_results.xlsx", "results/raw_pareto_results.xlsx"]
    file_path = next((f for f in files if os.path.exists(f)), None)

    # 如果找不到，就报错退出
    if not file_path:
        print("[Error] 未找到 raw_pareto_results.xlsx 文件。请先运行主程序生成该文件。")
        return  
    
    #读入 Pareto 结果
    print(f"[Info] 读取数据: {file_path}")
    df_opt = pd.read_excel(file_path)

    # 2. 计算 RD 并筛选
    print("[Info] 正在计算致密度 (RD)...")
    df_opt['ED_Calculated'] = df_opt['P_W'] / (df_opt['V_mm_s'] * df_opt['H_um'] * df_opt['LT_um'] * 1e-6)
    df_opt['RD_Predicted'] = df_opt.apply(calculate_rd_manual, axis=1)
     

    #筛选标准: RD >= 95%
    df_valid = df_opt[df_opt['RD_Predicted'] >= 99].copy()
    print(f"   -> 合格解数量 (RD >= 99.5%): {len(df_valid)}")

    if len(df_valid) == 0:
       print("警告：没有解满足 99.5%")
       return
    
    if len(df_valid) > 0:
        # 3. 调用标准 TOPSIS 决策
        df_valid['Score'] = run_topsis_standard(df_valid)  #返回每一行对应的 TOPSIS 得分（0~1 越大越好）你把这个得分直接存到 Score 列。

        # 4. 输出结果
        print("\n" + "="*40)
        print("🏆 各层厚最佳工艺参数 (Best Solutions)")
        print("="*40)
        best_sols = pd.DataFrame()


        for lt in [80, 100, 120]:
            sub = df_valid[df_valid['LT_um'] == lt]
            if not sub.empty:
                best = sub.loc[sub['Score'].idxmax()]
                best_sols = pd.concat([best_sols, best.to_frame().T])
                print(f"[LT={lt}um] P={best['P_W']:.1f}W, V={best['V_mm_s']:.1f}mm/s, H={best['H_um']:.1f}um")
                print(f"   -> RD={best['RD_Predicted']:.2f}%, Cost={best['Obj_Cost']:.2f}, Score={best['Score']:.4f}")

        
        # 保存
        if not os.path.exists('results'): os.makedirs('results')
        df_valid.to_excel("results/final_processed_results.xlsx", index=False)
        print(f"\n✅ 结果已保存至: results/final_processed_results.xlsx")

        plot_3d(df_valid, best_sols)
    else:
        print("❌ 错误：所有解的致密度均过低。请检查优化约束。")

    
if __name__ == "__main__":
    main()