/* ─────────────────────────────────────────────────────────────────────────────
   Music Downloader — Frontend Application
   Vanilla JS, no dependencies.
───────────────────────────────────────────────────────────────────────────── */

const API = '/api';

// ── State ──────────────────────────────────────────────────────────────────

const state = {
  source: 'spotify',        // 'spotify' | 'youtube'
  tracks: [],               // TrackInfo[]
  selectedIds: new Set(),   // Set<string>
  playlistName: '',
  fetchLoading: false,

  // Download
  activeJobId: null,
  jobStatus: null,          // 'running' | 'done' | 'cancelled' | null
  trackProgress: {},        // id -> { status, progress, message, error }

  // Settings (persisted)
  format: 'mp3',
  quality: '320',
  filenameTemplate: '{artist} - {title}',
  normalizeAudio: false,
  embedArtwork: true,
  downloadThumbnail: false,

  // Tokens
  availableTokens: [],
  presets: [],

  // History
  history: [],              // { title, artist, format, timestamp, jobId, trackId }

  // UI
  showLog: false,
  showHistory: false,
  logLines: [],
};

// ── Persistence ────────────────────────────────────────────────────────────

function saveSettings() {
  const s = {
    format: state.format,
    quality: state.quality,
    filenameTemplate: state.filenameTemplate,
    normalizeAudio: state.normalizeAudio,
    embedArtwork: state.embedArtwork,
    downloadThumbnail: state.downloadThumbnail,
    source: state.source,
  };
  localStorage.setItem('md_settings', JSON.stringify(s));
}

function loadSettings() {
  try {
    const raw = localStorage.getItem('md_settings');
    if (!raw) return;
    const s = JSON.parse(raw);
    Object.assign(state, s);
  } catch { /* ignore */ }

  try {
    const hist = localStorage.getItem('md_history');
    if (hist) state.history = JSON.parse(hist);
  } catch { /* ignore */ }
}

function saveHistory() {
  localStorage.setItem('md_history', JSON.stringify(state.history.slice(0, 50)));
}

// ── Toast ──────────────────────────────────────────────────────────────────

function toast(msg, type = 'info', duration = 4000) {
  const el = document.createElement('div');
  el.className = `toast ${type === 'error' ? 'error' : type === 'warn' ? 'warn' : ''}`;
  const icon = type === 'error' ? '✕' : type === 'warn' ? '⚠' : '✓';
  el.innerHTML = `<span>${icon}</span><span>${msg}</span>`;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => {
    el.classList.add('fading');
    setTimeout(() => el.remove(), 320);
  }, duration);
}

// ── API Helpers ────────────────────────────────────────────────────────────

