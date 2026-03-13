# job_info_collector

多网站招聘数据采集项目。当前已实现字节跳动、腾讯、网易互娱、库洛游戏、阿里巴巴(蚂蚁集团),米哈游校园招聘数据抓取。

## 项目结构

```
job_info_collector/
├── src/
│   └── bytedance_campus_scraper.py   # Phase 1 爬虫脚本
│   └── tencent_campus_scraper.py      # 腾讯校招 API 抓取脚本
│   └── netease_campus_scraper.py      # 网易互娱校招 API 抓取脚本
│   └── kurogame_campus_scraper.py     # 库洛校招 API 抓取脚本
│   └── antgroup_campus_scraper.py     # 蚂蚁校招 API 抓取脚本
├── data/
│   ├── bytedance_jobs.jsonl           # 主输出（每行一条职位 JSON）
│   └── bytedance_jobs.csv             # 主输出（CSV）
│   ├── tencent_jobs.jsonl             # 腾讯输出（每行一条职位 JSON）
│   └── tencent_jobs.csv               # 腾讯输出（CSV）
│   ├── netease_jobs.jsonl             # 网易输出（每行一条职位 JSON）
│   └── netease_jobs.csv               # 网易输出（CSV）
│   ├── kurogame_jobs.jsonl            # 库洛输出（每行一条职位 JSON）
│   └── kurogame_jobs.csv              # 库洛输出（CSV）
│   ├── antgroup_jobs.jsonl            # 蚂蚁输出（每行一条职位 JSON）
│   └── antgroup_jobs.csv              # 蚂蚁输出（CSV）
├── docs/
│   ├── BYTEDANCE_CAMPUS_SCRAPER_PLAN.md   # 字节爬虫技术规划
│   ├── CONTEXT.md                          # 项目全局上下文与状态速查
│   └── DECISIONS.md                        # 关键技术决策日志
│   └── TENCENT_SCRAPER_MAINTENANCE.md      # 腾讯爬虫复盘与维护手册
├── logs/                              # 运行日志（暂为空，Phase 2 填充）
├── README.md
└── requirements.txt
```

## 目标网站

| 网站 | 状态 | 脚本 |
|------|------|------|
| 字节跳动校园招聘 | ✅ MVP 完成 | `src/bytedance_campus_scraper.py` |
| 腾讯校园招聘 | ✅ API 版完成 | `src/tencent_campus_scraper.py` |
| 网易互娱校园招聘 | ✅ API 版完成 | `src/netease_campus_scraper.py` |
| 库洛游戏 | ✅ API 版完成 | `src/kurogame_campus_scraper.py` |
| 阿里巴巴(蚂蚁集团) | ✅ API 版完成 | `src/antgroup_campus_scraper.py` |


## 环境依赖

```powershell
pip install -r requirements.txt
```

无需额外下载 Playwright 浏览器，**默认使用系统 Edge**。  
若要使用 Playwright 内置 Chromium：

```powershell
python -m playwright install chromium
```

## 使用说明

### 一键流水线（推荐）

项目已提供统一流水线入口，会自动执行：爬取 -> 分析 -> 前端导出。

```powershell
# 方式 1：直接调用 Python 入口（全流程）
python src/run_data_pipeline.py

# 方式 2：使用 PowerShell 包装脚本（全流程）
./run_pipeline.ps1
```

常用模式：

```powershell
# 只刷新分析 + 前端（不重跑爬虫，速度快）
python src/run_data_pipeline.py --skip-crawlers

# 仅跑指定站点（示例：米哈游）再联动分析和前端导出
python src/run_data_pipeline.py --only mihoyo

# 包装脚本同样支持参数
./run_pipeline.ps1 -SkipCrawlers
./run_pipeline.ps1 -Only mihoyo
```

### 分析模块（ipynb + 可复用接口）

项目新增招聘数据分析接口：`src/analysis_api.py`。Notebook 与后续前端服务都应复用这层接口，避免重复实现。

分析 Notebook：`notebooks/jobs_analysis.ipynb`

分析文档（含求职规划解读）：`docs/JOB_MARKET_ANALYSIS.md`

项目协作规范：`CLAUDE.md`

迭代路线图：`docs/ROADMAP.md`

### 招聘信息前端集成站（卡片筛选）

前端页面目录：`web/`

功能包括：

- 卡片化展示招聘岗位
- 按公司、招聘项目（`recruit_type`）、岗位类别、城市筛选
- 筛选联动：每个下拉项会根据其他已选条件动态收缩，避免范围不匹配
- 按岗位名称搜索
- 按职责/要求/加分项关键词搜索
- 提供默认常见关键词快捷搜索
- 前端统计分析模块（Top 公司/类别/城市/关键词命中）
- 性能优化（输入防抖、预计算搜索字段、分页加载更多）

先导出前端数据：

```powershell
python src/export_frontend_jobs.py
```

导出后会生成：

