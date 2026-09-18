// Plex Duplicate Finder - Frontend Application Logic

let availableDrives = [];
let selectedDriveRoots = new Set();
let duplicateGroups = [];
let selectedFilesForDeletion = new Map(); // path -> {size, filename}
let scanPollInterval = null;
let currentFilter = 'all';

// DOM Elements
const drivesGrid = document.getElementById('drives-grid');
const btnSelectPlex = document.getElementById('btn-select-plex');
const btnSelectAll = document.getElementById('btn-select-all');
const btnDeselectAll = document.getElementById('btn-deselect-all');
const inputMinSize = document.getElementById('input-min-size');
const btnStartScan = document.getElementById('btn-start-scan');
const btnCancelScan = document.getElementById('btn-cancel-scan');
const scanProgressBanner = document.getElementById('scan-progress-banner');
const scanProgressBar = document.getElementById('scan-progress-bar');
const scanProgressPct = document.getElementById('scan-progress-pct');
const progDriveInfo = document.getElementById('prog-drive-info');
const scanStatusText = document.getElementById('scan-status-text');
const scanCurrentPath = document.getElementById('scan-current-path');
const progScannedCount = document.getElementById('prog-scanned-count');
const progMediaCount = document.getElementById('prog-media-count');

const duplicateGroupsList = document.getElementById('duplicate-groups-list');
const totalReclaimableVal = document.getElementById('total-reclaimable-val');
const totalGroupsVal = document.getElementById('total-groups-val');
const badgeGroupsCount = document.getElementById('badge-groups-count');
const filterCountAll = document.getElementById('filter-count-all');
const filterCountExact = document.getElementById('filter-count-exact');
const filterCountQuality = document.getElementById('filter-count-quality');

const btnSmartSelect = document.getElementById('btn-smart-select');
const btnClearSelection = document.getElementById('btn-clear-selection');
const btnDeleteSelected = document.getElementById('btn-delete-selected');
const selectedCountEl = document.getElementById('selected-count');
const selectedSizeEl = document.getElementById('selected-size');

// Modal Elements
const modalDelete = document.getElementById('modal-delete');
const btnModalClose = document.getElementById('btn-modal-close');
const btnModalCancel = document.getElementById('btn-modal-cancel');
const btnModalConfirm = document.getElementById('btn-modal-confirm');
const checkConfirmAction = document.getElementById('check-confirm-action');
const modalDeleteCount = document.getElementById('modal-delete-count');
const modalDeleteReclaim = document.getElementById('modal-delete-reclaim');
const modalFileList = document.getElementById('modal-file-list');

// Init
document.addEventListener('DOMContentLoaded', () => {
  loadDrives();
  setupEventListeners();
  initScanState();
});

// Restore cached scan results or resume active scan on page load
async function initScanState() {
  try {
    const res = await fetch('/api/scan/status');
    const data = await res.json();
    if (data.status === 'ok') {
      // If a scan was already running when user opened page, resume tracking
      if (data.is_scanning) {
        btnStartScan.classList.add('hidden');
        btnCancelScan.classList.remove('hidden');
        scanProgressBanner.classList.remove('hidden');

        if (scanPollInterval) clearInterval(scanPollInterval);
        scanPollInterval = setInterval(pollScanStatus, 800);
      }

      // If cached duplicate results exist, immediately restore and display them!
      if (data.duplicate_groups && data.duplicate_groups.length > 0) {
        duplicateGroups = data.duplicate_groups;
        updateStats();
        renderDuplicateGroups();
      }
    }
  } catch (err) {
    console.error('Failed to initialize scan state:', err);
  }
}