async function apiFetch(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Duration helper ────────────────────────────────────────────────────────

function fmtDuration(ms) {
  if (!ms) return '--:--';
  const s = Math.round(ms / 1000);
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${sec.toString().padStart(2, '0')}`;
}

function estimateSize(ms, fmt, quality) {
  if (!ms) return '';
  const secs = ms / 1000;
  const lossless = ['flac', 'wav'];
  let kbps = parseInt(quality) || 320;
  if (lossless.includes(fmt)) kbps = 1411; // ~CD quality
  const bytes = (kbps * 1000 / 8) * secs;
  if (bytes > 1024 * 1024) return `~${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `~${Math.round(bytes / 1024)} KB`;
}

// ── Template Preview ───────────────────────────────────────────────────────

function previewTemplate(template, sampleTrack) {
  if (!sampleTrack) return template;
  const dur = fmtDuration(sampleTrack.duration_ms);
  const vals = {
    title: sampleTrack.title || 'Title',
    artist: sampleTrack.artist || 'Artist',
    artists: (sampleTrack.artists || [sampleTrack.artist]).join(', ') || 'Artist',
    album: sampleTrack.album || 'Album',
    album_artist: sampleTrack.album_artist || sampleTrack.artist || 'Artist',
    track_number: String(sampleTrack.track_number || 1).padStart(2, '0'),
    disc_number: String(sampleTrack.disc_number || 1),
    year: sampleTrack.year || '2024',
    date: sampleTrack.date || '2024-01-01',
    genre: sampleTrack.genre || 'Unknown',
    duration: dur,
    playlist: sampleTrack.playlist_name || 'Playlist',
    playlist_index: String(sampleTrack.playlist_index || 1).padStart(3, '0'),
    source: sampleTrack.source || 'spotify',
  };
  let result = template;
  for (const [k, v] of Object.entries(vals)) {
    result = result.replaceAll(`{${k}}`, v);
  }
  return result;
}

// ── Sanitize filename preview ──────────────────────────────────────────────

function sanitizePreview(s) {
  return s.replace(/[/\\:*?"<>|]/g, '_').trim().slice(0, 80);
}

// ── Render Helpers ─────────────────────────────────────────────────────────

function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'class') e.className = v;
    else if (k === 'html') e.innerHTML = v;
    else e.setAttribute(k, v);
  }
  for (const c of children) {
    if (typeof c === 'string') e.appendChild(document.createTextNode(c));
    else if (c) e.appendChild(c);
  }
  return e;
}

function svg(path, size = 16, title = '') {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-label="${title}">${path}</svg>`;
}

const ICONS = {
  music: '<circle cx="9" cy="18" r="3"/><circle cx="18" cy="16" r="3"/><polyline points="12 18 12 2 21 2"/><path d="M21 2H12L9 8"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
  search: '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
  check: '<polyline points="20 6 9 17 4 12"/>',
  x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  list: '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>',
  trash: '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/>',
  chevron: '<polyline points="9 18 15 12 9 6"/>',
  archive: '<polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/>',
  info: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
  warn: '<path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
  clipboard: '<rect x="9" y="2" width="6" height="4" rx="1"/><path d="M17 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>',
};

// ── Main Render ────────────────────────────────────────────────────────────

function render() {
  document.getElementById('root').innerHTML = '';
  renderHeader();
  renderMain();
  bindGlobalEvents();
}

function renderHeader() {
  const header = document.querySelector('header');
  header.innerHTML = `
    <div class="logo">
      ${svg(ICONS.music, 22)}
      <span>MusicDL</span>
    </div>
  `;
}

function renderMain() {
  const main = document.getElementById('root');
  main.innerHTML = '';
  main.appendChild(renderUrlSection());
  main.appendChild(renderTemplateSection());
  main.appendChild(renderSettingsSection());

  if (state.fetchLoading) {
    main.appendChild(renderSkeleton());
  } else if (state.tracks.length > 0) {
    main.appendChild(renderTrackTable());
    main.appendChild(renderDownloadActions());
  }

  if (state.activeJobId || state.jobStatus) {
    main.appendChild(renderProgressSection());
  }

  main.appendChild(renderHistorySection());
  main.appendChild(renderMemorial());
}

// ── URL Section ────────────────────────────────────────────────────────────

function renderUrlSection() {
  const wrap = document.createElement('div');
  wrap.className = 'card';
  wrap.innerHTML = `
    <div class="card-header">
      <span class="card-title">URL</span>
    </div>
    <div class="url-area">
      <div class="url-input-wrap">
        <input
          type="url"
          id="url-input"
          class="url-input"
          placeholder="Paste a Spotify or YouTube track, album, or playlist URL…"
          value="${state.lastUrl || ''}"
          aria-label="URL input"
          autocomplete="off"
        >
      </div>
      <button id="paste-btn" class="btn btn-secondary" title="Paste from clipboard">
        ${svg(ICONS.clipboard, 15)} Paste
      </button>
      <button id="fetch-btn" class="btn btn-primary" ${state.fetchLoading ? 'disabled' : ''}>
        ${state.fetchLoading
          ? '<span class="spinner"></span> Fetching…'
          : `${svg(ICONS.search, 15)} Fetch`}
      </button>
    </div>
    <p class="text-xs text-muted mt-2">
      Tip: drag &amp; drop a URL onto this page, or press <kbd>Enter</kbd> to fetch.
    </p>
  `;

  const input = wrap.querySelector('#url-input');
  const btn = wrap.querySelector('#fetch-btn');
  const pasteBtn = wrap.querySelector('#paste-btn');

  btn.onclick = () => doFetch(input.value.trim());
  input.addEventListener('keydown', e => { if (e.key === 'Enter') doFetch(input.value.trim()); });

  pasteBtn.onclick = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) { input.value = text; input.focus(); }
    } catch {
      toast('Clipboard access denied — use Ctrl+V instead', 'warn');
    }
  };

  // Drag & drop
  wrap.addEventListener('dragover', e => { e.preventDefault(); input.classList.add('drag-over'); });
  wrap.addEventListener('dragleave', () => input.classList.remove('drag-over'));
  wrap.addEventListener('drop', e => {
    e.preventDefault();
    input.classList.remove('drag-over');
    const url = e.dataTransfer.getData('text/plain') || e.dataTransfer.getData('text/uri-list');
    if (url) { input.value = url; doFetch(url.trim()); }
  });

  return wrap;
}

// ── Fetch ──────────────────────────────────────────────────────────────────

async function doFetch(url) {
  if (!url) { toast('Please enter a URL', 'warn'); return; }
  state.lastUrl = url;
  state.fetchLoading = true;
  state.tracks = [];
  state.selectedIds.clear();
  renderMain();

  try {
    const data = await apiFetch('/fetch', {
      method: 'POST',
      body: JSON.stringify({ url }),
    });
    state.tracks = data.tracks;
    state.playlistName = data.playlist_name || '';
    state.selectedIds = new Set(data.tracks.map(t => t.id));
    if (data.tracks.length === 0) {
      toast('No tracks found for this URL', 'warn');
    } else {
      toast(`Found ${data.tracks.length} track${data.tracks.length > 1 ? 's' : ''}`, 'info');
    }
  } catch (err) {
    toast(err.message, 'error', 6000);
  } finally {
    state.fetchLoading = false;
    renderMain();
  }
}

// ── Skeleton ───────────────────────────────────────────────────────────────

function renderSkeleton() {
  const card = document.createElement('div');
  card.className = 'card';
  card.innerHTML = `
    <div class="card-header">
      <span class="card-title">Fetching tracks…</span>
      <span class="spinner"></span>
    </div>
    ${[...Array(4)].map(() => `
      <div style="display:flex;gap:10px;align-items:center;margin-bottom:10px;">
        <div class="skeleton" style="width:36px;height:36px;border-radius:4px;flex-shrink:0;"></div>
        <div style="flex:1;">
          <div class="skeleton" style="height:12px;width:60%;margin-bottom:5px;"></div>
          <div class="skeleton" style="height:10px;width:35%;"></div>
        </div>
        <div class="skeleton" style="width:50px;height:10px;"></div>
      </div>
    `).join('')}
  `;
  return card;
}

// ── Track Table ────────────────────────────────────────────────────────────

function renderTrackTable() {
  const card = document.createElement('div');
  card.className = 'card';

  const selectedCount = state.selectedIds.size;
  const total = state.tracks.length;
  const allSelected = selectedCount === total;

  card.innerHTML = `
    <div class="card-header">
      <span class="card-title">
        ${state.playlistName
          ? `📋 ${state.playlistName} — `
          : ''
        }${total} Track${total !== 1 ? 's' : ''}
      </span>
      <span class="track-count">${selectedCount} selected</span>
    </div>
    <div class="track-controls">
      <button id="select-all-btn" class="btn btn-secondary btn-sm">
        ${allSelected ? 'Deselect All' : 'Select All'}
      </button>
      <button id="invert-btn" class="btn btn-secondary btn-sm">Invert</button>
    </div>
    <div class="track-table-wrap">
      <table class="track-table" role="grid">
        <thead>
          <tr>
            <th><input type="checkbox" class="track-check" id="check-all" ${allSelected ? 'checked' : ''} aria-label="Select all"></th>
            <th>#</th>
            <th></th>
            <th>Title</th>
            <th>Artist</th>
            <th>Album</th>
            <th>Duration</th>
          </tr>
        </thead>
        <tbody id="track-tbody">
          ${state.tracks.map((t, i) => renderTrackRow(t, i)).join('')}
        </tbody>
      </table>
    </div>
  `;

  card.querySelector('#check-all').onchange = e => {
    if (e.target.checked) state.selectedIds = new Set(state.tracks.map(t => t.id));
    else state.selectedIds.clear();
    renderMain();
  };

  card.querySelector('#select-all-btn').onclick = () => {
    if (allSelected) state.selectedIds.clear();
    else state.selectedIds = new Set(state.tracks.map(t => t.id));
    renderMain();
  };

  card.querySelector('#invert-btn').onclick = () => {
    const newSel = new Set();
    for (const t of state.tracks) {
      if (!state.selectedIds.has(t.id)) newSel.add(t.id);
    }
    state.selectedIds = newSel;
    renderMain();
  };

  card.querySelectorAll('.track-row-check').forEach(cb => {
    cb.onchange = () => {
      const id = cb.dataset.id;
      if (cb.checked) state.selectedIds.add(id);
      else state.selectedIds.delete(id);
      renderMain();
    };
  });

  card.querySelectorAll('.no-match-btn').forEach(btn => {
    btn.onclick = () => openManualUrlModal(btn.dataset.id);
  });

  return card;
}

function renderTrackRow(track, index) {
  const sel = state.selectedIds.has(track.id);
  const artSrc = track.album_art_url
    ? `<img src="${track.album_art_url}" class="album-art-thumb" loading="lazy" alt="">`
    : `<div class="no-art">♪</div>`;

  return `
    <tr class="${sel ? 'selected' : ''}" data-id="${track.id}">
      <td><input type="checkbox" class="track-check track-row-check" data-id="${track.id}" ${sel ? 'checked' : ''} aria-label="Select ${track.title}"></td>
      <td class="track-num">${track.playlist_index || index + 1}</td>
      <td class="album-art-cell">${artSrc}</td>
      <td title="${track.title}">${track.title || '—'}</td>
      <td title="${track.artist}">${track.artist || '—'}</td>
      <td title="${track.album}" class="text-muted">${track.album || '—'}</td>
      <td class="duration-cell">${fmtDuration(track.duration_ms)}</td>
    </tr>
  `;
}

// ── Template Section ───────────────────────────────────────────────────────

function renderTemplateSection() {
  const card = document.createElement('div');
  card.className = 'card';

  const sampleTrack = state.tracks[0] || null;
  const preview = sampleTrack
    ? sanitizePreview(previewTemplate(state.filenameTemplate, sampleTrack))
    : state.filenameTemplate;

  card.innerHTML = `
    <div class="card-header">
      <span class="card-title">Filename Template</span>
      <div style="position:relative;">
        <button class="tokens-btn" id="tokens-btn">{} Tokens</button>
        <div class="tokens-popup" id="tokens-popup"></div>
      </div>
    </div>
    <div class="template-area">
      <select class="preset-select" id="preset-select" title="Template presets">
        <option value="">— Presets —</option>
        ${state.presets.map(p => `<option value="${p.template}">${p.label}</option>`).join('')}
      </select>
      <input
        type="text"
        id="template-input"
        class="template-input"
        value="${state.filenameTemplate}"
        placeholder="{artist} - {title}"
        spellcheck="false"
        aria-label="Filename template"
      >
    </div>
    <div class="template-preview">
      Preview: <span>${preview}.mp3</span>
    </div>
  `;

  const templateInput = card.querySelector('#template-input');
  const previewEl = card.querySelector('.template-preview span');

  templateInput.oninput = () => {
    state.filenameTemplate = templateInput.value;
    saveSettings();
    const p = sampleTrack
      ? sanitizePreview(previewTemplate(state.filenameTemplate, sampleTrack))
      : state.filenameTemplate;
    previewEl.textContent = `${p}.${state.format}`;
  };

  card.querySelector('#preset-select').onchange = e => {
    if (e.target.value) {
      state.filenameTemplate = e.target.value;
      templateInput.value = e.target.value;
      const p = sampleTrack
        ? sanitizePreview(previewTemplate(state.filenameTemplate, sampleTrack))
        : state.filenameTemplate;
      previewEl.textContent = `${p}.${state.format}`;
      saveSettings();
    }
  };

  const tokensBtn = card.querySelector('#tokens-btn');
  const tokensPopup = card.querySelector('#tokens-popup');

  tokensPopup.innerHTML = `
    <div style="font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:8px;">Click a token to insert</div>
    ${state.availableTokens.map(t =>
      `<span class="token-pill" data-token="{${t.token}}" title="${t.description}: e.g. ${t.example}">{${t.token}}</span>`
    ).join('')}
  `;

  tokensBtn.onclick = e => {
    e.stopPropagation();
    tokensPopup.classList.toggle('open');
  };

  tokensPopup.querySelectorAll('.token-pill').forEach(pill => {
    pill.onclick = () => {
      const token = pill.dataset.token;
      const pos = templateInput.selectionStart;
      const before = templateInput.value.slice(0, pos);
      const after = templateInput.value.slice(templateInput.selectionEnd);
      templateInput.value = before + token + after;
      templateInput.selectionStart = templateInput.selectionEnd = pos + token.length;
      templateInput.focus();
      templateInput.dispatchEvent(new Event('input'));
      tokensPopup.classList.remove('open');
    };
  });

  document.addEventListener('click', () => tokensPopup.classList.remove('open'), { once: false });

  return card;
}

// ── Settings Section ───────────────────────────────────────────────────────

function renderSettingsSection() {
  const card = document.createElement('div');
  card.className = 'card';

  const totalMs = state.tracks
    .filter(t => state.selectedIds.has(t.id))
    .reduce((sum, t) => sum + (t.duration_ms || 0), 0);

  card.innerHTML = `
    <div class="card-header">
      <span class="card-title">Audio Settings</span>
      <span class="size-estimate">${totalMs ? estimateSize(totalMs, state.format, state.quality) : ''}</span>
    </div>
    <div class="settings-row">
      <div class="setting-group">
        <span class="setting-label">Format</span>
        <select class="setting-select" id="format-sel" aria-label="Audio format">
          ${['mp3','flac','wav','ogg','m4a'].map(f =>
            `<option value="${f}" ${state.format === f ? 'selected' : ''}>${f.toUpperCase()}</option>`
          ).join('')}
        </select>
      </div>
      <div class="setting-group" id="quality-group" ${['flac','wav'].includes(state.format) ? 'style="opacity:.4;pointer-events:none"' : ''}>
        <span class="setting-label">Bitrate</span>
        <select class="setting-select" id="quality-sel" aria-label="Audio quality">
          ${[['128','128 kbps'],['192','192 kbps'],['256','256 kbps'],['320','320 kbps (best)'],['best','Best available']].map(([v, l]) =>
            `<option value="${v}" ${state.quality === v ? 'selected' : ''}>${l}</option>`
          ).join('')}
        </select>
      </div>
    </div>
    <div class="toggle-wrap">
      <input type="checkbox" class="toggle" id="normalize-tog" ${state.normalizeAudio ? 'checked' : ''}>
      <label for="normalize-tog">Normalize audio levels (ffmpeg loudnorm)</label>
    </div>
    <div class="toggle-wrap">
      <input type="checkbox" class="toggle" id="artwork-tog" ${state.embedArtwork ? 'checked' : ''}>
      <label for="artwork-tog">Embed album artwork</label>
    </div>
  `;

  card.querySelector('#format-sel').onchange = e => {
    state.format = e.target.value;
    saveSettings();
    renderMain();
  };
  card.querySelector('#quality-sel').onchange = e => {
    state.quality = e.target.value;
    saveSettings();
  };
  card.querySelector('#normalize-tog').onchange = e => {
    state.normalizeAudio = e.target.checked;
    saveSettings();
  };
  card.querySelector('#artwork-tog').onchange = e => {
    state.embedArtwork = e.target.checked;
    saveSettings();
  };

  return card;
}

// ── Download Actions ───────────────────────────────────────────────────────

function renderDownloadActions() {
  const wrap = document.createElement('div');
  wrap.className = 'card';
  const isRunning = state.jobStatus === 'running';

  wrap.innerHTML = `
    <div class="download-actions">
      <button id="dl-selected-btn" class="btn btn-primary" ${state.selectedIds.size === 0 || isRunning ? 'disabled' : ''}>
        ${svg(ICONS.download, 15)} Download Selected (${state.selectedIds.size})
      </button>
      <button id="dl-all-btn" class="btn btn-secondary" ${state.tracks.length === 0 || isRunning ? 'disabled' : ''}>
        ${svg(ICONS.download, 15)} Download All (${state.tracks.length})
      </button>
      ${isRunning
        ? `<button id="cancel-btn" class="btn btn-danger">${svg(ICONS.x, 15)} Cancel</button>`
        : ''
      }
      ${state.jobStatus === 'done' && state.activeJobId
        ? `<button id="dl-zip-btn" class="btn btn-secondary">
            ${svg(ICONS.archive, 15)} Download ZIP
           </button>`
        : ''
      }
    </div>
  `;

  wrap.querySelector('#dl-selected-btn')?.addEventListener('click', () => {
    const tracks = state.tracks.filter(t => state.selectedIds.has(t.id));
    startDownload(tracks);
  });
  wrap.querySelector('#dl-all-btn')?.addEventListener('click', () => startDownload(state.tracks));
  wrap.querySelector('#cancel-btn')?.addEventListener('click', cancelDownload);
  wrap.querySelector('#dl-zip-btn')?.addEventListener('click', () => {
    window.open(`${API}/batch/${state.activeJobId}`, '_blank');
  });

  return wrap;
}

// ── Download Logic ─────────────────────────────────────────────────────────

async function startDownload(tracks) {
  if (!tracks.length) { toast('No tracks selected', 'warn'); return; }

  state.trackProgress = {};
  tracks.forEach(t => {
    state.trackProgress[t.id] = { status: 'queued', progress: 0, message: '', error: null };
  });
  state.logLines = [];
  state.jobStatus = 'running';
  renderMain();

  try {
    const data = await apiFetch('/download', {
      method: 'POST',
      body: JSON.stringify({
        tracks,
        settings: {
          format: state.format,
          quality: state.quality,
          filename_template: state.filenameTemplate,
          normalize_audio: state.normalizeAudio,
          embed_artwork: state.embedArtwork,
          download_thumbnail: state.downloadThumbnail,
        },
      }),
    });

    state.activeJobId = data.job_id;
    renderMain();
    subscribeSSE(data.job_id, tracks);
  } catch (err) {
    toast(err.message, 'error');
    state.jobStatus = null;
    renderMain();
  }
}

async function cancelDownload() {
  if (!state.activeJobId) return;
  try {
    await apiFetch(`/cancel/${state.activeJobId}`, { method: 'POST' });
    toast('Download cancelled', 'warn');
  } catch (err) {
    toast(err.message, 'error');
  }
}

// ── SSE ────────────────────────────────────────────────────────────────────

let _sseSource = null;

function subscribeSSE(jobId, tracks) {
  if (_sseSource) _sseSource.close();

  const es = new EventSource(`${API}/status/${jobId}`);
  _sseSource = es;

  es.addEventListener('track_update', e => {
    const d = JSON.parse(e.data);
    state.trackProgress[d.track_id] = {
      status: d.status,
      progress: d.progress,
      message: d.message,
      error: d.error || null,
    };
    updateProgressUI();
  });

  es.addEventListener('job_update', e => {
    const d = JSON.parse(e.data);
    if (d.status === 'done') {
      state.jobStatus = 'done';
      toast(`Download complete! ${d.completed_tracks} tracks done, ${d.failed_tracks} failed.`, 'info');
      // Add to history
      tracks.forEach(t => {
        if (state.trackProgress[t.id]?.status === 'done') {
          state.history.unshift({
            title: t.title,
            artist: t.artist,
            format: state.format,
            timestamp: Date.now(),
            jobId,
            trackId: t.id,
          });
        }
      });
      saveHistory();
      es.close();
      renderMain();
    } else if (d.status === 'cancelled') {
      state.jobStatus = 'cancelled';
      toast('Download cancelled', 'warn');
      es.close();
      renderMain();
    } else {
      updateProgressUI();
    }
  });

  es.addEventListener('log', e => {
    const d = JSON.parse(e.data);
    addLog(d.message, 'warn');
  });

  es.addEventListener('done', () => {
    es.close();
    _sseSource = null;
  });

  es.onerror = () => {
    if (state.jobStatus !== 'done' && state.jobStatus !== 'cancelled') {
      addLog('Connection lost. Progress may continue in background.', 'error');
    }
  };
}

function updateProgressUI() {
  // Update track progress items without full re-render
  const container = document.getElementById('track-progress-container');
  if (!container) return;

  const completed = Object.values(state.trackProgress).filter(p => p.status === 'done').length;
  const total = Object.keys(state.trackProgress).length;
  const failed = Object.values(state.trackProgress).filter(p => p.status === 'error').length;

  // Overall bar
  const overallPct = total ? (completed / total) * 100 : 0;
  const overallBar = document.getElementById('overall-bar');
  const overallText = document.getElementById('overall-text');
  if (overallBar) overallBar.style.width = `${overallPct}%`;
  if (overallText) overallText.textContent = `${completed} / ${total} complete${failed ? ` (${failed} failed)` : ''}`;

  // Per-track items
  for (const [tid, prog] of Object.entries(state.trackProgress)) {
    const item = document.getElementById(`tp-${tid}`);
    if (!item) continue;
    const bar = item.querySelector('.progress-bar');
    const badge = item.querySelector('.status-badge');
    const msg = item.querySelector('.track-progress-msg');
    if (bar) bar.style.width = `${prog.progress}%`;
    if (badge) {
      badge.className = `status-badge badge-${prog.status}`;
      badge.textContent = prog.status;
    }
    if (msg) msg.textContent = prog.message || '';
    item.className = `track-progress-item ${prog.status === 'done' ? 'done' : prog.status === 'error' ? 'error' : ''}`;
    if (prog.status === 'done') {
      // Show individual download link
      const dlBtn = item.querySelector('.track-dl-btn');
      if (dlBtn) dlBtn.classList.remove('hidden');
    }
  }
}

// ── Progress Section ───────────────────────────────────────────────────────

function renderProgressSection() {
  const card = document.createElement('div');
  card.className = 'card';

  const trackIds = Object.keys(state.trackProgress);
  const completed = trackIds.filter(id => state.trackProgress[id]?.status === 'done').length;
  const failed = trackIds.filter(id => state.trackProgress[id]?.status === 'error').length;
  const total = trackIds.length;
  const overallPct = total ? (completed / total) * 100 : 0;

  const statusText = state.jobStatus === 'done' ? 'Complete'
    : state.jobStatus === 'cancelled' ? 'Cancelled'
    : 'Downloading…';

  card.innerHTML = `
    <div class="card-header">
      <span class="card-title">Progress — ${statusText}</span>
      <button class="collapsible-btn ${state.showLog ? 'open' : ''}" id="log-toggle">
        ${svg(ICONS.list, 13)} Console
        ${svg(ICONS.chevron, 13)}
      </button>
    </div>

    <div class="overall-progress-wrap">
      <div class="overall-info">
        <span id="overall-text">${completed} / ${total} complete${failed ? ` (${failed} failed)` : ''}</span>
        <span>${overallPct.toFixed(0)}%</span>
      </div>
      <div class="progress-bar-wrap">
        <div class="progress-bar" id="overall-bar" style="width:${overallPct}%"></div>
      </div>
    </div>

    <div class="track-progress-list" id="track-progress-container">
      ${state.tracks
        .filter(t => state.trackProgress[t.id])
        .map(t => renderTrackProgressItem(t))
        .join('')}
    </div>

    <div class="log-console ${state.showLog ? 'open' : ''}" id="log-console">
      ${state.logLines.map(l => `<div class="log-line ${l.type}">${escHtml(l.msg)}</div>`).join('')}
    </div>
  `;

  card.querySelector('#log-toggle').onclick = () => {
    state.showLog = !state.showLog;
    const btn = card.querySelector('#log-toggle');
    const log = card.querySelector('#log-console');
    btn.classList.toggle('open', state.showLog);
    log.classList.toggle('open', state.showLog);
  };

  return card;

  function renderTrackProgressItem(track) {
    const prog = state.trackProgress[track.id] || { status: 'queued', progress: 0, message: '' };
    return `
      <div class="track-progress-item ${prog.status === 'done' ? 'done' : prog.status === 'error' ? 'error' : ''}"
           id="tp-${track.id}">
        <div class="track-progress-header">
          <span class="track-progress-title" title="${track.title} — ${track.artist}">
            ${track.title} <span class="text-muted text-xs">— ${track.artist}</span>
          </span>
          <span class="status-badge badge-${prog.status}">${prog.status}</span>
          <a href="${API}/download/${state.activeJobId}/${track.id}"
             class="btn btn-sm btn-secondary track-dl-btn ${prog.status === 'done' ? '' : 'hidden'}"
             download title="Download this track">
            ${svg(ICONS.download, 13)}
          </a>
        </div>
        <div class="progress-bar-wrap">
          <div class="progress-bar" style="width:${prog.progress}%"></div>
        </div>
        <div class="track-progress-msg">${prog.message || ''}</div>
      </div>
    `;
  }
}

function addLog(msg, type = 'info') {
  state.logLines.push({ msg, type });
  const el = document.getElementById('log-console');
  if (el) {
    const line = document.createElement('div');
    line.className = `log-line ${type}`;
    line.textContent = msg;
    el.appendChild(line);
    el.scrollTop = el.scrollHeight;
  }
}

// ── History Section ────────────────────────────────────────────────────────

function renderHistorySection() {
  if (!state.history.length) return document.createDocumentFragment();

  const card = document.createElement('div');
  card.className = 'card';
  card.innerHTML = `
    <div class="card-header">
      <span class="card-title">${svg(ICONS.list, 14)} Download History (this session)</span>
      <div style="display:flex;gap:8px;">
        <button class="collapsible-btn ${state.showHistory ? 'open' : ''}" id="hist-toggle">
          ${svg(ICONS.chevron, 13)}
        </button>
        <button class="btn btn-sm btn-secondary" id="clear-hist">
          ${svg(ICONS.trash, 13)} Clear
        </button>
      </div>
    </div>
    <div id="history-list" ${state.showHistory ? '' : 'class="hidden"'}>
      ${state.history.slice(0, 20).map(h => `
        <div class="history-item">
          <div class="history-info">
            <div class="history-title">${escHtml(h.title)}</div>
            <div class="history-meta">${escHtml(h.artist)} · ${h.format.toUpperCase()} · ${new Date(h.timestamp).toLocaleTimeString()}</div>
          </div>
          <a href="${API}/download/${h.jobId}/${h.trackId}"
             class="btn btn-sm btn-secondary" download title="Re-download">
            ${svg(ICONS.download, 13)}
          </a>
        </div>
      `).join('')}
    </div>
  `;

  card.querySelector('#hist-toggle').onclick = () => {
    state.showHistory = !state.showHistory;
    card.querySelector('#history-list').classList.toggle('hidden', !state.showHistory);
    card.querySelector('#hist-toggle').classList.toggle('open', state.showHistory);
  };

  card.querySelector('#clear-hist').onclick = () => {
    state.history = [];
    saveHistory();
    renderMain();
  };

  return card;
}

// ── Manual URL Modal ───────────────────────────────────────────────────────

function openManualUrlModal(trackId) {
  const track = state.tracks.find(t => t.id === trackId);
  if (!track) return;

  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal" role="dialog" aria-modal="true" aria-label="Set YouTube URL">
      <h3>Set YouTube URL for "${track.title}"</h3>
      <p class="text-muted" style="margin-bottom:10px;font-size:12px;">
        Couldn't auto-match this track. Paste the YouTube URL manually.
      </p>
      <input type="url" id="manual-url" placeholder="https://www.youtube.com/watch?v=...">
      <div class="modal-actions">
        <button class="btn btn-secondary" id="modal-cancel">Cancel</button>
        <button class="btn btn-primary" id="modal-save">Save</button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);
  overlay.querySelector('#modal-cancel').onclick = () => overlay.remove();
  overlay.querySelector('#modal-save').onclick = () => {
    const url = overlay.querySelector('#manual-url').value.trim();
    if (url) {
      const t = state.tracks.find(t => t.id === trackId);
      if (t) t.youtube_url = url;
      overlay.remove();
      toast('YouTube URL saved', 'info');
    }
  };
  overlay.onclick = e => { if (e.target === overlay) overlay.remove(); };
}

// ── Memorial ───────────────────────────────────────────────────────────────

function renderMemorial() {
  const section = document.createElement('div');
  section.className = 'memorial';
  const names = [
    'RIP JAY DEE',
    'RIP PROOF',
    'RIP BAATIN',
    'RIP PHIFE',
    'RIP DOOM',
    'RIP AMP FIDDLER',
    'RIP ROY HARGROVE',
    'RIP TRUGOY',
    'RIP ROY AYERS',
    'RIP D\'ANGELO',
    'RIP BOB POWER',
  ];
  section.innerHTML = names.map(n => `<span>${n}</span>`).join('');
  return section;
}

// ── Global Events ──────────────────────────────────────────────────────────

function bindGlobalEvents() {
  // Global drag & drop
  document.body.addEventListener('dragover', e => e.preventDefault());
  document.body.addEventListener('drop', e => {
    e.preventDefault();
    const url = e.dataTransfer.getData('text/plain') || e.dataTransfer.getData('text/uri-list');
    if (url) {
      const input = document.getElementById('url-input');
      if (input) { input.value = url; doFetch(url.trim()); }
    }
  });

  // Keyboard shortcuts
  document.addEventListener('keydown', e => {
    if (e.ctrlKey && e.key === 'Enter') {
      // Ctrl+Enter: download all
      if (state.tracks.length && state.jobStatus !== 'running') {
        startDownload(state.tracks);
      }
    }
  });
}

// ── Utility ────────────────────────────────────────────────────────────────

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Init ───────────────────────────────────────────────────────────────────

async function init() {
  loadSettings();

  // Fetch tokens and presets from backend
  try {
    const data = await apiFetch('/tokens');
    state.availableTokens = data.tokens;
    state.presets = data.presets;
  } catch {
    // Fallback tokens
    state.availableTokens = [
      {token:'title',description:'Song title',example:'Bohemian Rhapsody'},
      {token:'artist',description:'Artist',example:'Queen'},
      {token:'album',description:'Album',example:'A Night at the Opera'},
      {token:'year',description:'Year',example:'1975'},
      {token:'track_number',description:'Track number',example:'01'},
    ];
    state.presets = [
      {template:'{artist} - {title}', label:'Simple'},
      {template:'{track_number}. {title}', label:'Track listing'},
      {template:'{artist} - {album} - {track_number} {title}', label:'Full detail'},
    ];
  }

  // Check backend health
  try {
    const health = await apiFetch('/health');
    if (health.warnings?.length) {
      health.warnings.forEach(w => toast(w, 'warn', 8000));
    }
  } catch {
    toast('Backend unavailable. Is the server running?', 'error', 10000);
  }

  render();
}

init();