- `web/data/jobs.index.json`（索引与元信息）
- `web/data/chunks/jobs-*.json`（分片岗位数据，前端渐进加载）
- `web/data/jobs.json`（兼容模式全量文件）

再启动静态服务（示例）：

```powershell
cd web
python -m http.server 8080
```

浏览器打开：`http://localhost:8080`

### 公网部署（GitHub Pages）

仓库已支持 GitHub Actions 自动部署，工作流文件：

- `.github/workflows/deploy-pages.yml`

每次推送到 `main` 会自动执行：

1. 运行 `python src/export_frontend_jobs.py` 生成前端数据
2. 发布 `web/` 目录到 GitHub Pages

首次开启步骤：

1. 打开仓库 `Settings -> Pages`
2. 在 `Build and deployment` 中选择 `Source: GitHub Actions`
3. 推送一次代码或在 `Actions` 手动运行 `Deploy Pages`

发布成功后，访问地址通常为：

- `https://<your-github-username>.github.io/<repo-name>/`

命令行入口：

```powershell
python src/run_analysis.py --data-dir data --output-dir data/analysis --top-n 15
```

启用高级 ML/NLP 分析（聚类、主题、二维语义嵌入）：

```powershell
python src/run_analysis.py --data-dir data --output-dir data/analysis --advanced --clusters 10 --topics 10 --top-n 20
```

执行后会在 `data/analysis/` 下生成：

- `analysis_report.json`（前端可直接读取的聚合结果）
- `company_distribution.csv`
- `city_distribution.csv`
- `job_category_distribution.csv`
- `skill_keyword_hits.csv`
- `ml_embeddings_2d.csv`（高级模式）
- `ml_cluster_summary.csv`（高级模式）
- `ml_topic_summary.csv`（高级模式）

接口示例（供前端后端服务调用）：

```python
from analysis_api import get_analysis_payload

payload = get_analysis_payload(
	data_dir="data",
	output_dir="data/analysis",
	top_n=15,
)

report = payload["report"]
artifacts = payload["artifacts"]
```

### 常用命令

```powershell
# 抓取第 1-5 页，每页 10 条（使用系统 Edge，推荐）
python src/bytedance_campus_scraper.py --browser-channel msedge --start-page 1 --end-page 5

# 指定输出路径
python src/bytedance_campus_scraper.py --browser-channel msedge --start-page 1 --end-page 20 --jsonl data/bytedance_jobs.jsonl --csv data/bytedance_jobs.csv

# 使用 Playwright 内置 Chromium（需先安装）
python src/bytedance_campus_scraper.py --browser-channel chromium --start-page 1 --end-page 5

# 有头模式调试
python src/bytedance_campus_scraper.py --browser-channel msedge --start-page 1 --end-page 1 --headed

# 抓取腾讯校招（默认抓取全量页）
python src/tencent_campus_scraper.py

# 腾讯：仅抓取前 3 页进行快速验证
python src/tencent_campus_scraper.py --start-page 1 --end-page 3

# 腾讯：自定义输出
python src/tencent_campus_scraper.py --jsonl data/tencent_jobs.jsonl --csv data/tencent_jobs.csv

# 抓取网易互娱校招（默认 projectId=30，全量）
python src/netease_campus_scraper.py

# 网易：仅抓取前 2 页进行快速验证
python src/netease_campus_scraper.py --start-page 1 --end-page 2

# 网易：指定项目 ID 与输出路径
python src/netease_campus_scraper.py --project-id 30 --jsonl data/netease_jobs.jsonl --csv data/netease_jobs.csv

# 抓取库洛校招（默认抓取全量页）
python src/kurogame_campus_scraper.py

# 库洛：仅抓取前 2 页进行快速验证
python src/kurogame_campus_scraper.py --start-page 1 --end-page 2

# 库洛：指定输出路径
python src/kurogame_campus_scraper.py --jsonl data/kurogame_jobs.jsonl --csv data/kurogame_jobs.csv

# 抓取蚂蚁校招（默认批次 ID=26022600074513）
python src/antgroup_campus_scraper.py

# 蚂蚁：仅抓取前 2 页进行快速验证
python src/antgroup_campus_scraper.py --start-page 1 --end-page 2

# 蚂蚁：指定批次 ID（可重复）
python src/antgroup_campus_scraper.py --batch-id 26022600074513 --batch-id 26022800000000

# 蚂蚁：指定输出路径
python src/antgroup_campus_scraper.py --jsonl data/antgroup_jobs.jsonl --csv data/antgroup_jobs.csv
```

### 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--start-page` | 1 | 起始页码 |
| `--end-page` | 3 | 结束页码 |
| `--limit` | 10 | 每页条数 |
| `--browser-channel` | msedge | 浏览器通道：msedge / chrome / chromium |
| `--headed` | false | 有头模式（调试用） |
| `--delay-min` | 1.0 | 页间最小延迟秒数 |
| `--delay-max` | 2.5 | 页间最大延迟秒数 |
| `--jsonl` | data/bytedance_jobs.jsonl | JSONL 输出路径 |
| `--csv` | data/bytedance_jobs.csv | CSV 输出路径 |

