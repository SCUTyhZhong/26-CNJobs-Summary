const FALLBACK_KEYWORDS = [
  "python", "java", "c++", "go", "sql", "机器学习", "深度学习", "推荐", "数据分析", "后端", "前端", "产品"
];

const PAGE_SIZE_DESKTOP = 36;
const PAGE_SIZE_MOBILE = 10;
const INVITE_STORAGE_KEY = "job-nav-invite-ok";
const DEFAULT_INVITE_CODES = ["AYOHI2026"];
const FETCH_TIMEOUT_MS = 15000;
const CACHE_KEY = "job-nav-jobs-cache-v1";
const CACHE_MAX_AGE_MS = 1000 * 60 * 30;

function isMobileClient() {
  return /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent || "");
}

function toText(value) {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.filter(Boolean).join("/");
  if (value === null || value === undefined) return "";
  return String(value);
}

function trimText(text, max = 180) {
  if (!text) return "暂无";
  if (text.length <= max) return text;
  return `${text.slice(0, max)}...`;
}

function uniqSorted(values) {
  return [...new Set(values.map(toText).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-Hans-CN"));
}

function debounce(fn, wait) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

function hasActiveFilters(filters) {
  return Boolean(filters.company || filters.project || filters.category || filters.city || filters.title || filters.keyword);
}

const INVITE_CODES = (Array.isArray(window.__INVITE_CODES__) && window.__INVITE_CODES__.length
  ? window.__INVITE_CODES__
  : DEFAULT_INVITE_CODES)
  .map(code => toText(code).trim().toLowerCase())
  .filter(Boolean);

const state = {
  jobs: [],
  filtered: [],
  visibleCount: 0,
  pageSize: isMobileClient() ? PAGE_SIZE_MOBILE : PAGE_SIZE_DESKTOP,
  isMobile: isMobileClient(),
  commonKeywords: FALLBACK_KEYWORDS,
  dataBaseUrl: "",
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
  inviteGate: document.getElementById("inviteGate"),
  inviteCodeInput: document.getElementById("inviteCodeInput"),
  inviteSubmit: document.getElementById("inviteSubmit"),
  inviteError: document.getElementById("inviteError"),
  inviteSuccess: document.getElementById("inviteSuccess"),
  statTotal: document.getElementById("statTotal"),
  statFiltered: document.getElementById("statFiltered"),
  statShown: document.getElementById("statShown"),
  loadState: document.getElementById("loadState"),
  dataUpdated: document.getElementById("dataUpdated"),
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
  loadMore: document.getElementById("loadMore")
};

function setLoadState(text) {
  if (els.loadState) {
    els.loadState.textContent = text;
  }
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
  const byLocationData = new URL("data/", window.location.href).toString();
  const scriptBase = scriptDerivedDataBaseUrl();
  const bases = [];
  if (state.dataBaseUrl) bases.push(state.dataBaseUrl);
  if (scriptBase) bases.push(scriptBase);
  bases.push(byLocationData);
  return [...new Set(bases)];
}

function buildDataUrl(relativePath, baseUrl = state.dataBaseUrl) {
  const base = baseUrl || new URL("data/", window.location.href).toString();
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

async function fetchJobsPayloadStatic() {
  let lastErr = null;
  const bases = candidateBaseUrls();

  for (const baseUrl of bases) {
    try {
      const pathHint = new URL(baseUrl).pathname || baseUrl;
      setLoadState(`加载静态整包: ${pathHint}`);
      const payload = await fetchJsonFromUrl(buildDataUrl("jobs.json", baseUrl));
      state.dataBaseUrl = baseUrl;
      return payload;
    } catch (err) {
      lastErr = err;
    }
  }

  throw lastErr || new Error("jobs.json not found");
}

function preprocessJobs(jobs) {
  return jobs.map(job => {
    const normalized = {
      ...job,
      company: toText(job.company),
      recruit_type: toText(job.recruit_type),
      job_category: toText(job.job_category),
      job_function: toText(job.job_function),
      work_city: toText(job.work_city),
      title: toText(job.title),
      responsibilities: toText(job.responsibilities),
      requirements: toText(job.requirements),
      bonus_points: toText(job.bonus_points),
      detail_url: toText(job.detail_url),
      source_page: toText(job.source_page),
      publish_time: toText(job.publish_time),
      fetched_at: toText(job.fetched_at),
      tags: Array.isArray(job.tags) ? job.tags : toText(job.tags).split("/").filter(Boolean),
      work_cities: Array.isArray(job.work_cities) ? job.work_cities : toText(job.work_cities).split("/").filter(Boolean),
      search_blob: toText(job.search_blob)
    };

    normalized._metaRow = `${normalized.company || "未知公司"} | ${normalized.recruit_type || "未知项目"} | ${normalized.work_city || "未知城市"}`;
    normalized._responsibilitiesShort = trimText(normalized.responsibilities, 220);
    normalized._requirementsShort = trimText(normalized.requirements, 220);
    normalized._bonusShort = trimText(normalized.bonus_points, 160);
    normalized._tags = [normalized.company, normalized.recruit_type, normalized.job_category, normalized.work_city].filter(Boolean);
    return normalized;
  });
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

function matchesFilters(job, filters, excludeKeys = new Set()) {
  if (!excludeKeys.has("company") && filters.company && job.company !== filters.company) return false;
  if (!excludeKeys.has("project") && filters.project && job.recruit_type !== filters.project) return false;
  if (!excludeKeys.has("category") && filters.category && job.job_category !== filters.category) return false;
  if (!excludeKeys.has("city") && filters.city && job.work_city !== filters.city) return false;
  if (!excludeKeys.has("title") && filters.title && !titleLower(job).includes(filters.title.toLowerCase())) return false;
  if (!excludeKeys.has("keyword") && filters.keyword && !textBlobLower(job).includes(filters.keyword.toLowerCase())) return false;
  return true;
}

function computeFilteredJobs() {
  if (!hasActiveFilters(state.filters)) {
    return state.jobs;
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
  if (Array.isArray(job._tags)) {
    return state.isMobile ? job._tags.slice(0, 2) : job._tags;
  }
  const tags = [job.company, job.recruit_type, job.job_category, job.work_city].filter(Boolean);
  return state.isMobile ? tags.slice(0, 2) : tags;
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
    node.querySelector(".meta-row").textContent = job._metaRow;

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

    node.querySelector(".responsibilities").textContent = state.isMobile
      ? (toText(job.responsibilities) || "暂无")
      : (job._responsibilitiesShort || trimText(job.responsibilities, 220));

    node.querySelector(".requirements").textContent = state.isMobile
      ? (toText(job.requirements) || "暂无")
      : (job._requirementsShort || trimText(job.requirements, 220));

    node.querySelector(".bonus").textContent = state.isMobile
      ? (toText(job.bonus_points) || "暂无")
      : (job._bonusShort || trimText(job.bonus_points, 160));

    if (state.isMobile) {
      const fullInfo = document.createElement("div");
      fullInfo.className = "mobile-full-info";
      fullInfo.innerHTML = `
        <p><strong>岗位 ID：</strong>${toText(job.job_id) || "暂无"}</p>
        <p><strong>岗位类别：</strong>${toText(job.job_category) || "暂无"}</p>
        <p><strong>岗位职能：</strong>${toText(job.job_function) || "暂无"}</p>
        <p><strong>工作城市列表：</strong>${toText(job.work_cities) || "暂无"}</p>
        <p><strong>标签：</strong>${toText(job.tags) || "暂无"}</p>
        <p><strong>发布时间：</strong>${toText(job.publish_time) || "暂无"}</p>
        <p><strong>采集时间：</strong>${toText(job.fetched_at) || "暂无"}</p>
        <p><strong>来源页：</strong>${toText(job.source_page) || "暂无"}</p>
      `;
      node.appendChild(fullInfo);
    }

    fragment.appendChild(node);
  });

  els.results.appendChild(fragment);
  els.emptyState.classList.toggle("hidden", state.filtered.length > 0);

  if (els.statFiltered) {
    els.statFiltered.textContent = String(state.filtered.length);
  }
  if (els.statShown) {
    els.statShown.textContent = String(Math.min(state.filtered.length, state.visibleCount));
  }

  const canLoadMore = state.filtered.length > state.visibleCount;
  els.loadMore.classList.toggle("hidden", !canLoadMore);
  if (canLoadMore) {
    els.loadMore.textContent = `加载更多 (${toShow.length}/${state.filtered.length})`;
  }
}

function applyFilters() {
  syncFilterOptions();
  state.filtered = computeFilteredJobs();
  state.visibleCount = state.pageSize;
  renderCards();
}

function refreshFromCurrentData() {
  syncFilterOptions();
  state.filtered = computeFilteredJobs();
  renderCards();
}

function bindEvents() {
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

  const debouncedApply = debounce(() => applyFilters(), state.isMobile ? 200 : 120);

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
      state.visibleCount += state.pageSize;
      renderCards();
    });
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

function readPayloadCache() {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || !Array.isArray(parsed.jobs) || typeof parsed.cachedAt !== "number") return null;
    if (Date.now() - parsed.cachedAt > CACHE_MAX_AGE_MS) return null;
    return parsed;
  } catch (_err) {
    return null;
  }
}

