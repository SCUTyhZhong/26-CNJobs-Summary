# 哔哩哔哩校招爬虫复盘与维护手册

> 最后更新：2026-03-14
> 适用脚本：src/bilibili_campus_scraper.py

---

## 1. 实现目标与当前结论

### 目标
- 稳定抓取哔哩哔哩校招岗位数据。
- 对齐项目统一 schema：公司、岗位类别、招聘类型、岗位职责、岗位要求、加分项、工作地等。
- 输出 JSONL + CSV，供后续分析与前端聚合使用。

### 当前结论
- 采用 API 直连方案（不依赖 Playwright）。
- 需要先获取 CSRF token，再访问列表/详情接口。
- 2026-03-14 全量实测可完成：311 条岗位，job_id 唯一数 311。

---

## 2. 抓取架构（两阶段 + CSRF 预处理）

### 阶段 0：获取 CSRF
- 接口：GET https://jobs.bilibili.com/api/auth/v1/csrf/token
- 作用：拿到后续列表/详情请求所需 `x-csrf`。
- 判定成功：返回 `code == 0` 且 `data` 非空字符串。

### 阶段 A：列表分页
- 接口：POST https://jobs.bilibili.com/api/campus/position/positionList
- 作用：获取分页岗位列表与总数 total。
- 关键参数：
  - pageNum: 页码（从 1 开始）
  - pageSize: 每页条数（默认 10）
  - positionName: 关键词（可空）
  - workTypeList: 默认 ["0"]
  - positionTypeList: 默认 ["0"]
  - recruitType: 可选，默认 None 跟随站点默认
  - onlyHotRecruit: 默认 0

### 阶段 B：详情补全（可选）
- 接口：GET https://jobs.bilibili.com/api/campus/position/detail/{id}
- 作用：补齐详情字段（当 `--fetch-detail` 开启时）。
- 默认策略：关闭详情抓取，仅用列表字段即可稳定落地主干字段。

---

## 3. 必要请求头与接口依赖

### 默认请求头
脚本常量 `DEFAULT_HEADERS` 目前依赖以下关键头：
- `x-appkey: ops.ehr-api.auth`
- `x-usertype: 2`
- `x-channel: campus`
- `Referer: https://jobs.bilibili.com/campus/positions?type=0`
- `Origin: https://jobs.bilibili.com`
- `User-Agent`: 浏览器 UA（脚本内置）

### 动态请求头
- 在获取 CSRF 后，列表/详情请求会追加：
  - `x-csrf: <token>`

### 风险提示
- 若未来接口增加签名/风控参数，最先出现的现象通常是 `code != 0`、403 或返回结构变化。

---

## 4. 字段映射策略（统一 schema）

### 核心映射
- company <- 固定值 哔哩哔哩
- job_id <- id
- title <- positionName
- recruit_type <- positionTypeName
- job_category <- postCodeName
- job_function <- positionTypeName
- work_city <- workLocation
- work_cities <- [workLocation]
- team_intro <- deptIntro
- responsibilities / requirements / bonus_points <- 从 positionDescription 解析
- publish_time <- pushTime
- detail_url <- https://jobs.bilibili.com/campus/positions/{job_id}
- tags <- jobHighlights（当前按单标签列表处理）

### 文本解析规则
- 脚本先做 HTML 清洗（如 `<br>`、`<p>`）。
- 再按常见段落标题拆分：
  - 岗位职责
  - 任职要求 / 岗位要求
  - 加分项
- 若未匹配到结构化标题，则整段落入 `responsibilities` 作为兜底。

---

## 5. 稳定性设计

### 重试机制
- 所有 HTTP 请求统一走 `request_json`。
- 默认重试 3 次，指数退避 + 随机抖动。

### 节流策略
- 页间延迟：`page-delay-min/max`
- 详情延迟：`detail-delay-min/max`
- 目标：降低突发请求密度，减少限流概率。

### 去重策略
- 运行期以 `job_id` 进行内存去重。
- 输出前按 `job_id` 排序，便于版本比对。

---

## 6. 运行与验收（Runbook）

### 日常验证（每次改动后）
1. 语法检查
- `python -m py_compile src/bilibili_campus_scraper.py`

2. 小样本抓取（单页）
- `python src/bilibili_campus_scraper.py --start-page 1 --end-page 1 --page-size 10 --jsonl data/bilibili_jobs_sample.jsonl --csv data/bilibili_jobs_sample.csv`

3. 抽查字段（随机 3-5 条）
- `job_id` 非空且唯一。
- `title/job_category/work_city` 为可读文本。
- `detail_url` 与 `job_id` 对应。

### 全量执行
- `python src/bilibili_campus_scraper.py --start-page 1 --end-page 999 --page-size 10 --jsonl data/bilibili_jobs.jsonl --csv data/bilibili_jobs.csv`

### 详情增强抓取（可选）
- `python src/bilibili_campus_scraper.py --fetch-detail --start-page 1 --end-page 999 --jsonl data/bilibili_jobs.jsonl --csv data/bilibili_jobs.csv`

### 结果核验
1. JSONL 行数与列表接口 `total` 对齐。
2. CSV 数据行数与 JSONL 一致。
3. `job_id` 去重后数量不下降。

---

## 7. 常见故障与排查

### R1：CSRF 获取失败
- 现象：脚本启动即报错 `Failed to fetch csrf token`。
- 排查：
  1) 检查网络连通与 DNS。
  2) 检查 `DEFAULT_HEADERS` 是否被误改（尤其 Referer/Origin）。
  3) 观察接口是否新增鉴权字段。

### R2：列表接口返回 code 非 0
- 现象：`Position list API returned non-success`。
- 排查：
  1) 确认 `x-csrf` 已携带且未过期。
  2) 检查 `x-appkey/x-usertype/x-channel` 是否缺失。
  3) 用浏览器抓包对比请求体字段是否变化。

### R3：字段突然大面积为空
- 现象：`job_category` 或 `positionDescription` 等核心字段为空比例异常。
- 排查：
  1) 保存一页原始响应样本进行结构对比。
  2) 更新 `normalize_record` 映射优先级与兜底逻辑。

### R4：CSV 中中文显示异常
- 现象：PowerShell 直接查看 CSV 出现乱码。
- 排查：
  1) 用 Python `encoding='utf-8'` 读取确认。
  2) 或使用支持 UTF-8 的编辑器/表格工具打开。

---

## 8. 参数说明（维护高频）

- `--start-page` / `--end-page`: 抓取页范围。
- `--page-size`: 每页条数。
- `--keyword`: 按岗位名称关键字过滤。
- `--work-type-list`: 对应接口 `workTypeList`。
- `--position-type-list`: 对应接口 `positionTypeList`。
- `--recruit-type`: 对应接口 `recruitType`（可空）。
- `--only-hot-recruit`: 1 仅热门岗位，0 全量。
- `--fetch-detail`: 是否调用详情接口补全。
- `--timeout`: 单次请求超时时间（秒）。
- `--retries`: 请求重试次数。
- `--jsonl` / `--csv`: 输出路径。

---

## 9. 后续优化建议（按优先级）

1. 断点续跑
- 引入 `state` 文件记录已完成页与 job_id，减少中断后的重复抓取成本。

2. 增量抓取
- 与历史快照对比，仅更新新增或变更岗位。

3. 质量报告自动化
- 每次抓取后自动输出缺失率、类别分布、城市分布，快速发现字段漂移。

4. 通用化抽象
- 将 `request_json`、重试、输出写入与字段标准化抽到公共模块，减少多站脚本重复实现。
