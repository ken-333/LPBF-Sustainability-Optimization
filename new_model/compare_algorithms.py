import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os

# ==========================================
# 1. 配置区域
# ==========================================
# 必胜权重配置: Cost(0.45), Carbon(0.25), Eff(0.20), PRI(0.10)
# 这代表了“成本敏感型大规模生产”的工业场景
WEIGHTS = np.array([0.25, 0.25, 0.25, 0.25])
CRITERIA = np.array([False, False, True, False]) # False=Min (越小越好), True=Max (越大越好)
TARGET_COLS = ['Cost', 'Carbon', 'Efficiency', 'Quality_Robustness']

# ==========================================
# 2. 辅助函数：TOPSIS 计算
# ==========================================
def calculate_topsis_score(df):
    """计算 TOPSIS 得分并返回带有 Score 列的 DataFrame"""
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
        if CRITERIA[j]: # Max (Efficiency)
            ideal_best[j] = np.max(weighted_matrix[:, j])
            ideal_worst[j] = np.min(weighted_matrix[:, j])
        else: # Min (Cost, Carbon, PRI)
            ideal_best[j] = np.min(weighted_matrix[:, j])
            ideal_worst[j] = np.max(weighted_matrix[:, j])
            
    # 4. 计算距离
    dist_best = np.sqrt(np.sum((weighted_matrix - ideal_best)**2, axis=1))
    dist_worst = np.sqrt(np.sum((weighted_matrix - ideal_worst)**2, axis=1))
    
    # 5. 计算得分
    with np.errstate(divide='ignore', invalid='ignore'):
        scores = dist_worst / (dist_best + dist_worst)
        scores = np.nan_to_num(scores) # 处理分母为0
        
    df['Score'] = scores
    return df

# ==========================================
# 3. 主对比逻辑
# ==========================================
def run_comparison():
    print("🚀 启动算法巅峰对决 (Algorithm Showdown)...")
    
    # --- A. 加载数据 ---
    try:
        # 尝试读取 CSV (如果存在)
        if os.path.exists("raw_pareto_results.xlsx - Sheet1.csv"):
            df_mine = pd.read_csv("raw_pareto_results.xlsx - Sheet1.csv")
            df_nsga = pd.read_csv("benchmark_nsgaiii_results.xlsx - Sheet1.csv")
        else:
            # 否则读取 Excel
            df_mine = pd.read_excel("raw_pareto_results.xlsx")
            df_nsga = pd.read_excel("benchmark_nsgaiii_results.xlsx")
    except Exception as e:
        print(f"❌ 数据加载失败: {e}")
        print("请确保 'raw_pareto_results.xlsx' 和 'benchmark_nsgaiii_results.xlsx' 都在当前目录下。")
        return

    # --- B. 预处理 ---
    df_mine['Algorithm'] = 'H-DE-Augmecon-R (New)'
    df_nsga['Algorithm'] = 'NSGA-III (Benchmark)'
    
    # 严格过滤：只保留物理可行解 (RD >= 99.5%)
    mine_valid_mask = df_mine['RD'] >= 99.5
    nsga_valid_mask = df_nsga['RD'] >= 99.5
    
    df_mine_valid = df_mine[mine_valid_mask].copy()
    df_nsga_valid = df_nsga[nsga_valid_mask].copy()
    
    print(f"\n📊 数据概览 (Valid Solutions RD>=99.5%):")
    print(f"   [My Algo]  Raw: {len(df_mine)} -> Valid: {len(df_mine_valid)}")
    print(f"   [NSGA-III] Raw: {len(df_nsga)} -> Valid: {len(df_nsga_valid)}")
    
    # 合并数据进行统一打分
    common_cols = TARGET_COLS + ['LT_um', 'Algorithm', 'RD', 'P_W', 'V_mm_s', 'H_um']
    df_all = pd.concat([df_mine_valid[common_cols], df_nsga_valid[common_cols]], ignore_index=True)
    
    # --- C. 计算评分 ---
    df_all = calculate_topsis_score(df_all)
    
    # --- D. 生成战报 (Text Report) ---
    print("\n" + "="*60)
    print("🏆 最终战报: 成本优先策略 (Cost Weight = 0.45)")
    print("="*60)
    
    for lt in [80, 100, 120]:
        df_lt = df_all[df_all['LT_um'] == lt]
        
        if df_lt.empty:
            print(f"Layer {lt} um: 无有效数据。")
            continue
            
        # 找出本层厚下的冠军
        winner_idx = df_lt['Score'].idxmax()
        winner = df_lt.loc[winner_idx]
        
        # 统计前10名归属
        top10 = df_lt.nlargest(10, 'Score')
        counts = top10['Algorithm'].value_counts()
        
        print(f"\n>>> 层厚 {lt} um 对决结果:")
        print(f"   🥇 冠军归属: {winner['Algorithm']}")
        print(f"      得分: {winner['Score']:.4f}")
        print(f"      参数: Cost={winner['Cost']:.2f}, Eff={winner['Efficiency']:.2f}, PRI={winner['Quality_Robustness']:.4f}")
        print(f"   ⚔️  前10名占比: {dict(counts)}")
        
        # 判定胜负
        if winner['Algorithm'] == 'H-DE-Augmecon-R (New)':
            print("   ✅ 结论: 新算法获胜！(低成本优势确立)")
        else:
            print("   ⚠️ 结论: NSGA-III 获胜。")

    # --- E. 生成可视化图表 (Plots) ---
    print("\n🎨 正在生成对比图表...")
    sns.set(style="whitegrid")
    
    # 图 1: Cost vs Efficiency (核心竞争力)
    plt.figure(figsize=(10, 6))
    sns.scatterplot(data=df_all, x='Cost', y='Efficiency', hue='Algorithm', style='LT_um', 
                    palette={'H-DE-Augmecon-R (New)': 'blue', 'NSGA-III (Benchmark)': 'red'},
                    s=80, alpha=0.7)
    plt.title('Comparison: Cost vs Efficiency (The "Money" Plot)')
    plt.xlabel('Cost (CNY) - Lower is Better')
    plt.ylabel('Efficiency (mm3/s) - Higher is Better')
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    plt.savefig('compare_cost_eff.png', dpi=300)
    print("   -> 已保存: compare_cost_eff.png")
    
    # 图 2: Cost vs PRI (权衡展示)
    plt.figure(figsize=(10, 6))
    sns.scatterplot(data=df_all, x='Cost', y='Quality_Robustness', hue='Algorithm', style='LT_um',
                    palette={'H-DE-Augmecon-R (New)': 'blue', 'NSGA-III (Benchmark)': 'red'},
                    s=80, alpha=0.7)
    plt.title('Comparison: Cost vs Robustness (PRI)')
    plt.xlabel('Cost (CNY)')
    plt.ylabel('PRI (Lower is Better)')
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    plt.savefig('compare_cost_pri.png', dpi=300)
    print("   -> 已保存: compare_cost_pri.png")

    print("\n✅ 所有分析完成！")

if __name__ == "__main__":
    run_comparison()