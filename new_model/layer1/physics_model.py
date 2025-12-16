import numpy as np
import config as cfg

# ==========================================
# 1. 回归模型系数 (保持不变)
# ==========================================
REG_COEFFS = {
    'Intercept': 136.59848,
    # --- 一次项 ---
    'P': 0.094923,
    'V': -0.028654,
    'H': -0.201185,
    'LT': -0.108546,
    'ED': -0.524864,
    # --- 二次项 ---
    'P^2': -0.000051,
    'V^2': 0.00000883923,
    'H^2': 0.000575,
    'ED^2': 0.002459,
    # --- 交互项 ---
    'P*V': -0.000012,
    'P*H': -0.000123,
    'P*ED': -0.000122,
    'V*H': 0.000013,
    'V*ED': 0.000096,
    'H*ED': 0.000450
}

def predict_performance(x, lt_val_um):
    """
    输入: 
        x = [P, V, H] (numpy array or list)
        lt_val_um (int/float): 当前层厚
    输出: 
        Cost (float): 总成本
        Carbon (float): 总碳排放
        RD (float): 相对致密度 (%)
    """
    P, V, H = x  # 解包变量

    # 1. 基础物理量计算
    # InvRate = 1 / (V * H * LT) * 1e6 (单位换算)
    # 注意: V(mm/s), H(um), LT(um). V*H*LT 单位是 mm/s * um * um
    # 我们需要体积速率 mm^3/s -> V * (H/1000) * (LT/1000)
    # 你的原代码中 InvRate = 1 / (V * H * LT * 1e-6)
    
    vol_rate = V * H * lt_val_um * 1e-6 # mm^3/s
    inv_rate = 1.0 / vol_rate           # s/mm^3 (打印 1 mm^3 需要的秒数)

    # Energy Density (ED) = P / (V * H * LT)
    # 原单位 J/mm^3 = W / (mm^3/s)
    ED = P * inv_rate

    # 2. 计算致密度 (RD) - 使用回归系数
    # 这是一个长公式，直接翻译原来的 Pyomo 表达式
    rc = REG_COEFFS
    RD = (rc['Intercept'] +
          rc['P'] * P +
          rc['V'] * V +
          rc['H'] * H +
          rc['LT'] * lt_val_um +
          rc['ED'] * ED +
          
          rc['P^2'] * (P ** 2) +
          rc['V^2'] * (V ** 2) +
          rc['H^2'] * (H ** 2) +
          rc['ED^2'] * (ED ** 2) +
          
          rc['P*V'] * (P * V) +
          rc['P*H'] * (P * H) +
          rc['P*ED'] * (P * ED) +
          rc['V*H'] * (V * H) +
          rc['V*ED'] * (V * ED) +
          rc['H*ED'] * (H * ED))

    # 3. 计算成本 (Cost)
    # (参考原代码逻辑)
    
    # 3.1 材料成本期望 (Expected Material Cost)
    expected_mat_cost = 0
    for s in cfg.SCENARIOS:
        # 材料费 = 密度 * (1+损耗) * 单价
        mat_cost = cfg.RHO * (1 + s['loss_rate']) * s['price']
        expected_mat_cost += s['prob'] * mat_cost
    
    # 3.2 后处理成本
    # 动态查表: cfg.POST_COST_MAP[lt_val_um] * (1 + 0.0001 * V)
    base_post_cost = cfg.POST_COST_MAP.get(lt_val_um, 0.020) # 默认取0.020防报错
    post_cost_dynamic = base_post_cost * (1 + 0.0001 * V)
    
    # 总成本 = 时间成本 + 材料成本 + 后处理 + 功率微小惩罚
    # 时间成本 = C_TIME_TOTAL * inv_rate
    Cost = (cfg.C_TIME_TOTAL * inv_rate) + expected_mat_cost + post_cost_dynamic + (0.01 * P)
    # 注意: 原代码里是 maximize(-Cost)，这里我们直接返回正的 Cost，方便后面最小化

    # 4. 计算碳排放 (Carbon)
    # 4.1 材料碳排放期望
    expected_mat_carbon = 0
    for s in cfg.SCENARIOS:
        mat_c = cfg.RHO * (1 + s['loss_rate']) * cfg.EF_POWDER
        expected_mat_carbon += s['prob'] * mat_c
        
    # 4.2 电力碳排放
    # (P_laser + P_base) * EF_ELEC * Time
    process_carbon = (P + cfg.P_BASE) * cfg.EF_ELEC * inv_rate
    
    Carbon = process_carbon + expected_mat_carbon

    return Cost, Carbon, RD, ED