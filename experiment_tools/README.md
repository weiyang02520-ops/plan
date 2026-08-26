# DG-202611 实验分析工具

这是一套不依赖 ROS2 的最小实验工具骨架。它们是“尺子”，用于保存和检查数据，当前不是参赛算法。

## 四个工具分别做什么

- `calc_position_error.py`：读取估计轨迹和独立真值 CSV，按最近时间戳匹配，输出平面误差和高程绝对误差的逐样本结果及多种统计量。
- `calc_feature_repeatability.py`：读取上游已经提取好的特征和相邻帧关系，使用透明的最近邻一对一参考匹配，输出每个帧对的重复率。
- `calc_relocalization_success.py`：读取每个重定位 trial 的记录，按 `invalid`、超时、人工接管和成功/失败规则统计成功率。
- `check_rosbag.py`：读取 JSON 格式的 bag inspection manifest，检查话题覆盖、时间戳、字段和场景声明，输出 `PASS/PARTIAL/FAIL/NOT_APPLICABLE` 及 A/B/C 等级。

## 现在能做什么

- 使用 Python 标准库运行；所有脚本都有 `--help`。
- 对输入文件、必需字段、数值、布尔值和 JSON 结构做显式检查。
- 输出 CSV/JSON 机器可读文件，保留逐样本或逐 trial 明细。
- 保存输入文件 SHA-256、配置 SHA-256（如提供）、工具版本和 Git SHA（可获取时）。
- 定位误差默认只做最近时间戳匹配，不插值。
- 特征工具只做统计，不提取 LiDAR 特征。

## 现在不能做什么

- 当前不直接解析真实 ROS2 rosbag，不包含 ROS2 节点、EKF、AMCL、Nav2、LiDAR 或 GNSS 算法。
- 当前不定义比赛最终指标口径，也不判断是否达到 20 cm、95% 或 >95%。
- 当前不生成真实比赛实验结果。三个比赛指标仍未实测，官方统计口径仍待确认。

## 最短运行示例

在仓库根目录执行，输出目录请使用未跟踪的本地临时目录：

```text
python experiment_tools/calc_position_error.py --estimate experiment_tools/examples/position_estimate.csv --truth experiment_tools/examples/position_truth.csv --config experiment_tools/configs/example_position_config.json --output <local-output>
python experiment_tools/calc_feature_repeatability.py --features experiment_tools/examples/features.csv --pairs experiment_tools/examples/frame_pairs.csv --config experiment_tools/configs/example_repeatability_config.json --output <local-output>
python experiment_tools/calc_relocalization_success.py --trials experiment_tools/examples/relocalization_trials.csv --config experiment_tools/configs/example_relocalization_config.json --output <local-output>
python experiment_tools/check_rosbag.py --manifest experiment_tools/examples/bag_manifest_pass.json --output <local-output>
```

真实 rosbag 自动读取属于下一阶段 adapter。若未来环境提供 `rosbag2_py`，可以在不改变统计核心的前提下增加输入适配层；当前 checker 的判定核心已经可独立测试。

## 数据与安全

`examples/` 下全部数据都标记为 `SYNTHETIC / TEST ONLY`，只用于公式、错误处理、边界条件和输出文件测试，不是比赛数据。

真实 rosbag、真值原始数据、设备用户 ID、账号、Token、串口凭据和其他私密配置不得进入 Public 仓库。实验记录中只保存脱敏索引、必要的文件哈希和可公开的技术事实。
