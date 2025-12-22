import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import os

def plot_4d_pareto():
    print("🎨 启动 4D 可视化绘图 (3D坐标 + 颜色映射)...")

    # 1. 加载数据
    # 优先加载经过排序的文件(final_ranked_results)，因为它包含 Score
    # 如果没有，加载原始结果(raw_pareto_results)
    file_path = "final_ranked_results.xlsx"
    if not os.path.exists(file_path):
        file_path = "raw_pareto_results.xlsx"
        
    if not os.path.exists(file_path):
        print(f"❌ 找不到数据文件: {file_path}。请先运行优化程序。")
        return

    try:
        df = pd.read_excel(file_path)
        print(f"📂 已加载数据: {file_path}, 共 {len(df)} 行")
    except:
        # 尝试 CSV 格式
        df = pd.read_csv(file_path.replace('.xlsx', '.csv'))

    # 2. 数据清洗
    # 确保只展示可行解
    if 'RD' in df.columns:
        df = df[df['RD'] >= 99.5].copy()
    
    # 3. 针对每个层厚分别画图
    for lt in [80, 100, 120]:
        df_lt = df[df['LT_um'] == lt]
        
        if df_lt.empty:
            continue
            
        print(f"\n>>> 正在绘制层厚 {lt} um 的 4D 图...")
        
        # --- 创建 3D 画布 ---
        fig = plt.figure(figsize=(12, 9))
        ax = fig.add_subplot(111, projection='3d')
        
        # --- 定义 4 个维度 ---
        # X, Y, Z 用于空间位置
        x = df_lt['Cost']          # X轴: 成本 (Min)
        y = df_lt['Efficiency']    # Y轴: 效率 (Max)
        z = df_lt['Carbon']        # Z轴: 碳排 (Min)
        
        # C 用于颜色 (第4维)
        c = df_lt['Quality_Robustness'] # 颜色: PRI (Min)
        
        # --- 核心绘图 ---
        # cmap='viridis': 紫色=低值(好), 黄色=高值(差) -> 适合 PRI
        # s=50: 点的大小
        # alpha=0.8: 透明度，防止重叠看不清
        img = ax.scatter(x, y, z, c=c, cmap='viridis', s=60, alpha=0.8, edgecolors='w', linewidth=0.5)
        
        # --- 添加颜色条 (Colorbar) ---
        cbar = fig.colorbar(img, ax=ax, pad=0.1, shrink=0.6, aspect=15)
        cbar.set_label('PRI (Quality Robustness)\nLower(Purple) is Better', rotation=270, labelpad=20, fontsize=10)
        
        # --- 高亮最佳解 (如果有 Score 列) ---
        if 'Score' in df_lt.columns:
            best_idx = df_lt['Score'].idxmax()
            best = df_lt.loc[best_idx]
            
            # 画一个大大的红色五角星
            ax.scatter(best['Cost'], best['Efficiency'], best['Carbon'], 
                       color='red', s=300, marker='*', edgecolors='black', linewidth=1.5, zorder=20,
                       label='Best Trade-off Solution')
            
            # 在旁边标出坐标
            label_text = f"Best:\nCost={best['Cost']:.2f}\nEff={best['Efficiency']:.1f}\nPRI={best['Quality_Robustness']:.3f}"
            ax.text(best['Cost'], best['Efficiency'], best['Carbon'], label_text, fontsize=9, color='black')

        # --- 设置坐标轴标签 ---
        ax.set_xlabel('Cost (CNY) -> Min', fontsize=11, labelpad=10)
        ax.set_ylabel('Efficiency (mm3/s) -> Max', fontsize=11, labelpad=10)
        ax.set_zlabel('Carbon (kg) -> Min', fontsize=11, labelpad=10)
        
        ax.set_title(f'4-Objective Optimization (Layer {lt}um)\nColor Represents Robustness (PRI)', fontsize=14)
        
        # --- 调整视角 ---
        # elev=30 (俯仰角), azim=45 (方位角) -> 这是看帕累托面比较好的角度
        ax.view_init(elev=30, azim=135)
        
        plt.legend(loc='upper left')
        plt.tight_layout()
        
        # 保存图片
        filename = f"4D_Pareto_LT{lt}.png"
        plt.savefig(filename, dpi=300)
        print(f"✅ 图片已保存: {filename}")
        plt.close()

if __name__ == "__main__":
    plot_4d_pareto()