function setupEventListeners() {
  // Event delegation for drive cards to prevent inline JS backslash escaping issues
  drivesGrid.addEventListener('click', (e) => {
    const card = e.target.closest('.drive-card');
    if (!card) return;
    const letter = card.getAttribute('data-letter');
    if (letter) {
      toggleDriveByLetter(letter);
    }
  });

  btnSelectPlex.addEventListener('click', () => {
    selectedDriveRoots.clear();
    availableDrives.forEach(d => {
      const labelLower = (d.label || '').toLowerCase();
      // Select drives containing 'plex', 'wd', or known Plex drive letters
      if (d.is_plex_drive || labelLower.includes('plex') || labelLower.includes('wd') || d.letter === 'J') {
        selectedDriveRoots.add(d.root);
      }
    });
    saveSelectedDrives();
    renderDrives();
  });

  btnSelectAll.addEventListener('click', () => {
    availableDrives.forEach(d => selectedDriveRoots.add(d.root));
    saveSelectedDrives();
    renderDrives();
  });

  btnDeselectAll.addEventListener('click', () => {
    selectedDriveRoots.clear();
    saveSelectedDrives();
    renderDrives();
  });

  btnStartScan.addEventListener('click', startScan);
  btnCancelScan.addEventListener('click', cancelScan);

  // Filter tabs
  document.querySelectorAll('.filter-tab').forEach(tab => {
    tab.addEventListener('click', (e) => {
      document.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
      e.target.classList.add('active');
      currentFilter = e.target.getAttribute('data-filter');
      renderDuplicateGroups();
    });
  });

  btnSmartSelect.addEventListener('click', autoSelectLowerQuality);
  btnClearSelection.addEventListener('click', clearSelection);
  // Event delegation for duplicate candidate file selection
  duplicateGroupsList.addEventListener('click', (e) => {
    const row = e.target.closest('.file-row');
    if (!row) return;
    const encodedPath = row.getAttribute('data-encoded-path');
    if (!encodedPath) return;
    const fullPath = decodeURIComponent(encodedPath);
    const item = window.mediaItemsByPath?.get(fullPath);
    if (item) {
      toggleFileSelection(fullPath, item.size_bytes, item.filename);
    }
  });

  btnDeleteSelected.addEventListener('click', openDeleteModal);

  // Modal
  btnModalClose.addEventListener('click', closeDeleteModal);
  btnModalCancel.addEventListener('click', closeDeleteModal);
  checkConfirmAction.addEventListener('change', (e) => {
    btnModalConfirm.disabled = !e.target.checked;
  });
  btnModalConfirm.addEventListener('click', executeSafeDeletion);
}

// Drives Management
async function loadDrives() {
  try {
    const res = await fetch('/api/drives');
    const data = await res.json();
    if (data.status === 'ok') {
      availableDrives = data.drives;

      // Restore saved user drive selections if available
      const savedLetters = getSavedSelectedLetters();
      if (savedLetters && savedLetters.length > 0) {
        selectedDriveRoots.clear();
        availableDrives.forEach(d => {
          if (savedLetters.includes(d.letter)) {
            selectedDriveRoots.add(d.root);
          }
        });
      } else {
        // Default to all Plex drives including J:
        selectedDriveRoots.clear();
        availableDrives.forEach(d => {
          const labelLower = (d.label || '').toLowerCase();
          if (d.is_plex_drive || labelLower.includes('plex') || labelLower.includes('wd') || d.letter === 'J') {
            selectedDriveRoots.add(d.root);
          }
        });
      }
      renderDrives();
    }
  } catch (err) {
    drivesGrid.innerHTML = `<div class="error-msg">Failed to load drives: ${err.message}</div>`;
  }
}

