# job_info_collector

多网站校园招聘数据采集项目。当前采用 Scrapy + 增量去重写入统一数据文件，并构建 LanceDB 供后续 RAG 与 API 查询使用。

## 项目结构

```text
job_info_collector/
├── scrapy_crawlers/
│   ├── scrapy.cfg
│   └── crawlers/
│       ├── settings.py
│       ├── items.py
│       ├── pipelines.py           # 增量写入 data/jobs.csv + data/jobs.jsonl
│       └── spiders/
│           ├── tencent.py
│           ├── bilibili.py
│           ├── netease.py
│           ├── antgroup.py
│           └── mihoyo.py
├── src/
│   ├── bytedance_campus_scraper.py # Playwright（增量写入统一数据文件）
│   ├── merge_job_files.py          # 历史分站文件合并到统一文件
│   ├── build_jobs_lancedb.py
│   ├── api_server.py
│   ├── run_data_pipeline.py
│   ├── run_analysis.py
│   └── export_frontend_jobs.py
├── data/
│   ├── jobs.csv
│   ├── jobs.jsonl
│   ├── lancedb/
│   └── lancedb_meta.json
├── docs/
├── web/
├── README.md
└── requirements.txt
```

## 目标网站

| 网站 | 状态 | 运行方式 |
|------|------|---------|
| 腾讯校园招聘 | Scrapy | `python -m scrapy crawl tencent` |
| 哔哩哔哩校园招聘 | Scrapy | `python -m scrapy crawl bilibili` |
| 网易互娱校园招聘 | Scrapy | `python -m scrapy crawl netease` |
| 阿里巴巴(蚂蚁集团)校园招聘 | Scrapy | `python -m scrapy crawl antgroup` |
| 米哈游校园招聘 | Scrapy | `python -m scrapy crawl mihoyo` |
| 字节跳动校园招聘 | Playwright | `python src/bytedance_campus_scraper.py` |

## 环境依赖

```powershell
pip install -r requirements.txt
```

若需要 Playwright 内置浏览器：

```powershell
python -m playwright install chromium
```

## 增量更新机制

- 统一数据文件：`data/jobs.csv`、`data/jobs.jsonl`
- 去重键：`(company, job_id)`
- Scrapy 爬虫与字节跳动脚本都以追加模式写入统一文件
- 已存在职位会自动跳过，重复运行不会产生重复数据

## 本地产物清理与忽略

项目已提供 `/.gitignore`，默认忽略本地运行产生的文件：

- `logs/*.log`
- `data/lancedb/`
- `data/lancedb_meta.json`
- `__pycache__/`、`.pytest_cache/`、`.venv/` 等缓存/环境目录

常用清理命令：

```powershell
Remove-Item -Recurse -Force data/lancedb -ErrorAction SilentlyContinue
Remove-Item -Force data/lancedb_meta.json -ErrorAction SilentlyContinue
Get-ChildItem logs -Filter *.log -ErrorAction SilentlyContinue | Remove-Item -Force
```

## 使用说明

### 一键流水线

流水线顺序：爬取 -> 重建 LanceDB -> 分析 -> 前端导出

```powershell
python src/run_data_pipeline.py
```

常用参数：

```powershell
# 只做分析 + 前端导出
python src/run_data_pipeline.py --skip-crawlers --skip-lancedb

# 仅运行指定站点爬虫后继续下游步骤
python src/run_data_pipeline.py --only mihoyo
```

### 单独运行 Scrapy 爬虫

```powershell
cd scrapy_crawlers
python -m scrapy list
python -m scrapy crawl tencent
```

### 重建 LanceDB

```powershell
python src/build_jobs_lancedb.py
```

### 启动 API

```powershell
python src/api_server.py
# GET http://localhost:8000/api/jobs/payload
```

## 网站加载数据自检

### 1) 检查 API 数据是否可读

```powershell
python src/api_server.py
# 新终端请求：
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/jobs/payload
```

通过标准：

- `/api/health` 返回 `status=ok`
- `/api/jobs/payload` 返回 200，且 `jobs` 数组非空

### 2) 检查前端静态数据是否可加载

```powershell
cd web
python -m http.server 8080
# 浏览器打开 http://127.0.0.1:8080
```

通过标准：

- 页面无“加载失败”提示
- 职位列表成功渲染
- 搜索和筛选可正常交互

### 历史分站文件一次性合并

```powershell
python src/merge_job_files.py --cleanup
```

说明：该命令会将 `*_jobs.csv/jsonl` 合并到 `jobs.csv/jsonl`，并删除旧分站文件。
