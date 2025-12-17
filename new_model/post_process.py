import pandas as pd                           # for data handling
import numpy as np                            # for numerical arrays
import matplotlib.pyplot as plt               # for plotting
from mpl_toolkits.mplot3d import Axes3D       # for 3D plotting
import os                                     # for file/path checks
import ast                                    # for safe string parsing

# import topsis module
try:
    from topsis import Topsis
except ImportError:
    print("[Error] topsis.py module not found. Please ensure it is in the same directory.")
    exit()

# ==========================================
# 1. 回归模型系数
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
        # 兼容处理：如果没有 P_W，尝试找 P
        P = row.get('P_W', row.get('P', 0))
        V = row.get('V_mm_s', row.get('V', 0))
        H = row.get('H_um', row.get('H', 0))
        LT = row.get('LT_um', row.get('LT', 0))
    except Exception:
        return 0

    if V * H * LT == 0: return 0
    ED = P / (V * H * LT * 1e-6)

    c = REG_COEFFS
    rd_val = (
        c['Intercept'] +
        c['P']*P + c['V']*V + c['H']*H + c['LT']*LT + c['ED']*ED +
        c['P^2']*(P**2) + c['V^2']*(V**2) + c['H^2']*(H**2) + c['ED^2']*(ED**2) +
        c['P*V']*(P*V) + c['P*H']*(P*H) + c['P*ED']*(P*ED) +
        c['V*H']*(V*H) + c['V*ED']*(V*ED) + c['H*ED']*(H*ED)
    )
    return min(rd_val, 100.0)

# ==========================================
# [关键修改] 数据预处理：统一列名
# ==========================================
def preprocess_data(df):
    """
    智能识别列名，解决 Cost vs Obj_Cost 的问题
    """
    print("\n[Debug] Excel 文件中的列名:", df.columns.tolist())
    
    # 1. 尝试拆分 'x' 列 (如果存在)
    if 'x' in df.columns and 'P_W' not in df.columns:
        print("[Info] 发现打包参数列 'x'，正在拆分...")
        def parse_x(val):
            if isinstance(val, str):
                try:
                    val = val.replace('\n', ' ').replace('  ', ' ')
                    if ',' not in val:
                         val = val.replace('[', '').replace(']', '').split()
                         return [float(v) for v in val]
                    return ast.literal_eval(val)
                except: return [0, 0, 0]
            elif isinstance(val, (list, np.ndarray)):
                return val
            return [0, 0, 0]

        parsed_x = df['x'].apply(parse_x)
        df['P_W'] = parsed_x.apply(lambda l: l[0] if len(l)>0 else 0)
        df['V_mm_s'] = parsed_x.apply(lambda l: l[1] if len(l)>1 else 0)
        df['H_um'] = parsed_x.apply(lambda l: l[2] if len(l)>2 else 0)
    
    # 2. [核心修复] 统一目标函数列名
    # 如果 Excel 里叫 'Cost'，我们就把它复制一份叫 'Obj_Cost'
    rename_map = {
        'Cost': 'Obj_Cost',
        'Carbon': 'Obj_Carbon',
        'Efficiency': 'Obj_Efficiency'
    }
    for old, new in rename_map.items():
        if old in df.columns:
            if new not in df.columns:
                print(f"   -> 自动映射列名: {old} -> {new}")
                df[new] = df[old]
    
    return df

# ==========================================
# 2. 对接标准 TOPSIS 算法
# ==========================================
def run_topsis_standard(df):
    print("   -> 正在准备 TOPSIS 数据...")
    required_cols = ['Obj_Cost', 'Obj_Carbon', 'Obj_Efficiency']
    
    # 检查缺失列
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        print(f"❌ 错误：TOPSIS 缺少必要的列: {missing}")
        print(f"   当前可用列: {df.columns.tolist()}")
        return np.zeros(len(df))

    eval_matrix = df[required_cols].to_numpy(dtype=float)
    # 权重: Cost=0.4, Carbon=0.2, Efficiency=0.4
    weights = [0.4, 0.2, 0.4]
    # 方向: Min, Min, Max (False=Min, True=Max)
    criteria = [False, False, True]

    try:
        t = Topsis(eval_matrix, weights, criteria)
        t.step_2()
        t.step_3()
        t.step_4()
        t.step_5()
        t.step_6()
        return t.worst_similarity
    except Exception as e:
        print(f"❌ TOPSIS 计算出错: {e}")
        return np.zeros(len(df))

