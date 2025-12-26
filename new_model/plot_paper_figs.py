import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.path import Path
import matplotlib.patches as patches
import matplotlib.ticker as ticker
import os

# ==========================================
# 0. 全局 SCI 绘图风格设置
# ==========================================
plt.rcParams['font.family'] = 'serif'
plt.rcParams['font.serif'] = ['Times New Roman']
plt.rcParams['mathtext.fontset'] = 'stix'
plt.rcParams['axes.labelsize'] = 14
plt.rcParams['xtick.labelsize'] = 12
plt.rcParams['ytick.labelsize'] = 12
plt.rcParams['figure.dpi'] = 300

# ==========================================
# 1. 数据加载
# ==========================================
def load_data():
    file_mine = "final_ranked_results.xlsx"
    file_nsga = "benchmark_nsgaiii_results.xlsx"
    
    if not os.path.exists(file_mine) or not os.path.exists(file_nsga):
        print("❌ 错误：找不到数据文件。请确保目录下有 final_ranked_results.xlsx")
        return None, None

    df_mine = pd.read_excel(file_mine)
    df_nsga = pd.read_excel(file_nsga)
    
    # 统一列名
    rename_map = {'Obj_Cost': 'Cost', 'Obj_Carbon': 'Carbon', 'Obj_Efficiency': 'Efficiency'}
    df_mine.rename(columns=rename_map, inplace=True)
    df_nsga.rename(columns=rename_map, inplace=True)

    # 标记算法
    df_mine['Algorithm'] = 'H-DE'
    df_nsga['Algorithm'] = 'NSGA-III'
    
    # 筛选有效解 (RD >= 99.5)
    df_mine = df_mine[df_mine['RD'] >= 99.5]
    df_nsga = df_nsga[df_nsga['RD'] >= 99.5]
    
    return df_mine, df_nsga

