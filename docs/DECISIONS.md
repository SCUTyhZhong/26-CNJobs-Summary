# 技术决策日志

> 每次重要设计选择均记录在此，方便回溯和与 AI 对话时快速同步背景。

---

## [2026-03-11] Phase 1 初始化

### D-001 · 采集方案：Playwright 浏览器驱动 vs 纯 HTTP

**结论**：采用 Playwright 浏览器驱动（网络响应捕获）。

**背景**：  
站点接口 `POST /api/v1/search/job/posts` 需要 CSRF token（首次页面加载由 `/api/v1/csrf/token` 下发）和 `_signature` URL 参数。两者逆向复杂度不同：
- CSRF token：每次 session 生成，Playwright 访问页面后可从 Cookie 读取。
- `_signature`：URL 附带，当前验证不严（翻页时同一 signature 仍有效），但机制未公开，存在加强的可能。

**理由**：  
Playwright 驱动让浏览器自行完成 CSRF 握手，signature 附在 URL 即可复用，完全绕开逆向问题，维护成本极低。未来如 signature 加强，只需改浏览器打开相应页面后通过 `page.request` 直接代理，无需更改架构。

**否决方案**：纯 HTTP + 逆向 signature — 算法未公开，维护成本高，暂不采用。

---

### D-002 · 页面加载策略：`networkidle` vs `domcontentloaded`

**结论**：使用 `domcontentloaded` + 固定等待 2500ms。

**背景**：  
站点存在持续上报的 telemetry 请求（`/monitor_browser/collect/batch/`），导致 `networkidle` 永不触发，爬虫卡死。

**理由**：  
`domcontentloaded` 后 API 请求通常已完成，额外等待 2.5s 缓冲足够；比 `networkidle` 更稳定，单页等待时间更可预测。

---

### D-003 · 浏览器通道：系统 Edge 优先

**结论**：默认 `--browser-channel msedge`，可选 chromium / chrome。

**背景**：  
Windows 环境中 Edge 开箱即有，Playwright 可以直接使用系统安装的 Edge 而无需下载独立浏览器二进制（~170 MB）。

**理由**：  
减少安装时间和存储依赖；Chromium 仍作为备选（`--browser-channel chromium`）并在 `README.md` 中记录了安装命令。

---

### D-004 · DOM 兜底提取策略

**结论**：API 捕获失败时解析页面 `<a href*="/detail">` 卡片链接。

**背景**：  
如果 API 响应未被监听器捕获，空结果会导致该页数据丢失。

**理由**：  
DOM 卡片包含 job_id（可从 href 提取）、title（文本首行）、部分描述，可为 Phase 2 详情页补全留下足迹。字段覆盖度低于 API，但保证不完全丢页。

---

### D-005 · 输出格式：JSONL + CSV 双格式

**结论**：同时输出 JSONL 和 CSV。

**理由**：  
- JSONL：每行独立 JSON 对象，支持流式追加，不破坏已有记录，适合增量写入和 Python 处理。
- CSV：列格式，便于直接用 Excel/数据分析工具查看，多值字段（cities, tags）以 `|` 分隔。

**注意**：当前每次运行覆盖写出，增量合并策略在 Phase 3 实现。

---

## 待决策

| ID | 问题 | 时间 |
|----|------|------|
| D-006 | 详情页抓取节奏：与列表页合并一次 Playwright 会话，还是两阶段分别运行？ | Phase 2 开始时决策 |
| D-007 | 增量去重存储：继续 JSONL 扫描，还是引入 SQLite 主键索引？ | Phase 3 开始时决策 |
| D-008 | 多站点抽象方式：共享基类 + 子类，还是独立脚本 + 公共工具库？ | Phase 5 开始时决策 |

---

## [2026-03-11] 腾讯校招接入

### D-009 · 腾讯采集方案：API 直连 vs Playwright

**结论**：采用 API 直连（urllib），不依赖浏览器会话。

**背景**：  
实测 `searchPosition` 与 `getJobDetailsByPostId` 在无登录情况下可返回完整数据，未发现 CSRF 动态令牌或签名校验。

**理由**：  
- 请求链路简单，速度更快；
- 依赖更轻（无浏览器启动成本）；
- 稳定性高，便于后续定时任务与批量重跑。

**保留策略**：  
若后续出现风控升级（例如新增签名校验），切回 Playwright 抓取网络响应作为降级方案。

---

### D-010 · 腾讯字段拼接策略：列表 + 详情两阶段

**结论**：列表接口拿分页主键（`postId`），详情接口补全文本字段后统一落地。

**关键映射**：
- 岗位描述：`detail.desc` → `responsibilities`
- 岗位要求：`detail.request` → `requirements`
- 加分项：`detail.internBonus` 或 `detail.graduateBonus` → `bonus_points`
- 工作地：`detail.workCity` + 城市字典映射 → `work_cities`

**理由**：
- 列表数据轻量，适合快速分页；
- 详情字段结构化程度高，能满足统一 schema 的核心字段。

---

## [2026-03-12] 网易互娱校招接入

### D-011 · 网易采集方案：API 直连 vs 页面解析

**结论**：采用 API 直连，不解析 HTML。

**背景**：  
职位详情页虽然可见正文，但 HTML 首屏不直接包含完整职位文本；页面加载后会调用 `GET /api/recruitment/campus/position/detail?positionId=...` 获取数据。

**理由**：  
- 接口稳定且结构清晰；
- 避免解析动态页面 DOM；
- 与腾讯脚本架构一致，维护成本更低。

---

### D-012 · 网易字段拼接策略：列表 + 详情两阶段

**结论**：列表接口负责分页与主键，详情接口负责长文本与标签补全。

**关键映射**：
- 职位名称：`info.externalPositionName`
- 招聘类型：`info.projectName`
- 岗位类别：`info.positionTypeAbbreviation`
- 岗位描述：`info.positionDescription`
- 任职资格：`info.positionRequirement`
- 工作地：`info.workCities`
- 标签：`info.externalTags`

**理由**：
- 列表接口只包含摘要字段；
- 详情接口 `info` 已覆盖统一 schema 所需主要内容。
