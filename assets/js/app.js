(() => {
  'use strict';

  const state = {
    countries: [],
    settings: null,
    manifest: null,
    countryCode: 'US',
    date: null,
    category: 'All',
    dayData: null,
    visibleCount: 12,
    requestId: 0,
  };

  const elements = {};
  const STATUS_LABELS = {
    current: 'Current',
    partial: 'Partially Updated',
    retained: 'Retained From Previous Update',
    empty: 'No Articles Retrieved',
    failed: 'Data Generation Failed',
    missing: 'Archive File Missing',
    unavailable: 'Source Unavailable',
    sample: 'Sample Preview',
  };

  document.addEventListener('DOMContentLoaded', init);

  async function init() {
    cacheElements();
    bindEvents();
    try {
      const [countries, settings, manifest] = await Promise.all([
        fetchJson('config/countries.json'),
        fetchJson('config/settings.json'),
        fetchManifest(),
      ]);
      state.countries = [...countries].sort((a, b) => a.order - b.order);
      state.settings = settings;
      state.manifest = manifest;
      state.visibleCount = settings.initialStoryCount || 12;
      restoreInitialState();
      renderCountryTabs();
      renderCategoryFilters();
      renderGlobalStatus();
      await selectView({ updateHistory: false });
    } catch (error) {
      console.error(error);
      showFatalState('News Data Unavailable', 'The generated manifest or configuration files could not be loaded.');
    }
  }

  function cacheElements() {
    const ids = [
      'country-tabs', 'date-tabs', 'category-filters', 'lead-story', 'story-list',
      'loading-state', 'empty-state', 'empty-title', 'empty-message', 'load-more',
      'sample-banner', 'data-notice', 'result-count', 'selected-date-label',
      'edition-heading', 'edition-summary', 'global-status', 'global-status-dot',
      'last-updated', 'day-status-badge', 'metric-articles', 'metric-publishers',
      'metric-sources', 'metric-timezone', 'status-detail', 'source-health-list',
      'live-region'
    ];
    ids.forEach((id) => { elements[toCamel(id)] = document.getElementById(id); });
  }

  function bindEvents() {
    elements.loadMore.addEventListener('click', () => {
      state.visibleCount += state.settings.loadMoreCount || 12;
      renderStories();
      announce(`Showing ${Math.min(state.visibleCount, filteredArticles().length)} stories.`);
    });
    window.addEventListener('popstate', async () => {
      restoreStateFromUrl();
      renderCountryTabs();
      renderCategoryFilters();
      await selectView({ updateHistory: false });
    });
  }

  function restoreInitialState() {
    const params = new URLSearchParams(location.search);
    const urlCountry = normalizeCountry(params.get('country'));
    const savedCountry = safeStorageGet('worldline-country');
    state.countryCode = urlCountry || normalizeCountry(savedCountry) || state.settings.defaultCountry || 'US';
    const country = currentCountry();
    const dates = getSevenDateKeys(country.timeZone);
    const requestedDate = params.get('date');
    state.date = dates.includes(requestedDate) ? requestedDate : dates[0];
    state.category = normalizeCategory(params.get('category'));
    writeUrl('replace');
  }

  function restoreStateFromUrl() {
    const params = new URLSearchParams(location.search);
    state.countryCode = normalizeCountry(params.get('country')) || state.settings.defaultCountry || 'US';
    const dates = getSevenDateKeys(currentCountry().timeZone);
    state.date = dates.includes(params.get('date')) ? params.get('date') : dates[0];
    state.category = normalizeCategory(params.get('category'));
    state.visibleCount = state.settings.initialStoryCount || 12;
  }

  function normalizeCountry(value) {
    if (!value) return null;
    const code = String(value).toUpperCase();
    return state.countries.some((country) => country.code === code) ? code : null;
  }

  function normalizeCategory(value) {
    if (!state.settings) return 'All';
    if (!value) return 'All';
    const slug = String(value).toLowerCase();
    return state.settings.categories.find((item) => categorySlug(item) === slug) || 'All';
  }

  function currentCountry() {
    return state.countries.find((country) => country.code === state.countryCode) || state.countries[0];
  }

  function renderCountryTabs() {
    const fragment = document.createDocumentFragment();
    state.countries.forEach((country) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'country-tab';
      button.setAttribute('role', 'tab');
      button.setAttribute('aria-selected', String(country.code === state.countryCode));
      button.dataset.country = country.code;
      button.addEventListener('click', () => changeCountry(country.code));
      button.addEventListener('keydown', (event) => handleTabArrow(event, '.country-tab'));

      const flag = document.createElement('span');
      flag.className = 'flag';
      flag.setAttribute('aria-hidden', 'true');
      flag.textContent = country.flag;
      const label = document.createElement('span');
      label.textContent = country.name;
      button.setAttribute('aria-label', `${country.name} edition`);
      button.append(flag, label);

      const countryManifest = state.manifest?.countries?.[country.code];
      if (countryManifest?.dates && Object.values(countryManifest.dates).some((entry) => entry.articleCount > 0)) {
        const availability = document.createElement('span');
        availability.className = 'availability';
        availability.setAttribute('aria-label', 'Archive available');
        button.append(availability);
      }
      fragment.append(button);
    });
    elements.countryTabs.replaceChildren(fragment);
  }

  async function changeCountry(countryCode) {
    if (countryCode === state.countryCode) return;
    state.countryCode = countryCode;
    safeStorageSet('worldline-country', countryCode);
    const dates = getSevenDateKeys(currentCountry().timeZone);
    if (!dates.includes(state.date)) state.date = dates[0];
    state.category = 'All';
    state.visibleCount = state.settings.initialStoryCount || 12;
    renderCountryTabs();
    renderCategoryFilters();
    await selectView({ updateHistory: true });
  }

  function renderDateTabs() {
    const country = currentCountry();
    const keys = getSevenDateKeys(country.timeZone);
    const fragment = document.createDocumentFragment();
    keys.forEach((dateKey, index) => {
      const entry = state.manifest?.countries?.[country.code]?.dates?.[dateKey];
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'date-tab';
      button.setAttribute('role', 'tab');
      button.setAttribute('aria-selected', String(dateKey === state.date));
      button.dataset.date = dateKey;
      button.addEventListener('click', () => changeDate(dateKey));
      button.addEventListener('keydown', (event) => handleTabArrow(event, '.date-tab'));

      const main = document.createElement('span');
      main.className = 'date-main';
      main.textContent = index === 0 ? 'Today' : index === 1 ? 'Yesterday' : formatDateTab(dateKey);
      const sub = document.createElement('span');
      sub.className = 'date-sub';
      const count = Number(entry?.articleCount || 0);
      const status = entry?.status || 'missing';
      sub.textContent = `${count} ${count === 1 ? 'article' : 'articles'}`;
      if (['partial', 'retained', 'failed', 'missing', 'empty'].includes(status)) {
        sub.classList.add('date-warning');
        button.setAttribute('aria-label', `${main.textContent}, ${sub.textContent}, ${statusLabel(status)}`);
      } else {
        button.setAttribute('aria-label', `${main.textContent}, ${sub.textContent}`);
      }
      button.append(main, sub);
      fragment.append(button);
    });
    elements.dateTabs.replaceChildren(fragment);
  }

  async function changeDate(dateKey) {
    if (dateKey === state.date) return;
    state.date = dateKey;
    state.visibleCount = state.settings.initialStoryCount || 12;
    renderDateTabs();
    await selectView({ updateHistory: true, datesAlreadyRendered: true });
  }

  function renderCategoryFilters() {
    const fragment = document.createDocumentFragment();
    state.settings.categories.forEach((category) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'filter-button';
      button.textContent = category;
      button.setAttribute('aria-pressed', String(category === state.category));
      button.addEventListener('click', () => {
        state.category = category;
        state.visibleCount = state.settings.initialStoryCount || 12;
        renderCategoryFilters();
        renderStories();
        writeUrl('replace');
        announce(`${category} filter selected.`);
      });
      fragment.append(button);
    });
    elements.categoryFilters.replaceChildren(fragment);
  }

  async function selectView({ updateHistory, datesAlreadyRendered = false }) {
    const requestId = ++state.requestId;
    if (!datesAlreadyRendered) renderDateTabs();
    setLoading(true);
    clearNotices();
    const country = currentCountry();
    elements.editionHeading.textContent = `${country.name} News`;
    elements.editionSummary.textContent = `Headlines are shown in ${friendlyTimeZone(country.timeZone)} local time.`;
    elements.metricTimezone.textContent = friendlyTimeZone(country.timeZone);
    elements.selectedDateLabel.textContent = longDateLabel(state.date, country.timeZone);
    document.title = `${country.name} Headlines | Worldline`;
    if (updateHistory) writeUrl('push');

    try {
      const entry = state.manifest?.countries?.[country.code]?.dates?.[state.date];
      if (!entry) throw new ArchiveError('missing', 'This archive file is currently unavailable.');
      const dayData = await loadDayData(country.code, state.date, entry);
      if (requestId !== state.requestId) return;
      state.dayData = dayData;
      state.visibleCount = state.settings.initialStoryCount || 12;
      renderDayStatus(entry, dayData);
      renderStories();
      elements.sampleBanner.hidden = !(state.manifest.samplePreview || dayData.samplePreview);
    } catch (error) {
      if (requestId !== state.requestId) return;
      console.error(error);
      state.dayData = null;
      renderLoadFailure(error);
    } finally {
      if (requestId === state.requestId) setLoading(false);
      prefetchAdjacentDate();
    }
  }

  async function loadDayData(countryCode, dateKey, entry) {
    const cacheKey = `worldline-day-${countryCode}-${dateKey}`;
    const expectedVersion = entry.lastSuccessfulUpdate || entry.generatedAt || state.manifest.generatedAt;
    const cached = safeJsonParse(safeStorageGet(cacheKey));
    if (cached?.version === expectedVersion && cached?.data) return cached.data;
    const path = entry.path || `data/${countryCode}/${dateKey}.json`;
    const data = await fetchJson(path, expectedVersion);
    cacheDay(cacheKey, expectedVersion, data);
    return data;
  }

  function cacheDay(key, version, data) {
    const indexKey = 'worldline-day-cache-index';
    const index = safeJsonParse(safeStorageGet(indexKey)) || [];
    const filtered = index.filter((item) => item !== key);
    filtered.unshift(key);
    const limit = state.settings.cache?.maxLocalFiles || 3;
    filtered.slice(limit).forEach((oldKey) => safeStorageRemove(oldKey));
    safeStorageSet(key, JSON.stringify({ version, data }));
    safeStorageSet(indexKey, JSON.stringify(filtered.slice(0, limit)));
  }

  function renderStories() {
    elements.leadStory.replaceChildren();
    elements.storyList.replaceChildren();
    elements.emptyState.hidden = true;
    elements.loadMore.hidden = true;
    if (!state.dayData) return;

    const articles = filteredArticles();
    elements.resultCount.textContent = `${articles.length} ${articles.length === 1 ? 'story' : 'stories'}`;
    if (!articles.length) {
      elements.emptyTitle.textContent = state.category === 'All' ? 'No Articles Retrieved' : `No ${state.category} Stories`;
      elements.emptyMessage.textContent = state.category === 'All'
        ? 'No articles were retrieved for this date.'
        : 'No stories in this archive match the selected category.';
      elements.emptyState.hidden = false;
      return;
    }

    const lead = articles[0];
    elements.leadStory.append(buildLeadStory(lead));
    elements.leadStory.hidden = false;
    const list = articles.slice(1, state.visibleCount);
    const fragment = document.createDocumentFragment();
    list.forEach((article, index) => fragment.append(buildStoryCard(article, index + 2)));
    elements.storyList.append(fragment);
    elements.loadMore.hidden = state.visibleCount >= articles.length;
  }

  function filteredArticles() {
    const articles = Array.isArray(state.dayData?.articles) ? state.dayData.articles : [];
    if (state.category === 'All') return articles;
    return articles.filter((article) => article.category === state.category);
  }

  function buildLeadStory(article) {
    const container = document.createDocumentFragment();
    const imageWrap = document.createElement('div');
    imageWrap.className = 'lead-image-wrap';
    imageWrap.append(buildImage(article, true));

    const body = document.createElement('div');
    body.className = 'lead-body';
    body.append(buildMeta(article));

    const title = document.createElement('h3');
    title.className = 'lead-title';
    title.append(buildArticleLink(article, displayTitle(article)));
    body.append(title);
    appendOriginalTitle(body, article);

    if (article.description) {
      const description = document.createElement('p');
      description.className = 'lead-description';
      description.textContent = article.description;
      body.append(description);
    }

    const actions = document.createElement('div');
    actions.className = 'story-actions';
    const originalLink = buildArticleLink(article, 'View Original Article');
    originalLink.className = 'text-link';
    const icon = document.createElement('span');
    icon.className = 'external-icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = '↗';
    originalLink.append(icon);
    actions.append(originalLink);
    if (article.related?.length) actions.append(buildRelatedDetails(article));
    body.append(actions);
    container.append(imageWrap, body);
    return container;
  }

  function buildStoryCard(article, number) {
    const card = document.createElement('article');
    card.className = 'story-card';
    const numberEl = document.createElement('span');
    numberEl.className = 'story-number';
    numberEl.textContent = String(number).padStart(2, '0');
    numberEl.setAttribute('aria-hidden', 'true');

    const content = document.createElement('div');
    content.className = 'story-content';
    const row = document.createElement('div');
    row.className = 'story-main-row';
    const copy = document.createElement('div');
    copy.className = 'story-copy';
    copy.append(buildMeta(article));

    const title = document.createElement('h3');
    title.className = 'story-title';
    title.append(buildArticleLink(article, displayTitle(article)));
    copy.append(title);
    appendOriginalTitle(copy, article);
    if (article.description) {
      const description = document.createElement('p');
      description.className = 'story-description';
      description.textContent = article.description;
      copy.append(description);
    }
    if (article.related?.length) copy.append(buildRelatedDetails(article));

    const thumb = document.createElement('div');
    thumb.className = 'story-thumb';
    thumb.append(buildImage(article, false));
    row.append(copy, thumb);
    content.append(row);
    card.append(numberEl, content);
    return card;
  }

  function buildMeta(article) {
    const meta = document.createElement('div');
    meta.className = 'story-meta';
    const publisher = document.createElement('span');
    publisher.className = 'publisher';
    publisher.textContent = article.sourceName || 'Unknown publisher';
    const time = document.createElement('time');
    time.dateTime = article.publishedAt || '';
    time.textContent = formatArticleTime(article.publishedAt, currentCountry().timeZone);
    const category = document.createElement('span');
    category.className = 'category-label';
    category.textContent = article.category || 'General';
    meta.append(publisher, time, category);
    if (article.related?.length) {
      const related = document.createElement('span');
      related.textContent = `+${article.related.length} source${article.related.length === 1 ? '' : 's'}`;
      meta.append(related);
    }
    return meta;
  }

  function appendOriginalTitle(parent, article) {
    if (!article.translatedTitle || article.translatedTitle === article.title) return;
    const original = document.createElement('p');
    original.className = 'original-title';
    const label = document.createElement('span');
    label.className = 'translation-label';
    label.textContent = 'Machine translated';
    original.append(label, document.createTextNode(article.title));
    parent.append(original);
  }

  function buildRelatedDetails(article) {
    const details = document.createElement('details');
    details.className = 'related-details';
    const summary = document.createElement('summary');
    summary.textContent = `Related Coverage (${article.related.length})`;
    const list = document.createElement('div');
    list.className = 'related-list';
    article.related.forEach((related) => {
      const item = document.createElement('div');
      item.className = 'related-item';
      item.append(buildArticleLink(related, displayTitle(related)));
      const meta = document.createElement('span');
      meta.className = 'related-meta';
      meta.textContent = `${related.sourceName || 'Publisher'} · ${formatArticleTime(related.publishedAt, currentCountry().timeZone)}`;
      item.append(meta);
      list.append(item);
    });
    details.append(summary, list);
    return details;
  }

  function buildArticleLink(article, label) {
    const link = document.createElement('a');
    const url = safeExternalUrl(article.canonicalUrl || article.url);
    link.textContent = label || 'View article';
    if (url) {
      link.href = url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.referrerPolicy = 'no-referrer-when-downgrade';
      link.setAttribute('aria-label', `${label}. Opens ${article.sourceName || 'publisher'} in a new tab.`);
    } else {
      link.href = '#';
      link.addEventListener('click', (event) => event.preventDefault());
      link.setAttribute('aria-disabled', 'true');
    }
    return link;
  }

  function buildImage(article, lead) {
    const imageUrl = safeImageUrl(article.imageUrl);
    if (!imageUrl) return buildPlaceholder(article.sourceName);
    const image = document.createElement('img');
    image.className = lead ? 'lead-image' : '';
    image.src = imageUrl;
    image.alt = article.imageAlt || '';
    image.loading = lead ? 'eager' : 'lazy';
    image.decoding = 'async';
    image.referrerPolicy = 'no-referrer';
    image.width = lead ? 800 : 240;
    image.height = lead ? 420 : 180;
    image.addEventListener('error', () => image.replaceWith(buildPlaceholder(article.sourceName)), { once: true });
    return image;
  }

  function buildPlaceholder(sourceName) {
    const placeholder = document.createElement('div');
    placeholder.className = 'image-placeholder';
    placeholder.setAttribute('role', 'img');
    placeholder.setAttribute('aria-label', 'No article image available');
    const initials = document.createElement('span');
    initials.className = 'placeholder-initials';
    initials.textContent = publisherInitials(sourceName);
    placeholder.append(initials);
    return placeholder;
  }

  function renderDayStatus(entry, dayData) {
    const articles = dayData.articles || [];
    const publishers = new Set(articles.map((article) => article.sourceName).filter(Boolean));
    const health = Array.isArray(dayData.sourceHealth) ? dayData.sourceHealth : [];
    const successful = health.filter((item) => item.status === 'success').length;
    const status = dayData.status || entry.status || 'current';
    setStatusBadge(status);
    elements.metricArticles.textContent = String(articles.length);
    elements.metricPublishers.textContent = String(publishers.size);
    elements.metricSources.textContent = `${successful} of ${health.length}`;
    elements.statusDetail.textContent = statusDescription(status, entry, dayData);
    renderSourceHealth(health);
    renderDataNotice(status, entry, dayData);
  }

  function renderSourceHealth(health) {
    const fragment = document.createDocumentFragment();
    if (!health.length) {
      const empty = document.createElement('p');
      empty.className = 'status-detail';
      empty.textContent = 'No source-level details are available for this sample file.';
      fragment.append(empty);
    } else {
      health.forEach((source) => {
        const row = document.createElement('div');
        row.className = 'source-health-row';
        const name = document.createElement('span');
        name.textContent = source.sourceName || source.sourceId || 'Source';
        const status = document.createElement('span');
        status.className = source.status === 'success' ? 'health-success' : source.status === 'retained' ? 'health-warning' : 'health-error';
        status.textContent = source.status === 'success' ? `${source.articlesRetrieved || 0} items` : humanize(source.status || 'failed');
        row.append(name, status);
        fragment.append(row);
      });
    }
    elements.sourceHealthList.replaceChildren(fragment);
  }

  function renderDataNotice(status, entry, dayData) {
    clearNotices();
    if (status === 'partial') {
      showNotice('Some sources were unavailable, so this list may be incomplete.', 'notice-info');
    } else if (status === 'retained') {
      const timestamp = entry.lastSuccessfulUpdate || dayData.lastSuccessfulUpdate;
      showNotice(`The most recent successful data is being shown${timestamp ? ` from ${formatTimestamp(timestamp, currentCountry().timeZone)}` : ''}.`, '');
    } else if (['failed', 'missing'].includes(status)) {
      showNotice('This archive file is currently unavailable.', 'notice-error');
    }
  }

  function renderLoadFailure(error) {
    elements.leadStory.hidden = true;
    elements.storyList.replaceChildren();
    elements.resultCount.textContent = '0 stories';
    elements.emptyTitle.textContent = error.status === 'missing' ? 'Archive File Missing' : 'News Data Unavailable';
    elements.emptyMessage.textContent = error.message || 'This archive file is currently unavailable.';
    elements.emptyState.hidden = false;
    setStatusBadge(error.status || 'failed');
    elements.metricArticles.textContent = '0';
    elements.metricPublishers.textContent = '0';
    elements.metricSources.textContent = '0 of 0';
    elements.statusDetail.textContent = 'The browser could not load a valid generated daily file.';
    elements.sourceHealthList.replaceChildren();
    showNotice(error.message || 'The daily archive could not be loaded.', 'notice-error');
  }

  function renderGlobalStatus() {
    const manifest = state.manifest;
    const status = manifest.overallStatus || (manifest.samplePreview ? 'sample' : 'current');
    elements.globalStatus.textContent = manifest.samplePreview ? 'Sample preview data' : statusLabel(status);
    elements.globalStatusDot.className = `status-dot ${statusClass(status)}`;
    if (manifest.generatedAt) {
      elements.lastUpdated.dateTime = manifest.generatedAt;
      elements.lastUpdated.textContent = `Last updated ${formatTimestamp(manifest.generatedAt, currentCountry()?.timeZone || 'America/New_York')}`;
    }
  }

  function setStatusBadge(status) {
    elements.dayStatusBadge.textContent = statusLabel(status);
    elements.dayStatusBadge.className = `status-badge ${badgeClass(status)}`;
  }

  function statusDescription(status, entry, dayData) {
    if (status === 'current') return 'This daily archive was generated successfully during the latest collection.';
    if (status === 'partial') return 'Enough current data was collected, but at least one configured source failed.';
    if (status === 'retained') return 'A recent collection was incomplete, so the previous valid archive was preserved.';
    if (status === 'sample') return 'This is clearly labeled sample data for interface preview only.';
    if (status === 'empty') return 'No valid articles were retrieved for this local calendar date.';
    return dayData?.warning || entry?.warning || 'The daily archive is unavailable or failed validation.';
  }

  function showFatalState(title, message) {
    setLoading(false);
    elements.emptyTitle.textContent = title;
    elements.emptyMessage.textContent = message;
    elements.emptyState.hidden = false;
    elements.leadStory.hidden = true;
    elements.dayStatusBadge.textContent = 'Unavailable';
    elements.dayStatusBadge.className = 'status-badge badge-error';
    elements.globalStatus.textContent = 'News Data Unavailable';
    elements.globalStatusDot.className = 'status-dot status-error';
  }

  function setLoading(loading) {
    elements.loadingState.hidden = !loading;
    if (loading) {
      elements.leadStory.hidden = true;
      elements.storyList.replaceChildren();
      elements.emptyState.hidden = true;
      elements.loadMore.hidden = true;
    }
  }

  function clearNotices() {
    elements.dataNotice.hidden = true;
    elements.dataNotice.textContent = '';
    elements.dataNotice.className = 'notice';
  }

  function showNotice(text, className) {
    elements.dataNotice.textContent = text;
    elements.dataNotice.className = `notice ${className || ''}`.trim();
    elements.dataNotice.hidden = false;
  }

  function writeUrl(mode) {
    const params = new URLSearchParams();
    params.set('country', state.countryCode);
    params.set('date', state.date);
    if (state.category !== 'All') params.set('category', categorySlug(state.category));
    const next = `${location.pathname}?${params.toString()}${location.hash}`;
    if (mode === 'push') history.pushState(null, '', next);
    else history.replaceState(null, '', next);
  }

  function getSevenDateKeys(timeZone) {
    const today = dateKeyInTimeZone(new Date(), timeZone);
    return Array.from({ length: 7 }, (_, index) => shiftDateKey(today, -index));
  }

  function dateKeyInTimeZone(date, timeZone) {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone, year: 'numeric', month: '2-digit', day: '2-digit'
    }).formatToParts(date).reduce((acc, part) => ({ ...acc, [part.type]: part.value }), {});
    return `${parts.year}-${parts.month}-${parts.day}`;
  }

  function shiftDateKey(dateKey, amount) {
    const [year, month, day] = dateKey.split('-').map(Number);
    const date = new Date(Date.UTC(year, month - 1, day + amount, 12));
    return date.toISOString().slice(0, 10);
  }

  function formatDateTab(dateKey) {
    const date = dateFromKey(dateKey);
    return new Intl.DateTimeFormat('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' }).format(date);
  }

  function longDateLabel(dateKey, timeZone) {
    const keys = getSevenDateKeys(timeZone);
    if (dateKey === keys[0]) return 'Today';
    if (dateKey === keys[1]) return 'Yesterday';
    return new Intl.DateTimeFormat('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric', timeZone: 'UTC' }).format(dateFromKey(dateKey));
  }

  function dateFromKey(dateKey) {
    const [year, month, day] = dateKey.split('-').map(Number);
    return new Date(Date.UTC(year, month - 1, day, 12));
  }

  function formatArticleTime(value, timeZone) {
    if (!value) return 'Time unavailable';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return 'Time unavailable';
    return new Intl.DateTimeFormat('en-US', {
      timeZone, hour: 'numeric', minute: '2-digit', hour12: true, timeZoneName: 'short'
    }).format(date);
  }

  function formatTimestamp(value, timeZone) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return 'at an unknown time';
    return new Intl.DateTimeFormat('en-US', {
      timeZone, month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true, timeZoneName: 'short'
    }).format(date);
  }

  function friendlyTimeZone(timeZone) {
    return timeZone.replaceAll('_', ' ').replace('/', ' / ');
  }

  function safeExternalUrl(value) {
    if (!value) return null;
    try {
      const url = new URL(value);
      return ['https:', 'http:'].includes(url.protocol) ? url.toString() : null;
    } catch { return null; }
  }

  function safeImageUrl(value) {
    if (!value) return null;
    try {
      const url = new URL(value);
      if (url.protocol !== 'https:') return null;
      if (/\.(svg|gif)(\?|$)/i.test(url.pathname)) return null;
      return url.toString();
    } catch { return null; }
  }

  function displayTitle(article) {
    return article.translatedTitle || article.title || 'Untitled article';
  }

  function publisherInitials(name) {
    const words = String(name || 'News').trim().split(/\s+/).filter(Boolean);
    return words.slice(0, 2).map((word) => word[0]).join('').toUpperCase() || 'N';
  }

  function statusLabel(status) { return STATUS_LABELS[status] || humanize(status || 'unknown'); }
  function statusClass(status) {
    if (['current'].includes(status)) return 'status-current';
    if (['partial', 'retained', 'sample'].includes(status)) return 'status-warning';
    return 'status-error';
  }
  function badgeClass(status) {
    if (status === 'current') return 'badge-current';
    if (['partial', 'retained', 'sample'].includes(status)) return 'badge-warning';
    return 'badge-error';
  }
  function categorySlug(value) { return String(value).toLowerCase().replace('&', 'and').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''); }
  function humanize(value) { return String(value).replaceAll('_', ' ').replace(/\b\w/g, (char) => char.toUpperCase()); }

  async function fetchManifest() {
    const url = assetUrl('data/manifest.json');
    const separator = url.includes('?') ? '&' : '?';
    const response = await fetch(`${url}${separator}t=${Date.now()}`, { cache: 'no-store', headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error(`Manifest request failed with ${response.status}`);
    return response.json();
  }

  async function fetchJson(path, version = '') {
    const url = assetUrl(path);
    const requestUrl = version ? `${url}${url.includes('?') ? '&' : '?'}v=${encodeURIComponent(version)}` : url;
    const response = await fetch(requestUrl, { cache: version ? 'default' : 'no-cache', headers: { Accept: 'application/json' } });
    if (!response.ok) throw new ArchiveError(response.status === 404 ? 'missing' : 'failed', `Request failed with ${response.status}.`);
    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('json')) throw new ArchiveError('failed', 'The server returned an unexpected file type.');
    return response.json();
  }

  function assetUrl(path) { return new URL(path, document.baseURI).toString(); }

  function prefetchAdjacentDate() {
    if (!state.manifest || !state.date) return;
    const keys = getSevenDateKeys(currentCountry().timeZone);
    const index = keys.indexOf(state.date);
    const adjacent = [keys[index - 1], keys[index + 1]].filter(Boolean).find((key) => state.manifest.countries?.[state.countryCode]?.dates?.[key]);
    if (!adjacent) return;
    const entry = state.manifest.countries[state.countryCode].dates[adjacent];
    const link = document.createElement('link');
    link.rel = 'prefetch';
    link.as = 'fetch';
    link.crossOrigin = 'anonymous';
    link.href = assetUrl(entry.path || `data/${state.countryCode}/${adjacent}.json`);
    document.head.append(link);
  }

  function handleTabArrow(event, selector) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    const tabs = [...event.currentTarget.parentElement.querySelectorAll(selector)];
    const current = tabs.indexOf(event.currentTarget);
    let next = current;
    if (event.key === 'ArrowLeft') next = (current - 1 + tabs.length) % tabs.length;
    if (event.key === 'ArrowRight') next = (current + 1) % tabs.length;
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = tabs.length - 1;
    event.preventDefault();
    tabs[next].focus();
    tabs[next].scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }

  function announce(message) { elements.liveRegion.textContent = message; }
  function toCamel(value) { return value.replace(/-([a-z])/g, (_, char) => char.toUpperCase()); }
  function safeJsonParse(value) { try { return value ? JSON.parse(value) : null; } catch { return null; } }
  function safeStorageGet(key) { try { return localStorage.getItem(key); } catch { return null; } }
  function safeStorageSet(key, value) { try { localStorage.setItem(key, value); } catch { /* Storage is optional. */ } }
  function safeStorageRemove(key) { try { localStorage.removeItem(key); } catch { /* Storage is optional. */ } }

  class ArchiveError extends Error {
    constructor(status, message) { super(message); this.name = 'ArchiveError'; this.status = status; }
  }
})();