function writePayloadCache(payload, sourceUrl) {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify({
      jobs: payload.jobs || [],
      meta: payload.meta || {},
      sourceUrl: sourceUrl || "",
      cachedAt: Date.now()
    }));
  } catch (_err) {
    // Ignore quota errors and continue normal flow.
  }
}

function renderPayload(payload, sourceLabel = "") {
  state.jobs = preprocessJobs(payload.jobs || []);
  state.filtered = [...state.jobs];
  state.visibleCount = state.pageSize;

  const commonKeywords = payload.meta?.common_keywords?.length
    ? payload.meta.common_keywords
    : FALLBACK_KEYWORDS;

  state.commonKeywords = commonKeywords;

  if (els.statTotal) {
    els.statTotal.textContent = String(payload.meta?.total_jobs || state.jobs.length);
  }
  if (els.dataUpdated) {
    els.dataUpdated.textContent = payload.meta?.generated_at || "-";
  }

  renderKeywordChips(commonKeywords);
  refreshFromCurrentData();

  const mode = state.isMobile ? "移动端静态极速" : "静态模式";
  setLoadState(sourceLabel ? `完成(${mode} | ${sourceLabel})` : `完成(${mode})`);
}

async function init() {
  await bindInviteGate();
  bindEvents();

  if (state.isMobile) {
    const cache = readPayloadCache();
    if (cache) {
      renderPayload(cache, "缓存命中");
      queueMicrotask(async () => {
        try {
          const fresh = await fetchJobsPayloadStatic();
          writePayloadCache(fresh, state.dataBaseUrl);
          renderPayload(fresh, "缓存已刷新");
        } catch (_err) {
          // Keep cached result if refresh fails.
        }
      });
      return;
    }
  }

  try {
    setLoadState("加载静态整包 jobs.json");
    const payload = await fetchJobsPayloadStatic();
    renderPayload(payload, "网络加载");
    if (state.isMobile) {
      writePayloadCache(payload, state.dataBaseUrl);
    }
  } catch (err) {
    if (els.results) {
      const dataHint = state.dataBaseUrl ? `Data: ${state.dataBaseUrl}` : "Data 未检测到可用目录";
      const protocolHint = window.location.protocol === "file:"
        ? "当前是 file:// 打开，浏览器会拦截本地 fetch，请改用本地静态服务器。"
        : "请检查 web/data/jobs.json 是否可访问。";
      els.results.innerHTML = `<p class='empty'>数据加载失败，请检查静态 data 目录。<br>${dataHint}<br>${protocolHint}</p>`;
    }
    setLoadState("加载失败");
    console.error(err);
  }
}

init();
