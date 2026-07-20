(() => {
  'use strict';

  const state = {
    countries: [],
    settings: null,
    manifest: null,
    countryCode: 'US',
    date: null,
    dayData: null,
    visibleCount: 12,
    requestId: 0,
  };

  const elements = {};
  const ENGLISH_LANGUAGE_CODES = new Set(['en', 'en-us', 'en-gb', 'english']);
  const TRANSLATION_CACHE_KEY = 'worldline-translation-cache-v1';
  const STATUS_LABELS = {
    current: 'Current',
    partial: 'Partially Updated',
    retained: 'Retained From Previous Update',
    empty: 'No Articles Retrieved',
    failed: 'Data Generation Failed',
    missing: 'Not Ready',
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
      const activeCodes = new Set((settings.activeCountries || []).map((code) => String(code).toUpperCase()));
      state.countries = countries
        .filter((country) => !activeCodes.size || activeCodes.has(country.code))
        .sort((a, b) => a.order - b.order);
      state.settings = settings;
      state.manifest = manifest;
      state.visibleCount = settings.initialStoryCount || 12;
      restoreInitialState();
      renderCountryTabs();
      renderGlobalStatus();
      await selectView({ updateHistory: false });
    } catch (error) {
      console.error(error);
      showFatalState('News Data Unavailable', 'The generated manifest or configuration files could not be loaded.');
    } finally {
      revealApp();
    }
  }

  function cacheElements() {
    const ids = [
      'country-rail', 'country-tabs', 'date-tabs', 'news-column', 'lead-story', 'story-list',
      'loading-state', 'empty-state', 'empty-title', 'empty-message', 'load-more',
      'data-notice', 'result-count', 'selected-date-label',
      'edition-heading', 'edition-summary', 'global-status',
      'last-updated', 'live-region'
    ];
    ids.forEach((id) => { elements[toCamel(id)] = document.getElementById(id); });
  }

  function bindEvents() {
    elements.loadMore.addEventListener('click', () => {
      state.visibleCount += state.settings.loadMoreCount || 12;
      renderStories();
      void translateVisibleArticles(state.requestId);
      announce(`Showing ${Math.min(state.visibleCount, filteredArticles().length)} stories.`);
    });
    window.addEventListener('popstate', async () => {
      restoreStateFromUrl();
      renderCountryTabs();
      await selectView({ updateHistory: false });
    });
    elements.countryTabs.addEventListener('wheel', handleHorizontalWheel, { passive: false });
    elements.dateTabs.addEventListener('wheel', handleHorizontalWheel, { passive: false });
    elements.countryTabs.addEventListener('scroll', updateCountryRailEdges, { passive: true });
    elements.countryTabs.addEventListener('pointerdown', startCountryDrag);
    elements.countryTabs.addEventListener('pointermove', moveCountryDrag);
    elements.countryTabs.addEventListener('pointerup', endCountryDrag);
    elements.countryTabs.addEventListener('pointercancel', endCountryDrag);
    elements.countryTabs.addEventListener('click', suppressDraggedCountryClick, true);
  }

  function restoreInitialState() {
    const params = new URLSearchParams(location.search);
    const urlCountry = normalizeCountry(params.get('country'));
    const savedCountry = safeStorageGet('worldline-country');
    state.countryCode = urlCountry || normalizeCountry(savedCountry) || state.settings.defaultCountry || 'US';
    const country = currentCountry();
    const dates = getSevenDateKeys(country.timeZone);
    const requestedDate = params.get('date');
    if (dates.includes(requestedDate) && isPreparedDate(country.code, requestedDate)) {
      state.date = requestedDate;
    } else {
      state.date = latestPreparedDate(country.code, country.timeZone);
    }
    writeUrl('replace');
  }

  function restoreStateFromUrl() {
    const params = new URLSearchParams(location.search);
    state.countryCode = normalizeCountry(params.get('country')) || state.settings.defaultCountry || 'US';
    const dates = getSevenDateKeys(currentCountry().timeZone);
    if (dates.includes(params.get('date')) && isPreparedDate(state.countryCode, params.get('date'))) {
      state.date = params.get('date');
    } else {
      state.date = latestPreparedDate(state.countryCode, currentCountry().timeZone);
    }
    state.visibleCount = state.settings.initialStoryCount || 12;
  }

  function normalizeCountry(value) {
    if (!value) return null;
    const code = String(value).toUpperCase();
    return state.countries.some((country) => country.code === code) ? code : null;
  }

  function currentCountry() {
    return state.countries.find((country) => country.code === state.countryCode) || state.countries[0];
  }

  function renderCountryTabs() {
    const fragment = document.createDocumentFragment();
    state.countries.forEach((country) => {
      const selected = country.code === state.countryCode;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'country-tab';
      button.setAttribute('aria-pressed', String(selected));
      if (selected) button.setAttribute('aria-current', 'true');
      button.dataset.country = country.code;
      button.addEventListener('click', () => changeCountry(country.code));
      button.addEventListener('keydown', (event) => handleFilterArrow(event, '.country-tab'));

      const flag = document.createElement('img');
      flag.className = 'flag-image';
      flag.src = assetUrl(`assets/flags/${country.code.toLowerCase()}.svg`);
      flag.alt = '';
      flag.width = 320;
      flag.height = 200;
      flag.draggable = false;
      const label = document.createElement('span');
      label.className = 'country-name';
      label.textContent = country.name;
      button.setAttribute('aria-label', `${country.name} edition`);
      button.append(flag, label);
      fragment.append(button);
    });
    elements.countryTabs.replaceChildren(fragment);
    updateCountryRailEdges();
    requestAnimationFrame(scrollSelectedCountryIntoView);
  }

  async function changeCountry(countryCode) {
    if (countryCode === state.countryCode) return;
    state.countryCode = countryCode;
    safeStorageSet('worldline-country', countryCode);
    // A country switch should always open that country's local Today. The
    // same calendar date can be Today in one time zone and Yesterday in
    // another, so preserving state.date makes the default inconsistent.
    const country = currentCountry();
    state.date = latestPreparedDate(country.code, country.timeZone);
    state.visibleCount = state.settings.initialStoryCount || 12;
    renderCountryTabs();
    await selectView({ updateHistory: true });
  }

  function renderDateTabs() {
    const country = currentCountry();
    const keys = getSevenDateKeys(country.timeZone);
    const fragment = document.createDocumentFragment();
    keys.forEach((dateKey, index) => {
      const entry = state.manifest?.countries?.[country.code]?.dates?.[dateKey];
      const selected = dateKey === state.date;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'date-tab';
      button.setAttribute('aria-pressed', String(selected));
      if (selected) button.setAttribute('aria-current', 'date');
      button.dataset.date = dateKey;
      button.addEventListener('click', () => changeDate(dateKey));
      button.addEventListener('keydown', (event) => handleFilterArrow(event, '.date-tab'));

      const main = document.createElement('span');
      main.className = 'date-main';
      main.textContent = index === 0 ? 'Today' : index === 1 ? 'Yesterday' : formatDateTab(dateKey);
      const status = entry?.status || 'missing';
      if (['partial', 'retained', 'failed', 'missing', 'empty'].includes(status)) {
        button.setAttribute('aria-label', `${longDateLabel(dateKey, country.timeZone)}, ${statusLabel(status)}`);
      } else {
        button.setAttribute('aria-label', longDateLabel(dateKey, country.timeZone));
      }
      button.append(main);
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

  async function selectView({ updateHistory, datesAlreadyRendered = false }) {
    const requestId = ++state.requestId;
    if (!datesAlreadyRendered) renderDateTabs();
    setLoading(true);
    clearNotices();
    const country = currentCountry();
    elements.editionHeading.textContent = `${country.name} News`;
    elements.editionSummary.textContent = `Headlines are shown in ${friendlyTimeZone(country.timeZone)} local time.`;
    elements.selectedDateLabel.textContent = longDateLabel(state.date, country.timeZone);
    document.title = `${country.name} Headlines | Worldline`;
    if (updateHistory) writeUrl('push');

    try {
      const entry = state.manifest?.countries?.[country.code]?.dates?.[state.date];
      if (!entry) throw new ArchiveError('missing');
      const dayData = await loadDayData(country.code, state.date, entry);
      if (requestId !== state.requestId) return;
      state.dayData = dayData;
      state.visibleCount = state.settings.initialStoryCount || 12;
      renderDayStatus(entry, dayData);
      renderStories();
      void translateVisibleArticles(requestId);
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
    elements.resultCount.textContent = `${articles.length} ${articles.length === 1 ? 'headline' : 'headlines'}`;
    if (!articles.length) {
      elements.emptyTitle.textContent = 'No Articles Retrieved';
      elements.emptyMessage.textContent = 'No articles were retrieved for this date.';
      elements.emptyState.hidden = false;
      return;
    }

    const lead = articles[0];
    elements.leadStory.append(buildLeadStory(lead));
    elements.leadStory.hidden = false;
    const secondaryCount = evenSecondaryCount(articles.length);
    const list = articles.slice(1, secondaryCount + 1);
    const fragment = document.createDocumentFragment();
    list.forEach((article) => fragment.append(buildStoryCard(article)));
    elements.storyList.append(fragment);
    elements.loadMore.hidden = secondaryCount >= Math.max(0, articles.length - 1);
    revealApp();
  }

  async function translateVisibleArticles(requestId) {
    const translationSettings = state.settings?.translation || {};
    if (translationSettings.clientSide === false || requestId !== state.requestId) return;

    const articles = filteredArticles().slice(0, Math.min(
      filteredArticles().length,
      Math.max(1, state.visibleCount + 1),
    ));
    const candidates = articles.filter((article) => isNonEnglishArticle(article) && !isTranslated(article));
    if (!candidates.length) return;

    const cache = safeJsonParse(safeStorageGet(TRANSLATION_CACHE_KEY)) || {};
    let changed = false;
    const pending = [];
    for (const article of candidates) {
      const cached = cache[article.id];
      if (cached?.sourceTitle === article.title && cached.translatedTitle) {
        article.translatedTitle = cached.translatedTitle;
        article.translationProvider = 'Google Translate';
        changed = true;
      } else {
        pending.push(article);
      }
    }
    if (changed && requestId === state.requestId) renderStories();
    if (!pending.length || requestId !== state.requestId) {
      if (changed) safeStorageSet(TRANSLATION_CACHE_KEY, JSON.stringify(cache));
      return;
    }

    let cursor = 0;
    const workers = Array.from({ length: 4 }, async () => {
      while (cursor < pending.length) {
        const article = pending[cursor++];
        try {
          const translatedTitle = await translateTitle(article.title);
          if (!translatedTitle || translatedTitle.localeCompare(article.title, undefined, { sensitivity: 'accent' }) === 0) continue;
          article.translatedTitle = translatedTitle;
          article.translationProvider = 'Google Translate';
          cache[article.id] = { sourceTitle: article.title, translatedTitle };
          safeStorageSet(TRANSLATION_CACHE_KEY, JSON.stringify(cache));
          if (requestId === state.requestId) {
            renderStories();
            changed = true;
          }
        } catch {
          // Translation is optional; keep the original title when it is unavailable.
        }
        if (requestId !== state.requestId) return;
      }
    });
    await Promise.all(workers);
    if (changed && requestId === state.requestId) renderStories();
  }

  async function translateTitle(title) {
    const url = `https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=en&dt=t&q=${encodeURIComponent(title)}`;
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch(url, { signal: controller.signal, credentials: 'omit' });
      if (!response.ok) throw new Error(`Translation request failed with ${response.status}.`);
      const data = await response.json();
      return Array.isArray(data?.[0])
        ? data[0].map((part) => part?.[0] || '').join('').trim()
        : '';
    } finally {
      window.clearTimeout(timer);
    }
  }

  function isNonEnglishArticle(article) {
    const language = String(article.language || '').trim().toLowerCase().replaceAll('_', '-');
    return Boolean(language) && !ENGLISH_LANGUAGE_CODES.has(language) && !language.startsWith('en-');
  }

  function evenSecondaryCount(articleCount) {
    const available = Math.max(0, articleCount - 1);
    const requested = Math.max(0, state.visibleCount);
    const completedRow = requested + (requested % 2);
    return Math.min(available, completedRow);
  }

  function filteredArticles() {
    return Array.isArray(state.dayData?.articles) ? state.dayData.articles : [];
  }

  function buildLeadStory(article) {
    const container = document.createDocumentFragment();
    const imageWrap = document.createElement('div');
    imageWrap.className = 'lead-image-wrap';
    imageWrap.append(buildImage(article, true));
    const scrim = document.createElement('div');
    scrim.className = 'lead-scrim';
    scrim.setAttribute('aria-hidden', 'true');
    imageWrap.append(scrim);

    const body = document.createElement('div');
    body.className = 'lead-body';
    body.append(buildMeta(article, true));

    const title = document.createElement('h3');
    title.className = 'lead-title';
    title.append(buildArticleLink(article, displayTitle(article)));
    body.append(title);

    container.append(imageWrap, body);
    return container;
  }

  function buildStoryCard(article) {
    const card = document.createElement('article');
    card.className = 'story-card';
    const thumb = document.createElement('div');
    thumb.className = 'story-thumb';
    thumb.append(buildImage(article, false));

    const copy = document.createElement('div');
    copy.className = 'story-copy';
    copy.append(buildMeta(article, true));

    const title = document.createElement('h3');
    title.className = 'story-title';
    title.append(buildArticleLink(article, displayTitle(article)));
    copy.append(title);
    card.append(thumb, copy);
    return card;
  }

  function buildMeta(article, showTranslation = false) {
    const meta = document.createElement('div');
    meta.className = 'story-meta';
    const publisher = document.createElement('span');
    publisher.className = 'publisher';
    publisher.textContent = article.sourceName || 'Unknown publisher';
    const time = document.createElement('time');
    time.dateTime = article.publishedAt || '';
    time.textContent = formatArticleTime(article.publishedAt, currentCountry().timeZone);
    meta.append(publisher, time);
    if (showTranslation && isTranslated(article)) {
      const translated = document.createElement('span');
      translated.className = 'translation-label';
      translated.textContent = 'Translated';
      meta.append(translated);
    }
    return meta;
  }

  function isTranslated(article) {
    return Boolean(article.translatedTitle && article.translatedTitle !== article.title);
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
    if (lead) image.fetchPriority = 'high';
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
    const status = dayData.status || entry.status || 'current';
    renderDataNotice(status, entry, dayData);
  }

  function renderDataNotice(status, entry, dayData) {
    clearNotices();
    if (isTodayDate(state.date) && ['failed', 'missing'].includes(status)) {
      showNotice('News is being prepared. Check back later!', 'notice-fallback');
    }
  }

  function renderLoadFailure(error) {
    elements.leadStory.hidden = true;
    elements.storyList.replaceChildren();
    elements.resultCount.textContent = 'No headlines';
    const todayUnavailable = isTodayDate(state.date) && ['missing', 'failed'].includes(error.status);
    elements.emptyTitle.textContent = todayUnavailable ? 'News is being prepared.' : 'News Data Unavailable';
    elements.emptyMessage.textContent = todayUnavailable ? 'Check back later!' : 'No news is available for this date.';
    elements.emptyState.hidden = false;
    clearNotices();
    if (todayUnavailable) showNotice('News is being prepared. Check back later!', 'notice-fallback');
    revealApp();
  }

  function renderGlobalStatus() {
    const manifest = state.manifest;
    const status = manifest.overallStatus || (manifest.samplePreview ? 'sample' : 'current');
    elements.globalStatus.textContent = manifest.samplePreview ? 'Sample preview data' : statusLabel(status);
    if (manifest.generatedAt) {
      elements.lastUpdated.dateTime = manifest.generatedAt;
      elements.lastUpdated.textContent = `Last updated ${formatTimestamp(manifest.generatedAt, currentCountry()?.timeZone || 'America/New_York')}`;
    }
  }

  function showFatalState(title, message) {
    setLoading(false);
    elements.emptyTitle.textContent = title;
    elements.emptyMessage.textContent = message;
    elements.emptyState.hidden = false;
    elements.leadStory.hidden = true;
    elements.globalStatus.textContent = 'News Data Unavailable';
    revealApp();
  }

  function revealApp() {
    document.documentElement.classList.remove('app-loading');
  }

  function setLoading(loading) {
    const hasRenderedView = !elements.leadStory.hidden || elements.storyList.childElementCount > 0 || !elements.emptyState.hidden;
    elements.newsColumn.setAttribute('aria-busy', String(loading));
    elements.loadingState.hidden = !loading || hasRenderedView;
    if (loading && !hasRenderedView) {
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
    const next = `${location.pathname}?${params.toString()}${location.hash}`;
    if (mode === 'push') history.pushState(null, '', next);
    else history.replaceState(null, '', next);
  }

  function getSevenDateKeys(timeZone) {
    const today = dateKeyInTimeZone(new Date(), timeZone);
    return Array.from({ length: 7 }, (_, index) => shiftDateKey(today, -index));
  }

  function isTodayDate(dateKey) {
    return dateKey === getSevenDateKeys(currentCountry().timeZone)[0];
  }

  function latestPreparedDate(countryCode, timeZone) {
    const keys = getSevenDateKeys(timeZone);
    return keys.find((dateKey) => isPreparedDate(countryCode, dateKey)) || keys[0];
  }

  function isPreparedDate(countryCode, dateKey) {
    const entry = state.manifest?.countries?.[countryCode]?.dates?.[dateKey];
    const usableStatuses = new Set(['current', 'partial', 'retained', 'sample']);
    return Boolean(entry?.path && usableStatuses.has(entry.status));
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
      if (/\.(svg|gif|3gp|avi|m3u8|m4v|mkv|mov|mp3|mp4|mpeg|mpg|ogg|ogv|ts|wav|webm|wmv)$/i.test(url.pathname)) return null;
      if (/(^|\.)((youtube|youtu|vimeo|dailymotion)\.com)$/i.test(url.hostname) || url.hostname === 'youtu.be') return null;
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

  function handleFilterArrow(event, selector) {
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

  function handleHorizontalWheel(event) {
    const rail = event.currentTarget;
    if (rail.scrollWidth <= rail.clientWidth || Math.abs(event.deltaX) >= Math.abs(event.deltaY)) return;
    const delta = event.deltaY;
    const atStart = rail.scrollLeft <= 0;
    const atEnd = Math.ceil(rail.scrollLeft + rail.clientWidth) >= rail.scrollWidth;
    if ((delta < 0 && atStart) || (delta > 0 && atEnd)) return;
    event.preventDefault();
    rail.scrollLeft += delta;
  }

  const countryDrag = { pointerId: null, startX: 0, startScrollLeft: 0, moved: false, captured: false, suppressClick: false };

  function startCountryDrag(event) {
    if (event.pointerType !== 'mouse' || event.button !== 0 || elements.countryTabs.scrollWidth <= elements.countryTabs.clientWidth) return;
    countryDrag.pointerId = event.pointerId;
    countryDrag.startX = event.clientX;
    countryDrag.startScrollLeft = elements.countryTabs.scrollLeft;
    countryDrag.moved = false;
  }

  function moveCountryDrag(event) {
    if (event.pointerId !== countryDrag.pointerId) return;
    const delta = event.clientX - countryDrag.startX;
    if (Math.abs(delta) < 4) return;
    countryDrag.moved = true;
    if (elements.countryTabs.setPointerCapture) {
      elements.countryTabs.setPointerCapture(event.pointerId);
      countryDrag.captured = true;
    }
    elements.countryTabs.classList.add('is-dragging');
    event.preventDefault();
    elements.countryTabs.scrollLeft = countryDrag.startScrollLeft - delta;
  }

  function endCountryDrag(event) {
    if (event.pointerId !== countryDrag.pointerId) return;
    if (countryDrag.moved) {
      countryDrag.suppressClick = true;
      window.setTimeout(() => { countryDrag.suppressClick = false; }, 0);
    }
    if (countryDrag.captured) elements.countryTabs.releasePointerCapture?.(event.pointerId);
    countryDrag.pointerId = null;
    countryDrag.captured = false;
    elements.countryTabs.classList.remove('is-dragging');
  }

  function suppressDraggedCountryClick(event) {
    if (!countryDrag.suppressClick) return;
    event.preventDefault();
    event.stopPropagation();
    countryDrag.suppressClick = false;
  }

  function updateCountryRailEdges() {
    const rail = elements.countryRail;
    const tabs = elements.countryTabs;
    if (!rail || !tabs) return;
    const maxScrollLeft = Math.max(0, tabs.scrollWidth - tabs.clientWidth);
    rail.classList.toggle('is-at-start', tabs.scrollLeft <= 1);
    rail.classList.toggle('is-at-end', tabs.scrollLeft >= maxScrollLeft - 1);
  }

  function scrollSelectedCountryIntoView() {
    const selected = elements.countryTabs.querySelector('[aria-current="true"]');
    if (!selected) return;
    const maxLeft = elements.countryTabs.scrollWidth - elements.countryTabs.clientWidth;
    const targetLeft = selected.offsetLeft - ((elements.countryTabs.clientWidth - selected.offsetWidth) / 2);
    elements.countryTabs.scrollTo({
      left: Math.max(0, Math.min(maxLeft, targetLeft)),
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
    });
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
