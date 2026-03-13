# CLAUDE.md

本文件是 job_info_collector 的项目级协作与扩展规范。
目标是让后续新增爬虫、分析和前端功能时保持统一架构、可维护性和可回归验证。

## 1. 项目目标与模块边界

项目拆分为三层：

1. 数据爬取层
- 职责：从不同招聘站点采集岗位数据，清洗并统一字段后写入 data。
- 目录：src/*_campus_scraper.py。
- 输出：data/*_jobs.jsonl 与 data/*_jobs.csv。

2. 数据分析层
- 职责：对统一岗位数据做统计分析、NLP/ML 分析、求职指导分析，并导出机器可消费结果。
- 目录：src/analysis_api.py, src/run_analysis.py, notebooks/jobs_analysis.ipynb。
- 输出：data/analysis/*。

3. 前端展示层
- 职责：招聘信息卡片化展示、联动筛选、关键词搜索、统计分析、渐进加载。
- 目录：web/index.html, web/assets/*, web/data/*。
- 输入：web/data/jobs.index.json + web/data/chunks/*.json（主），web/data/jobs.json（兼容）。

## 2. 数据爬取模块实现总结

### 2.1 统一数据契约

所有爬虫输出字段应保持一致，至少包含：
- company
- job_id
- title
- recruit_type
- job_category
- job_function
- work_city
- work_cities
- responsibilities
- requirements
- bonus_points
- tags
- publish_time
- detail_url
- fetched_at
- source_page

原则：
- job_id 尽量稳定唯一。
- work_cities 与 tags 在 CSV 中用 | 分隔。
- 缺失字段保留为空字符串，不删除字段。

### 2.2 新网站爬取需求如何实现

建议按以下步骤执行：

1. 站点侦察
- 确认是否有公开 API（优先 API）。
- 确认分页机制、详情接口、反爬限制。
- 明确字段映射关系。

2. 设计与评审
- 在 docs 增加方案文档（目标接口、分页策略、失败重试、字段映射）。
- 明确样本规模（先小规模验证）。

3. 实现脚本
- 新增 src/<site>_campus_scraper.py。
- 支持参数：起止页、超时、重试、输出路径。
- 先抓列表，再补详情（需要时）。

4. 质量校验
- 去重检查（company + job_id / detail_url）。
- 字段缺失率检查。
- 样本人工 spot check。

5. 并入主流程
- 输出到 data/<site>_jobs.csv/jsonl。
- 更新 README 命令说明。

### 2.3 爬取模块扩展建议

- 抽象通用工具层（分页、重试、请求封装、统一日志）。
- 引入站点配置文件（headers、endpoint、mapping）减少重复代码。
- 增加增量抓取模式（按 job_id 或 publish_time）。

## 3. 数据分析模块实现总结

### 3.1 分析接口

核心入口：src/analysis_api.py 的 get_analysis_payload。

当前分析能力：
- overview：分布统计。
- quality：缺失率、重复率、文本长度。
- skills：关键词命中、技术词频。
- advanced_ml_nlp：TF-IDF + KMeans + NMF + SVD 二维语义。
- career_guidance：赛道需求、实习切入、城市机会、行动建议。

导出入口：
- src/run_analysis.py。
- 输出到 data/analysis。

### 3.2 新数据分析项目如何接入

新增一个分析主题时，建议遵循：

1. 在 analysis_api.py 新增独立函数
- 输入：jobs list[dict]。
- 输出：可 JSON 序列化对象（dict/list/str/number）。
- 不耦合 notebook 逻辑。

2. 接入 build_analysis_report
- 通过新增顶层键接入，如 report["salary_insight"]。

3. 接入导出
- 在 export_analysis_artifacts 增加对应 CSV/JSON 导出。

4. Notebook 展示
- 在 notebooks/jobs_analysis.ipynb 新增图表和解释单元。

5. 文档更新
- 在 docs/JOB_MARKET_ANALYSIS.md 增加口径与解读方法。

### 3.3 分析模块扩展方向

- 岗位趋势（按日期/周）。
- 公司-岗位-城市三维机会矩阵。
- 关键词共现网络。
- 投递优先级评分模型（可解释规则优先）。

## 4. 前端模块实现总结

### 4.1 当前前端能力

- 卡片化岗位展示。
- 联动筛选（公司/项目/类别/城市）。
- 岗位标题搜索。
- 职责/要求/加分项关键词搜索。
- 默认关键词 chips。
- 统计分析模块（Top 公司/类别/城市/关键词命中）。
- 性能优化：防抖、预计算搜索字段、分页加载更多。
- 渐进数据加载：jobs.index.json + chunks。

### 4.2 前端如何调用接口/数据

当前是静态数据调用：

1. 主路径
- 读取 web/data/jobs.index.json。
- 根据 chunks 清单逐片拉取 web/data/chunks/jobs-*.json。
- 首片优先渲染，后续渐进补齐。

2. 兼容路径
- 如果 index 不存在，回退 web/data/jobs.json。

3. 部署前数据生成
- 运行 python src/export_frontend_jobs.py。

### 4.3 前端扩展规则

- 新筛选项必须接入联动机制。
- 新统计卡必须基于 state.filtered 计算。
- 重计算逻辑尽量复用现有函数，避免多处口径不一致。
- 保持移动端可用（<940px 布局）。

## 5. 新需求管理与交付流程

建议按以下流程管理需求：

1. 需求归类
- 爬取需求
- 分析需求
- 前端需求
- 基础设施/部署需求

2. 需求模板（每条需求最少包含）
- 背景与目标
- 输入与输出
- 验收标准
- 风险与依赖

3. 实施顺序
- 先方案（不超过 1 页）
- 再最小可用版本（MVP）
- 最后增强与优化

4. 验收清单
- 功能正确性
- 数据口径一致性
- 性能（首屏与筛选响应）
- 文档是否同步更新

5. 变更记录
- 关键决策写入 docs/DECISIONS.md。
- 复杂站点写维护文档（参考腾讯复盘文档）。

## 6. 版本与发布策略

### 6.1 Git 提交流程

- 分支建议：feature/*, fix/*。
- 提交消息建议：
  - feat: ...
  - fix: ...
  - docs: ...

### 6.2 公网发布（GitHub Pages）

- 工作流：.github/workflows/deploy-pages.yml。
- main 分支推送后自动：
  1. 执行数据导出。
  2. 发布 web 目录。

### 6.3 发布前检查

- export_frontend_jobs.py 成功执行。
- web/data/jobs.index.json 与 chunks 存在。
- 页面显示数据更新时间和数据来源。
- 关键筛选链路人工验证。

## 7. 质量红线

以下情况禁止合入：

- 爬虫输出字段与统一契约不兼容。
- 分析模块输出无法 JSON 序列化。
- 前端新增筛选未接入联动逻辑。
- 新增功能无文档更新。

## 8. 后续优先级建议

1. 抽象通用爬虫基类，减少站点脚本重复。
2. 分析模块服务化（HTTP API），支持前端在线调用。
3. 前端增加钻取联动和收藏比较。
4. 增加数据质量自动报告（CI 里跑轻量校验）。

## 9. 需求模板与 PR 检查清单

### 9.1 需求模板（可复制）

提交新需求时，建议直接使用下面模板：

```
【需求名称】

1. 背景
- 业务背景：
- 当前问题：

2. 目标
- 目标结果：
- 非目标（本次不做）：

3. 输入与输出
- 输入数据/依赖：
- 预期输出（文件/API/页面）：

4. 实现范围
- 必做：
- 可选增强：

5. 验收标准
- 功能验收：
- 数据验收：
- 性能验收：

6. 风险与回滚
- 风险点：
- 回滚方式：

7. 交付物
- 代码文件：
- 文档文件：
- 运行命令：
```

### 9.2 PR 检查清单（合并前）

每个 PR 合并前建议勾选：

1. 代码与结构
- [ ] 是否遵循模块边界（爬取/分析/前端）
- [ ] 是否复用已有函数，避免重复实现

2. 数据与口径
- [ ] 输出字段是否兼容统一数据契约
- [ ] 分析结果是否可 JSON 序列化
- [ ] 关键统计口径是否在文档中说明

3. 前端与体验
- [ ] 新筛选是否接入联动逻辑
- [ ] 新增统计是否基于 state.filtered 计算
- [ ] 移动端布局是否可用

4. 运行与性能
- [ ] 本地命令可跑通（爬取/分析/导出/前端）
- [ ] 首屏加载和筛选响应无明显卡顿

5. 文档与发布
- [ ] README/相关 docs 已更新
- [ ] 若影响部署，Actions/Pages 配置已验证

### 9.3 建议的 PR 描述结构

```
## 变更摘要

## 主要改动

## 验证方式

## 风险与影响范围

## 后续事项
```

---

维护原则：
- 先保证统一数据契约，再做功能扩展。
- 先可用、再完善；先文档、再复杂优化。
- 任何新增模块都必须可回归验证、可追溯决策。
