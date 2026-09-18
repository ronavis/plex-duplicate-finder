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
});

function setupEventListeners() {
  btnSelectPlex.addEventListener('click', () => {
    selectedDriveRoots.clear();
    availableDrives.forEach(d => {
      if (d.is_plex_drive || d.label.toLowerCase().includes('plex')) {
        selectedDriveRoots.add(d.root);
      }
    });
    renderDrives();
  });

  btnSelectAll.addEventListener('click', () => {
    availableDrives.forEach(d => selectedDriveRoots.add(d.root));
    renderDrives();
  });

  btnDeselectAll.addEventListener('click', () => {
    selectedDriveRoots.clear();
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
  btnDeleteSelected.addEventListener('click', openDeleteModal);

  // Modal
  btnModalClose.addEventListener('click', closeDeleteModal);
  btnModalCancel.addEventListener('click', closeDeleteModal);
  checkConfirmAction.addEventListener('change', (e) => {
    btnModalConfirm.disabled = !e.target.checked;
  });
  btnModalConfirm.addEventListener('click', executeSafeDeletion);
}

// Drives
async function loadDrives() {
  try {
    const res = await fetch('/api/drives');
    const data = await res.json();
    if (data.status === 'ok') {
      availableDrives = data.drives;
      // Default select Plex drives
      availableDrives.forEach(d => {
        if (d.is_plex_drive || d.label.toLowerCase().includes('plex')) {
          selectedDriveRoots.add(d.root);
        }
      });
      renderDrives();
    }
  } catch (err) {
    drivesGrid.innerHTML = `<div class="error-msg">Failed to load drives: ${err.message}</div>`;
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
      <div class="drive-card ${isSelected ? 'selected' : ''}" onclick="toggleDrive('${d.root}')">
        <div class="drive-card-top">
          <div>
            <span class="drive-letter-badge">${d.letter}:</span>
            <span class="drive-label">${d.label || 'Local Disk'}</span>
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

window.toggleDrive = function(root) {
  if (selectedDriveRoots.has(root)) {
    selectedDriveRoots.delete(root);
  } else {
    selectedDriveRoots.add(root);
  }
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

    if (!data.is_scanning) {
      clearInterval(scanPollInterval);
      scanPollInterval = null;

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

  duplicateGroupsList.innerHTML = filtered.map(group => {
    // Find best item (highest resolution, then largest size)
    const sortedItems = [...group.items].sort((a, b) => {
      const resRank = { '4K / 2160p': 4, '1080p': 3, '720p': 2, '480p / SD': 1 };
      const rankDiff = (resRank[b.resolution] || 0) - (resRank[a.resolution] || 0);
      if (rankDiff !== 0) return rankDiff;
      return b.size_bytes - a.size_bytes;
    });
    const bestPath = sortedItems[0]?.path;

    const fileRows = group.items.map(item => {
      const isSelected = selectedFilesForDeletion.has(item.path);
      const isBest = item.path === bestPath;

      const resBadgeClass = item.resolution.includes('4K') ? 'badge-res-4k' :
                            item.resolution.includes('1080') ? 'badge-res-1080p' : 'badge-res-sd';

      return `
        <div class="file-row ${isSelected ? 'marked-delete' : ''}">
          <div>
            <input type="checkbox" id="chk-${btoa(item.path).slice(0, 16)}" 
              ${isSelected ? 'checked' : ''} 
              onchange="toggleFileSelection('${escapePath(item.path)}', ${item.size_bytes}, '${escapePath(item.filename)}')">
          </div>
          <div class="file-drive">[Drive ${item.drive}:]</div>
          <div class="file-path-col">
            <div class="file-name" title="${item.path}">${item.filename}</div>
            <div class="file-parent">${item.parent_folder}</div>
          </div>
          <div class="file-badges">
            <span class="badge ${resBadgeClass}">${item.resolution}</span>
            ${item.codec !== 'Unknown' ? `<span class="badge badge-accent">${item.codec}</span>` : ''}
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
          <div class="group-title">${group.title}</div>
          <div class="group-meta">
            <span class="badge ${group.type === 'exact_match' ? 'badge-res-4k' : 'badge-accent'}">
              ${group.match_reason}
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

function escapePath(path) {
  return (path || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
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
      alert(`Successfully processed ${filesToDelete.length} files!\nReclaimed: ${data.reclaimed_human}`);
      selectedFilesForDeletion.clear();
      updateSelectedCounter();
      closeDeleteModal();

      duplicateGroups = data.remaining_groups || [];
      updateStats();
      renderDuplicateGroups();
    }
  } catch (err) {
    alert('Error removing files: ' + err.message);
  } finally {
    btnModalConfirm.textContent = 'Confirm Removal';
  }
}
