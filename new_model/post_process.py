import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import os
import ast

# 尝试导入 topsis 模块
try:
    from topsis import Topsis
except ImportError:
    print("[Error] topsis.py module not found. Please ensure it is in the same directory.")
    Topsis = None

# ==========================================
# 1. 回归模型系数 (保持不变)
# ==========================================
REG_COEFFS = {
    'Intercept': 136.59848,
    'P':0.094923, 'V':-0.028654, 'H':-0.201185, 'LT':-0.108546, 'ED':-0.524864,
    'P^2': -0.000051, 'V^2': 0.00000883923, 'H^2': 0.000575, 'ED^2': 0.002459,
    'P*V': -0.000012, 'P*H': -0.000123, 'P*ED': -0.000122,
    'V*H': 0.000013, 'V*ED': 0.000096, 'H*ED': 0.000450
}

def calculate_rd_manual(row):
    try:
        P = row.get('P_W', row.get('P', 0))
        V = row.get('V_mm_s', row.get('V', 0))
        H = row.get('H_um', row.get('H', 0))
        LT = row.get('LT_um', row.get('LT', 0))
    except: return 0
    if V*H*LT == 0: return 0
    ED = P / (V * H * LT * 1e-6)
    c = REG_COEFFS
    rd_val = (c['Intercept'] + c['P']*P + c['V']*V + c['H']*H + c['LT']*LT + c['ED']*ED +
              c['P^2']*(P**2) + c['V^2']*(V**2) + c['H^2']*(H**2) + c['ED^2']*(ED**2) +
              c['P*V']*(P*V) + c['P*H']*(P*H) + c['P*ED']*(P*ED) +
              c['V*H']*(V*H) + c['V*ED']*(V*ED) + c['H*ED']*(H*ED))
    return min(rd_val, 100.0)

# ==========================================
# 2. 核心功能：TOPSIS 排序
# ==========================================
def run_topsis_standard(df_input):
    """执行 4 目标 TOPSIS 排序"""
    print("\n" + "="*40)
    print("🏆 执行 TOPSIS 多目标决策 (4-Objective)")
    print("="*40)
    
    # 复制数据
    df_data = df_input.copy()
    
    # ----------------------------------------------------
    # 🟢 [关键修复] 强制列名映射
    # 不管有没有，都尝试把 Cost 复制一份给 Obj_Cost
    # ----------------------------------------------------
    print(f"   [Debug] 原始列名: {list(df_data.columns)}")
    
    if 'Cost' in df_data.columns: df_data['Obj_Cost'] = df_data['Cost']
    if 'Carbon' in df_data.columns: df_data['Obj_Carbon'] = df_data['Carbon']
    if 'Efficiency' in df_data.columns: df_data['Obj_Efficiency'] = df_data['Efficiency']
    
    # ----------------------------------------------------
    
    # 定义需要的列
    target_cols = ['Obj_Cost', 'Obj_Carbon', 'Obj_Efficiency', 'Quality_Robustness']
    
    # 检查列是否齐备
    missing_cols = [c for c in target_cols if c not in df_data.columns]
    if missing_cols:
        print(f"❌ 错误：映射后仍然缺少列: {missing_cols}")
        print(f"   当前列: {list(df_data.columns)}")
        return None

    # 提取矩阵
    eval_matrix = df_data[target_cols].astype(float).values
    
    # 定义权重 (Cost, Carbon, Eff, PRI)
    weights = ([0.45, 0.25, 0.20, 0.10])
    
    # 定义方向 (根据 topsis.py: False=Min, True=Max)
    # Cost(Min), Carbon(Min), Efficiency(Max), PRI(Min)
    criteria = [False, False, True, False]
    
    try:
        if Topsis is None:
             raise ImportError("Topsis module not loaded.")
        

        t = Topsis(eval_matrix, weights, criteria)
        t.calc() # 这里会打印中间步骤
        scores = t.worst_similarity
        
        # 将得分写回原始 DataFrame
        # 注意：这里我们写回 df_input (用户传进来的那个变量)，这样外部也能看到
        df_input['Score'] = scores
        
        # 输出最佳结果
        df_sorted = df_input.sort_values(by='Score', ascending=False)
        best_row = df_sorted.iloc[0]
        
        print(f"\n🌟 综合最佳解 (Top 1 Solution):")
        print(f"   P={best_row['P_W']:.1f}, V={best_row['V_mm_s']:.1f}, H={best_row['H_um']:.1f}")
        print(f"   Cost={best_row.get('Cost',0):.2f}, PRI={best_row['Quality_Robustness']:.4f}, Score={best_row['Score']:.4f}")

        # 保存带得分的结果
        output_file = "final_ranked_results.xlsx"
        df_sorted.to_excel(output_file, index=False)
        print(f"\n📄 排序后的详细结果已保存至: {os.path.abspath(output_file)}")
        
        # 画图
        plot_3d_result(df_sorted)
        
        return scores
        
    except Exception as e:
        print(f"❌ TOPSIS 计算错误: {e}")
        return None

# ==========================================
# 3. 绘图功能
# ==========================================
def plot_3d_result(df):
    try:
        fig = plt.figure(figsize=(10, 8))
        ax = fig.add_subplot(111, projection='3d')
        
        # 优先使用 Obj_ 前缀，如果没有则用原始名
        x_col = 'Obj_Cost' if 'Obj_Cost' in df.columns else 'Cost'
        y_col = 'Obj_Efficiency' if 'Obj_Efficiency' in df.columns else 'Efficiency'
        z_col = 'Obj_Carbon' if 'Obj_Carbon' in df.columns else 'Carbon'
        c_col = 'Quality_Robustness'

        sc = ax.scatter(df[x_col], df[y_col], df[z_col], c=df[c_col], cmap='viridis_r', s=40)
        plt.colorbar(sc, label='PRI (Lower is Better)')
        
        ax.set_xlabel('Cost')
        ax.set_ylabel('Efficiency')
        ax.set_zlabel('Carbon')
        
        plt.savefig('pareto_result_3d.png', dpi=300)
        print("🖼️  图片已保存: pareto_result_3d.png")
    except Exception as e:
        print(f"⚠️ 绘图失败: {e}")

# ==========================================
# 4. 程序入口 
# ==========================================
if __name__ == "__main__":
    # 指定要读取的文件名 (由 main.py 生成)
    input_file = "raw_pareto_results.xlsx"
    
    if os.path.exists(input_file):
        print(f"📂 正在加载数据: {input_file}")
        try:
            # 读取 Excel 文件
            df = pd.read_excel(input_file)
            
            # 运行 TOPSIS 排序
            run_topsis_standard(df)
            
        except Exception as e:
            print(f"❌ 读取文件出错: {e}")
    else:
        print(f"❌ 找不到文件 '{input_file}'。请先运行 main.py 生成数据。")