const state = {
  allJobs: [],
  filteredJobs: [],
  visibleCount: 0,
  pageSize: 30,
  chunkWarmCount: 2,
  loadState: "准备中",
  dataRoot: "",
  useFallback: false,
  filters: {
    company: "",
    project: "",
    category: "",
    city: "",
    query: "",
    sortBy: "publish_time",
  },
};

const els = {
  overlay: document.getElementById("inviteOverlay"),
  inviteForm: document.getElementById("inviteForm"),
  inviteInput: document.getElementById("inviteInput"),
  inviteError: document.getElementById("inviteError"),
  loadStateText: document.getElementById("loadStateText"),
  updatedAtText: document.getElementById("updatedAtText"),
  resultCountText: document.getElementById("resultCountText"),
  statusMessage: document.getElementById("statusMessage"),
  searchInput: document.getElementById("searchInput"),
  filterCompany: document.getElementById("filterCompany"),
  filterProject: document.getElementById("filterProject"),
  filterCategory: document.getElementById("filterCategory"),
  filterCity: document.getElementById("filterCity"),
  sortBy: document.getElementById("sortBy"),
  clearFilters: document.getElementById("clearFilters"),
  listContainer: document.getElementById("listContainer"),
  loadMoreBtn: document.getElementById("loadMoreBtn"),
  cardTpl: document.getElementById("jobCardTpl"),
  overviewEntry: document.getElementById("overviewEntry"),
};

function setLoadState(nextState, message) {
  state.loadState = nextState;
  els.loadStateText.textContent = nextState;
  if (message) {
    els.statusMessage.textContent = message;
  }
}

function getInviteCodes() {
  const codes = Array.isArray(window.JOB_NAV_INVITE_CODES) ? window.JOB_NAV_INVITE_CODES : [];
  return codes.map((code) => String(code).trim()).filter(Boolean);
}

function setupInviteGate(onPass) {
  const codes = getInviteCodes();
  if (!codes.length) {
    els.overlay.classList.add("is-hidden");
    els.overlay.setAttribute("aria-hidden", "true");
    onPass();
    return;
  }

  els.inviteForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const value = els.inviteInput.value.trim();
    if (codes.includes(value)) {
      els.inviteError.textContent = "";
      els.overlay.classList.add("is-hidden");
      els.overlay.setAttribute("aria-hidden", "true");
      onPass();
      return;
    }
    els.inviteError.textContent = "邀请码错误，请重试。";
  });
}

