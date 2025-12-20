import numpy as np
from scipy.optimize import minimize
import physics_model as test  # 确保这里引用的是你最新的 layer1/physics_model.py

def check_physical_limits():
    print(f"{'='*50}")
    print("🔬 物理极限探底测试 (Physical Limit Check)")
    print(f"{'='*50}")
    
    bounds = [(385, 460), (700, 1150), (90, 115)] # P, V, H
    
    for lt in [80, 100, 120]:
        # 目标：最大化 RD (即最小化 -RD)
        def obj_func(x):
            _, _, rd, _ = test.predict_performance(x, lt)
            return -rd
            
        # 换用 SLSQP 强力爬山
        # 初始点选一个中间值，或者多试几个初始点
        res = minimize(obj_func, x0=[420, 900, 100], bounds=bounds, method='SLSQP')
        
        max_rd = -res.fun
        print(f"Layer {lt} um:")
        print(f"  -> 理论最高致密度 (Max RD): {max_rd:.5f}%")
        
        if max_rd < 99.5:
            print(f"  ❌ 结论：物理上无法满足 99.5%！差距: {99.5 - max_rd:.5f}%")
            print("     建议：必须降低约束标准。")
        else:
            print(f"  ✅ 结论：物理可行。问题出在求解器搜索能力。")
            print("     建议：增大 DE 的 popsize 或 maxiter。")
        print("-" * 30)

if __name__ == "__main__":
    check_physical_limits()