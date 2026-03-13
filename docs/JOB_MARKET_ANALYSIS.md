# 招聘数据分析与求职规划建议

本文档基于 `data/*.csv` 的聚合数据与 NLP/ML 结果生成，服务两类场景：
- 业务展示：前端看板或定期报告
- 求职决策：岗位方向、城市选择、投递策略

## 1. 数据来源与口径

- 数据源：字节、腾讯、网易互娱、库洛、蚂蚁的校园招聘抓取结果
- 主输入：`data/*_jobs.csv`（排除 `_sample.csv`）
- 核心接口：`src/analysis_api.py -> get_analysis_payload(...)`

## 2. 核心分析模块

1. 总览模块（overview）
- 公司分布、岗位类别分布、城市分布、招聘类型分布

2. 质量模块（quality）
- 字段缺失率、重复记录、文本长度分布

3. 技能模块（skills）
- 技能关键词命中（keyword hits）
- 英文技术词频（top tokens）

4. 高级 ML/NLP（advanced_ml_nlp）
- TF-IDF 表征
- KMeans 聚类（带语义标签 `cluster_name`）
- NMF 主题抽取
- SVD 二维语义投影

5. 求职规划模块（career_guidance）
- `career_track_demand`: 赛道需求规模
- `internship_ratio_by_track`: 实习切入友好度
- `city_opportunity`: 城市机会指数
- `company_track_focus`: 公司主要招聘赛道
- `actionable_suggestions`: 可执行建议

## 3. 如何解读用于求职

1. 先看赛道需求（career_track_demand）
- 高需求赛道通常意味着更多面试机会和更高容错率。

2. 再看实习占比（internship_ratio_by_track）
- 如果某赛道实习占比较高，适合通过实习转正路线进入。

3. 结合城市机会指数（city_opportunity）
- 机会指数综合了岗位数量和赛道多样性，适合作为投递城市优先级。

4. 公司赛道偏好（company_track_focus）
- 可用于定制简历版本与项目描述，提升匹配度。

## 4. 建议的投递策略

1. 双主线策略
- 主线：高需求赛道（保障面试机会）
- 副线：技能强相关赛道（提高通过率）

2. 城市优先级
- 第一梯队：高机会指数城市
- 第二梯队：个人资源更强城市（实习渠道、内推等）

3. 简历与项目优化
- 项目描述优先覆盖：岗位 JD 高频关键词 + 目标公司主赛道关键词

## 5. 可视化与产物

- 数据文件：
  - `data/analysis/analysis_report.json`
  - `data/analysis/ml_cluster_summary.csv`
  - `data/analysis/ml_topic_summary.csv`
  - `data/analysis/ml_embeddings_2d.csv`
  - `data/analysis/career_track_demand.csv`
  - `data/analysis/city_opportunity.csv`

- 图表目录：`data/analysis/charts/`

## 6. 运行方式

```powershell
python src/run_analysis.py --data-dir data --output-dir data/analysis --advanced --clusters 10 --topics 10 --top-n 20
```

Notebook 入口：`notebooks/jobs_analysis.ipynb`
