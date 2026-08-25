# 专题 2：动态环境 LiDAR 鲁棒感知

## 研究问题

比赛要求在动态目标和异常反射条件下提取稳定 LiDAR 特征，并使相邻帧有效特征重复率达到至少 95%。当前机器人只有 RPLidar A2 二维 `/scan`，没有已确认的动态点检测、异常反射处理或特征重复率统计模块。因此本专题既研究 3D 成熟路线，也明确它们与当前二维硬件的差距。

## 主要方法谱系

1. **离线地图清理**：Removert、ERASOR、MapCleaner，适合已有轨迹和点云后处理。
2. **在线动态检测**：Dynablox、LiDAR-MOS、时空占据/可见性模型，适合实时运行但常依赖 3D 点云、体素或学习模型。
3. **几何稳定特征**：LOAM/局部平面、USIP/3D keypoint、3DMatch 局部描述子；重点是先定义“有效特征”再计算重复率。
4. **传感器与自体过滤**：机器人自体点、NaN/离群点、二次回波或异常范围值应在特征统计前明确处理。

## 可靠来源

### D1 — Remove, then Revert: Static Point cloud Map Construction using Multiresolution Range Images（Removert）

- 作者：Giseop Kim、Ayoung Kim；年份：2020；IROS；[论文/代码说明](https://github.com/gisbi-kim/removert)。状态：`inspected`（项目 README，论文正文未完整下载）。
- 研究问题：多帧 3D LiDAR 累积地图中，动态物体留下长尾和残影，如何构建静态地图。
- 核心方法/实验：多分辨率 range image 的 remove-then-revert 流程，输入是带位姿的扫描序列；README 说明可在离线数据上运行，示例包括 KITTI 和 MulRan。
- 关键结果：README 报告单次清理可超过 10 Hz，但项目当前主要是离线工具。
- 可借鉴：把动态点处理拆成“候选删除—保守恢复—地图质量评价”，并保留原始扫描。
- 不能证明：无法直接处理当前二维 LaserScan，也不能把离线地图清理结果等同于在线相邻帧 95% 特征重复率。

### D2 — ERASOR: Egocentric Ratio of Pseudo Occupancy-based Dynamic Object Removal

- 作者：Hyungtae Lim、Sungwon Hwang、Hyun Myung；年份：2021；IEEE RA-L；[arXiv](https://arxiv.org/abs/2103.04316)、[代码链接](https://github.com/LimHyungTae/ERASOR.Officialpytorch)。状态：`abstract-only`/`inspected`（摘要和方法概览）。
- 研究问题：车辆、行人等动态物体在静态 3D 地图中留下残影，影响定位和导航。
- 核心方法/实验：伪占据比、分区地面拟合（R-GPF），在 SemanticKITTI 上与其他地图清理方法比较。
- 关键结果：摘要报告在 SemanticKITTI 上优于当时方法；当前没有把具体表格数字作为本项目结果。
- 可借鉴：利用“物体与地面接触”这一几何先验、分区处理和保守筛选。
- 不能证明：依赖 3D 点云和地图构建阶段，不能直接映射到 A2 的 2D 扫描，也不直接处理反射异常。

### D3 — Dynablox: Real-Time Detection of Diverse Dynamic Objects in Complex Environments

- 作者：Lukas Schmid、Olov Andersson、Aurelio Sulser、Patrick Pfreundschuh、Roland Siegwart；年份：2023；IEEE RA-L；DOI：`10.1109/LRA.2023.3305239`；[论文](https://arxiv.org/abs/2304.10049)、[代码](https://github.com/ethz-asl/dynablox)。状态：`inspected`（摘要、论文元数据、README）。
- 研究问题：不依赖对象外观或类别，在复杂场景在线检测多种动态物体。
- 核心方法/实验：在线体素地图、高置信自由空间估计，建模传感噪声、状态估计和地图限制；测试多层建筑、楼梯、门和球等场景。
- 关键结果：论文摘要报告典型机器人设置约 86% IoU、17 FPS；这是其 3D 场景和平台结果。
- 可借鉴：把观测可见性、自由空间和状态估计误差一起纳入动态判断，而不是只依赖目标检测器。
- 不能证明：当前 A2 二维扫描没有体素高度信息；也不能把 IoU 直接换成比赛“有效特征重复率”。

### D4 — LiDAR-MOS: Moving Object Segmentation in 3D LiDAR Data

- 作者/来源：PRBonn/相关论文作者团队；年份：2021；[GitHub](https://github.com/PRBonn/LiDAR-MOS)。状态：`inspected`（README）。
- 研究问题：利用连续 3D LiDAR 序列做学习式移动物体分割。
- 核心方法/实验：顺序点云、学习式动态分割、KITTI/语义数据和下游地图清理；README 说明可与 Removert 组合。
- 关键结果：README 提供训练、推理和评测入口，但当前没有把其 benchmark 数字写入本资料库。
- 可借鉴：在线主动剔除一批动态点，再用几何后处理清理残留的组合思路。
- 不能证明：需要 3D 点云、训练模型、标签/算力和许可证审查，不适合未经验证地放入 Jetson A2 方案。

### D5 — Removing Moving Objects without Registration from 3D LiDAR Data Using Range Flow Coupled with IMU Measurements

- 作者：论文页面列出的武汉大学团队；年份：2023；Remote Sensing 15(13):3390；DOI：`10.3390/rs15133390`；[论文](https://www.mdpi.com/2072-4292/15/13/3390)。状态：`inspected`（论文页面和表格）。
- 研究问题：注册误差严重时，传统依赖配准的动态物体剔除会失效。
- 核心方法/实验：range image 时空梯度估计 range flow，并结合 IMU 改善流估计；在 SemanticKITTI 和自建城市数据上比较。
- 关键结果：页面报告平均 mIoU 45.8%，Removert 43.2%，Peopleremover 32.2%；数字属于论文数据集。
- 可借鉴：当 LiDAR 配准本身退化时，利用 IMU 作为运动约束；把“注册质量”纳入动态点处理的前置条件。
- 不能证明：论文处理的是 3D LiDAR 和 range image，不代表 A2 的 `/scan` 直接可用。

### D6 — MapCleaner: Efficiently Removing Moving Objects from Point Cloud Maps

- 作者/来源：Remote Sensing 论文作者团队；年份：2022；DOI：`10.3390/rs14184496`；[论文](https://www.mdpi.com/2072-4292/14/18/4496)。状态：`inspected`（论文页面和结果表）。
- 研究问题：生成可用于定位的清洁点云地图，减少动态物体残留。
- 核心方法/实验：先进行地形建模，再识别动态点；在 SemanticKITTI 上与 Octomap、Peopleremover、Removert、ERASOR 比较。
- 关键结果：页面给出按序列的 precision、recall、F1 表；例如其展示的序列 00 F1 为 0.9853，ERASOR 为 0.955。该数字不能替代比赛指标。
- 可借鉴：分别报告删除精度和保留率，避免只报“删得多”。
- 不能证明：地图清洁 F1 与相邻帧特征重复率是不同构念。

### D7 — USIP: Unsupervised Stable Interest Point Detection from 3D Point Clouds

- 作者：Jiaxin Li、Gim Hee Lee；年份：2019；ICCV；[CVF 正文](https://openaccess.thecvf.com/content_ICCV_2019/html/Li_USIP_Unsupervised_Stable_Interest_Point_Detection_From_3D_Point_Clouds_ICCV_2019_paper.html)。状态：`inspected`（论文正文和公式/图表）。
- 研究问题：在视角、噪声、缺失部分等变化下检测稳定且可重复的 3D 关键点。
- 核心方法/实验：无监督关键点提议网络、概率 Chamfer 损失；在 KITTI、Oxford、Redwood、ModelNet40 上做 repeatability 测试。
- 指标定义：若变换后的关键点到另一帧最近关键点距离小于阈值 `ε`，则判为 repeatable；相对重复率为可重复关键点数除以检测关键点数。
- 可借鉴：为比赛“有效特征重复率”提供可解释的数学起点，并明确空间容差与分母。
- 不能证明：USIP 需要 3D 点云和训练/推理链，且论文的关键点定义不等于比赛指定特征。

### D8 — 3DMatch: Learning Local Geometric Descriptors from RGB-D Reconstructions

- 作者：Andy Zeng 等；年份：2017；[项目主页和数据/评测](https://3dmatch.cs.princeton.edu/)、[论文](https://arxiv.org/abs/1603.08182)。状态：`inspected`（项目主页、论文摘要和评测说明）。
- 研究问题：从部分 3D 数据中学习可匹配的局部几何描述子。
- 核心方法/实验：RGB-D 重建中自动产生对应关系，构造匹配/非匹配局部块，评估描述子和几何注册。
- 关键结果：项目页报告在合成注册基准上 65.1% recall、25.2% precision；这是 3DMatch 的基准结果。
- 可借鉴：将“特征检测重复性”和“特征描述/匹配正确性”分开报告，避免把两个指标混在一起。
- 不能证明：该 benchmark 是 RGB-D/3D 局部块，不直接适用于二维相邻 LaserScan。

## 当前候选处理链

1. 对 `/scan` 做时间戳、NaN/Inf、量程边界、自体点和异常跳变检查。
2. 结合 `/odom` 和 `/imu/data` 做相邻帧运动补偿，统一到局部坐标或地图坐标。
3. 在重叠区域计算稳定线段/角点/栅格占据特征；将动态目标候选与异常范围值分别标记。
4. 用几何残差、可见性、连续帧一致性和数量阈值输出 LiDAR 质量分数。
5. 把“有效特征重复率”作为独立指标，不直接用地图 F1、AMCL 分数或 Nav2 成功代替。

这只是测试和实现候选，必须先用实机/rosbag 验证二维数据是否足以形成稳定特征。
