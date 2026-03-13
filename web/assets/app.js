const FALLBACK_KEYWORDS = [
  "python", "java", "c++", "go", "sql", "机器学习", "深度学习", "推荐", "数据分析", "后端", "前端", "产品"
];

const PAGE_SIZE = 36;

const state = {
  jobs: [],
  filtered: [],
  visibleCount: PAGE_SIZE,
  commonKeywords: FALLBACK_KEYWORDS,
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

const els = {
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
  return [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-Hans-CN"));
}

function trimText(text, max = 180) {
  if (!text) return "暂无";
  if (text.length <= max) return text;
  return `${text.slice(0, max)}...`;
}

function contains(haystack, needle) {
  return (haystack || "").toLowerCase().includes((needle || "").toLowerCase());
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

function preprocessJobs(jobs) {
  return jobs.map(job => ({
    ...job,
    _titleLower: (job.title || "").toLowerCase(),
    _textBlobLower: `${job.responsibilities || ""} ${job.requirements || ""} ${job.bonus_points || ""}`.toLowerCase()
  }));
}

function populateSelect(selectEl, values, selectedValue = "") {
  const first = selectEl.options[0];
  selectEl.innerHTML = "";
  selectEl.appendChild(first);

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
  if (!excludeKeys.has("title") && filters.title && !job._titleLower.includes(filters.title.toLowerCase())) return false;
  if (!excludeKeys.has("keyword") && filters.keyword && !job._textBlobLower.includes(filters.keyword.toLowerCase())) return false;
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
  els.keywordChips.innerHTML = "";
  keywords.forEach(word => {
    const btn = document.createElement("button");
    btn.className = "chip";
    btn.type = "button";
    btn.textContent = word;
    btn.addEventListener("click", () => {
      els.keywordSearch.value = word;
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
  const toShow = state.filtered.slice(0, state.visibleCount);
  const fragment = document.createDocumentFragment();
  els.results.innerHTML = "";
  toShow.forEach(job => {
    const node = els.cardTpl.content.firstElementChild.cloneNode(true);

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
  els.statFiltered.textContent = String(state.filtered.length);
  els.statShown.textContent = String(toShow.length);

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
      if (row._textBlobLower.includes(keyword.toLowerCase())) {
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
  els.metricJobs.textContent = String(rows.length);
  els.metricCompanies.textContent = String(new Set(rows.map(r => r.company).filter(Boolean)).size);
  els.metricProjects.textContent = String(new Set(rows.map(r => r.recruit_type).filter(Boolean)).size);
  els.metricCities.textContent = String(new Set(rows.map(r => r.work_city).filter(Boolean)).size);

  renderBarList(els.chartCompany, topCounts(rows, "company"));
  renderBarList(els.chartCategory, topCounts(rows, "job_category"));
  renderBarList(els.chartCity, topCounts(rows, "work_city"));
  renderBarList(els.chartKeyword, keywordHits(rows, state.commonKeywords));
}

function applyFilters() {
  syncFilterOptions();
  state.filtered = state.jobs.filter(job => matchesFilters(job, state.filters));

  state.visibleCount = PAGE_SIZE;
  updateAnalytics();
  renderCards();
}

function refreshFromCurrentData() {
  syncFilterOptions();
  state.filtered = state.jobs.filter(job => matchesFilters(job, state.filters));
  updateAnalytics();
  renderCards();
}

async function loadChunkFile(filePath) {
  const resp = await fetch(`data/${filePath}`, { cache: "no-store" });
  if (!resp.ok) {
    throw new Error(`Chunk load failed: ${filePath}`);
  }
  const payload = await resp.json();
  const jobs = preprocessJobs(payload.jobs || []);
  state.jobs.push(...jobs);
  state.chunkProgress.loaded += 1;
  setLoadState(`加载中 ${state.chunkProgress.loaded}/${state.chunkProgress.total}`);
  refreshFromCurrentData();
}

function renderMeta(meta) {
  if (els.dataUpdated) {
    els.dataUpdated.textContent = meta?.generated_at || "-";
  }
  if (els.dataSources) {
    els.dataSources.textContent = (meta?.source_files || []).join("、") || "-";
  }
}

async function progressiveLoadChunks() {
  if (!state.chunks.length) {
    setLoadState("无数据分片");
    return;
  }

  await loadChunkFile(state.chunks[0].file);

  for (let i = 1; i < state.chunks.length; i++) {
    const file = state.chunks[i].file;
    await loadChunkFile(file);
    await new Promise(resolve => setTimeout(resolve, 0));
  }

  setLoadState(`完成 ${state.chunkProgress.loaded}/${state.chunkProgress.total}`);
}

function bindEvents() {
  els.companyFilter.addEventListener("change", e => {
    state.filters.company = e.target.value;
    applyFilters();
  });

  els.projectFilter.addEventListener("change", e => {
    state.filters.project = e.target.value;
    applyFilters();
  });

  els.categoryFilter.addEventListener("change", e => {
    state.filters.category = e.target.value;
    applyFilters();
  });

  els.cityFilter.addEventListener("change", e => {
    state.filters.city = e.target.value;
    applyFilters();
  });

  const debouncedApply = debounce(() => applyFilters(), 120);

  els.titleSearch.addEventListener("input", e => {
    state.filters.title = e.target.value.trim();
    debouncedApply();
  });

  els.keywordSearch.addEventListener("input", e => {
    state.filters.keyword = e.target.value.trim();
    debouncedApply();
  });

  els.resetFilters.addEventListener("click", () => {
    state.filters = {
      company: "",
      project: "",
      category: "",
      city: "",
      title: "",
      keyword: ""
    };

    els.companyFilter.value = "";
    els.projectFilter.value = "";
    els.categoryFilter.value = "";
    els.cityFilter.value = "";
    els.titleSearch.value = "";
    els.keywordSearch.value = "";
    applyFilters();
  });

  els.loadMore.addEventListener("click", () => {
    state.visibleCount += PAGE_SIZE;
    renderCards();
  });
}

async function init() {
  try {
    setLoadState("读取索引");
    let payload;
    try {
      const indexResp = await fetch("data/jobs.index.json", { cache: "no-store" });
      if (!indexResp.ok) {
        throw new Error("missing jobs.index.json");
      }
      payload = await indexResp.json();
      state.chunks = payload.chunks || [];
      state.chunkProgress.total = state.chunks.length;
      renderMeta(payload.meta || {});

      const commonKeywords = payload.meta?.common_keywords?.length
        ? payload.meta.common_keywords
        : FALLBACK_KEYWORDS;
      state.commonKeywords = commonKeywords;

      els.statTotal.textContent = String(payload.meta?.total_jobs || 0);
      renderKeywordChips(commonKeywords);
      bindEvents();
      await progressiveLoadChunks();
    } catch (_chunkErr) {
      const resp = await fetch("data/jobs.json", { cache: "no-store" });
      payload = await resp.json();
      state.jobs = preprocessJobs(payload.jobs || []);
      state.filtered = [...state.jobs];

      const commonKeywords = payload.meta?.common_keywords?.length
        ? payload.meta.common_keywords
        : FALLBACK_KEYWORDS;
      state.commonKeywords = commonKeywords;

      els.statTotal.textContent = String(state.jobs.length);
      renderMeta(payload.meta || {});
      renderKeywordChips(commonKeywords);
      bindEvents();
      refreshFromCurrentData();
      setLoadState("完成(兼容模式)");
    }
  } catch (err) {
    els.results.innerHTML = "<p class='empty'>数据加载失败，请先运行导出脚本并使用本地服务器打开页面。</p>";
    setLoadState("加载失败");
    console.error(err);
  }
}

init();
