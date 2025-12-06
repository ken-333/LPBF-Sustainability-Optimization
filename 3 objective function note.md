按下：
Ctrl + Shift + V
即可看到实时预览

# 3 objective functions 
## 1. 碳排放公式 (Carbon Emission) 所需参数
公式回顾：$$Min \ CE = \underbrace{[\rho \times (1 + \eta_{loss}) \times EF_{powder}]}_{\text{材料碳足迹}} + \underbrace{[\frac{P_{laser} + P_{base}}{V \times H \times LT} \times EF_{electricity}]}_{\text{能耗碳足迹}}$$

$\rho$材料密度$7.70 \ g/cm^3$  (注意换算为 $7.7 \times 10^{-6} kg/mm^3$)
手稿原文：Eq.(1)下方定义 "nominal density of SS-CX (7.70 g/cm3)" 。

$EF_{powder}$粉末碳排放因子$1.45 \ kg CO_2/kg$
手稿原文：Table 6 中 "Stainless steel" 对应的数值。

$EF_{electricity}$电力碳排放因子$0.5366 \ kg CO_2/kWh$
手稿原文：引用了中国生态环境部2022年的公告数据。

$\eta_{loss}$粉末损耗率$13\%$ (即 0.13)
手稿原文：Table 7 显示 Stainless steel 的回收利用率 (utilization rate) 为 87% 
![alt text](image.png)
$P_{base}$设备基础功率建议取 $1.5 \sim 3.0 \ kW$
文献推断：手稿未提及。参考 Thomas (2014) 5，激光器能耗仅占总能耗的 16%，加热和电机占大头。如果你的激光满载是 500W ($0.5kW$)，那么总功率约为 $0.5 / 0.16 \approx 3.1 kW$。减去激光，基础功率约 2.6 kW。（此方案废除×）
分析：设备的额定总功率是 $6.5 \ kW$。假设你的实验只用了单激光（根据你的论文描述 P=385-460W），那么激光器满载消耗约 $0.5 \ kW$。结论：你的 $P_{base}$ (非激光能耗：加热、风扇、运动系统、控制柜) 实际上非常高！计算：$P_{base} \approx 6.5 \ kW (\text{总}) - 1.0 \ kW (\text{激光满载余量}) = \mathbf{5.5 \ kW}$。

## 2. 综合成本公式 (Total Cost) 所需参数
公式回顾：$$Min \ Cost = \underbrace{\frac{C_{machine} + C_{labor}+C_{gas}}{V \cdot H \cdot LT}}_{\text{加工费}} + \underbrace{\rho (1+\eta_{loss}) C_{powder}}_{\text{材料费}} + \underbrace{K \cdot (100-RD)^2}_{\text{质量惩罚}}$$

$C_{powder}$粉末单价$210 \ Yuan/kg$
手稿原文：Table 8 "Metal powder: 210 Yuan/kg" 。

$C_{electricity}$电费单价$1.336 \ Yuan/kWh$
手稿原文：Table 8 "Commercial power: 1.336 Yuan/kWh" 。

$C_{labor}$人工时薪建议 $50 \sim 100 \ Yuan/h$估算：手稿提到人工成本来自中国重汽调查 8，但未给出时薪。Table 9 给出了"Processing cost" (含人工) 约为 12.52 Yuan 9，但这可能不是时薪。建议按当地技工市价估算。

$C_{machine}$机器小时费率建议 $150 \sim 200 \ Yuan/h$
计算得出：
1. 设备原值 $OV = 2,600,000$ (Table 9 Laser cladding参考值)。
2. 残值 $RV = 5\%$ 11。
3. 寿命 $T = 10$ 年。
4. 假设年工作时间 $awt = 1600$ 小时 (单班制)。计算： $\frac{2.6M \times 0.95}{10 \times 1600} \approx 154 \ Yuan/h$。

$K_{penalty}$质量惩罚系数建议 $20 \sim 50$
文献佐证：参考 Thomas (2014) 13，后处理成本约占总成本的 8% ~ 13%。
设定逻辑：假设打印 $1cm^3$ 成本约 50 元。如果致密度降 1%，需要 5 元后处理费。
$K \times (100-99)^2 = 5 \rightarrow K=5$。为了加大惩罚力度（模拟废品风险），建议设为 20-50。
![alt text](image-1.png)
新增 $Cost_{gas}$ (气体成本) —— 让模型更精准图片信息：惰性气体消耗：$Ar$ 或 $N_2$, 3L/min。应用：你之前的成本公式里虽然提到了气体，但现在有了确切的消耗速率。公式修正建议：在 $Cost_{Operation}$ 中，除了人工和机器折旧，可以精确加上气体成本：$$Cost_{Gas} = \frac{3 \ (L/min)}{60} \times \frac{1}{V \cdot H \cdot LT} \times Price_{Gas}$$(注：$1/(V \cdot H \cdot LT)$ 是打印单位体积所需的时间秒数)

## 3. 生产效率公式 (Efficiency)
$$Max \ Eff = V \times H \times LT
$$这三个变量是你的决策变量 (Decision Variables)，它们的取值范围 (Constraint Range) 已经完全包含在你的手稿中：
$V$ (速度): $700 - 1150 \ mm/s$
$H$ (扫描间距): $90 - 115 \ \mu m$
$LT$ (层厚): $80, 100, 120 \ \mu m$ 

## 为了让论文无懈可击，建议在文中补充以下说明
1. 确认 $P_{base}$：找一下你的 R250M2 设备铭牌，看它的额定功率是多少（通常写在机器背面，比如 "Rated Power 3.5kW"）。如果找不到，就引用 Thomas 的 "16% 激光占比" 理论推导一个值。(已经解决，通过查找官网，后续论文可以提及估算的方法)
2. 解释 $K_{penalty}$：引用 Thomas (2014) 关于 "Ill-structured costs" 和 "Post-processing costs (approx 8.4%)" 的数据，说明你为什么把惩罚系数设定在这个范围。