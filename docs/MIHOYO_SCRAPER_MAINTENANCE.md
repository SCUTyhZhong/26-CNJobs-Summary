# 米哈游校招爬虫复盘与维护手册

> 最后更新：2026-03-13
> 适用脚本：src/mihoyo_campus_scraper.py

---

## 1. 实现目标与当前结论

### 目标
- 稳定抓取米哈游校园招聘岗位数据。
- 对齐项目统一 schema：公司、岗位类别、招聘类型、岗位职责、岗位要求、加分项、工作地。
- 输出 JSONL + CSV，供后续分析与前端聚合使用。

### 当前结论
- 采用 API 直连方案（不依赖 Playwright）。
- 列表与详情接口可匿名访问（无需登录态）。
- 2026-03-13 全量实测可完成：259 条岗位，job_id 唯一数 259。

---

## 2. 抓取架构（两阶段）

### 阶段 A：列表分页
- 接口：POST https://ats.openout.mihoyo.com/ats-portal/v1/job/list
- 作用：获取岗位列表与总数 total。
- 关键参数：
  - pageNo: 页码（从 1 开始）
  - pageSize: 每页条数（实测 100 可用）
  - channelDetailIds: [1]（校招渠道）
  - hireType: 1（校园招聘）

### 阶段 B：详情补全
- 接口：POST https://ats.openout.mihoyo.com/ats-portal/v1/job/info
- 作用：按 id 补齐长文本字段（职责、要求、加分项等）。
- 请求体：
  - id: 职位 ID（字符串）
  - channelDetailIds: [1]
  - hireType: 1

---

## 3. 字段映射策略（统一 schema）

### 核心映射
- company <- 固定值 米哈游
- job_id <- 列表/详情 id
- title <- 详情 title（为空时回退列表 title）
- recruit_type <- projectName（实习生专项 / 2026年春招）
- job_category <- competencyType
- job_function <- jobNature（全职 / 实习）
- work_cities <- addressDetailList[].addressDetail 去重后列表
- work_city <- work_cities 第一个
- responsibilities <- description
- requirements <- jobRequire
- bonus_points <- addition
- tags <- tagList（当前多为空）
- detail_url <- https://jobs.mihoyo.com/#/campus/position/{job_id}
- publish_time <- 当前 API 未提供，置空

### 已知数据特征（非程序错误）
- publish_time 当前全量缺失（接口侧无该字段）。
- 部分岗位没有要求或加分项内容，属业务侧真实缺失。

---

## 4. 稳定性设计

### 重试机制
- 所有 HTTP 请求统一通过 post_json。
- 默认重试 3 次，指数退避 + 随机抖动。

### 节流策略
- 页间延迟：page-delay-min/max。
- 详情延迟：detail-delay-min/max。
- 目的：降低请求突发，减少限流和连接抖动风险。

### 去重策略
- 运行期以 job_id 做内存去重。
- 输出前统一排序，确保结果稳定可比。

---

## 5. 本次全量运行结果（2026-03-13）

### 产出文件
- data/mihoyo_jobs.jsonl
- data/mihoyo_jobs.csv

### 核验指标
- 总条数：259
- job_id 唯一数：259
- responsibilities 缺失：0
- requirements 缺失：2
- bonus_points 缺失：85
- publish_time 缺失：259

### 分布概览
- 职能类型 Top5：
  - 程序&技术类: 94
  - 美术&表现类: 59
  - 产品策划类: 28
  - 国际化类: 21
  - 综合类: 18
- 招聘项目：
  - 实习生专项: 151
  - 2026年春招: 108
- 城市：
  - 上海: 256
  - 北京: 3

---

## 6. 维护风险与监控点

### 风险 R1：接口鉴权升级
- 现象：返回未登录、403 或增加签名校验。
- 处理：
  1) 浏览器抓包确认是否新增 token/签名。
  2) 如需动态签名，临时切换 Playwright 抓接口响应。

### 风险 R2：字段名变更
- 现象：description/jobRequire/addition 字段缺失或改名。
- 处理：
  1) 保存异常响应样本。
  2) 更新 normalize_record 映射优先级。

### 风险 R3：渠道参数失效
- 现象：接口返回参数校验失败（如 职位渠道不可以为空）。
- 处理：
  1) 保持 channelDetailIds 和 hireType 为显式参数。
  2) 需要时用 enum 接口重新确认可用值。

### 风险 R4：网络抖动导致中断
- 现象：偶发连接超时。
- 处理：
  1) 保持 retries >= 2。
  2) 适当增加 timeout 与 delay 区间。

---

## 7. 维护操作清单（Runbook）

### 日常验证（每次改动后）
1. 语法检查
- C:/Users/yohi.zhong/AppData/Local/Programs/Python/Python314/python.exe -m py_compile src/mihoyo_campus_scraper.py

2. 小样本抓取
- C:/Users/yohi.zhong/AppData/Local/Programs/Python/Python314/python.exe src/mihoyo_campus_scraper.py --start-page 1 --end-page 1 --jsonl data/mihoyo_jobs_sample.jsonl --csv data/mihoyo_jobs_sample.csv

3. 关键字段抽查（随机 3-5 条）
- detail_url 可打开且和 job_id 一致。
- responsibilities/requirements 字段有值时不乱码。
- work_cities 为可读城市文本。

### 全量执行
- C:/Users/yohi.zhong/AppData/Local/Programs/Python/Python314/python.exe src/mihoyo_campus_scraper.py --jsonl data/mihoyo_jobs.jsonl --csv data/mihoyo_jobs.csv

### 结果核验
1. JSONL 行数与列表接口 total 对齐。
2. CSV 数据行数与 JSONL 一致。
3. job_id 去重后数量不下降。

---

## 8. 后续优化建议（按优先级）

1. 增量抓取
- 基于历史 job_id 跳过旧岗位，降低重复请求成本。

2. 断点续跑
- 支持从指定 pageNo 和已完成 job_id 集合恢复运行。

3. 质量报告自动化
- 在 CI 中增加缺失率、类别分布、城市分布的轻量校验。

4. 站点通用化
- 抽象公共 HTTP 重试、输出写入、字段标准化模块，减少多站重复代码。