function getSavedSelectedLetters() {
  try {
    const raw = localStorage.getItem('plex_selected_drive_letters');
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

function saveSelectedDrives() {
  try {
    const letters = [];
    availableDrives.forEach(d => {
      if (selectedDriveRoots.has(d.root)) {
        letters.push(d.letter);
      }
    });
    localStorage.setItem('plex_selected_drive_letters', JSON.stringify(letters));
  } catch (e) {
    console.error('Failed to save selected drives:', e);
  }
}

function renderDrives() {
  if (!availableDrives.length) {
    drivesGrid.innerHTML = '<div class="empty-state">No drives detected.</div>';
    return;
  }

  drivesGrid.innerHTML = availableDrives.map(d => {
    const isSelected = selectedDriveRoots.has(d.root);
    const usedPercent = d.used_percent || 0;
    const barClass = usedPercent > 90 ? 'danger' : usedPercent > 75 ? 'warning' : '';
    const freeGb = (d.free_bytes / (1024 ** 3)).toFixed(1);
    const totalGb = (d.total_bytes / (1024 ** 3)).toFixed(1);

    return `
      <div class="drive-card ${isSelected ? 'selected' : ''}" data-letter="${d.letter}" title="Click to ${isSelected ? 'deselect' : 'select'} drive ${d.letter}:">
        <div class="drive-card-top">
          <div class="drive-card-header-left">
            <input type="checkbox" class="drive-card-checkbox" ${isSelected ? 'checked' : ''} data-letter="${d.letter}" onclick="event.stopPropagation(); toggleDriveByLetter('${d.letter}')">
            <div class="drive-title-group">
              <span class="drive-letter-badge">${d.letter}:</span>
              <span class="drive-label" title="${d.label || 'Local Disk'}">${d.label || 'Local Disk'}</span>
            </div>
          </div>
          <span class="drive-fs">${d.filesystem}</span>
        </div>
        <div class="drive-capacity-bar">
          <div class="drive-capacity-fill ${barClass}" style="width: ${usedPercent}%"></div>
        </div>
        <div class="drive-capacity-text">
          <span>${usedPercent}% Used</span>
          <span>${freeGb} GB Free / ${totalGb} GB</span>
        </div>
      </div>
    `;
  }).join('');
}

window.toggleDriveByLetter = function(letter) {
  const drive = availableDrives.find(d => d.letter === letter);
  if (!drive) return;

  if (selectedDriveRoots.has(drive.root)) {
    selectedDriveRoots.delete(drive.root);
  } else {
    selectedDriveRoots.add(drive.root);
  }
  saveSelectedDrives();
  renderDrives();
};

// Scan
async function startScan() {
  if (selectedDriveRoots.size === 0) {
    alert('Please select at least one drive to scan.');
    return;
  }

  const minSizeMb = parseInt(inputMinSize.value, 10) || 50;
  const paths = Array.from(selectedDriveRoots);

  try {
    const res = await fetch('/api/scan/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paths, min_size_mb: minSizeMb })
    });
    const data = await res.json();
    if (data.status === 'started') {
      btnStartScan.classList.add('hidden');
      btnCancelScan.classList.remove('hidden');
      scanProgressBanner.classList.remove('hidden');

      selectedFilesForDeletion.clear();
      updateSelectedCounter();

      if (scanPollInterval) clearInterval(scanPollInterval);
      scanPollInterval = setInterval(pollScanStatus, 800);
    }
  } catch (err) {
    alert('Error starting scan: ' + err.message);
  }
}

async function cancelScan() {
  try {
    await fetch('/api/scan/cancel', { method: 'POST' });
  } catch (err) {
    console.error(err);
  }
}

async function pollScanStatus() {
  try {
    const res = await fetch('/api/scan/status');
    const data = await res.json();

    progScannedCount.textContent = data.total_files_scanned.toLocaleString();
    progMediaCount.textContent = data.total_media_files.toLocaleString();
    scanCurrentPath.textContent = data.current_scanning_path || '';

    // Update Percentage Bar & Badges
    const pct = typeof data.progress_pct === 'number' ? Math.min(100.0, Math.max(0.0, data.progress_pct)) : 0.0;
    scanProgressBar.style.width = `${pct}%`;
    if (scanProgressPct) {
      scanProgressPct.textContent = `${pct.toFixed(1)}%`;
    }

    if (data.current_phase) {
      scanStatusText.textContent = data.current_phase;
    }

    if (progDriveInfo) {
      if (data.total_drives > 0 && data.current_drive_index > 0) {
        progDriveInfo.textContent = `Drive ${data.current_drive_index} of ${data.total_drives}`;
      } else {
        progDriveInfo.textContent = '';
      }
    }

    // Real-time duplicate streaming: render duplicate candidates as soon as they are discovered!
    if (data.duplicate_groups && data.duplicate_groups.length !== duplicateGroups.length) {
      duplicateGroups = data.duplicate_groups;
      updateStats();
      renderDuplicateGroups();
    }

    if (!data.is_scanning) {
      clearInterval(scanPollInterval);
      scanPollInterval = null;

      scanProgressBar.style.width = '100%';
      if (scanProgressPct) scanProgressPct.textContent = '100.0%';

      btnStartScan.classList.remove('hidden');
      btnCancelScan.classList.add('hidden');
      scanProgressBanner.classList.add('hidden');

      duplicateGroups = data.duplicate_groups || [];
      updateStats();
      renderDuplicateGroups();
    }
  } catch (err) {
    console.error('Error polling status:', err);
  }
}

function updateStats() {
  let totalReclaimable = 0;
  let exactCount = 0;
  let qualityCount = 0;

  duplicateGroups.forEach(g => {
    totalReclaimable += g.reclaimable_bytes || 0;
    if (g.type === 'exact_match') exactCount++;
    else qualityCount++;
  });

  totalReclaimableVal.textContent = formatBytes(totalReclaimable);
  totalGroupsVal.textContent = duplicateGroups.length;
  badgeGroupsCount.textContent = `${duplicateGroups.length} Groups`;
  filterCountAll.textContent = duplicateGroups.length;
  filterCountExact.textContent = exactCount;
  filterCountQuality.textContent = qualityCount;
}

// Render Results
function renderDuplicateGroups() {
  const filtered = duplicateGroups.filter(g => {
    if (currentFilter === 'all') return true;
    return g.type === currentFilter;
// Render Results
window.mediaItemsByPath = new Map();

function renderDuplicateGroups() {
  const filtered = duplicateGroups.filter(g => {
    if (currentFilter === 'all') return true;
    return g.type === currentFilter;
  });

  if (!filtered.length) {
    duplicateGroupsList.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">✅</div>
        <h3>No Duplicates in this View</h3>
        <p>No duplicate groups matched your current filter.</p>
      </div>
    `;
    return;
  }

  duplicateGroupsList.innerHTML = filtered.map((group, groupIdx) => {
    // Find best item (highest resolution, then largest size)
    const sortedItems = [...group.items].sort((a, b) => {
      const resRank = { '4K / 2160p': 4, '1080p': 3, '720p': 2, '480p / SD': 1 };
      const rankDiff = (resRank[b.resolution] || 0) - (resRank[a.resolution] || 0);
      if (rankDiff !== 0) return rankDiff;
      return b.size_bytes - a.size_bytes;
    });
    const bestPath = sortedItems[0]?.path;

    const fileRows = group.items.map((item, itemIdx) => {
      window.mediaItemsByPath.set(item.path, item);
      const isSelected = selectedFilesForDeletion.has(item.path);
      const isBest = item.path === bestPath;

      const resBadgeClass = item.resolution.includes('4K') ? 'badge-res-4k' :
                            item.resolution.includes('1080') ? 'badge-res-1080p' : 'badge-res-sd';

      const encodedPath = encodeURIComponent(item.path);

      return `
        <div class="file-row ${isSelected ? 'marked-delete' : ''}" data-encoded-path="${encodedPath}">
          <div>
            <input type="checkbox" id="chk-${groupIdx}-${itemIdx}" class="file-select-checkbox"
              ${isSelected ? 'checked' : ''} 
              data-encoded-path="${encodedPath}">
          </div>
          <div class="file-drive">[Drive ${item.drive}:]</div>
          <div class="file-path-col">
            <div class="file-name" title="${escapeHtml(item.path)}">${escapeHtml(item.filename)}</div>
            <div class="file-parent">${escapeHtml(item.parent_folder)}</div>
          </div>
          <div class="file-badges">
            <span class="badge ${resBadgeClass}">${item.resolution}</span>
            ${item.codec !== 'Unknown' ? `<span class="badge badge-accent">${escapeHtml(item.codec)}</span>` : ''}
            ${isBest ? `<span class="badge badge-keep">⭐ Keep</span>` : ''}
          </div>
          <div class="file-date">${formatDate(item.modified_time)}</div>
          <div class="file-size">${item.size_human}</div>
        </div>
      `;
    }).join('');

    return `
      <div class="duplicate-group-card">
        <div class="group-header">
          <div class="group-title">${escapeHtml(group.title)}</div>
          <div class="group-meta">
            <span class="badge ${group.type === 'exact_match' ? 'badge-res-4k' : 'badge-accent'}">
              ${escapeHtml(group.match_reason)}
            </span>
            <span class="group-reclaimable">Reclaimable: ${group.reclaimable_human}</span>
          </div>
        </div>
        <div class="group-files-list">
          ${fileRows}
        </div>
      </div>
    `;
  }).join('');
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatDate(timestamp) {
  if (!timestamp) return '';
  const d = new Date(timestamp * 1000);
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function formatBytes(bytes) {
  if (!bytes) return '0.00 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (bytes >= 1024 && i < units.length - 1) {
    bytes /= 1024;
    i++;
  }
  return `${bytes.toFixed(2)} ${units[i]}`;
}

// Selection Logic
window.toggleFileSelection = function(path, size, filename) {
  if (selectedFilesForDeletion.has(path)) {
    selectedFilesForDeletion.delete(path);
  } else {
    selectedFilesForDeletion.set(path, { size, filename });
  }
  updateSelectedCounter();
  renderDuplicateGroups();
};

function autoSelectLowerQuality() {
  selectedFilesForDeletion.clear();

  duplicateGroups.forEach(group => {
    // Rank files in group to find the single best one to KEEP
    const sorted = [...group.items].sort((a, b) => {
      const resRank = { '4K / 2160p': 4, '1080p': 3, '720p': 2, '480p / SD': 1 };
      const rankDiff = (resRank[b.resolution] || 0) - (resRank[a.resolution] || 0);
      if (rankDiff !== 0) return rankDiff;
      return b.size_bytes - a.size_bytes;
    });

    // Best item is index 0; mark all others (indices 1..) for deletion
    for (let i = 1; i < sorted.length; i++) {
      const item = sorted[i];
      selectedFilesForDeletion.set(item.path, { size: item.size_bytes, filename: item.filename });
    }
  });

  updateSelectedCounter();
  renderDuplicateGroups();
}

function clearSelection() {
  selectedFilesForDeletion.clear();
  updateSelectedCounter();
  renderDuplicateGroups();
}

function updateSelectedCounter() {
  const count = selectedFilesForDeletion.size;
  let totalBytes = 0;
  for (const info of selectedFilesForDeletion.values()) {
    totalBytes += info.size;
  }

  selectedCountEl.textContent = count;
  selectedSizeEl.textContent = formatBytes(totalBytes);
  btnDeleteSelected.disabled = count === 0;
}

// Deletion Modal
function openDeleteModal() {
  if (selectedFilesForDeletion.size === 0) return;

  const count = selectedFilesForDeletion.size;
  let totalBytes = 0;
  modalFileList.innerHTML = '';

  for (const [path, info] of selectedFilesForDeletion.entries()) {
    totalBytes += info.size;
    const li = document.createElement('li');
    li.textContent = `${info.filename} (${formatBytes(info.size)}) - ${path}`;
    modalFileList.appendChild(li);
  }

  modalDeleteCount.textContent = count;
  modalDeleteReclaim.textContent = formatBytes(totalBytes);
  checkConfirmAction.checked = false;
  btnModalConfirm.disabled = true;

  modalDelete.classList.remove('hidden');
}

function closeDeleteModal() {
  modalDelete.classList.add('hidden');
}

async function executeSafeDeletion() {
  const mode = document.querySelector('input[name="delete_mode"]:checked').value;
  const useRecycleBin = mode === 'recycle_bin';
  const filesToDelete = Array.from(selectedFilesForDeletion.keys());

  btnModalConfirm.disabled = true;
  btnModalConfirm.textContent = 'Removing files...';

  try {
    const res = await fetch('/api/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        files: filesToDelete,
        use_recycle_bin: useRecycleBin
      })
    });
    const data = await res.json();

    if (data.status === 'completed') {
      // Close modal immediately so it disappears from screen
      closeDeleteModal();

      // Clear selections
      selectedFilesForDeletion.clear();
      updateSelectedCounter();

      // Update remaining duplicates list
      duplicateGroups = data.remaining_groups || [];
      updateStats();
      renderDuplicateGroups();

      // Show sleek non-blocking notification
      showToast(`Removed ${filesToDelete.length} duplicate file(s). Reclaimed: ${data.reclaimed_human}`);
    } else {
      alert('Error removing files: ' + (data.message || 'Operation failed.'));
    }
  } catch (err) {
    alert('Error removing files: ' + err.message);
  } finally {
    btnModalConfirm.textContent = 'Confirm Removal';
    btnModalConfirm.disabled = false;
  }
}

function showToast(message) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = `
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" style="color: var(--plex-gold);">
      <circle cx="12" cy="12" r="10" />
      <path d="m9 12 2 2 4-4" />
    </svg>
    <span>${escapeHtml(message)}</span>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(15px)';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}
