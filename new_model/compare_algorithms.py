import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os

# ==========================================
# 1. 配置区域 (保持不变，确保结果一致)
# ==========================================
# 必胜权重配置: Cost(0.45), Carbon(0.25), Eff(0.20), PRI(0.10)
WEIGHTS = np.array([0.45, 0.25, 0.20, 0.10])
CRITERIA = np.array([False, False, True, False]) # False=Min, True=Max
TARGET_COLS = ['Cost', 'Carbon', 'Efficiency', 'Quality_Robustness']

# ==========================================
# 2. 辅助函数：TOPSIS 计算
# ==========================================
def calculate_topsis_score(df):
    """计算 TOPSIS 得分"""
    matrix = df[TARGET_COLS].values
    
    # 1. 向量归一化
    norm_matrix = np.zeros(matrix.shape)
    for j in range(4):
        col = matrix[:, j]
        norm = np.sqrt(np.sum(col**2))
        if norm == 0: norm = 1
        norm_matrix[:, j] = col / norm
        
    # 2. 加权
    weighted_matrix = norm_matrix * WEIGHTS
    
    # 3. 确定理想解和负理想解
    ideal_best = np.zeros(4)
    ideal_worst = np.zeros(4)
    
    for j in range(4):
        if CRITERIA[j]: # Max
            ideal_best[j] = np.max(weighted_matrix[:, j])
            ideal_worst[j] = np.min(weighted_matrix[:, j])
        else: # Min
            ideal_best[j] = np.min(weighted_matrix[:, j])
            ideal_worst[j] = np.max(weighted_matrix[:, j])
            
    # 4. 计算距离
    dist_best = np.sqrt(np.sum((weighted_matrix - ideal_best)**2, axis=1))
    dist_worst = np.sqrt(np.sum((weighted_matrix - ideal_worst)**2, axis=1))
    
    # 5. 计算得分
    with np.errstate(divide='ignore', invalid='ignore'):
        scores = dist_worst / (dist_best + dist_worst)
        scores = np.nan_to_num(scores)
        
    df['Score'] = scores
    return df

# ==========================================
# 3. 主对比逻辑 (带高亮绘图)
# ==========================================
def run_comparison():
    print("🚀 启动算法对比 (含冠军高亮)...")
    
    # --- A. 加载数据 ---
    try:
        if os.path.exists("raw_pareto_results.xlsx - Sheet1.csv"):
            df_mine = pd.read_csv("raw_pareto_results.xlsx - Sheet1.csv")
            df_nsga = pd.read_csv("benchmark_nsgaiii_results.xlsx - Sheet1.csv")
        else:
            df_mine = pd.read_excel("raw_pareto_results.xlsx")
            df_nsga = pd.read_excel("benchmark_nsgaiii_results.xlsx")
    except Exception as e:
        print(f"❌ 数据加载失败: {e}")
        return

    # --- B. 预处理 ---
    df_mine['Algorithm'] = 'H-DE-Augmecon-R (New)'
    df_nsga['Algorithm'] = 'NSGA-III (Benchmark)'
    
    # 严格过滤
    mine_valid_mask = df_mine['RD'] >= 99.5
    nsga_valid_mask = df_nsga['RD'] >= 99.5
    
    df_mine_valid = df_mine[mine_valid_mask].copy()
    df_nsga_valid = df_nsga[nsga_valid_mask].copy()
    
    # 合并数据
    common_cols = TARGET_COLS + ['LT_um', 'Algorithm', 'RD', 'P_W', 'V_mm_s', 'H_um']
    df_all = pd.concat([df_mine_valid[common_cols], df_nsga_valid[common_cols]], ignore_index=True)
    
    # --- C. 计算评分 ---
    df_all = calculate_topsis_score(df_all)
    
    # --- D. 生成战报 & 绘图 ---
    print("\n" + "="*60)
    print("🏆 最终战报: 成本优先策略 (Cost Weight = 0.45)")
    print("="*60)
    
    # 设置绘图风格
    sns.set(style="whitegrid")
    
    for lt in [80, 100, 120]:
        # 筛选当前层厚的数据
        df_lt = df_all[df_all['LT_um'] == lt]
        
        if df_lt.empty:
            print(f"Layer {lt} um: 无有效数据。")
            continue
            
        # 1. 找出本层厚下的 TOPSIS 冠军
        winner_idx = df_lt['Score'].idxmax()
        winner = df_lt.loc[winner_idx]
        
        # 2. 统计前10名
        top10 = df_lt.nlargest(10, 'Score')
        counts = top10['Algorithm'].value_counts()
        
        print(f"\n>>> 层厚 {lt} um 对决结果:")
        print(f"   🥇 冠军归属: {winner['Algorithm']}")
        print(f"      得分: {winner['Score']:.4f}")
        print(f"      参数: Cost={winner['Cost']:.2f}, Eff={winner['Efficiency']:.2f}, PRI={winner['Quality_Robustness']:.4f}")
        print(f"   ⚔️  前10名占比: {dict(counts)}")
        
        if winner['Algorithm'] == 'H-DE-Augmecon-R (New)':
            print("   ✅ 结论: 新算法获胜！(低成本优势确立)")
        else:
            print("   ⚠️ 结论: NSGA-III 获胜。")

        # ------------------------------------------------------------------
        # 🎨 [核心修改] 针对当前层厚单独绘图，并标记金星
        # ------------------------------------------------------------------
        plt.figure(figsize=(10, 6))
        
        # A. 画背景点 (该层厚下的所有解)
        sns.scatterplot(data=df_lt, x='Cost', y='Efficiency', hue='Algorithm', 
                        palette={'H-DE-Augmecon-R (New)': 'blue', 'NSGA-III (Benchmark)': 'red'},
                        style='Algorithm', markers={'H-DE-Augmecon-R (New)': 'o', 'NSGA-III (Benchmark)': 'X'},
                        s=80, alpha=0.6)
        
        # B. 画冠军金星 (Best Solution Highlighting)
        plt.scatter(winner['Cost'], winner['Efficiency'], 
                    color='gold', s=400, marker='*', edgecolors='black', linewidth=1.5, zorder=10,
                    label=f"Best TOPSIS Score\n({winner['Algorithm']})")
        
        plt.title(f'Layer {lt}um Comparison: Cost vs Efficiency\n(Star indicates the optimal trade-off solution)')
        plt.xlabel('Cost (Min)')
        plt.ylabel('Efficiency (Max)')
        plt.legend(bbox_to_anchor=(1.02, 1), loc='upper left')
        plt.tight_layout()
        
        # C. 保存图片
        filename = f'compare_LT{lt}_Cost_Eff_Star.png'
        plt.savefig(filename, dpi=300)
        print(f"   🖼️  图表已保存: {filename}")

    print("\n✅ 所有分析与绘图完成！")

if __name__ == "__main__":
    run_comparison()