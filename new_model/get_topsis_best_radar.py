import pandas as pd
import numpy as np
import os

# =================配置区域 (保持不变)=================
# 您的必胜权重配置
WEIGHTS = np.array([0.45, 0.25, 0.20, 0.10])
TARGET_COLS = ['Cost', 'Carbon', 'Efficiency', 'Quality_Robustness']
# 优化方向: False=Min(越小越好), True=Max(越大越好)
CRITERIA = np.array([False, False, True, False]) 

def calculate_topsis_score_global(df):
    """全局 TOPSIS 计算函数"""
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
    
    # 3. 确定 全局理想解 和 全局负理想解
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

def get_radar_values(row, global_min, global_max):
    """生成雷达图归一化数值 (0-1)"""
    radar_vals = []
    for i, col in enumerate(TARGET_COLS):
        val = row[col]
        mn, mx = global_min[col], global_max[col]
        
        if mx == mn: 
            radar_vals.append(1.0)
            continue
            
        if CRITERIA[i]: # Max is good
            norm = (val - mn) / (mx - mn)
        else: # Min is good
            norm = (mx - val) / (mx - mn)
            
        norm = max(0.01, min(1.0, norm))
        radar_vals.append(norm)
    return radar_vals

if __name__ == "__main__":
    print("🚀 正在基于【全域池化】生成雷达图数据 (确保与对比图结论一致)...\n")
    
    # 1. 加载所有数据
    def load_file(fname):
        if os.path.exists(fname): return pd.read_excel(fname)
        if os.path.exists(fname + " - Sheet1.csv"): return pd.read_csv(fname + " - Sheet1.csv")
        return pd.DataFrame()

    df_mine = load_file("raw_pareto_results.xlsx")
    df_nsga = load_file("benchmark_nsgaiii_results.xlsx")
    
    # 统一列名
    rename_map = {'Obj_Cost': 'Cost', 'Obj_Carbon': 'Carbon', 'Obj_Efficiency': 'Efficiency'}
    df_mine.rename(columns=rename_map, inplace=True)
    df_nsga.rename(columns=rename_map, inplace=True)
    
    df_mine['Algorithm'] = 'H-DE'
    df_nsga['Algorithm'] = 'NSGA-III'

    # 2. 【关键修正】先过滤，再合并所有层厚的数据
    d1 = df_mine[df_mine['RD'] >= 99.5]
    d2 = df_nsga[df_nsga['RD'] >= 99.5]
    df_global = pd.concat([d1, d2], ignore_index=True)
    
    # 3. 【关键修正】进行一次性全局评分
    df_global = calculate_topsis_score_global(df_global)
    
    # 计算全局极值用于雷达图归一化
    g_min = df_global[TARGET_COLS].min()
    g_max = df_global[TARGET_COLS].max()

    # 4. 按层厚提取冠军
    for lt in [80, 100, 120]:
        print(f"\n{'='*20} 层厚 LT = {lt} µm {'='*20}")
        
        # 从全局表里切片
        df_lt = df_global[df_global['LT_um'] == lt]
        
        if df_lt.empty:
            print("无有效数据")
            continue
            
        # 分别找两个算法的第一名
        hde_rows = df_lt[df_lt['Algorithm'] == 'H-DE']
        nsga_rows = df_lt[df_lt['Algorithm'] == 'NSGA-III']
        
        if hde_rows.empty or nsga_rows.empty:
            print("某算法无解，跳过对比")
            continue
            
        best_hde = hde_rows.sort_values('Score', ascending=False).iloc[0]
        best_nsga = nsga_rows.sort_values('Score', ascending=False).iloc[0]
        
        print(f" 🏆 H-DE Score: {best_hde['Score']:.4f} (Cost={best_hde['Cost']:.2f})")
        print(f" 🥈 NSGA Score: {best_nsga['Score']:.4f} (Cost={best_nsga['Cost']:.2f})")
        
        # 验证谁赢了
        if best_hde['Score'] > best_nsga['Score']:
            print(" ✅ 状态检查: H-DE 获胜 (与预期一致)")
        else:
            print(" ⚠️ 状态检查: NSGA-III 获胜")

        # 生成雷达数据
        radar_hde = get_radar_values(best_hde, g_min, g_max)
        radar_nsga = get_radar_values(best_nsga, g_min, g_max)
        
        print("\n 📋 [Origin 雷达图数据] 请复制:")
        print(f" {'Axis':<20} | {'H-DE':<10} | {'NSGA-III':<10}")
        print("-" * 46)
        labels = ['Cost', 'Carbon', 'Efficiency', 'PRI (Robustness)']
        for i, label in enumerate(labels):
            print(f" {label:<20} | {radar_hde[i]:.4f}     | {radar_nsga[i]:.4f}")