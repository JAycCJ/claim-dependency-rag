# 从检索到可撤回的结论

1. **建立基线。** 原项目提交 bcfb925，277 项测试通过。旧系统可以找到相关的遗传学记录，并检查引文中的数字。跨记录关系仍需知道哪一个值属于哪一个来源。
2. **精确定位。** 对完整指定的比较解析表型、注释、组织、样本、人群，或基因及 mask。在工作区授权与过滤范围内取目标记录；歧义查询回退至原有检索。
3. **建立依赖。** 每项 Fact 绑定记录、字段、数值。Derived 保存两个操作数，按方向计算大小和差值。校验器从引用复算。取走一方只撤回依赖这一方的结论；恢复时即使文档顺序交换也能复算。
4. **处理 WES 的粒度。** 汇总与明确要求的 mask 可以分别引用，同一基因组只占一个证据组位置。组内多个 mask 不应当作独立支持。WES 数据缺少组织与人群字段，因此干扰条件使用同一基因的另一种 mask，指标单列。
5. **冻结实验。** 固定种子 61113，开发集 28 题；按目标记录组排重后另设 200 道 LDSC 和 40 道 WES。文件哈希见 split-manifest。对照系统共享同一上下文；四种证据条件按同一问题配对。二值比例报告 Wilson 95% 区间，配对差异使用 10,000 次 bootstrap。服务失败、拒答、自动校验结果分别统计。
6. **开发测试定位问题。** Fenno 首轮 8 次只有一次结构化返回。模型正确计算了一个有序差值，旧校验器将差值当作原始字段查找，产生误报。同时发现撤掉子记录后，父记录嵌套元数据仍可能暴露该 mask 的数值。修复覆盖 prompt 字段裁剪、按减法方向复算、错误诊断以及防止单条引用支撑两方比较。一次独立的在线恢复条件复测成功（12.22 秒）；另外对已保存的回答离线重放，验证了两种英文差值句式。
7. **完整结果。** 集成环境通过 291 项 Python 测试、55 个子测试和 11 项前端测试。全量离线复跑后，从冻结题按比例固定抽样（42 道 LDSC、8 道 WES），使用 Fenno gpt-6.1-sol 做 200 次请求。缺失或含干扰的条件中，成功返回 78 份，其中 48 份为整题拒答。可用性、合规返回与内容质量分别见结果表。
8. **解读不足。** 两道题的样本名称包含人群代码样式，导致解析回退，恢复正确率为 238/240。在旧盲测四道 WES 题中引用精确率和召回率达到 100%，但一个回答遗漏用户要求的 mask 名称。固定模板成绩不能外推所有科学问答；自动判定器也可能漏掉同义表达。

## 代码与复现入口

独立演示运行 README 中的命令。若已有获授权的原始项目 bcfb925，请在其单独工作树运行：

1. 在原项目根目录对本仓库的 integration/capstone.patch 使用 git apply --check，再使用 git apply。该补丁包含原系统的检索、上下文、生成器、API、前端配置和评估输出位置调整。
2. 将本仓库 scripts/ 的实验脚本复制到原项目 scripts/ 下。准备原项目八集合语料、匹配的 BM25 索引和重排模型。使用原项目 Python 环境。
3. 在尚未生成分割文件的工作树运行 python scripts/build_dependency_ablation.py；已有冻结集应直接核对 results/split-manifest.json 的哈希。运行 python scripts/evaluate_dependencies.py --split dev，再运行 python scripts/evaluate_dependencies.py。运行原项目的冻结检索和盲测脚本，并为输出指定独立目录。
4. 托管对照为独立计费步骤。通过集成界面输入中转站密钥，选择 gpt-6.1-sol，然后运行 200 次冻结评估。程序在发起请求前写入尝试记录，禁用模型自动修复重试，已有结果目录会阻止重复运行。运行 python scripts/report_fenno_full.py 生成逐条件表、区间及人工复核表。

### 英文简历表述

- Extended a team-built, citation-grounded RAG assistant for a drug-discovery client (Python, FastAPI, BM25; 159,607 passages across 8 genetics datasets) with claim-level dependency tracking: comparisons are computed from the cited records and re-derived by the validator, so removing a source withdraws only the conclusions that depend on it.
- On 240 frozen paired questions under 4 evidence conditions (1,920 answers), gave the correct comparison in 238 (99.2%, 95% CI 97.0-99.8%) with full evidence, and made 0 unsupported comparisons across 480 missing-evidence runs while keeping the surviving value and citation in all 480; a hosted GPT baseline refused outright in 48 of 78 such responses (50-question sample).
- Raised citation precision from 59.4% to 69.0% and recall from 82.5% to 87.5% on a separate 40-question blind benchmark by counting same-gene records as one evidence group; Wilson intervals and 10,000-resample paired bootstrap; 291 automated tests.