# ==========================================
# 2. 核心：自定义多轴平行坐标图 (Custom PCP)
# ==========================================
def plot_custom_parallel_coordinates(df_mine, df_nsga):
    print("🎨 正在绘制高定版平行坐标图 (Deb Style)...")
    
    # 定义要画的轴和标签
    cols = ['Cost', 'Carbon', 'Efficiency', 'Quality_Robustness']
    col_labels = ['Production Cost\n(CNY)', 'Carbon Emission\n(kg CO2e)', 'Build Efficiency\n(mm³/s)', 'Process Robustness\n(PRI)']
    
    # 合并数据以确定每个轴的全局 Min/Max
    df_all = pd.concat([df_mine[cols], df_nsga[cols]], ignore_index=True)
    
    # 计算每个轴的范围 (加一点余量)
    ranges = {}
    for col in cols:
        mn, mx = df_all[col].min(), df_all[col].max()
        padding = (mx - mn) * 0.05
        ranges[col] = (mn - padding, mx + padding)
    
    # 准备绘图画布
    fig, host = plt.subplots(figsize=(12, 6))
    
    # 创建多个独立坐标轴
    axes = [host] + [host.twinx() for i in range(len(cols) - 1)]
    for i, ax in enumerate(axes):
        ax.set_ylim(ranges[cols[i]])
        ax.spines['top'].set_visible(False)
        ax.spines['bottom'].set_visible(False)
        if i > 0:
            ax.spines['left'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.xaxis.set_ticks([])
        
        # 🟢 关键步骤：处理“方向”
        # Efficiency 是“越大越好”，其他是“越小越好”
        # 为了让图上“越往下越优秀”，我们需要把 Efficiency 的轴反转
        if cols[i] == 'Efficiency':
            ax.invert_yaxis() 
            
    # 设置 X 轴位置 (0, 1, 2, 3)
    host.set_xlim(0, len(cols) - 1)
    
    # 定义绘制线条的辅助函数
    def plot_lines(df, color, alpha, linewidth, label):
        # 将数据归一化到 0-1 (基于每个轴的 ranges) 用于绘图位置计算
        # 注意：这里只为了算 y 坐标，真实的 y 刻度由上面的 axes 控制
        xs = list(range(len(cols)))
        
        for idx, row in df.iterrows():
            ys = []
            for i, col in enumerate(cols):
                mn, mx = ranges[col]
                val = row[col]
                # 计算归一化高度 (0-1)
                norm_val = (val - mn) / (mx - mn)
                
                # 如果轴被反转了(Efficiency)，绘图坐标也要反转吗？
                # 不，matplotlib 的 invert_yaxis 会自动处理显示，
                # 但如果我们用 host.plot 画线，我们需要自己映射到 host 的坐标系。
                # 🔴 更简单的做法：直接在该 axis 上画？不行，线要跨轴。
                # ✅ 标准做法：我们把所有数据映射到 0-1 空间画线，然后手动设置每个轴的刻度标签。
                
                # 重新修正策略：
                # 1. 每一列数据独立归一化到 [0, 1]
                # 2. Efficiency (Max好) -> 1是好，0是差。
                # 3. Cost (Min好) -> 0是好，1是差。
                # 4. 为了"越下越好"，Cost 保持 [0,1]，Efficiency 反转为 [1,0] (即值越大，y越小)
                
                if col == 'Efficiency': # Max is better, we want Max to be Bottom (y=0)
                     # 原始: Max -> y=1. 反转后: Max -> y=0
                     norm_y = 1 - (val - mn) / (mx - mn)
                else: # Min is better, we want Min to be Bottom (y=0)
                     norm_y = (val - mn) / (mx - mn)
                ys.append(norm_y)
            
            host.plot(xs, ys, color=color, alpha=alpha, linewidth=linewidth)
        
        # 加一个空的 Line2D 用于图例
        return plt.Line2D([0], [0], color=color, linewidth=linewidth)

    # 绘制背景线 (NSGA-III)
    # 为了防止卡死，如果数据量太大，只抽样画 200 条
    if len(df_nsga) > 200:
        df_nsga_plot = df_nsga.sample(200, random_state=42)
    else:
        df_nsga_plot = df_nsga
    l_nsga = plot_lines(df_nsga_plot, '#BDC3C7', 0.3, 1, 'NSGA-III (Benchmark)') # 灰色
    
    # 绘制前景线 (H-DE)
    if len(df_mine) > 300:
        df_mine_plot = df_mine.sample(300, random_state=42)
    else:
        df_mine_plot = df_mine
    l_mine = plot_lines(df_mine_plot, '#2980B9', 0.5, 1.5, 'H-DE (Proposed)') # 蓝色

    # 绘制最佳解 (Best Trade-off)
    # 找 Score 最高的
    if 'Score' in df_mine.columns:
        best_row = df_mine.sort_values('Score', ascending=False).iloc[0]
    else:
        best_row = df_mine.sort_values('Cost').iloc[0]
    
    # 单独画这一条粗红线
    # 构造单行 DataFrame
    l_best = plot_lines(pd.DataFrame([best_row]), '#C0392B', 1.0, 3, 'Best Trade-off')

    # ==========================
    # 3. 手动美化坐标轴 (画回真实刻度)
    # ==========================
    # 现在 host 的 y 轴是 0-1。我们需要把 4 个轴的真实刻度画上去。
    # 我们把 axes[i] 移动到对应的 x 位置
    
    for i, ax in enumerate(axes):
        ax.xaxis.set_major_locator(ticker.FixedLocator([i]))
        # 移动轴的位置
        ax.spines['left'].set_position(('data', i))
        ax.spines['left'].set_visible(True)
        # 设置真实刻度
        mn, mx = ranges[cols[i]]
        
        # 设定显示的刻度数 (比如 5 个)
        ticks = np.linspace(mn, mx, 5)
        ax.set_yticks(ticks)
        
        # 格式化刻度标签 (保留2位小数)
        if cols[i] == 'Carbon':
            ax.set_yticklabels([f"{v:.3f}" for v in ticks])
        else:
            ax.set_yticklabels([f"{v:.1f}" for v in ticks])
            
        # 标签名
        ax.set_xlabel(col_labels[i], fontsize=12, labelpad=15)
        
        # 如果是 Efficiency，记得我们刚才反转了画线逻辑 (Max在下)，
        # 所以坐标轴刻度也要反转显示吗？
        # 刚才代码逻辑：Eff 越大 -> y 越小 (趋近0)。
        # Host 的 y=0 对应 Eff_Max，y=1 对应 Eff_Min。
        # 所以我们设置 ax 的 ylim 应该是 (Max, Min) 才能对应 Host 的 (0, 1)
        if cols[i] == 'Efficiency':
            ax.set_ylim(mx, mn) # 倒置刻度：上面是小(Min)，下面是大(Max) -> 此时线越往下越好
            # 修正：刚才 plot_lines 里 Eff 越大 norm_y 越接近 0 (底部)。
            # 所以底部 (y=0) 应该是 Max。顶部 (y=1) 应该是 Min。
            # ax.set_ylim(mn, mx) -> 底部是 mn。
            # 所以我们要 set_ylim(mn, mx) 并且 invert_yaxis() 
            # 或者直接 set_ylim(mx, mn) ?
            # Matplotlib 的 twinx 共享 x 轴但不共享 y 轴。
            # Host 的 Y 是 0-1。
            # 我们只是借用 ax 画刻度。我们希望 ax 的刻度位置对齐 host 的 0-1。
            # Host 0 (底) -> Eff Max. Host 1 (顶) -> Eff Min.
            # 所以 ax 的底部刻度应该是 Max，顶部是 Min。
            ax.set_ylim(mn, mx) 
            ax.invert_yaxis()
        else:
            # 其他 Cost: Min 越好。Plot逻辑: Min -> y=0 (底).
            # 所以底部是 Min, 顶部是 Max。
            ax.set_ylim(mn, mx)

    # 去掉 host 的自带刻度
    host.yaxis.set_ticks([])
    host.spines['left'].set_visible(False)
    host.spines['right'].set_visible(False)
    host.spines['top'].set_visible(False)
    host.spines['bottom'].set_visible(False)
    
    # 图例
    plt.legend([l_mine, l_nsga, l_best], 
               ['H-DE Solutions', 'NSGA-III Solutions', 'Best Trade-off'], 
               loc='upper center', bbox_to_anchor=(0.5, 1.15), ncol=3, frameon=False)
    
    plt.title("Fig. 1: Parallel Coordinate Plot (Visual Alignment: Lower is Better)", y=1.15, fontsize=16)
    
    # 保存
    plt.tight_layout()
    plt.savefig('Fig_1_PCP_Refined.png', dpi=300, bbox_inches='tight')
    print("✅ 已保存: Fig_1_PCP_Refined.png")

if __name__ == "__main__":
    df_mine, df_nsga = load_data()
    if df_mine is not None:
        plot_custom_parallel_coordinates(df_mine, df_nsga)