# ==========================================
# 3. 绘图与主流程
# ==========================================
def plot_3d(df, best_sols):
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')

    colors = {80: '#1f77b4', 100: '#2ca02c', 120: '#d62728'}
    markers = {80: 'o', 100: '^', 120: 's'}

    for lt in [80, 100, 120]:
        sub = df[df['LT_um'] == lt]
        if sub.empty: continue
        # 这里使用统一后的 Obj_ 前缀
        ax.scatter(sub['Obj_Cost'], sub['Obj_Efficiency'], sub['Obj_Carbon'],
                   c=colors.get(lt, 'b'), marker=markers.get(lt, 'o'), 
                   label=rf'LT {lt} $\mu m$', s=40, alpha=0.6)

    if not best_sols.empty:
        ax.scatter(best_sols['Obj_Cost'], best_sols['Obj_Efficiency'], best_sols['Obj_Carbon'],
                   c='gold', s=200, marker='*', edgecolors='black', label='Best Solution', zorder=10)
        
    ax.set_xlabel('Cost (CNY)')
    ax.set_ylabel('Efficiency ($mm^3/s$)')
    ax.set_zlabel('Carbon ($kg CO_2$)')
    ax.legend()

    if not os.path.exists('results'): os.makedirs('results')
    try:
        plt.savefig('results/pareto_front_3d.png', dpi=300)
        print("✅ 3D 图已保存至 results/pareto_front_3d.png")
    except Exception as e:
        print(f"⚠️ 保存图片失败 (可能是权限问题): {e}")
    # plt.show() # 如需弹窗显示请取消注释

def main():
    # 自动寻找文件
    files = ["raw_pareto_results.xlsx", "results/raw_pareto_results.xlsx"]
    file_path = next((f for f in files if os.path.exists(f)), None)

    if not file_path:
        print("[Error] 未找到 raw_pareto_results.xlsx 文件。请先运行主程序生成该文件。")
        return  
    
    print(f"[Info] 读取数据: {file_path}")
    df_opt = pd.read_excel(file_path)

    # --- [Step 1] 预处理：修复列名 ---
    df_opt = preprocess_data(df_opt)
    # -------------------------------

    # 检查是否具备工艺参数
    if 'P_W' not in df_opt.columns:
        print("❌ 无法继续：缺失工艺参数列 (P_W)。请检查是否成功拆分或优化结果是否包含参数。")
        return

    # --- [Step 2] 计算致密度 ---
    print("[Info] 正在计算致密度 (RD)...")
    df_opt['RD_Predicted'] = df_opt.apply(calculate_rd_manual, axis=1)

    # 筛选标准: RD >= 99.5%
    df_valid = df_opt[df_opt['RD_Predicted'] >= 99].copy()
    print(f"   -> 合格解数量 (RD >= 99.5%): {len(df_valid)}")

    if len(df_valid) == 0:
       print("警告：没有解满足 99.5%。")
       return
    
    # --- [Step 3] 运行 TOPSIS ---
    df_valid['Score'] = run_topsis_standard(df_valid)

    # --- [Step 4] 输出最佳结果 ---
    print("\n" + "="*40)
    print("🏆 各层厚最佳工艺参数 (Best Solutions)")
    print("="*40)
    best_sols = pd.DataFrame()

    for lt in [80, 100, 120]:
        sub = df_valid[df_valid['LT_um'] == lt]
        if not sub.empty:
            # 找到得分最高的行
            best = sub.loc[sub['Score'].idxmax()]
            best_sols = pd.concat([best_sols, best.to_frame().T])
            print(f"[LT={lt}um] P={best['P_W']:.1f}W, V={best['V_mm_s']:.1f}mm/s, H={best['H_um']:.1f}um")
            print(f"   -> RD={best['RD_Predicted']:.2f}%, Cost={best['Obj_Cost']:.2f}, Score={best['Score']:.4f}")

    # 保存最终结果
    if not os.path.exists('results'): os.makedirs('results')
    # 挑选一些易读的列进行保存
    cols_to_save = ['LT_um', 'P_W', 'V_mm_s', 'H_um', 'Obj_Cost', 'Obj_Carbon', 'Obj_Efficiency', 'RD_Predicted', 'Score']
    final_cols = [c for c in cols_to_save if c in df_valid.columns]
    
    df_valid[final_cols].to_excel("results/final_processed_results.xlsx", index=False)
    print(f"\n✅ 结果已保存至: results/final_processed_results.xlsx")

    plot_3d(df_valid, best_sols)

if __name__ == "__main__":
    main()