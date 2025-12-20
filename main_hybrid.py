import pandas as pd  # for data handling in order to store results and exchange to excel
import numpy as np   # in order to handle numerical arrays
from scipy.optimize import differential_evolution, minimize         # 这里从 SciPy 的优化模块里导入两个优化器（两个“求解器”） differential_evolution-差分进化（DE），全局搜索算法（进化算法）。  minimize-是 SciPy 的“统一接口”，里面可以选不同局部优化方法
import config as cfg
import test_new as test

def relaxed_objective_function(x, lt_val, eps_carbon)
    """
    阶段一：给DE用宽松目标函数
    作用：寻找大概率有解的区域，而不是精确值。
    """
    Cost, Carbon, RD, ED = test.predict_performance(x, lt_val_um)
