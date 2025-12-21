import numpy as np
import pandas as pd
from pymoo.core.problem import ElementwiseProblem
from pymoo.algorithms.moo.nsga3 import NSGA3
from pymoo.optimize import minimize
from pymoo.util.ref_dirs import get_reference_directions
from pymoo.termination import get_termination
import physics_model # 确保这个文件在同一目录下

class LPBFProblem(ElementwiseProblem):
    def __init__(self, lt_val):
        self.lt = lt_val
        super().__init__(n_var=3, 
                         n_obj=4,        # 4个目标
                         n_ieq_constr=2, # 2个约束 (RD, ED)
                         xl=np.array([385, 700, 90]), 
                         xu=np.array([460, 1150, 115]))

    def _evaluate(self, x, out, *args, **kwargs):
        # 1. 调用您的物理模型
        Cost, Carbon, RD, ED = physics_model.predict_performance(x, self.lt)
        
        # 2. 计算 Efficiency 和 PRI
        # pymoo 默认最小化，Efficiency (Max) 取负号
        efficiency = x[1] * (x[2] / 1000.0) * (self.lt / 1000.0)
        
        quality_loss = (100.0 - RD) ** 2
        stability_penalty = ((ED - 50.0) / 20.0) ** 2
        pri_val = quality_loss + 1.0 * stability_penalty

        # 3. 目标函数
        out["F"] = [Cost, Carbon, -efficiency, pri_val]
        
        # 4. 约束条件 (<= 0 表示满足)
        g1 = 99.5 - RD
        g2 = 0 
        out["G"] = [g1, g2]

def run_full_benchmark():
    all_results = []
    
    # ✅ 遍历所有层厚，和您的主算法保持一致
    for lt in [80, 100, 120]:
        print(f"\n⚔️  [NSGA-III] 正在运行层厚 LT={lt} um ...")
        
        problem = LPBFProblem(lt)
        
        # 创建参考方向 (4目标, partition=12 -> 约455个参考点)
        ref_dirs = get_reference_directions("das-dennis", 4, n_partitions=12)
        
        algorithm = NSGA3(
            pop_size=100, # 种群大小
            ref_dirs=ref_dirs
        )
        
        # 运行优化
        res = minimize(problem,
                       algorithm,
                       termination=get_termination("n_gen", 150), # 跑150代
                       seed=42,
                       verbose=True)
        
        if res.X is not None:
            print(f"   -> 找到 {len(res.X)} 个解")
            for i in range(len(res.X)):
                x = res.X[i]
                obj = res.F[i]
                
                # 再算一次物理属性以记录详细数据
                _, _, rd_val, ed_val = physics_model.predict_performance(x, lt)
                
                # 还原真实 Efficiency (负负得正)
                real_eff = -obj[2]
                
                all_results.append({
                    'LT_um': lt,  # ✅ 关键：加上层厚标记
                    'P_W': x[0], 'V_mm_s': x[1], 'H_um': x[2],
                    'Cost': obj[0],
                    'Carbon': obj[1],
                    'Efficiency': real_eff,
                    'Quality_Robustness': obj[3],
                    'RD': rd_val,
                    'ED': ed_val,
                    'Algorithm': 'NSGA-III' # 标记身份
                })
        else:
            print(f"   ⚠️ LT={lt} 未找到可行解")

    # 保存总表
    if all_results:
        df = pd.DataFrame(all_results)
        output_file = "benchmark_nsgaiii_results.xlsx"
        df.to_excel(output_file, index=False)
        print(f"\n💾 对比数据已保存至: {output_file}")
        print(f"📊 总解数: {len(df)}")
    else:
        print("❌ 运行失败，无数据生成")

if __name__ == "__main__":
    run_full_benchmark()