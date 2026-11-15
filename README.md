# Claim Dependency Tracking for Scientific RAG

A Python implementation of claim-level evidence tracking for genetic comparisons. When one source disappears, the assistant withdraws conclusions that depend on it and retains individually supported facts.

## 快速体验

运行 `python3 demo.py`（Python 3.10+，仅用标准库）。示例使用三个虚构的记录，依次展示完整比较、撤回 EU、加入同组干扰和恢复 EU。输出按记录列出保留的数值与缺失原因。

## 成果

| 实验 | 结果 |
|---|---|
| 原项目语料 | 8 个集合，159,607 个证据片段 |
| 冻结配对实验 | 240 道题、四种条件、两个离线系统，共 1,920 份回答 |
| 有完整证据时比较正确 | 238/240 |
| 移除一方后保留另一方的正确数值与引用 | 240/240；再加干扰仍为 240/240 |
| 独立 40 题盲测 | 引用精确率 59.4% → 69.0%，引用召回率 82.5% → 87.5% |
| Fenno GPT 托管基线 | 50 题、200 次请求；160 份结构化返回，151 份通过自动校验；39 次限流，1 次超时 |

证据缺失的两个条件下，托管基线的 78 份成功返回中有 48 份整题拒答；依赖系统在同样条件下保留了仍有依据的数值。托管基线的无依据比较率按规则判定同为 0（LDSC 0/31、0/35，WES 0/6、0/6），因此本实验没有显示新系统在这一指标上优于托管基线，差异在于事实保留、缺失说明和恢复一致。恢复一致率为 238/240，未达到 100% 的目标；盲测比较题引用精确率维持 0.62，未达到 0.90 的目标。

自动校验覆盖引用与数值等规则。托管自由文本判定器的独立人工复核尚待完成。盲测整体事实检查通过率从 92.5% 降至 90.0%；扩展检索集 Hit@10 从 0.90 降至 0.88。

- [设计、优化与复现流程](docs/workflow.md)
- [最终实验报告与回归结果](results/summary.md)
- [离线逐条件指标和置信区间](results/offline.md)
- [Fenno 分层对照与配对差异](results/hosted.md)

仓库提供核心源码、可运行示例、集成补丁和评测脚本。真实数据实验依赖获授权的原始项目、语料和索引。此仓库独立建库，原始记录及包含源片段的运行日志保存在本地。
