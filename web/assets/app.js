const FALLBACK_KEYWORDS = [
  "python", "java", "c++", "go", "sql", "机器学习", "深度学习", "推荐", "数据分析", "后端", "前端", "产品"
];

const PAGE_SIZE = 36;
const CHUNK_FETCH_RETRIES = 1;
const LOADING_REFRESH_INTERVAL = 2;
const INVITE_STORAGE_KEY = "job-nav-invite-ok";
const DEFAULT_INVITE_CODES = ["AYOHI2026"];
const DATA_BASE_CANDIDATES = ["data", "./data", "/data", "web/data", "./web/data", "/web/data"];
const API_BASE_CANDIDATES = ["/api", "./api", "http://localhost:8000/api", "http://127.0.0.1:8000/api"];
const FETCH_TIMEOUT_MS = 25000;

function toText(value) {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.filter(Boolean).join("/");
  if (value === null || value === undefined) return "";
  return String(value);
}

const INVITE_CODES = (Array.isArray(window.__INVITE_CODES__) && window.__INVITE_CODES__.length
  ? window.__INVITE_CODES__
  : DEFAULT_INVITE_CODES)
  .map(code => toText(code).trim().toLowerCase())
  .filter(Boolean);

const state = {
  jobs: [],
  filtered: [],
  visibleCount: PAGE_SIZE,
  commonKeywords: FALLBACK_KEYWORDS,
  currentView: "list",
  analyticsDirty: true,
  dataBaseUrl: "",
  apiBaseUrl: "",
  chunks: [],
  chunkProgress: {
    loaded: 0,
    total: 0
  },
  filters: {
    company: "",
    project: "",
    category: "",
    city: "",
    title: "",
    keyword: ""
  }
};

function hasActiveFilters(filters) {
  return Boolean(filters.company || filters.project || filters.category || filters.city || filters.title || filters.keyword);
}

const els = {
  appShell: document.getElementById("appShell"),
  inviteGate: document.getElementById("inviteGate"),
  inviteCodeInput: document.getElementById("inviteCodeInput"),
  inviteSubmit: document.getElementById("inviteSubmit"),
  inviteError: document.getElementById("inviteError"),
  inviteSuccess: document.getElementById("inviteSuccess"),
  listViewBtn: document.getElementById("listViewBtn"),
  statsViewBtn: document.getElementById("statsViewBtn"),
  listView: document.getElementById("listView"),
  statsView: document.getElementById("statsView"),
  statTotal: document.getElementById("statTotal"),
  statFiltered: document.getElementById("statFiltered"),
  statShown: document.getElementById("statShown"),
  loadState: document.getElementById("loadState"),
  dataUpdated: document.getElementById("dataUpdated"),
  dataSources: document.getElementById("dataSources"),
  companyFilter: document.getElementById("companyFilter"),
  projectFilter: document.getElementById("projectFilter"),
  categoryFilter: document.getElementById("categoryFilter"),
  cityFilter: document.getElementById("cityFilter"),
  titleSearch: document.getElementById("titleSearch"),
  keywordSearch: document.getElementById("keywordSearch"),
  keywordChips: document.getElementById("keywordChips"),
  resetFilters: document.getElementById("resetFilters"),
  results: document.getElementById("results"),
  emptyState: document.getElementById("emptyState"),
  cardTpl: document.getElementById("jobCardTemplate"),
  loadMore: document.getElementById("loadMore"),
  metricJobs: document.getElementById("metricJobs"),
  metricCompanies: document.getElementById("metricCompanies"),
  metricProjects: document.getElementById("metricProjects"),
  metricCities: document.getElementById("metricCities"),
  chartCompany: document.getElementById("chartCompany"),
  chartCategory: document.getElementById("chartCategory"),
  chartCity: document.getElementById("chartCity"),
  chartKeyword: document.getElementById("chartKeyword")
};