async function tryFetchJson(url) {
  const response = await fetch(url, { cache: "no-cache" });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status} ${url}`);
  }
  return response.json();
}

function resolveDataCandidates() {
  const fromModule = new URL("../data/", import.meta.url).toString();
  const fromCurrent = new URL("data/", window.location.href).toString();
  const fromRoot = new URL("/data/", window.location.origin).toString();
  return [...new Set([fromModule, fromCurrent, fromRoot])];
}

async function locateDataRoot() {
  setLoadState("定位数据目录", "正在定位数据目录...");
  const candidates = resolveDataCandidates();

  for (const base of candidates) {
    try {
      await tryFetchJson(new URL("jobs.index.json", base).toString());
      return base;
    } catch {
      // Continue probing.
    }
  }

  for (const base of candidates) {
    try {
      await tryFetchJson(new URL("jobs.json", base).toString());
      return base;
    } catch {
      // Continue probing.
    }
  }

  throw new Error("未找到可用数据目录，请确认 web/data 下存在 jobs.index.json 或 jobs.json");
}

function normalizeJob(job) {
  const workCities = Array.isArray(job.work_cities)
    ? job.work_cities
    : String(job.work_cities || "")
        .split("|")
        .map((x) => x.trim())
        .filter(Boolean);
  const tags = Array.isArray(job.tags)
    ? job.tags
    : String(job.tags || "")
        .split("|")
        .map((x) => x.trim())
        .filter(Boolean);

  const searchBlob = String(
    job.search_blob || `${job.title || ""} ${job.responsibilities || ""} ${job.requirements || ""} ${job.bonus_points || ""}`
  );

  return {
    ...job,
    work_cities: workCities,
    tags,
    search_blob: searchBlob,
    search_blob_lower: String(job.search_blob_lower || searchBlob).toLowerCase(),
    project: String(job.job_function || job.recruit_type || "").trim(),
  };
}

function pickDetailText(value) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text || "暂无信息";
}

function scoreByRelevance(job, q) {
  if (!q) return 0;
  const text = job.search_blob_lower;
  if (!text) return 0;

  let score = 0;
  let start = 0;
  while (true) {
    const found = text.indexOf(q, start);
    if (found === -1) break;
    score += 1;
    start = found + q.length;
  }
  return score;
}

function parseTimeOrZero(value) {
  const ms = Date.parse(String(value || ""));
  return Number.isFinite(ms) ? ms : 0;
}

function updateStatusText(message) {
  els.statusMessage.textContent = message;
}

function syncMetrics() {
  els.resultCountText.textContent = String(state.filteredJobs.length);
}

function updateLoadMoreButton() {
  const hasMore = state.visibleCount < state.filteredJobs.length;
  els.loadMoreBtn.disabled = !hasMore;
  els.loadMoreBtn.textContent = hasMore ? "加载更多" : "已加载全部";
}

function mergeJobsIntoState(jobs) {
  if (!jobs.length) return;
  const dedup = new Map();
  for (const job of state.allJobs.concat(jobs)) {
    const key = `${job.company || ""}@@${job.job_id || job.detail_url || ""}`;
    dedup.set(key, job);
  }
  state.allJobs = [...dedup.values()];
}

function renderList(reset = false) {
  if (reset) {
    els.listContainer.innerHTML = "";
    state.visibleCount = Math.min(state.pageSize, state.filteredJobs.length);
  }

  const fragment = document.createDocumentFragment();
  const jobsToRender = state.filteredJobs.slice(0, state.visibleCount);

  for (const job of jobsToRender) {
    const node = els.cardTpl.content.firstElementChild.cloneNode(true);
    const titleNode = node.querySelector(".title");
    const linkNode = node.querySelector(".detail-link");
    const companyNode = node.querySelector('[data-field="company"]');
    const projectNode = node.querySelector('[data-field="project"]');
    const categoryNode = node.querySelector('[data-field="category"]');
    const cityNode = node.querySelector('[data-field="city"]');
    const publishTimeNode = node.querySelector('[data-field="publishTime"]');
    const responsibilitiesNode = node.querySelector('[data-field="responsibilities"]');
    const requirementsNode = node.querySelector('[data-field="requirements"]');
    const bonusPointsNode = node.querySelector('[data-field="bonusPoints"]');

    titleNode.textContent = job.title || "未命名岗位";
    if (job.detail_url) {
      linkNode.href = job.detail_url;
    } else {
      linkNode.removeAttribute("href");
      linkNode.textContent = "无详情链接";
      linkNode.style.pointerEvents = "none";
      linkNode.style.opacity = "0.6";
    }

    companyNode.textContent = job.company || "未知公司";
    projectNode.textContent = job.project || "未知项目";
    categoryNode.textContent = job.job_category || "未知类别";
    cityNode.textContent = job.work_city || (Array.isArray(job.work_cities) ? job.work_cities.join("/") : "未知城市");
    publishTimeNode.textContent = job.publish_time || "时间未知";
    responsibilitiesNode.textContent = pickDetailText(job.responsibilities);
    requirementsNode.textContent = pickDetailText(job.requirements);
    bonusPointsNode.textContent = pickDetailText(job.bonus_points);

    fragment.appendChild(node);
  }

  els.listContainer.innerHTML = "";
  els.listContainer.appendChild(fragment);
  updateLoadMoreButton();
}

function extractOptions(jobs, key, fallback = "") {
  const set = new Set();
  for (const job of jobs) {
    const value = String(job[key] || fallback).trim();
    if (value) set.add(value);
  }
  return [...set].sort((a, b) => a.localeCompare(b, "zh-CN"));
}

function extractCities(jobs) {
  const set = new Set();
  for (const job of jobs) {
    if (job.work_city) set.add(String(job.work_city).trim());
    if (Array.isArray(job.work_cities)) {
      for (const city of job.work_cities) {
        if (city) set.add(String(city).trim());
      }
    }
  }
  return [...set].sort((a, b) => a.localeCompare(b, "zh-CN"));
}

function setSelectOptions(selectEl, options, placeholder) {
  const currentValue = selectEl.value;
  const html = [`<option value="">${placeholder}</option>`]
    .concat(options.map((option) => `<option value="${option}">${option}</option>`))
    .join("");
  selectEl.innerHTML = html;
  if (options.includes(currentValue)) {
    selectEl.value = currentValue;
  }
}

function refreshFilterOptions() {
  const byCompany = state.allJobs.filter((job) => !state.filters.company || job.company === state.filters.company);
  const byProject = byCompany.filter((job) => !state.filters.project || job.project === state.filters.project);
  const byCategory = byProject.filter((job) => !state.filters.category || job.job_category === state.filters.category);

  setSelectOptions(els.filterCompany, extractOptions(state.allJobs, "company"), "全部公司");
  setSelectOptions(els.filterProject, extractOptions(byCompany, "project"), "全部项目");
  setSelectOptions(els.filterCategory, extractOptions(byProject, "job_category"), "全部类别");
  setSelectOptions(els.filterCity, extractCities(byCategory), "全部城市");
}

function applyFilters() {
  const query = state.filters.query.trim().toLowerCase();

  const filtered = state.allJobs.filter((job) => {
    if (state.filters.company && job.company !== state.filters.company) return false;
    if (state.filters.project && job.project !== state.filters.project) return false;
    if (state.filters.category && job.job_category !== state.filters.category) return false;

    const cities = new Set([job.work_city, ...(job.work_cities || [])].filter(Boolean));
    if (state.filters.city && !cities.has(state.filters.city)) return false;

    if (query && !job.search_blob_lower.includes(query)) return false;
    return true;
  });

  if (state.filters.sortBy === "relevance") {
    filtered.sort((a, b) => scoreByRelevance(b, query) - scoreByRelevance(a, query));
  } else {
    filtered.sort((a, b) => parseTimeOrZero(b.publish_time) - parseTimeOrZero(a.publish_time));
  }

  state.filteredJobs = filtered;
  syncMetrics();
  renderList(true);

  if (!filtered.length) {
    updateStatusText("当前筛选条件下没有匹配岗位，请调整筛选或搜索词。");
  } else {
    updateStatusText(`已加载 ${state.allJobs.length} 条岗位，当前匹配 ${filtered.length} 条。`);
  }
}

function debounce(fn, wait) {
  let timer = null;
  return (...args) => {
    if (timer) window.clearTimeout(timer);
    timer = window.setTimeout(() => fn(...args), wait);
  };
}

function bindEvents() {
  const debouncedSearch = debounce((value) => {
    state.filters.query = value;
    applyFilters();
  }, 220);

  els.searchInput.addEventListener("input", (event) => {
    debouncedSearch(event.target.value || "");
  });

  els.filterCompany.addEventListener("change", (event) => {
    state.filters.company = event.target.value;
    state.filters.project = "";
    state.filters.category = "";
    state.filters.city = "";
    refreshFilterOptions();
    applyFilters();
  });

  els.filterProject.addEventListener("change", (event) => {
    state.filters.project = event.target.value;
    state.filters.category = "";
    state.filters.city = "";
    refreshFilterOptions();
    applyFilters();
  });

  els.filterCategory.addEventListener("change", (event) => {
    state.filters.category = event.target.value;
    state.filters.city = "";
    refreshFilterOptions();
    applyFilters();
  });

  els.filterCity.addEventListener("change", (event) => {
    state.filters.city = event.target.value;
    applyFilters();
  });

  els.sortBy.addEventListener("change", (event) => {
    state.filters.sortBy = event.target.value;
    applyFilters();
  });

  els.clearFilters.addEventListener("click", () => {
    state.filters = {
      ...state.filters,
      company: "",
      project: "",
      category: "",
      city: "",
      query: "",
      sortBy: "publish_time",
    };
    els.searchInput.value = "";
    els.sortBy.value = "publish_time";
    refreshFilterOptions();
    applyFilters();
  });

  els.loadMoreBtn.addEventListener("click", () => {
    state.visibleCount = Math.min(state.visibleCount + state.pageSize, state.filteredJobs.length);
    renderList(false);
  });

  els.overviewEntry.addEventListener("click", () => {
    window.alert("数据概览功能已预留入口，后续版本上线。当前先专注岗位检索与筛选。");
  });
}

async function loadWithIndex(base) {
  const index = await tryFetchJson(new URL("jobs.index.json", base).toString());
  const chunks = Array.isArray(index.chunks) ? index.chunks : [];
  const files = chunks.map((item) => item.file).filter(Boolean);

  const warm = files.slice(0, state.chunkWarmCount);
  const rest = files.slice(state.chunkWarmCount);
  state.allJobs = [];
  els.updatedAtText.textContent = index.generated_at || "-";

  for (let i = 0; i < warm.length; i++) {
    const name = warm[i];
    const records = await tryFetchJson(new URL(`chunks/${name}`, base).toString()).catch(() => []);
    mergeJobsIntoState(records.map(normalizeJob));
    refreshFilterOptions();
    applyFilters();
    setLoadState("加载中", `首批分片加载中... ${i + 1}/${warm.length}（${state.allJobs.length} 条）`);
  }

  setLoadState("加载中", `首批分片已加载 (${state.allJobs.length} 条)，正在补齐剩余数据...`);

  if (rest.length) {
    loadRestChunksBatched(base, rest);
  } else {
    setLoadState("完成", `分片加载完成，共 ${state.allJobs.length} 条岗位。`);
  }
}

// Load remaining chunks in small batches to respect mobile browser concurrency limits.
// Each batch is awaited before the next starts, so at most BATCH_SIZE requests run in parallel.
async function loadRestChunksBatched(base, files) {
  const BATCH_SIZE = 2;
  let failedCount = 0;

  for (let i = 0; i < files.length; i += BATCH_SIZE) {
    const batch = files.slice(i, i + BATCH_SIZE);
    const results = await Promise.all(
      batch.map((name) =>
        tryFetchJson(new URL(`chunks/${name}`, base).toString()).catch(() => {
          failedCount++;
          return [];
        })
      )
    );

    const newJobs = results.flat().map(normalizeJob);
    if (!newJobs.length) continue;
    mergeJobsIntoState(newJobs);
    refreshFilterOptions();
    applyFilters();
    setLoadState(
      "加载中",
      `正在补齐数据... 已加载 ${state.allJobs.length} 条（${i + batch.length}/${files.length} 批次完成）`
    );
  }

  if (failedCount > 0) {
    setLoadState("完成", `加载完成，共 ${state.allJobs.length} 条岗位（${failedCount} 个分片加载失败已跳过）。`);
  } else {
    setLoadState("完成", `已加载全部分片，共 ${state.allJobs.length} 条岗位。`);
  }
}

async function loadWithFallback(base, reason = "") {
  const jobs = await tryFetchJson(new URL("jobs.json", base).toString());
  state.allJobs = Array.isArray(jobs) ? jobs.map(normalizeJob) : [];
  state.useFallback = true;
  els.updatedAtText.textContent = "兼容模式";
  setLoadState("兼容模式", `已切换 jobs.json 回退加载。${reason}`.trim());
}

async function initDataFlow() {
  try {
    state.dataRoot = await locateDataRoot();
    setLoadState("加载中", "正在加载岗位数据...");

    try {
      await loadWithIndex(state.dataRoot);
    } catch (indexError) {
      await loadWithFallback(state.dataRoot, "index/chunks 不可用。");
      console.warn("index/chunks load failed:", indexError);
    }

    refreshFilterOptions();
    applyFilters();

    if (!state.useFallback && state.loadState !== "完成") {
      setLoadState("完成", `加载完成，共 ${state.allJobs.length} 条岗位。`);
    }
  } catch (error) {
    setLoadState("失败", "数据加载失败，请检查 web/data 目录是否可访问。");
    updateStatusText(String(error.message || error));
    console.error(error);
  }
}

function start() {
  bindEvents();
  setupInviteGate(async () => {
    await initDataFlow();
  });
}

start();
