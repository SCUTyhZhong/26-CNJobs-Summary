# 招聘网站爬虫 Skill

## 目标
- 快速完成新招聘站点接入，输出符合统一数据契约的 CSV/JSONL。
- 保证后续分析与前端流程无需额外改代码即可自动纳入新数据。

## 适用范围
- 校招/社招职位站点（SPA/API/传统页面）。
- 优先使用公开 API，其次使用浏览器网络拦截，再次使用 DOM 兜底。

## 输入
- 目标站点 URL。
- 目标范围（校招/社招、分页范围、关键词）。

## 输出
- 爬虫脚本：src/<site>_campus_scraper.py
- 数据文件：data/<site>_jobs.jsonl, data/<site>_jobs.csv
- 维护文档：docs/<SITE>_SCRAPER_MAINTENANCE.md

## 统一字段契约
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

## 标准流程
1. 站点侦察
- 确认是否存在公开 API。
- 确认列表接口、详情接口、分页参数、反爬约束。

2. 字段映射设计
- 建立接口字段到统一契约的映射表。
- 明确缺失字段的空值策略（保留空字符串/空列表）。

3. 脚本实现
- 结构建议：request/post 封装 -> list/detail 拉取 -> normalize_record -> write_csv/jsonl。
- 默认支持参数：start-page/end-page/timeout/retries/jsonl/csv。

4. 稳定性策略
- 重试：指数退避 + 抖动。
- 节流：页间与详情请求延迟。
- 去重：company + job_id（或 detail_url）去重。

5. 质量校验
- 行数与接口 total 对齐。
- job_id 唯一性检查。
- 关键字段缺失率统计（职责/要求/城市/详情链接）。

6. 并入主流程
- 运行 src/export_frontend_jobs.py，确认前端数据自动纳入。
- 运行 src/run_analysis.py，确认分析报告自动纳入。

## 验收清单
- 能稳定全量抓取（至少 1 次成功记录）。
- 输出字段与统一契约一致。
- 维护手册包含接口说明、风险点、Runbook。
- 前端和分析流程无需为新站点写额外硬编码。

## 常见风险与应对
- 接口鉴权升级：先抓包确认 token/signature，再决定是否引入 Playwright。
- 字段改名：在 normalize_record 中增加回退字段链。
- 频率限制：调大 delay，降低 page_size，必要时分批抓取。
- 乱码误判：统一 UTF-8 读写，CSV 用解析器查看。
