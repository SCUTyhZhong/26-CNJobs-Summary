# 腾讯校招爬虫复盘与维护手册

> 最后更新：2026-03-11
> 适用脚本：`src/tencent_campus_scraper.py`

---

## 1. 实现目标与当前结论

### 目标
- 稳定抓取腾讯校招岗位数据。
- 对齐项目统一 schema：公司、岗位类别、招聘类型、岗位描述、岗位要求、加分项、工作地。
- 输出 JSONL + CSV，供后续分析和合并多站数据。

### 当前结论
- 采用 API 直连方案（不依赖 Playwright）。
- 核心接口可无登录访问，当前无需 CSRF 或动态签名。
- 全量抓取可稳定完成（2026-03-11 实测 390 条）。

---

## 2. 抓取架构（两阶段）

### 阶段 A：列表分页
- 接口：`POST /api/v1/position/searchPosition`
- 作用：拿分页岗位列表与 `postId`。
- 关键分页参数：`pageIndex`, `pageSize`。
- 关键筛选参数：`projectMappingIdList`（通过接口动态获取，不写死）。

### 阶段 B：详情补全
- 接口：`GET /api/v1/jobDetails/getJobDetailsByPostId?postId=...`
- 作用：补齐长文本字段（岗位描述、要求、加分项等）。

### 元数据映射（启动时加载）
- `getProjectMapping`：构建 `projectMappingIdList`。
- `getPositionWorkCities`：城市编码 -> 城市名。
- `getPositionFamily`：岗位 ID -> 岗位类别标题（兜底）。

---

## 3. 字段映射策略（统一 schema）

### 核心映射
- `company` <- 固定值 `腾讯`
- `job_id` <- 列表 `postId`
- `title` <- 详情 `title`（为空时回退列表 `positionTitle`）
- `recruit_type` <- 列表 `recruitLabelName`
- `job_category` <- 优先级：
  1) 详情 `tidName`
  2) `position` 通过 `getPositionFamily` 映射
  3) `positionFamily` 数字映射（1-6 -> 综合/技术/产品/设计/市场/职能）
- `responsibilities` <- 详情 `desc`
- `requirements` <- 详情 `request`
- `bonus_points` <- 详情 `internBonus` 或 `graduateBonus`
- `work_cities` <- 优先级：
  1) 详情 `workCityList`
  2) 详情 `workCity` + 城市字典映射
  3) 列表 `workCities` 文本拆分
- `work_city` <- `work_cities` 第一个

### 已知数据特征（非程序错误）
- 部分岗位本身不提供 `desc/request/bonus`，因此会出现缺失。
- 多行文本在 CSV 内是合法换行字段；看行数时应使用 CSV 解析器，不要直接按文本行统计。

---

## 4. 稳定性设计

### 重试机制
- 所有 HTTP 请求统一走 `request_json`。
- 默认重试 3 次，指数退避 + 随机抖动。

### 节流策略
- 页间延迟：`page-delay-min/max`
- 详情延迟：`detail-delay-min/max`
- 目的：降低瞬时请求密度，减少被限流风险。

### 去重策略
- 运行期以 `job_id` 做内存去重，防止分页重复数据污染输出。

---

## 5. 维护风险与监控点

### 风险 R1：接口鉴权升级
- 现象：接口 401/403 或返回结构突然变化。
- 处理：
  1) 先用浏览器抓网络确认请求是否新增签名/令牌。
  2) 若有，临时切到 Playwright 抓取网络响应。

### 风险 R2：字段名变更
- 现象：`data` 内关键字段消失或改名。
- 处理：
  1) 对比线上返回 JSON。
  2) 更新 `normalize_record` 映射优先级。

### 风险 R3：城市或类别出现编码回退
- 现象：输出里出现纯数字城市/类别。
- 处理：
  1) 检查字典接口是否失败。
  2) 检查映射函数回退路径是否触发。

### 风险 R4：CSV 乱码误判
- 现象：PowerShell 直接 `Get-Content` 看到中文乱码。
- 处理：
  1) 用 Python `encoding='utf-8'` 读取确认。
  2) 或在支持 UTF-8 的编辑器查看。

---

## 6. 维护操作清单（Runbook）

### 日常验证（建议每次改动后执行）
1. 语法检查：
   - `python -m py_compile src/tencent_campus_scraper.py`
2. 小样本抓取：
   - `python src/tencent_campus_scraper.py --start-page 1 --end-page 2 --jsonl data/tencent_jobs_sample.jsonl --csv data/tencent_jobs_sample.csv`
3. 关键字段抽查（随机 3-5 条）：
   - `job_category` 是否为可读文本。
   - `work_cities` 是否包含可读城市名。
   - `responsibilities/requirements` 是否在有值岗位上正常填充。

### 全量执行
- `python src/tencent_campus_scraper.py --jsonl data/tencent_jobs.jsonl --csv data/tencent_jobs.csv`

### 结果核验
1. JSONL 条数与 `searchPosition.count` 对齐。
2. CSV 用解析器统计数据行数（应与 JSONL 一致）。
3. 检查 `job_id` 去重后数量是否一致。

---

## 7. 后续建议（按优先级）

1. 增量抓取
- 基于历史 `job_id` 做增量更新，降低全量重跑成本。

2. 结构化日志
- 记录失败接口、重试次数、耗时分布，写入 `logs/`。

3. 健康度监控
- 增加简单质量指标：字段缺失率、类别分布、城市编码残留率。

4. 多站统一抽象
- 抽取公共 HTTP、重试、CSV/JSONL 写入模块，减少站点脚本重复代码。
