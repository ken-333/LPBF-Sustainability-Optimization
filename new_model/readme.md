Project_Root/
├── Layer 1: 基础设施层 (保留)
│   ├── config.py           <-- [保留] 参数配置 (物理/经济参数)
│   └── physics_model.py    <-- [保留/重命名] 原 test_new.py (纯物理计算核心)
│
├── Layer 2: 核心算法库 (新增/独立)
│   └── augmecon_r.py       <-- [新增] 复刻版 GAMS 逻辑库 (通用控制器)
│
├── Layer 3: 求解适配层 (新建)
│   └── hybrid_solver.py    <-- [新建] H-DE + SLSQP 的具体实现 (特种部队)
│
└── Layer 4: 执行与后处理 (入口)
    ├── main.py             <-- [重写] 负责组装以上模块并运行
    └── post_process.py     <-- [保留] 负责画图、排序、导出