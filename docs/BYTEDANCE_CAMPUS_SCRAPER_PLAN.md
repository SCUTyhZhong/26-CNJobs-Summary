# 字节跳动校园招聘爬虫 技术规划

> 最后更新：2026-03-11

## 目标

1. 稳定持续地抓取字节跳动校园招聘列表数据。
2. 保持数据结构标准化，为后续多站点聚合做预留。
3. 遵从 robots.txt（站点允许 /campus），访问频率克制。

## 站点分析（已验证）

- 列表页为 React SPA，数据由接口驱动，不含静态 HTML 职位数据。
- 核心职位接口：`POST https://jobs.bytedance.com/campus/position`  
  实际 API：`POST https://jobs.bytedance.com/api/v1/search/job/posts`
- 鉴权机制：
  - 需要 `atsx-csrf-token` Cookie（页面加载时由 `/api/v1/csrf/token` 派发）。
  - `_signature` URL 参数存在但**并非强验证**：翻页后 signature 不变依旧可以请求成功。
- 分页参数：`current`（页码）, `limit`（每页条数）。
  - API 端使用 `offset = (current-1) * limit`。
- 数据总量：约 3049 条（2026-03-11 时点），305 页 (limit=10)。
- 详情页链接规律：`/campus/position/{job_id}/detail`。

## 数据采集方案

**当前方案：Playwright 浏览器驱动 + 网络响应捕获（API-first）**

流程：
1. Playwright 打开列表页 URL（`current=N`）。
2. 监听网络响应，拦截 `POST /api/v1/search/job/posts` 的返回 JSON。
3. 从 JSON 中提取 `data.job_post_list`，归一化字段。
4. 若 API 未捕获（超时 / 拦截），回退到 DOM 卡片提取（仅得到基础字段）。
5. 按 `job_id` 本轮去重，顺序追加到输出文件。

**备选方案（未采用）：纯 HTTP + 逆向 signature**
- 维护成本高，signature 算法可能频繁更新，不作为 MVP 选项。

## 输出 Schema（Phase 1）

| 字段 | 类型 | 来源 |
|------|------|------|
| job_id | str | API |
| title | str | API |
| sub_title | str\|null | API |
| description | str\|null | API |
| requirement | str\|null | API |
| city | str\|null | API city_info.name |
| cities | list[str] | API city_list |
| recruit_type | str\|null | API recruit_type.name |
| job_category | str\|null | API job_category.name |
| job_function | str\|null | API job_function.name |
| publish_time | int\|null | API（毫秒时间戳） |
| job_hot_flag | any | API |
| tags | list[str] | API tag_list |
| process_type | int\|null | API |
| detail_url | str | 构造 |
| source_current_page | int | 采集 |
| source_list_url | str | 采集 |
| fetched_at | str | 采集（ISO 8601 UTC） |

## 分页策略

- URL 参数 `current` 控制页码，`limit` 控制每页条数（建议 10-20）。
- 爬取范围由脚本参数 `--start-page` / `--end-page` 控制。
- 全量抓取终止条件（Phase 2）：连续 2 页 API 返回空列表。
- 推荐单次抓取范围 ≤ 50 页，超大量任务分批执行。

## 健壮性与合规

- 随机页间延迟：默认 1.0–2.5 秒。
- 失败重试：Phase 2 实现（指数退避，最多 3 次）。
- 去重键：`job_id`（运行内去重，全量去重在 Phase 3）。
- 输出确保：运行结束统一写文件，中途崩溃不会写脏数据。
- robots.txt：允许爬取 `/campus`，无访问频率限制。

## 交付阶段

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase 1 | 列表页爬虫，JSONL/CSV 输出，DOM 兜底 | ✅ 完成（2026-03-11） |
| Phase 2 | 详情页补全（部门/完整 JD/学历/截止日期）；增量更新（基于 job_id 跳过已有条目） | 🔲 待做 |
| Phase 3 | 全量去重合并；运行统计报表；失败重试日志 | 🔲 待做 |
| Phase 4 | 定时调度（Task Scheduler / cron）；监控告警 | 🔲 待做 |
| Phase 5 | 多站点抽象层；接入拉钩、Boss 直聘等 | 🔲 待做 |

## 已知限制与风险

- CSRF token Cookie 有过期时间，长时间运行或跨天任务可能需要重新获取（Playwright 重新开页自动解决）。
- `_signature` 目前可复用，但存在日后被加强校验的风险。
- 详情页需要额外一次请求，Phase 2 需评估总请求压力。

