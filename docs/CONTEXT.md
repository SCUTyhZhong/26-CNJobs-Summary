# 项目上下文速查

> 最后更新：2026-03-11

## 项目定位

多招聘网站数据采集项目。当期目标：采集校园招聘职位数据（字节 + 腾讯 + 网易已覆盖），输出结构化 JSONL/CSV，为后续职位数据分析、聚合、多站对比做数据基础。

---

## 当前状态（Phase 1.6）

- **已完成**：字节校园招聘爬虫（Playwright） + 腾讯校园招聘爬虫（API 直连） + 网易互娱校园招聘爬虫（API 直连）。
- **已验证**：腾讯站点 `searchPosition`（列表）和 `getJobDetailsByPostId`（详情）可无登录直接访问。
- **数据规模（腾讯）**：2026-03-11 实测 `count=390`（`pageSize=10`）。
- **数据规模（网易）**：2026-03-12 实测 `count=60`（每页 15 条，共 4 页）。

---

## 代码结构

```
src/
  bytedance_campus_scraper.py   Phase 1 完整实现
  tencent_campus_scraper.py     腾讯 API 直连实现
  netease_campus_scraper.py     网易 API 直连实现
data/
  bytedance_jobs.jsonl          主输出
  bytedance_jobs.csv            主输出
  tencent_jobs.jsonl            腾讯输出
  tencent_jobs.csv              腾讯输出
  netease_jobs.jsonl            网易输出
  netease_jobs.csv              网易输出
docs/
  CONTEXT.md                    本文件，全局上下文速查
  DECISIONS.md                  关键技术决策日志
  BYTEDANCE_CAMPUS_SCRAPER_PLAN.md   字节爬虫技术规划（详细）
  TENCENT_SCRAPER_MAINTENANCE.md     腾讯爬虫复盘与维护手册
```

---

## 关键技术事实

### 字节跳动校园招聘

| 项目 | 内容 |
|------|------|
| 列表 URL 模板 | `https://jobs.bytedance.com/campus/position?...&project=7194661126919358757&current={N}&limit={M}` |
| 职位列表 API | `POST https://jobs.bytedance.com/api/v1/search/job/posts` |
| 鉴权方式 | `x-csrf-token` 请求头 + `atsx-csrf-token` Cookie，Playwright 自动复用 |
| `_signature` | URL 参数，目前可复用不变，非强校验 |
| 分页参数 | API offset = (current-1) × limit |
| 详情页 URL | `/campus/position/{job_id}/detail` |
| robots.txt | 明确 Allow: /campus |

### 爬虫运行方式

- 默认调用系统 Edge（`--browser-channel msedge`），无需额外安装浏览器。
- 备选：`--browser-channel chromium`（需先执行 `python -m playwright install chromium`）。
- 有头模式调试：追加 `--headed`。
- 数据回落机制：API 未捕获时自动解析 DOM 卡片（字段较少）。

### 腾讯校园招聘

| 项目 | 内容 |
|------|------|
| 列表 API | `POST https://join.qq.com/api/v1/position/searchPosition` |
| 详情 API | `GET https://join.qq.com/api/v1/jobDetails/getJobDetailsByPostId?postId=...` |
| 项目映射 API | `GET https://join.qq.com/api/v1/position/getProjectMapping` |
| 城市字典 API | `GET https://join.qq.com/api/v1/position/getPositionWorkCities` |
| 岗位类别 API | `GET https://join.qq.com/api/v1/position/getPositionFamily` |
| 鉴权情况 | 当前无需登录、无动态签名，带常规浏览器请求头即可 |
| 分页参数 | `pageIndex` + `pageSize`（请求体） |
| 详情页 URL | `https://join.qq.com/post_detail.html?postid={postId}` |

### 网易互娱校园招聘

| 项目 | 内容 |
|------|------|
| 列表 API | `POST https://campus.game.163.com/api/recruitment/campus/position/list` |
| 详情 API | `GET https://campus.game.163.com/api/recruitment/campus/position/detail?positionId=...` |
| 筛选元数据 API | `GET https://campus.game.163.com/api/recruitment/campus/position/filters?projectId=...` |
| 鉴权情况 | 当前无需登录、无动态签名，常规浏览器请求头即可 |
| 分页参数 | `pageNum`（请求体），页面当前每页 15 条 |
| 详情页 URL | `https://campus.game.163.com/position-detail/{positionId}` |

---

## 下一步工作（Phase 2 推荐起始点）

1. **详情页补全** — 打开 `detail_url`，抓取部门/学历要求/薪资/截止日期等额外字段。
2. **增量更新** — 加载已有 JSONL，跳过已存在的 `job_id`，仅补采新岗位。
3. **失败重试 + 日志** — 爬取结果写入 `logs/` 目录（成功页数/失败页数/新增数）。

---

## 依赖与环境

| 依赖 | 版本要求 |
|------|----------|
| Python | 3.14.0（已验证） |
| playwright | ≥ 1.52.0 |
| 系统浏览器 | Edge（Win 默认有）或 Chrome |

安装命令：
```powershell
pip install -r requirements.txt
```
