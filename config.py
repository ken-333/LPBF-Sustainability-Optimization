# ==========================
# 1.physicial parameters
# ==========================
# accroding to the R250M2 device
P_TOTAL_RETED = 6500.0 #W(设备总额定功率)
P_LASER_MAX = 1000.0   #W（双激光 500W*2）
P_BASE = P_TOTAL_RETED - P_LASER_MAX #W（基座功率,非激光能耗：加热、风扇、运动系统、控制柜）

# material properties (SS-CX stainless stell)
RHO = 7.7e-6 #kg/mm^3 (密度: 7.70 g/cm^3)

# carbon emission factors
EF_ELEC = 1.49e-4 #kgCO2/kJ (即 0.5366 kgCO2/kWh)
EF_POWDER = 1.45  #kgCO2/kg
# ==========================
# 2.economic parameters
# ==========================
# gas consumption
GAS_FLOW_RATE = 3.0 / 60.0  # L/s (3 L/min)
PRICE_GAS = 0.053           # Yuan/L (53 Yuan/m^3)
C_GAS_SCE = GAS_FLOW_RATE * PRICE_GAS  # Yuan/s (每秒气体消耗成本)

# machine and labor cost
C_MACHINE = 154.0 / 3600.0  # Yuan/s (154 Yuan/hour)
C_LABOR = 60.0 / 3600.0    # Yuan/s (60 Yuan/hour)

#integrated time cost coefficient (CNY/s)
C_TIME_TOTAL = C_MACHINE + C_LABOR + C_GAS_SCE

# ==========================
# 3.stochastic parameters
# ==========================
# "Two-stage Stochastic Programming"
SCENARIOS = [
    # Scenerio 1:pessimistic
    {'prob': 0.25, 'loss_rate': 0.16,'price':110},
    # Scenerio 2:normal
    {'prob': 0.50, 'loss_rate': 0.13,'price':100},
    # Scenerio 3:optimistic
    {'prob': 0.25, 'loss_rate': 0.10,'price':90},
]

# ==========================
# 4.post-processing trade-off 后处理权衡
# ==========================
# 这是制造 "成本 vs 效率" 冲突的关键。
# 逻辑：层厚越大，表面越粗糙，后处理成本越高。
# 单位: Yuan/mm^3 (打印体积)
POST_COST_MAP = {
    80: 0.020,  # for 80 um  20 Yuan/cm3 (基准)
    100: 0.025, # for 100 um 25 Yuan/cm3 (增加 25%)
    120: 0.035, # for 120 um 35 Yuan/cm3 (增加 75%) 惩罚大层厚的粗糙度
}

# ==========================
# 5.variables and solver settings
# ==========================
BOUNDS = {
    'P':(385,460),         #W (laser power)
    'V':(700,1150),       #mm/s (scan speed)
    'H':(90,115),         #J/mm3 (volumetric energy density)
}

# constraint
ED_MIN = 30  #J/mm3 (目标能量密度)
ED_MAX = 70 #J/mm3 (目标能量密度)

#GUROBI settings
# NonConvex =2 this is the crucial parameter to deal with non-linear problems
SOLVER_OPTS = {
    'NonConvex': 2, # 开启非凸二次规划支持
    'MIPGap': 0.01, # 1% optimality gap
    'TimeLimit': 300 # seconds 限制每个点算5分钟，防止卡死
}