### 腾讯脚本参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--start-page` | 1 | 起始页码 |
| `--end-page` | 999 | 结束页码（自动裁剪到最大页） |
| `--page-size` | 10 | 每页条数 |
| `--timeout` | 20 | 单请求超时（秒） |
| `--retries` | 3 | 请求重试次数 |
| `--page-delay-min` | 0.2 | 页间最小延迟秒数 |
| `--page-delay-max` | 0.6 | 页间最大延迟秒数 |
| `--detail-delay-min` | 0.05 | 详情请求最小延迟秒数 |
| `--detail-delay-max` | 0.2 | 详情请求最大延迟秒数 |
| `--jsonl` | data/tencent_jobs.jsonl | JSONL 输出路径 |
| `--csv` | data/tencent_jobs.csv | CSV 输出路径 |

### 网易脚本参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--project-id` | 30 | 页面 `/position/{id}` 中的项目 ID |
| `--start-page` | 1 | 起始页码 |
| `--end-page` | 999 | 结束页码（自动裁剪到最大页） |
| `--timeout` | 20 | 单请求超时（秒） |
| `--retries` | 3 | 请求重试次数 |
| `--page-delay-min` | 0.2 | 页间最小延迟秒数 |
| `--page-delay-max` | 0.6 | 页间最大延迟秒数 |
| `--detail-delay-min` | 0.05 | 详情请求最小延迟秒数 |
| `--detail-delay-max` | 0.2 | 详情请求最大延迟秒数 |
| `--jsonl` | data/netease_jobs.jsonl | JSONL 输出路径 |
| `--csv` | data/netease_jobs.csv | CSV 输出路径 |

### 库洛脚本参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--start-page` | 1 | 起始页码 |
| `--end-page` | 999 | 结束页码（自动裁剪到最大页） |
| `--limit` | 10 | 每页条数 |
| `--timeout` | 20 | 单请求超时（秒） |
| `--retries` | 3 | 请求重试次数 |
| `--page-delay-min` | 0.2 | 页间最小延迟秒数 |
| `--page-delay-max` | 0.6 | 页间最大延迟秒数 |
| `--jsonl` | data/kurogame_jobs.jsonl | JSONL 输出路径 |
| `--csv` | data/kurogame_jobs.csv | CSV 输出路径 |

### 蚂蚁脚本参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--start-page` | 1 | 起始页码 |
| `--end-page` | 999 | 结束页码（自动裁剪到最大页） |
| `--page-size` | 10 | 每页条数 |
| `--keyword` | 空字符串 | 搜索关键词 |
| `--batch-id` | 26022600074513 | 校招批次 ID，可重复指定 |
| `--timeout` | 20 | 单请求超时（秒） |
| `--retries` | 3 | 请求重试次数 |
| `--page-delay-min` | 0.2 | 页间最小延迟秒数 |
| `--page-delay-max` | 0.6 | 页间最大延迟秒数 |
| `--jsonl` | data/antgroup_jobs.jsonl | JSONL 输出路径 |
| `--csv` | data/antgroup_jobs.csv | CSV 输出路径 |

## 新增站点扩展流程

为降低新增站点时的改造成本，项目已提供两项扩展能力：

1. 爬虫 Skill（给人工维护）
- 文件：`skills/recruitment_site_crawler_skill.md`
- 用途：规范站点侦察、字段映射、稳定性策略、验收清单。

2. 自动化流程编排（给脚本执行）
- 命令：

```powershell
python src/run_data_pipeline.py
```

- 行为：
	- 自动发现并执行 `src/*_campus_scraper.py`
	- 自动执行分析导出 `src/run_analysis.py`
	- 自动执行前端导出 `src/export_frontend_jobs.py`

- 常用参数：

```powershell
# 只跑指定站点 + 后续分析/前端导出
python src/run_data_pipeline.py --only tencent mihoyo

# 仅重建分析与前端数据（跳过爬虫）
python src/run_data_pipeline.py --skip-crawlers

# 仅查看将执行的命令，不实际运行
python src/run_data_pipeline.py --dry-run
```

## 输出字段说明

| 字段 | 说明 |
|------|------|
| company | 公司名称 |
| job_id | 职位唯一 ID |
| title | 职位名称 |
| recruit_type | 招聘类型 |
| job_category | 岗位类别 |
| job_function | 岗位职能（无则为空） |
| work_city | 主工作地 |
| work_cities | 全部工作地（CSV 使用 `\|` 分隔） |
| team_intro | 团队/岗位介绍 |
| responsibilities | 岗位描述 |
| requirements | 岗位要求 |
| bonus_points | 加分项 |
| tags | 标签（CSV 使用 `\|` 分隔） |
| publish_time | 发布时间（可为空） |
| detail_url | 职位详情页链接 |
| fetched_at | 采集时间（ISO 8601 UTC） |
| source_page | 来源页码 |

## 下一步计划


