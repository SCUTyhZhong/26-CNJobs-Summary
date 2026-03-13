# 前端数据加载调试 Skill

## 目标
- 快速定位招聘前端“总数有值但列表为空 / 页面直接加载失败 / 邀请码通过后无数据”的问题。
- 在不依赖后端服务的前提下，确认静态站点的数据文件、路径解析和本地运行方式是否正确。

## 适用范围
- `web/index.html`
- `web/assets/app.js`
- `web/data/jobs.index.json`
- `web/data/jobs.json`
- `web/data/chunks/jobs-*.json`
- `web/config/invite-codes.js`

## 核心结论
- 邀请码校验通常不是数据消失的根因；更常见根因是前端依赖的 `jobs.index.json` 或 `jobs.json` 缺失。
- 本地直接用 `file://` 打开 HTML，浏览器经常会拦截 `fetch` 本地 JSON，必须起静态服务器。
- 前端加载链路必须具备：
  1. 基础 data 目录探测
  2. `jobs.index.json` + chunks 渐进加载
  3. `jobs.json` 整包回退

## 快速排查顺序
1. 检查前端根数据文件是否存在
- 必须同时检查：
  - `web/data/jobs.index.json`
  - `web/data/jobs.json`
  - `web/data/chunks/`

2. 若缺失，先重新导出

```powershell
python src/export_frontend_jobs.py
```

3. 确认本地运行方式正确
- 正确：

```powershell
cd web
python -m http.server 8080
```

- 然后访问 `http://localhost:8080`
- 错误方式：直接双击 `web/index.html`

4. 核对邀请码入口是否阻塞初始化
- 验证成功后，遮罩必须消失。
- `init()` 必须继续执行，`loadState` 应从“准备中”进入“定位数据目录 / 加载中 / 完成”。

5. 核对前端数据路径探测
- `assets/app.js` 可放在 `web/assets/`。
- 关键不在 JS 放置位置，而在 `app.js` 是否能正确探测到 `../data/` 或其它候选 data 目录。

## 常见症状与对应根因
- 症状：显示总数，但列表为空
  - 根因：`jobs.index.json` 成功了，但 chunks 失败；需要检查 chunk 请求或触发 `jobs.json` 回退。

- 症状：邀请码正确，但页面没有数据
  - 根因：常见是遮罩没有隐藏或初始化未继续；也可能是 `jobs.index.json` / `jobs.json` 缺失。

- 症状：页面提示“数据加载失败，请检查 data 目录是否可访问”
  - 根因：data 路径不对、根文件缺失、或本地是 `file://` 访问。

## 修复动作清单
- 先执行 `python src/export_frontend_jobs.py`，确保根索引和整包文件被重新生成。
- 用静态服务器启动 `web/`，不要直接打开 HTML。
- 若新增邀请码/弹窗逻辑，验证成功后必须移除遮罩并继续初始化。
- 修改加载逻辑时，必须保留 `jobs.json` 回退能力。

## 验收标准
- 本地 `http.server` 环境下，输入正确邀请码后可以看到岗位列表。
- `loadState` 会进入“完成”或“完成(兼容模式)”。
- 删除/屏蔽 `jobs.index.json` 后，页面仍可通过 `jobs.json` 打开。