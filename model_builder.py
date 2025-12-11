from pyomo.environ import *
import config as cfg

def create_lpbf_model(lt_val_um): # 输入参数是（layer thickness）lt_val_um: 层厚 (单位: um)，例如 80, 100, 120
 # 1.Initialize the model
 m = ConcreteModel()
 # ==========================
 # 2.Define decision variables
 # ==========================
 # variables range from config.py BOUND
 m.P = Var(bounds=cfg.BOUNDS['P'],domain=Reals,name="Power_W")  #Var(...) 是 Pyomo 创建决策变量的函数/类。
 m.V = Var(bounds=cfg.BOUNDS['V'],domain=Reals,name="Speed_mm_s")
 m.H = Var(bounds=cfg.BOUNDS['H'],domain=Reals,name="Hatch_um") 

 # ==========================
 # 3.Define auxiliary variable 辅助变量
 # ==========================
 # 3.1 单位转换: H (um) -> H_mm (mm)
 # 这是一个线性约束: H_mm = H / 1000
 m.H_mm = Var(domain=Reals)
 m.con_unit_h = Constraint(expr= m.H_mm == m.H / 1000.0)

 # 3.2 层厚单位转换：lt_val_um → lt_mm（常数）
 lt_mm = lt_val_um /1000.0   #注意 lt_mm 是一个普通的 Python 浮点数，不是 Pyomo 变量。

 #define bulid rate (BuildRate = V * H_mm * LT_mm)
 # 这是一个二次非线性项 (V * H_mm)，因为 LT_mm 是常数
 m.BuildRate = Var(domain=NonNegativeReals, name="BuildRate", bounds=(0.1, None)) # 给它加一个极小的下界（比如0.1），这在物理上意味着打印速度不能是 0
 m.con_build_rate = Constraint(expr= m.BuildRate == m.V * m.H_mm * lt_mm)

 m.InvRate = Var(domain=NonNegativeReals, name="InvRate", bounds=(0, 20))
 #注意: Gurobi 需要特定语法来识别这种约束，但在 Pyomo 中我们先写成非线性形式
 # 只要在求解时开启 NonConvex=2，Gurobi 会自动处理这种 xy=1 的关系
 m.con_inv_rate = Constraint(expr= m.InvRate * m.BuildRate == 1.0)
 #构建速率的倒数InvRate，表示单位体积所需时间（s/mm³）
 
 # ==========================
 # 4.Define objective functions
 # ==========================
 # 必须使用 ObjectiveList，这是 PyAugmecon 的要求
 m.obj_list= ObjectiveList() #ObjectiveList  Pyomo 中用于存多个目标函数的容器（因为要做多目标优化）

 # calculate the expected materials cost and carbon emission
 expected_mat_cost = 0.0
 expected_mat_carbon = 0.0
 
 for s in cfg.SCENARIOS:
  # 材料成本 = 密度 * (1+损耗) * 价格
  mat_cost = cfg.RHO * (1+ s['loss_rate']) * s['price']  # Yuan/mm³
  expected_mat_cost += s['prob'] * mat_cost # expected materials cost (SUM over scenarios)

 # 材料碳排放 = 密度 * (1+损耗) * 因子
 mat_carbon = cfg.RHO * (1 + s['loss_rate']) * cfg.EF_POWDER  # kgCO2/mm³
 expected_mat_carbon += s['prob'] * mat_carbon

 # Obtain the post-processing cost corresponding to the current layer thickness (conflicting item)
 post_cost_dynamic = cfg.POST_COST_MAP[lt_val_um]* (1 + 0.0001 * m.V) #根据当前层厚 lt_val_um，查找对应的后处理成本。
 
 # ==========================
 # Objective 1: Minimize total cost (MAX -cost)
 # ==========================
 expr_cost = cfg.C_TIME_TOTAL * m.InvRate + expected_mat_cost + post_cost_dynamic + (0.01 * m.P)
 m.obj_list.add(expr=-1 * expr_cost, sense=maximize) # we need the minimize cost, but objective function only defelts to maximize. So we need to multiply -1 

 # ==========================
 # Objective 2: Minimize total carbon emission (MAX -carbon)
 # ==========================
 # P_total = P_laser (variable) + P_base (constant 5500)
 # 这是一个二次项 (P * InvRate)，Gurobi 可解
 expr_carbon=((m.P +cfg.P_BASE) * cfg.EF_ELEC * m.InvRate) + expected_mat_carbon
 m.obj_list.add(expr=-1 * expr_carbon, sense=maximize)

 # ==========================
 # Objective 3: MAXimize efficiency (BuildRate)
 # ==========================
 m.obj_list.add(expr = m.BuildRate, sense = maximize)
 
 # ==========================
 # 【关键修复】Deactivate all objectives
 # ==========================
 for i in range(1, len(m.obj_list) + 1):
     m.obj_list[i].deactivate()

 # ==========================
 # constriant 
 # ==========================
 # ED>=10 AND ED<=70 线性化为: 30 * BuildRate <= P <= 70 * BuildRate
 m.con_ed_min = Constraint(expr= m.P >= cfg.ED_MIN * m.BuildRate)
 m.con_ed_max = Constraint(expr= m.P <= cfg.ED_MAX * m.BuildRate)

 return m