function uniqSorted(values) {
  return [...new Set(values.map(toText).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-Hans-CN"));
}

function trimText(text, max = 180) {
  if (!text) return "暂无";
  if (text.length <= max) return text;
  return `${text.slice(0, max)}...`;
}

function debounce(fn, wait) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

function setLoadState(text) {
  if (els.loadState) {
    els.loadState.textContent = text;
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function uniqueArray(items) {
  return [...new Set(items)];
}

function scriptDerivedDataBaseUrl() {
  const script = document.querySelector('script[src*="assets/app.js"]');
  const src = script?.getAttribute("src") || "";
  if (!src) return "";

  try {
    const full = new URL(src, window.location.href);
    return new URL("../data/", full).toString();
  } catch (_err) {
    return "";
  }
}

function candidateBaseUrls() {
  const scriptBase = scriptDerivedDataBaseUrl();
  const candidates = DATA_BASE_CANDIDATES.map(base => new URL(`${base}/`, window.location.href).toString());
  if (scriptBase) {
    candidates.unshift(scriptBase);
  }
  if (state.dataBaseUrl) {
    candidates.unshift(state.dataBaseUrl);
  }
  return uniqueArray(candidates);
}

function buildDataUrl(relativePath, baseUrl = state.dataBaseUrl) {
  const base = baseUrl || new URL("data/", window.location.href).toString();
  return new URL(relativePath, base).toString();
}

function candidateApiBaseUrls() {
  const byLocation = new URL("api/", window.location.href).toString();
  const candidates = API_BASE_CANDIDATES.map(base => new URL(`${base}/`, window.location.href).toString());
  if (state.apiBaseUrl) {
    candidates.unshift(state.apiBaseUrl);
  }
  candidates.unshift(byLocation);
  return uniqueArray(candidates);
}

function buildApiUrl(relativePath, baseUrl = state.apiBaseUrl) {
  const base = baseUrl || new URL("api/", window.location.href).toString();
  return new URL(relativePath, base).toString();
}

async function fetchJsonFromUrl(url, timeoutMs = FETCH_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const resp = await fetch(url, { signal: controller.signal });
    if (!resp.ok) {
      throw new Error(`${url} => ${resp.status}`);
    }
    return await resp.json();
  } finally {
    clearTimeout(timer);
  }
}

async function fetchJsonWithFallback(relativePath, preferredBase = "") {
  let lastErr = null;
  const bases = preferredBase
    ? uniqueArray([preferredBase, ...candidateBaseUrls()])
    : candidateBaseUrls();

  for (const baseUrl of bases) {
    const url = buildDataUrl(relativePath, baseUrl);
    try {
      const payload = await fetchJsonFromUrl(url);
      state.dataBaseUrl = baseUrl;
      return payload;
    } catch (err) {
      lastErr = err;
    }
  }

  throw lastErr || new Error(`Failed to load ${relativePath}`);
}

async function fetchApiJsonWithFallback(relativePath) {
  let lastErr = null;
  const bases = candidateApiBaseUrls();
  for (const baseUrl of bases) {
    const url = buildApiUrl(relativePath, baseUrl);
    try {
      const payload = await fetchJsonFromUrl(url);
      state.apiBaseUrl = baseUrl;
      return payload;
    } catch (err) {
      lastErr = err;
    }
  }
  throw lastErr || new Error(`Failed to load API path: ${relativePath}`);
}

async function loadPayloadFromApi() {
  const payload = await fetchApiJsonWithFallback("jobs/payload");
  if (!payload || !Array.isArray(payload.jobs)) {
    throw new Error("Invalid API payload format");
  }
  return payload;
}

async function resolveDataBaseAndBootstrap() {
  const bases = candidateBaseUrls();
  let lastErr = null;

  for (const baseUrl of bases) {
    try {
      const indexPayload = await fetchJsonFromUrl(buildDataUrl("jobs.index.json", baseUrl), 15000);
      state.dataBaseUrl = baseUrl;
      return { baseUrl, indexPayload, jobsPayload: null };
    } catch (indexErr) {
      try {
        const jobsPayload = await fetchJsonFromUrl(buildDataUrl("jobs.json", baseUrl), 25000);
        state.dataBaseUrl = baseUrl;
        return { baseUrl, indexPayload: null, jobsPayload };
      } catch (jobsErr) {
        lastErr = jobsErr || indexErr;
      }
    }
  }

  throw lastErr || new Error("No usable data base path found");
}

function detectChunkConcurrency() {
  const isMobile = /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent || "");
  const net = navigator.connection?.effectiveType || "";
  if (net.includes("2g") || net === "slow-2g") return 1;
  if (isMobile || net.includes("3g")) return 2;
  return 3;
}

function detectInitialChunkCount(totalChunks) {
  const isMobile = /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent || "");
  if (totalChunks <= 1) return totalChunks;
  return isMobile ? 1 : Math.min(4, totalChunks);
}

function queueIdle(task) {
  if (typeof window.requestIdleCallback === "function") {
    window.requestIdleCallback(task, { timeout: 1200 });
    return;
  }
  setTimeout(task, 60);
}

function preprocessJobs(jobs) {
  return jobs.map(job => ({
    ...job,
    company: toText(job.company),
    recruit_type: toText(job.recruit_type),
    job_category: toText(job.job_category),
    work_city: toText(job.work_city),
    title: toText(job.title),
    responsibilities: toText(job.responsibilities),
    requirements: toText(job.requirements),
    bonus_points: toText(job.bonus_points),
    detail_url: toText(job.detail_url),
    search_blob: toText(job.search_blob)
  }));
}

function titleLower(job) {
  if (!job._titleLower) {
    job._titleLower = toText(job.title).toLowerCase();
  }
  return job._titleLower;
}

function textBlobLower(job) {
  if (!job._textBlobLower) {
    const source = job.search_blob || `${toText(job.responsibilities)} ${toText(job.requirements)} ${toText(job.bonus_points)}`;
    job._textBlobLower = source.toLowerCase();
  }
  return job._textBlobLower;
}

function computeFilteredJobs() {
  if (!hasActiveFilters(state.filters)) {
    return [...state.jobs];
  }
  return state.jobs.filter(job => matchesFilters(job, state.filters));
}

function populateSelect(selectEl, values, selectedValue = "") {
  if (!selectEl) return "";
  const first = selectEl.options[0];
  selectEl.innerHTML = "";
  if (first) selectEl.appendChild(first);

  values.forEach(v => {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    selectEl.appendChild(opt);
  });

  const next = values.includes(selectedValue) ? selectedValue : "";
  selectEl.value = next;
  return next;
}

function matchesFilters(job, filters, excludeKeys = new Set()) {
  if (!excludeKeys.has("company") && filters.company && job.company !== filters.company) return false;
  if (!excludeKeys.has("project") && filters.project && job.recruit_type !== filters.project) return false;
  if (!excludeKeys.has("category") && filters.category && job.job_category !== filters.category) return false;
  if (!excludeKeys.has("city") && filters.city && job.work_city !== filters.city) return false;
  if (!excludeKeys.has("title") && filters.title && !titleLower(job).includes(filters.title.toLowerCase())) return false;
  if (!excludeKeys.has("keyword") && filters.keyword && !textBlobLower(job).includes(filters.keyword.toLowerCase())) return false;
  return true;
}

function candidateRows(excludeKey) {
  return state.jobs.filter(job => matchesFilters(job, state.filters, new Set([excludeKey])));
}

function syncFilterOptions() {
  const companyRows = candidateRows("company");
  const projectRows = candidateRows("project");
  const categoryRows = candidateRows("category");
  const cityRows = candidateRows("city");

  state.filters.company = populateSelect(
    els.companyFilter,
    uniqSorted(companyRows.map(j => j.company)),
    state.filters.company
  );
  state.filters.project = populateSelect(
    els.projectFilter,
    uniqSorted(projectRows.map(j => j.recruit_type)),
    state.filters.project
  );
  state.filters.category = populateSelect(
    els.categoryFilter,
    uniqSorted(categoryRows.map(j => j.job_category)),
    state.filters.category
  );
  state.filters.city = populateSelect(
    els.cityFilter,
    uniqSorted(cityRows.map(j => j.work_city)),
    state.filters.city
  );
}

function renderKeywordChips(keywords) {
  if (!els.keywordChips) return;
  els.keywordChips.innerHTML = "";
  keywords.forEach(word => {
    const btn = document.createElement("button");
    btn.className = "chip";
    btn.type = "button";
    btn.textContent = word;
    btn.addEventListener("click", () => {
      if (els.keywordSearch) {
        els.keywordSearch.value = word;
      }
      state.filters.keyword = word;
      applyFilters();
    });
    els.keywordChips.appendChild(btn);
  });
}

function cardTags(job) {
  return [job.company, job.recruit_type, job.job_category, job.work_city].filter(Boolean);
}

function renderCards() {
  if (!els.results || !els.cardTpl || !els.emptyState || !els.loadMore) return;

  const toShow = state.filtered.slice(0, state.visibleCount);
  const fragment = document.createDocumentFragment();
  els.results.innerHTML = "";

  toShow.forEach(job => {
    const root = els.cardTpl.content.firstElementChild;
    if (!root) return;

    const node = root.cloneNode(true);
    node.querySelector(".job-title").textContent = job.title || "未命名岗位";
    node.querySelector(".meta-row").textContent = `${job.company || "未知公司"} | ${job.recruit_type || "未知项目"} | ${job.work_city || "未知城市"}`;

    const detailLink = node.querySelector(".detail-link");
    detailLink.href = job.detail_url || "#";
    if (!job.detail_url) {
      detailLink.textContent = "暂无链接";
      detailLink.removeAttribute("target");
    }

    const tagRow = node.querySelector(".tag-row");
    cardTags(job).forEach(tag => {
      const chip = document.createElement("span");
      chip.className = "tag";
      chip.textContent = tag;
      tagRow.appendChild(chip);
    });

    node.querySelector(".responsibilities").textContent = trimText(job.responsibilities, 220);
    node.querySelector(".requirements").textContent = trimText(job.requirements, 220);
    node.querySelector(".bonus").textContent = trimText(job.bonus_points, 160);

    fragment.appendChild(node);
  });

  els.results.appendChild(fragment);
  els.emptyState.classList.toggle("hidden", state.filtered.length > 0);
  updateResultCounters();

  const canLoadMore = state.filtered.length > state.visibleCount;
  els.loadMore.classList.toggle("hidden", !canLoadMore);
  if (canLoadMore) {
    els.loadMore.textContent = `加载更多 (${toShow.length}/${state.filtered.length})`;
  }
}

function topCounts(rows, key, limit = 6) {
  const counter = new Map();
  rows.forEach(row => {
    const name = row[key] || "Unknown";
    counter.set(name, (counter.get(name) || 0) + 1);
  });
  return [...counter.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([name, count]) => ({ name, count }));
}

function keywordHits(rows, keywords, limit = 6) {
  const hits = [];
  keywords.forEach(keyword => {
    let count = 0;
    rows.forEach(row => {
      if (textBlobLower(row).includes(keyword.toLowerCase())) {
        count += 1;
      }
    });
    if (count > 0) {
      hits.push({ name: keyword, count });
    }
  });
  return hits.sort((a, b) => b.count - a.count).slice(0, limit);
}

function renderBarList(el, items) {
  if (!el) return;
  el.innerHTML = "";
  if (!items.length) {
    el.innerHTML = "<p class='bar-label'>No data</p>";
    return;
  }

  const max = items[0].count || 1;
  const fragment = document.createDocumentFragment();
  items.forEach(item => {
    const row = document.createElement("div");
    row.className = "bar-row";
    const pct = Math.max(3, Math.round((item.count / max) * 100));
    row.innerHTML = `
      <span class="bar-label" title="${item.name}">${item.name}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
      <span class="bar-val">${item.count}</span>
    `;
    fragment.appendChild(row);
  });
  el.appendChild(fragment);
}

function updateAnalytics() {
  const rows = state.filtered;
  if (!els.metricJobs) return;

  els.metricJobs.textContent = String(rows.length);
  els.metricCompanies.textContent = String(new Set(rows.map(r => r.company).filter(Boolean)).size);
  els.metricProjects.textContent = String(new Set(rows.map(r => r.recruit_type).filter(Boolean)).size);
  els.metricCities.textContent = String(new Set(rows.map(r => r.work_city).filter(Boolean)).size);

  renderBarList(els.chartCompany, topCounts(rows, "company"));
  renderBarList(els.chartCategory, topCounts(rows, "job_category"));
  renderBarList(els.chartCity, topCounts(rows, "work_city"));
  renderBarList(els.chartKeyword, keywordHits(rows, state.commonKeywords));
  state.analyticsDirty = false;
}

function renderStatsIfNeeded(force = false) {
  if (state.currentView !== "stats") return;
  if (!force && !state.analyticsDirty) return;
  queueIdle(() => {
    if (state.currentView === "stats") {
      updateAnalytics();
    }
  });
}

function updateResultCounters() {
  if (els.statFiltered) {
    els.statFiltered.textContent = String(state.filtered.length);
  }
  if (els.statShown) {
    els.statShown.textContent = String(Math.min(state.filtered.length, state.visibleCount));
  }
}

function applyFilters() {
  syncFilterOptions();
  state.filtered = computeFilteredJobs();
  state.visibleCount = PAGE_SIZE;

  if (state.currentView === "list") {
    renderCards();
  } else {
    updateResultCounters();
  }

  state.analyticsDirty = true;
  renderStatsIfNeeded();
}

function refreshFromCurrentData() {
  syncFilterOptions();
  state.filtered = computeFilteredJobs();

  if (state.currentView === "list") {
    renderCards();
  } else {
    updateResultCounters();
  }

  state.analyticsDirty = true;
  renderStatsIfNeeded();
}

function refreshDuringLoading(force = false) {
  state.filtered = computeFilteredJobs();
  const shouldRender = force || state.chunkProgress.loaded === 1 || state.chunkProgress.loaded % (LOADING_REFRESH_INTERVAL + 2) === 0;
  if (shouldRender && state.currentView === "list") {
    renderCards();
  } else {
    updateResultCounters();
  }
  state.analyticsDirty = true;
}

async function loadChunkFile(filePath) {
  const payload = await fetchJsonWithFallback(filePath, state.dataBaseUrl);
  const jobs = preprocessJobs(payload.jobs || []);
  state.jobs.push(...jobs);
  state.chunkProgress.loaded += 1;
}

async function loadChunkWithRetry(filePath) {
  let lastErr = null;
  for (let attempt = 0; attempt <= CHUNK_FETCH_RETRIES; attempt++) {
    try {
      await loadChunkFile(filePath);
      return;
    } catch (err) {
      lastErr = err;
      if (attempt < CHUNK_FETCH_RETRIES) {
        await sleep(220 * (attempt + 1));
      }
    }
  }
  throw lastErr || new Error(`Chunk load failed: ${filePath}`);
}

function renderMeta(meta) {
  if (els.dataUpdated) {
    els.dataUpdated.textContent = meta?.generated_at || "-";
  }
  if (els.dataSources) {
    els.dataSources.textContent = (meta?.source_files || []).join("、") || "-";
  }
}

async function loadWholeDataFallback() {
  const payload = await fetchJsonWithFallback("jobs.json", state.dataBaseUrl);
  state.jobs = preprocessJobs(payload.jobs || []);

  const commonKeywords = payload.meta?.common_keywords?.length
    ? payload.meta.common_keywords
    : FALLBACK_KEYWORDS;

  state.commonKeywords = commonKeywords;
  if (els.statTotal) {
    els.statTotal.textContent = String(payload.meta?.total_jobs || state.jobs.length);
  }
  renderMeta(payload.meta || {});
  renderKeywordChips(commonKeywords);
  refreshFromCurrentData();
}

async function progressiveLoadChunks() {
  if (!state.chunks.length) {
    setLoadState("无数据分片");
    return;
  }

  const initialCount = detectInitialChunkCount(state.chunks.length);
  const firstBatch = state.chunks.slice(0, initialCount);
  const restBatch = state.chunks.slice(initialCount);
  let failed = 0;

  async function processQueue(items, concurrency) {
    const queue = [...items];

    async function worker() {
      while (queue.length) {
        const chunk = queue.shift();
        if (!chunk) return;

        try {
          await loadChunkWithRetry(chunk.file);
        } catch (err) {
          failed += 1;
          console.error("Chunk load error:", chunk.file, err);
        }

        setLoadState(`加载中 ${state.chunkProgress.loaded}/${state.chunkProgress.total}`);
        refreshDuringLoading();
        await sleep(0);
      }
    }

    await Promise.all(Array.from({ length: Math.max(1, concurrency) }, () => worker()));
  }

  await processQueue(firstBatch, detectChunkConcurrency());
  refreshDuringLoading(true);

  if (restBatch.length > 0) {
    setLoadState(`首屏已就绪，后台继续加载 ${state.chunkProgress.loaded}/${state.chunkProgress.total}`);
    await sleep(20);
    await processQueue(restBatch, detectChunkConcurrency());
  }

  if (state.jobs.length === 0 || failed >= state.chunkProgress.total) {
    await loadWholeDataFallback();
    setLoadState(`完成(分片失败，已切整包 ${state.jobs.length} 条)`);
    return;
  }

  if (failed > 0) {
    setLoadState(`部分完成 ${state.chunkProgress.loaded}/${state.chunkProgress.total}，失败 ${failed}`);
    refreshDuringLoading(true);
    refreshFromCurrentData();
    return;
  }

  refreshDuringLoading(true);
  refreshFromCurrentData();
  setLoadState(`完成 ${state.chunkProgress.loaded}/${state.chunkProgress.total}`);
}

function switchView(view) {
  state.currentView = view;

  if (!els.listView || !els.statsView || !els.listViewBtn || !els.statsViewBtn) {
    return;
  }

  const isList = view === "list";
  els.listView.classList.toggle("hidden", !isList);
  els.statsView.classList.toggle("hidden", isList);
  els.listViewBtn.classList.toggle("active", isList);
  els.statsViewBtn.classList.toggle("active", !isList);

  if (isList) {
    renderCards();
  } else {
    renderStatsIfNeeded(true);
  }
}

function isInviteCodeValid(rawCode) {
  const code = toText(rawCode).trim().toLowerCase();
  if (!code) return false;
  return INVITE_CODES.includes(code);
}

function bindInviteGate() {
  return new Promise(resolve => {
    let resolved = false;

    const finish = () => {
      if (resolved) return;
      resolved = true;
      resolve();
    };

    const gateEl = els.inviteGate || document.getElementById("inviteGate");

    const openApp = () => {
      try {
        if (gateEl) gateEl.classList.add("hidden");
        sessionStorage.setItem(INVITE_STORAGE_KEY, "1");
      } finally {
        finish();
      }
    };

    const showInviteError = () => {
      if (els.inviteSuccess) els.inviteSuccess.classList.add("hidden");
      if (els.inviteError) els.inviteError.classList.remove("hidden");
    };

    const showInviteSuccess = () => {
      if (els.inviteError) els.inviteError.classList.add("hidden");
      if (els.inviteSuccess) els.inviteSuccess.classList.remove("hidden");
    };

    if (!els.inviteCodeInput || !els.inviteSubmit) {
      openApp();
      return;
    }

    if (sessionStorage.getItem(INVITE_STORAGE_KEY) === "1") {
      openApp();
      return;
    }

    const submit = () => {
      const code = els.inviteCodeInput.value;
      if (isInviteCodeValid(code)) {
        showInviteSuccess();
        els.inviteCodeInput.disabled = true;
        els.inviteSubmit.disabled = true;
        setTimeout(openApp, 320);
        return;
      }
      showInviteError();
    };

    els.inviteSubmit.addEventListener("click", submit);
    els.inviteCodeInput.addEventListener("keydown", e => {
      if (e.key === "Enter") submit();
    });
  });
}

function bindViewSwitch() {
  if (!els.listViewBtn || !els.statsViewBtn) return;
  els.listViewBtn.addEventListener("click", () => switchView("list"));
  els.statsViewBtn.addEventListener("click", () => switchView("stats"));
}

function bindEvents() {
  bindViewSwitch();

  if (els.companyFilter) {
    els.companyFilter.addEventListener("change", e => {
      state.filters.company = e.target.value;
      applyFilters();
    });
  }

  if (els.projectFilter) {
    els.projectFilter.addEventListener("change", e => {
      state.filters.project = e.target.value;
      applyFilters();
    });
  }

  if (els.categoryFilter) {
    els.categoryFilter.addEventListener("change", e => {
      state.filters.category = e.target.value;
      applyFilters();
    });
  }

  if (els.cityFilter) {
    els.cityFilter.addEventListener("change", e => {
      state.filters.city = e.target.value;
      applyFilters();
    });
  }

  const debouncedApply = debounce(() => applyFilters(), 120);

  if (els.titleSearch) {
    els.titleSearch.addEventListener("input", e => {
      state.filters.title = e.target.value.trim();
      debouncedApply();
    });
  }

  if (els.keywordSearch) {
    els.keywordSearch.addEventListener("input", e => {
      state.filters.keyword = e.target.value.trim();
      debouncedApply();
    });
  }

  if (els.resetFilters) {
    els.resetFilters.addEventListener("click", () => {
      state.filters = {
        company: "",
        project: "",
        category: "",
        city: "",
        title: "",
        keyword: ""
      };

      if (els.companyFilter) els.companyFilter.value = "";
      if (els.projectFilter) els.projectFilter.value = "";
      if (els.categoryFilter) els.categoryFilter.value = "";
      if (els.cityFilter) els.cityFilter.value = "";
      if (els.titleSearch) els.titleSearch.value = "";
      if (els.keywordSearch) els.keywordSearch.value = "";
      applyFilters();
    });
  }

  if (els.loadMore) {
    els.loadMore.addEventListener("click", () => {
      state.visibleCount += PAGE_SIZE;
      renderCards();
    });
  }
}

async function initWithJobsPayload(payload) {
  state.jobs = preprocessJobs(payload.jobs || []);
  state.filtered = [...state.jobs];

  const commonKeywords = payload.meta?.common_keywords?.length
    ? payload.meta.common_keywords
    : FALLBACK_KEYWORDS;

  state.commonKeywords = commonKeywords;
  if (els.statTotal) {
    els.statTotal.textContent = String(payload.meta?.total_jobs || state.jobs.length);
  }

  renderMeta(payload.meta || {});
  renderKeywordChips(commonKeywords);
  bindEvents();
  switchView("list");
  refreshFromCurrentData();
  setLoadState("完成(兼容模式)");
}

async function init() {
  await bindInviteGate();

  try {
    setLoadState("连接数据库 API");
    const apiPayload = await loadPayloadFromApi();
    await initWithJobsPayload(apiPayload);
    setLoadState("完成(API)");
    return;
  } catch (_apiErr) {
    // Fall back to static files for compatibility.
  }

  try {
    setLoadState("定位数据目录");
    const bootstrap = await resolveDataBaseAndBootstrap();

    if (bootstrap.indexPayload) {
      const payload = bootstrap.indexPayload;
      state.chunks = payload.chunks || [];
      state.chunkProgress.total = state.chunks.length;
      renderMeta(payload.meta || {});

      const commonKeywords = payload.meta?.common_keywords?.length
        ? payload.meta.common_keywords
        : FALLBACK_KEYWORDS;

      state.commonKeywords = commonKeywords;
      if (els.statTotal) {
        els.statTotal.textContent = String(payload.meta?.total_jobs || 0);
      }

      renderKeywordChips(commonKeywords);
      bindEvents();
      switchView("list");
      await progressiveLoadChunks();
      return;
    }

    await initWithJobsPayload(bootstrap.jobsPayload || await fetchJsonWithFallback("jobs.json", bootstrap.baseUrl));
  } catch (err) {
    try {
      const payload = await fetchJsonWithFallback("jobs.json");
      await initWithJobsPayload(payload);
      return;
    } catch (_fatal) {
      if (els.results) {
        const apiHint = state.apiBaseUrl ? `API: ${state.apiBaseUrl}` : "API 未检测到可用地址";
        const dataHint = state.dataBaseUrl ? `Data: ${state.dataBaseUrl}` : "Data 未检测到可用目录";
        els.results.innerHTML = `<p class='empty'>数据加载失败，请检查数据库 API 或静态 data 目录。<br>${apiHint}<br>${dataHint}</p>`;
      }
      setLoadState("加载失败");
      console.error(err);
    }
  }
}

init();
