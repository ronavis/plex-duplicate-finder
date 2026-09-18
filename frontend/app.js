// Plex Space Reclaimer - Frontend Application Logic
// Features 1-7 Fully Integrated: Search & Multi-Filter, Plex Server API, Deep Media Stream Inspection,
// Drive Storage Balancer, Explorer Reveal & Quick Video Streaming, Library Cleaner, and Export & Audit Trail.

let availableDrives = [];
let selectedDriveRoots = new Set();
let duplicateGroups = [];
let selectedFilesForDeletion = new Map(); // path -> {size, filename}
let scanPollInterval = null;

// Filter States (Feature 1)
let currentFilter = 'all';
let searchQuery = '';
let selectedFilterDrive = 'all';
let selectedMinReclaimGb = 0;
let searchDebounceTimer = null;

// Feature 4: Balancer State
let balancerPollInterval = null;
let currentBalancerFile = null;

// Feature 6: Cleaner State
let cleanerScanResults = null;
let currentCleanerTab = 'empty_folders';
let selectedCleanerItems = new Set();

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

// Feature 1: Filter Elements
const inputSearchTitle = document.getElementById('input-search-title');
const btnClearSearch = document.getElementById('btn-clear-search');
const selectFilterDrive = document.getElementById('select-filter-drive');
const selectFilterMinSize = document.getElementById('select-filter-min-size');

const btnExportCsv = document.getElementById('btn-export-csv');
const btnSmartSelect = document.getElementById('btn-smart-select');
const btnClearSelection = document.getElementById('btn-clear-selection');
const btnDeleteSelected = document.getElementById('btn-delete-selected');
const selectedCountEl = document.getElementById('selected-count');
const selectedSizeEl = document.getElementById('selected-size');

// Delete Modal Elements
const modalDelete = document.getElementById('modal-delete');
const btnModalClose = document.getElementById('btn-modal-close');
const btnModalCancel = document.getElementById('btn-modal-cancel');
const btnModalConfirm = document.getElementById('btn-modal-confirm');
const checkConfirmAction = document.getElementById('check-confirm-action');
const modalDeleteCount = document.getElementById('modal-delete-count');
const modalDeleteReclaim = document.getElementById('modal-delete-reclaim');
const modalFileList = document.getElementById('modal-file-list');

// Top Nav Action Modals
const btnOpenPlexModal = document.getElementById('btn-open-plex-modal');
const btnOpenCleanerModal = document.getElementById('btn-open-cleaner-modal');
const btnOpenAuditModal = document.getElementById('btn-open-audit-modal');

// Plex Modal
const modalPlex = document.getElementById('modal-plex');
const btnModalPlexClose = document.getElementById('btn-modal-plex-close');
const inputPlexUrl = document.getElementById('input-plex-url');
const inputPlexToken = document.getElementById('input-plex-token');
const checkPlexAutorefresh = document.getElementById('check-plex-autorefresh');
const btnTestPlex = document.getElementById('btn-test-plex');
const btnSavePlex = document.getElementById('btn-save-plex');
const plexTestResult = document.getElementById('plex-test-result');
const plexStatusDot = document.getElementById('plex-status-dot');

// Cleaner Modal
const modalCleaner = document.getElementById('modal-cleaner');
const btnModalCleanerClose = document.getElementById('btn-modal-cleaner-close');
const btnCleanerCancel = document.getElementById('btn-cleaner-cancel');
const selectCleanerDrive = document.getElementById('select-cleaner-drive');
const btnStartCleanerScan = document.getElementById('btn-start-cleaner-scan');
const cleanerResultsContainer = document.getElementById('cleaner-results-container');
const cleanerFoundCount = document.getElementById('cleaner-found-count');
const cleanerReclaimVal = document.getElementById('cleaner-reclaim-val');
const cleanerItemsList = document.getElementById('cleaner-items-list');
const btnCleanerExecute = document.getElementById('btn-cleaner-execute');

// Balancer Modal
const modalBalancer = document.getElementById('modal-balancer');
const btnModalBalancerClose = document.getElementById('btn-modal-balancer-close');
const btnBalancerCancel = document.getElementById('btn-balancer-cancel');
const btnBalancerStart = document.getElementById('btn-balancer-start');
const balancerTargetFilename = document.getElementById('balancer-target-filename');
const balancerTargetSize = document.getElementById('balancer-target-size');
const balancerSourcePath = document.getElementById('balancer-source-path');
const selectBalancerTargetDrive = document.getElementById('select-balancer-target-drive');
const balancerProgressBox = document.getElementById('balancer-progress-box');
const balancerStatusText = document.getElementById('balancer-status-text');
const balancerPctText = document.getElementById('balancer-pct-text');
const balancerBarFill = document.getElementById('balancer-bar-fill');
const balancerSpeedText = document.getElementById('balancer-speed-text');
const balancerEtaText = document.getElementById('balancer-eta-text');

// Audit Modal
const modalAudit = document.getElementById('modal-audit');
const btnModalAuditClose = document.getElementById('btn-modal-audit-close');
const btnModalAuditCancel = document.getElementById('btn-modal-audit-cancel');
const btnClearAudit = document.getElementById('btn-clear-audit');
const auditTableContainer = document.getElementById('audit-table-container');

// Preview Modal
const modalPreview = document.getElementById('modal-preview');
const btnModalPreviewClose = document.getElementById('btn-modal-preview-close');
const previewVideoPlayer = document.getElementById('preview-video-player');
const previewModalTitle = document.getElementById('preview-modal-title');
const previewMetaDetails = document.getElementById('preview-meta-details');

// Inspect Modal
const modalInspect = document.getElementById('modal-inspect');
const btnModalInspectClose = document.getElementById('btn-modal-inspect-close');
const btnModalInspectCloseFooter = document.getElementById('btn-modal-inspect-close-footer');
const inspectContentBox = document.getElementById('inspect-content-box');

// Init
document.addEventListener('DOMContentLoaded', () => {
  loadDrives();
  setupEventListeners();
  initScanState();
  checkPlexInitialStatus();
});

// Restore cached scan results or resume active scan on page load
async function initScanState() {
  try {
    const res = await fetch('/api/scan/status');
    const data = await res.json();
    if (data.status === 'ok') {
      if (data.is_scanning) {
        btnStartScan.classList.add('hidden');
        btnCancelScan.classList.remove('hidden');
        scanProgressBanner.classList.remove('hidden');

        if (scanPollInterval) clearInterval(scanPollInterval);
        scanPollInterval = setInterval(pollScanStatus, 800);
      }

      if (data.duplicate_groups && data.duplicate_groups.length > 0) {
        duplicateGroups = data.duplicate_groups;
        autoSelectLowerQuality(false);
        updateStats();
        renderDuplicateGroups();
      }
    }
  } catch (err) {
    console.error('Failed to initialize scan state:', err);
  }
}

function setupEventListeners() {
  // Drives selection
  drivesGrid.addEventListener('click', (e) => {
    const card = e.target.closest('.drive-card');
    if (!card) return;
    const letter = card.getAttribute('data-letter');
    if (letter) toggleDriveByLetter(letter);
  });

  btnSelectPlex.addEventListener('click', () => {
    selectedDriveRoots.clear();
    availableDrives.forEach(d => {
      const labelLower = (d.label || '').toLowerCase();
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

  // Feature 1: Filter tabs and controls
  document.querySelectorAll('.filter-tab').forEach(tab => {
    tab.addEventListener('click', (e) => {
      document.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
      e.target.classList.add('active');
      currentFilter = e.target.getAttribute('data-filter');
      renderDuplicateGroups();
    });
  });

  if (inputSearchTitle) {
    inputSearchTitle.addEventListener('input', () => {
      searchQuery = inputSearchTitle.value.trim().toLowerCase();
      if (btnClearSearch) btnClearSearch.classList.toggle('hidden', searchQuery.length === 0);
      clearTimeout(searchDebounceTimer);
      searchDebounceTimer = setTimeout(renderDuplicateGroups, 120);
    });
  }

  if (btnClearSearch) {
    btnClearSearch.addEventListener('click', () => {
      inputSearchTitle.value = '';
      searchQuery = '';
      btnClearSearch.classList.add('hidden');
      renderDuplicateGroups();
    });
  }

  if (selectFilterDrive) {
    selectFilterDrive.addEventListener('change', (e) => {
      selectedFilterDrive = e.target.value;
      renderDuplicateGroups();
    });
  }

  if (selectFilterMinSize) {
    selectFilterMinSize.addEventListener('change', (e) => {
      selectedMinReclaimGb = parseFloat(e.target.value) || 0;
      renderDuplicateGroups();
    });
  }

  // Feature 7: Export CSV
  if (btnExportCsv) {
    btnExportCsv.addEventListener('click', () => {
      window.location.href = '/api/export/csv';
      showToast('Exporting duplicates spreadsheet to CSV...');
    });
  }

  btnSmartSelect.addEventListener('click', () => autoSelectLowerQuality(false));
  btnClearSelection.addEventListener('click', clearSelection);

  // High-performance event delegation for duplicate list items & row actions
  duplicateGroupsList.addEventListener('click', handleDuplicateListClick);

  btnDeleteSelected.addEventListener('click', openDeleteModal);

  // Delete Modal
  btnModalClose.addEventListener('click', closeDeleteModal);
  btnModalCancel.addEventListener('click', closeDeleteModal);
  checkConfirmAction.addEventListener('change', (e) => {
    btnModalConfirm.disabled = !e.target.checked;
  });
  btnModalConfirm.addEventListener('click', executeSafeDeletion);

  // Feature 2: Plex Modal Setup
  if (btnOpenPlexModal) btnOpenPlexModal.addEventListener('click', openPlexModal);
  if (btnModalPlexClose) btnModalPlexClose.addEventListener('click', () => modalPlex.classList.add('hidden'));
  if (btnTestPlex) btnTestPlex.addEventListener('click', testPlexConnection);
  if (btnSavePlex) btnSavePlex.addEventListener('click', savePlexConfig);

  // Feature 6: Cleaner Modal Setup
  if (btnOpenCleanerModal) btnOpenCleanerModal.addEventListener('click', openCleanerModal);
  if (btnModalCleanerClose) btnModalCleanerClose.addEventListener('click', () => modalCleaner.classList.add('hidden'));
  if (btnCleanerCancel) btnCleanerCancel.addEventListener('click', () => modalCleaner.classList.add('hidden'));
  if (btnStartCleanerScan) btnStartCleanerScan.addEventListener('click', executeCleanerScan);
  if (btnCleanerExecute) btnCleanerExecute.addEventListener('click', executeCleanerDelete);

  document.querySelectorAll('.cleaner-tab').forEach(tab => {
    tab.addEventListener('click', (e) => {
      document.querySelectorAll('.cleaner-tab').forEach(t => t.classList.remove('active'));
      e.target.classList.add('active');
      currentCleanerTab = e.target.getAttribute('data-tab');
      renderCleanerItems();
    });
  });

  // Feature 4: Balancer Modal Setup
  if (btnModalBalancerClose) btnModalBalancerClose.addEventListener('click', closeBalancerModal);
  if (btnBalancerCancel) btnBalancerCancel.addEventListener('click', cancelOrCloseBalancer);
  if (btnBalancerStart) btnBalancerStart.addEventListener('click', executeBalancerMove);

  // Feature 7: Audit Modal Setup
  if (btnOpenAuditModal) btnOpenAuditModal.addEventListener('click', openAuditModal);
  if (btnModalAuditClose) btnModalAuditClose.addEventListener('click', () => modalAudit.classList.add('hidden'));
  if (btnModalAuditCancel) btnModalAuditCancel.addEventListener('click', () => modalAudit.classList.add('hidden'));
  if (btnClearAudit) btnClearAudit.addEventListener('click', clearAuditHistory);

  // Feature 5: Preview Modal Setup
  if (btnModalPreviewClose) {
    btnModalPreviewClose.addEventListener('click', () => {
      previewVideoPlayer.pause();
      previewVideoPlayer.removeAttribute('src');
      previewVideoPlayer.load();
      modalPreview.classList.add('hidden');
    });
  }

  // Feature 3: Inspect Modal Setup
  if (btnModalInspectClose) btnModalInspectClose.addEventListener('click', () => modalInspect.classList.add('hidden'));
  if (btnModalInspectCloseFooter) btnModalInspectCloseFooter.addEventListener('click', () => modalInspect.classList.add('hidden'));
}

// Drives Management
async function loadDrives() {
  try {
    const res = await fetch('/api/drives');
    const data = await res.json();
    if (data.status === 'ok') {
      availableDrives = data.drives;

      // Populate Drive Dropdown for Feature 1 (Search & Filter)
      if (selectFilterDrive) {
        const prevVal = selectFilterDrive.value;
        selectFilterDrive.innerHTML = '<option value="all">All Drives</option>' +
          availableDrives.map(d => `<option value="${d.letter}">Drive ${d.letter}: (${d.label || 'Local Disk'})</option>`).join('');
        selectFilterDrive.value = prevVal || 'all';
      }

      // Restore saved user drive selections if available
      const savedLetters = getSavedSelectedLetters();
      if (savedLetters && savedLetters.length > 0) {
        selectedDriveRoots.clear();
        availableDrives.forEach(d => {
          if (savedLetters.includes(d.letter)) selectedDriveRoots.add(d.root);
        });
      } else {
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
      if (selectedDriveRoots.has(d.root)) letters.push(d.letter);
    });
    localStorage.setItem('plex_selected_drive_letters', JSON.stringify(letters));
  } catch (e) {
    console.error('Failed to save selected drives:', e);
  }
}

function renderDrives() {
  updateStoragePoolTotals();

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

function updateStoragePoolTotals() {
  let totalBytes = 0;
  let usedBytes = 0;
  let freeBytes = 0;
  let selectedCount = 0;

  availableDrives.forEach(d => {
    if (selectedDriveRoots.has(d.root)) {
      totalBytes += (d.total_bytes || 0);
      usedBytes += (d.used_bytes || 0);
      freeBytes += (d.free_bytes || 0);
      selectedCount++;
    }
  });

  const usedPercent = totalBytes > 0 ? (usedBytes / totalBytes) * 100 : 0;
  const usedPercentFixed = usedPercent.toFixed(1);

  const poolDrivesCountEl = document.getElementById('pool-drives-count');
  const poolTotalCapacityEl = document.getElementById('pool-total-capacity');
  const poolUsedSpaceEl = document.getElementById('pool-used-space');
  const poolUsedPctEl = document.getElementById('pool-used-pct');
  const poolFreeSpaceEl = document.getElementById('pool-free-space');
  const poolMeterFillEl = document.getElementById('pool-meter-fill');
  const headerPoolValEl = document.getElementById('header-pool-val');
  const headerPoolSubEl = document.getElementById('header-pool-sub');

  if (poolDrivesCountEl) poolDrivesCountEl.textContent = `${selectedCount} Drive${selectedCount === 1 ? '' : 's'} Selected`;
  if (poolTotalCapacityEl) poolTotalCapacityEl.textContent = formatBytes(totalBytes);
  if (poolUsedSpaceEl) poolUsedSpaceEl.textContent = formatBytes(usedBytes);
  if (poolUsedPctEl) poolUsedPctEl.textContent = `${usedPercentFixed}%`;
  if (poolFreeSpaceEl) poolFreeSpaceEl.textContent = formatBytes(freeBytes);
  if (poolMeterFillEl) {
    poolMeterFillEl.style.width = `${Math.min(100, usedPercent)}%`;
    poolMeterFillEl.className = 'pool-meter-fill ' + (usedPercent > 90 ? 'danger' : usedPercent > 75 ? 'warning' : 'healthy');
  }

  if (headerPoolValEl) headerPoolValEl.textContent = `${usedPercentFixed}% Full`;
  if (headerPoolSubEl) headerPoolSubEl.textContent = `${formatBytes(freeBytes)} Free / ${formatBytes(totalBytes)}`;
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

    const pct = typeof data.progress_pct === 'number' ? Math.min(100.0, Math.max(0.0, data.progress_pct)) : 0.0;
    scanProgressBar.style.width = `${pct}%`;
    if (scanProgressPct) scanProgressPct.textContent = `${pct.toFixed(1)}%`;

    if (data.current_phase) scanStatusText.textContent = data.current_phase;

    if (progDriveInfo) {
      if (data.total_drives > 0 && data.current_drive_index > 0) {
        progDriveInfo.textContent = `Drive ${data.current_drive_index} of ${data.total_drives}`;
      } else {
        progDriveInfo.textContent = '';
      }
    }

    if (data.duplicate_groups && data.duplicate_groups.length !== duplicateGroups.length) {
      duplicateGroups = data.duplicate_groups;
      autoSelectLowerQuality(false);
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
      autoSelectLowerQuality(false);
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
  filterCountAll.textContent = duplicateGroups.length;
  filterCountExact.textContent = exactCount;
  filterCountQuality.textContent = qualityCount;
}

// Render Results with Feature 1 (Search & Multi-Filters) and Feature 5 (Action Buttons)
window.mediaItemsByPath = new Map();

function renderDuplicateGroups() {
  // Feature 1: Multi-Filter Logic
  const filtered = duplicateGroups.filter(g => {
    // 1. Match type filter
    if (currentFilter !== 'all' && g.type !== currentFilter) return false;

    // 2. Drive filter
    if (selectedFilterDrive !== 'all') {
      const hasDrive = g.items.some(item => (item.drive || '').toUpperCase() === selectedFilterDrive.toUpperCase());
      if (!hasDrive) return false;
    }

    // 3. Minimum Reclaimable Space filter
    if (selectedMinReclaimGb > 0) {
      const groupGb = (g.reclaimable_bytes || 0) / (1024 ** 3);
      if (groupGb < selectedMinReclaimGb) return false;
    }

    // 4. Instant Title Search
    if (searchQuery) {
      const titleMatch = (g.title || '').toLowerCase().includes(searchQuery);
      const fileMatch = g.items.some(it => 
        (it.filename || '').toLowerCase().includes(searchQuery) ||
        (it.parent_folder || '').toLowerCase().includes(searchQuery)
      );
      if (!titleMatch && !fileMatch) return false;
    }

    return true;
  });

  badgeGroupsCount.textContent = `${filtered.length} of ${duplicateGroups.length} Groups`;

  if (!filtered.length) {
    duplicateGroupsList.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🔍</div>
        <h3>No Matching Duplicate Groups</h3>
        <p>No duplicate groups matched your current search and filter criteria.</p>
      </div>
    `;
    return;
  }

  duplicateGroupsList.innerHTML = filtered.map((group, groupIdx) => {
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
          <div class="file-actions-cell" onclick="event.stopPropagation();">
            <button type="button" class="btn-row-action btn-open-folder" data-encoded-path="${encodedPath}" title="Reveal in Windows File Explorer">📁</button>
            <button type="button" class="btn-row-action btn-preview-video" data-encoded-path="${encodedPath}" title="Preview in Media Player">▶</button>
            <button type="button" class="btn-row-action btn-inspect-streams" data-encoded-path="${encodedPath}" title="Inspect Audio/Video/HDR Streams">🔍</button>
            <button type="button" class="btn-row-action btn-balancer-move" data-encoded-path="${encodedPath}" title="Migrate file to another drive">⇄</button>
          </div>
        </div>
      `;
    }).join('');

    const hasSelectedInGroup = group.items.some(it => selectedFilesForDeletion.has(it.path));
    const toggleBtnText = hasSelectedInGroup ? '✕ Deselect Group' : '✓ Select Duplicates';
    const toggleBtnClass = hasSelectedInGroup ? 'btn-group-toggle is-selected' : 'btn-group-toggle';

    return `
      <div class="duplicate-group-card" data-group-idx="${groupIdx}">
        <div class="group-header">
          <div class="group-title">${escapeHtml(group.title)}</div>
          <div class="group-meta">
            <span class="badge ${group.type === 'exact_match' ? 'badge-res-4k' : 'badge-accent'}">
              ${escapeHtml(group.match_reason)}
            </span>
            <span class="group-reclaimable">Reclaimable: ${group.reclaimable_human}</span>
            <button type="button" class="${toggleBtnClass}" data-group-idx="${groupIdx}" title="${hasSelectedInGroup ? 'Click to uncheck all files in this group' : 'Click to check duplicate versions in this group'}">
              ${toggleBtnText}
            </button>
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

// Ultra-fast In-Place Selection & Action Delegator
function handleDuplicateListClick(e) {
  // Action 1: Open in Explorer (Feature 5)
  const btnFolder = e.target.closest('.btn-open-folder');
  if (btnFolder) {
    e.stopPropagation();
    const encoded = btnFolder.getAttribute('data-encoded-path');
    if (encoded) openInWindowsExplorer(decodeURIComponent(encoded));
    return;
  }

  // Action 2: Preview Video (Feature 5)
  const btnPreview = e.target.closest('.btn-preview-video');
  if (btnPreview) {
    e.stopPropagation();
    const encoded = btnPreview.getAttribute('data-encoded-path');
    if (encoded) openVideoPreview(decodeURIComponent(encoded));
    return;
  }

  // Action 3: Inspect Streams (Feature 3)
  const btnInspect = e.target.closest('.btn-inspect-streams');
  if (btnInspect) {
    e.stopPropagation();
    const encoded = btnInspect.getAttribute('data-encoded-path');
    if (encoded) openStreamInspector(decodeURIComponent(encoded));
    return;
  }

  // Action 4: Balancer Move (Feature 4)
  const btnMove = e.target.closest('.btn-balancer-move');
  if (btnMove) {
    e.stopPropagation();
    const encoded = btnMove.getAttribute('data-encoded-path');
    if (encoded) openBalancerModal(decodeURIComponent(encoded));
    return;
  }

  // Action 5: Group toggle button
  const groupBtn = e.target.closest('.btn-group-toggle');
  if (groupBtn) {
    e.stopPropagation();
    const groupCard = groupBtn.closest('.duplicate-group-card');
    if (groupCard) toggleGroupSelection(groupCard);
    return;
  }

  // Action 6: File row selection toggle
  const row = e.target.closest('.file-row');
  if (!row) return;

  const encodedPath = row.getAttribute('data-encoded-path');
  if (!encodedPath) return;
  const fullPath = decodeURIComponent(encodedPath);
  const item = window.mediaItemsByPath?.get(fullPath);
  if (!item) return;

  const isCheckbox = e.target.classList.contains('file-select-checkbox');
  const groupCard = row.closest('.duplicate-group-card');

  if (isCheckbox) {
    const isNowChecked = e.target.checked;
    if (isNowChecked) {
      selectedFilesForDeletion.set(fullPath, { size: item.size_bytes, filename: item.filename });
      row.classList.add('marked-delete');
    } else {
      selectedFilesForDeletion.delete(fullPath);
      row.classList.remove('marked-delete');
    }
  } else {
    const wasChecked = selectedFilesForDeletion.has(fullPath);
    const chk = row.querySelector('.file-select-checkbox');
    if (wasChecked) {
      selectedFilesForDeletion.delete(fullPath);
      row.classList.remove('marked-delete');
      if (chk) chk.checked = false;
    } else {
      selectedFilesForDeletion.set(fullPath, { size: item.size_bytes, filename: item.filename });
      row.classList.add('marked-delete');
      if (chk) chk.checked = true;
    }
  }

  if (groupCard) updateGroupCardHeaderButton(groupCard);
  updateSelectedCounter();
}

function updateGroupCardHeaderButton(groupCard) {
  if (!groupCard) return;
  const btn = groupCard.querySelector('.btn-group-toggle');
  if (!btn) return;
  const hasSelected = groupCard.querySelectorAll('.file-row.marked-delete').length > 0;
  if (hasSelected) {
    btn.textContent = '✕ Deselect Group';
    btn.classList.add('is-selected');
    btn.title = 'Click to uncheck all files in this group';
  } else {
    btn.textContent = '✓ Select Duplicates';
    btn.classList.remove('is-selected');
    btn.title = 'Click to check duplicate versions in this group';
  }
}

function toggleGroupSelection(groupCard) {
  if (!groupCard) return;
  const rows = Array.from(groupCard.querySelectorAll('.file-row'));
  if (!rows.length) return;

  const markedRows = groupCard.querySelectorAll('.file-row.marked-delete');
  const hasSelected = markedRows.length > 0;

  if (hasSelected) {
    rows.forEach(row => {
      const encodedPath = row.getAttribute('data-encoded-path');
      if (!encodedPath) return;
      const fullPath = decodeURIComponent(encodedPath);
      selectedFilesForDeletion.delete(fullPath);
      row.classList.remove('marked-delete');
      const chk = row.querySelector('.file-select-checkbox');
      if (chk) chk.checked = false;
    });
  } else {
    const hasKeepBadge = rows.some(r => r.querySelector('.badge-keep'));
    rows.forEach((row, idx) => {
      const isKeep = hasKeepBadge ? !!row.querySelector('.badge-keep') : (idx === 0);
      if (!isKeep) {
        const encodedPath = row.getAttribute('data-encoded-path');
        if (!encodedPath) return;
        const fullPath = decodeURIComponent(encodedPath);
        const item = window.mediaItemsByPath?.get(fullPath);
        if (item) {
          selectedFilesForDeletion.set(fullPath, { size: item.size_bytes, filename: item.filename });
        }
        row.classList.add('marked-delete');
        const chk = row.querySelector('.file-select-checkbox');
        if (chk) chk.checked = true;
      }
    });
  }

  updateGroupCardHeaderButton(groupCard);
  updateSelectedCounter();
}

function autoSelectLowerQuality(reRender = false) {
  selectedFilesForDeletion.clear();

  duplicateGroups.forEach(group => {
    const sorted = [...group.items].sort((a, b) => {
      const resRank = { '4K / 2160p': 4, '1080p': 3, '720p': 2, '480p / SD': 1 };
      const rankDiff = (resRank[b.resolution] || 0) - (resRank[a.resolution] || 0);
      if (rankDiff !== 0) return rankDiff;
      return b.size_bytes - a.size_bytes;
    });

    for (let i = 1; i < sorted.length; i++) {
      const item = sorted[i];
      selectedFilesForDeletion.set(item.path, { size: item.size_bytes, filename: item.filename });
    }
  });

  updateSelectedCounter();

  if (reRender) {
    renderDuplicateGroups();
  } else {
    const allCards = duplicateGroupsList.querySelectorAll('.duplicate-group-card');
    allCards.forEach(card => {
      const rows = Array.from(card.querySelectorAll('.file-row'));
      const hasKeepBadge = rows.some(r => r.querySelector('.badge-keep'));
      rows.forEach((row, idx) => {
        const isKeep = hasKeepBadge ? !!row.querySelector('.badge-keep') : (idx === 0);
        const shouldDelete = !isKeep;
        row.classList.toggle('marked-delete', shouldDelete);
        const chk = row.querySelector('.file-select-checkbox');
        if (chk) chk.checked = shouldDelete;
      });
      updateGroupCardHeaderButton(card);
    });
  }
}

function clearSelection() {
  selectedFilesForDeletion.clear();
  updateSelectedCounter();

  const markedRows = duplicateGroupsList.querySelectorAll('.file-row.marked-delete');
  markedRows.forEach(row => {
    row.classList.remove('marked-delete');
    const chk = row.querySelector('.file-select-checkbox');
    if (chk) chk.checked = false;
  });

  const groupCards = duplicateGroupsList.querySelectorAll('.duplicate-group-card');
  groupCards.forEach(card => updateGroupCardHeaderButton(card));
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
      closeDeleteModal();
      selectedFilesForDeletion.clear();
      updateSelectedCounter();

      duplicateGroups = data.remaining_groups || [];
      autoSelectLowerQuality(false);
      updateStats();
      renderDuplicateGroups();

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

// ==========================================
// FEATURE 5: Open in Windows Explorer & Quick Video Preview
// ==========================================
async function openInWindowsExplorer(filePath) {
  try {
    showToast('Revealing file in Windows Explorer...');
    const res = await fetch('/api/open_explorer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: filePath })
    });
    const data = await res.json();
    if (data.status !== 'ok') {
      alert('Could not open file in Explorer: ' + (data.message || 'File not found'));
    }
  } catch (err) {
    alert('Failed to launch Explorer: ' + err.message);
  }
}

function openVideoPreview(filePath) {
  const item = window.mediaItemsByPath?.get(filePath);
  previewModalTitle.textContent = item ? item.filename : 'Media Preview';
  previewMetaDetails.innerHTML = `
    <span>${escapeHtml(filePath)}</span>
    <span><strong>${item ? item.resolution : ''}</strong> ${item ? '(' + item.size_human + ')' : ''}</span>
  `;

  // Set stream URL
  const streamUrl = `/api/media/stream?path=${encodeURIComponent(filePath)}`;
  previewVideoPlayer.src = streamUrl;
  modalPreview.classList.remove('hidden');
  previewVideoPlayer.play().catch(e => console.log('Autoplay deferred:', e));
}

// ==========================================
// FEATURE 3: Deep Media Stream Inspector
// ==========================================
async function openStreamInspector(filePath) {
  inspectContentBox.innerHTML = '<div class="loading-placeholder">Reading Matroska / MP4 stream headers...</div>';
  modalInspect.classList.remove('hidden');

  try {
    const res = await fetch('/api/media/inspect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: filePath })
    });
    const data = await res.json();

    if (data.status === 'ok') {
      inspectContentBox.innerHTML = `
        <div style="margin-bottom: 12px;">
          <h4 style="color: var(--text-primary); margin-bottom: 4px;">${escapeHtml(data.filename)}</h4>
          <span style="font-size: 0.76rem; font-family: monospace; color: var(--text-muted);">${escapeHtml(data.path)}</span>
        </div>

        <div class="tech-grid">
          <div class="tech-card">
            <span class="tech-card-label">Container</span>
            <span class="tech-card-val">${data.container}</span>
          </div>
          <div class="tech-card">
            <span class="tech-card-label">Video Codec</span>
            <span class="tech-card-val">${data.video && data.video[0] ? data.video[0].codec : 'Standard Video'}</span>
          </div>
          <div class="tech-card">
            <span class="tech-card-label">HDR / Color Space</span>
            <span class="tech-card-val" style="color: ${data.has_dolby_vision ? 'var(--plex-gold)' : data.has_hdr10 ? '#60a5fa' : 'var(--text-primary)'};">
              ${data.hdr_format}
            </span>
          </div>
          <div class="tech-card">
            <span class="tech-card-label">Primary Audio</span>
            <span class="tech-card-val" style="color: var(--emerald);">${data.primary_audio}</span>
          </div>
          <div class="tech-card">
            <span class="tech-card-label">Audio Channels</span>
            <span class="tech-card-val">${data.audio_channels}</span>
          </div>
          <div class="tech-card">
            <span class="tech-card-label">Exact File Size</span>
            <span class="tech-card-val">${formatBytes(data.file_size_bytes)}</span>
          </div>
        </div>

        <div style="margin-top: 14px; background: rgba(0,0,0,0.3); padding: 10px 14px; border-radius: var(--radius-sm); border: 1px solid var(--border-color); font-size: 0.85rem;">
          <strong style="color: var(--text-primary);">Stream Signature:</strong>
          <span style="color: var(--text-secondary); margin-left: 6px;">${escapeHtml(data.codec_summary)}</span>
        </div>
      `;
    } else {
      inspectContentBox.innerHTML = `<div class="error-msg">${escapeHtml(data.message || 'Inspection failed.')}</div>`;
    }
  } catch (err) {
    inspectContentBox.innerHTML = `<div class="error-msg">Failed to inspect streams: ${err.message}</div>`;
  }
}

// ==========================================
// FEATURE 4: Drive Storage Balancer ("Move to Drive")
// ==========================================
function openBalancerModal(filePath) {
  const item = window.mediaItemsByPath?.get(filePath);
  currentBalancerFile = item || { path: filePath, filename: filePath.split('\\').pop(), size_bytes: 0, drive: filePath[0] };

  balancerTargetFilename.textContent = currentBalancerFile.filename;
  balancerTargetSize.textContent = formatBytes(currentBalancerFile.size_bytes);
  balancerSourcePath.textContent = currentBalancerFile.path;
  balancerProgressBox.classList.add('hidden');
  btnBalancerStart.disabled = false;
  btnBalancerStart.textContent = 'Start Migration';

  // Populate target drives (excluding current drive)
  const currentDriveLetter = (currentBalancerFile.drive || currentBalancerFile.path[0]).toUpperCase();
  const options = availableDrives
    .filter(d => d.letter.toUpperCase() !== currentDriveLetter)
    .map(d => {
      const freeGb = (d.free_bytes / (1024 ** 3)).toFixed(1);
      return `<option value="${d.letter}">Drive ${d.letter}: (${freeGb} GB Free) - ${d.label || 'Storage'}</option>`;
    });

  selectBalancerTargetDrive.innerHTML = options.join('');
  modalBalancer.classList.remove('hidden');
}

function closeBalancerModal() {
  if (balancerPollInterval) {
    clearInterval(balancerPollInterval);
    balancerPollInterval = null;
  }
  modalBalancer.classList.add('hidden');
}

async function cancelOrCloseBalancer() {
  try {
    await fetch('/api/balance/cancel', { method: 'POST' });
  } catch (e) {}
  closeBalancerModal();
}

async function executeBalancerMove() {
  if (!currentBalancerFile) return;

  const targetDrive = selectBalancerTargetDrive.value;
  btnBalancerStart.disabled = true;
  btnBalancerStart.textContent = 'Migrating...';
  balancerProgressBox.classList.remove('hidden');

  try {
    const res = await fetch('/api/balance/move', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_path: currentBalancerFile.path,
        target_drive: targetDrive
      })
    });
    const data = await res.json();

    if (data.status === 'started') {
      if (balancerPollInterval) clearInterval(balancerPollInterval);
      balancerPollInterval = setInterval(pollBalancerStatus, 500);
    } else {
      alert('Could not start migration: ' + (data.message || 'Error occurred.'));
      btnBalancerStart.disabled = false;
      btnBalancerStart.textContent = 'Start Migration';
    }
  } catch (err) {
    alert('Migration failed to start: ' + err.message);
    btnBalancerStart.disabled = false;
  }
}

async function pollBalancerStatus() {
  try {
    const res = await fetch('/api/balance/status');
    const data = await res.json();
    const info = data.balancer;

    if (!info) return;

    balancerPctText.textContent = `${info.progress_pct}%`;
    balancerBarFill.style.width = `${info.progress_pct}%`;
    balancerStatusText.textContent = info.status_message || 'Migrating...';
    balancerSpeedText.textContent = `${info.speed_mbps} MB/s`;
    balancerEtaText.textContent = info.eta_seconds > 0 ? `ETA: ${info.eta_seconds}s` : 'Finishing...';

    if (!info.is_moving) {
      clearInterval(balancerPollInterval);
      balancerPollInterval = null;

      if (info.last_error) {
        alert('File migration failed: ' + info.last_error);
      } else {
        showToast('Successfully migrated file to destination drive!');
        closeBalancerModal();
        loadDrives(); // Refresh storage pool numbers
      }
    }
  } catch (err) {
    console.error('Balancer poll error:', err);
  }
}

// ==========================================
// FEATURE 2: Direct Plex Server API Integration
// ==========================================
async function checkPlexInitialStatus() {
  try {
    const res = await fetch('/api/plex/status');
    const data = await res.json();
    if (data.connection && data.connection.connected) {
      if (plexStatusDot) {
        plexStatusDot.className = 'status-dot dot-green';
        plexStatusDot.title = `Connected to ${data.connection.server_name} (${data.connection.server_url})`;
      }
    } else {
      if (plexStatusDot) plexStatusDot.className = 'status-dot dot-gray';
    }
  } catch (e) {}
}

async function openPlexModal() {
  modalPlex.classList.remove('hidden');
  plexTestResult.classList.add('hidden');

  try {
    const res = await fetch('/api/plex/status');
    const data = await res.json();
    if (data.config) {
      inputPlexUrl.value = data.config.server_url || 'http://127.0.0.1:32400';
      checkPlexAutorefresh.checked = data.config.auto_refresh_on_delete;
    }
  } catch (e) {}
}

async function testPlexConnection() {
  btnTestPlex.disabled = true;
  btnTestPlex.textContent = 'Testing...';
  plexTestResult.className = 'diagnostic-box';
  plexTestResult.classList.remove('hidden');
  plexTestResult.textContent = 'Testing connection to Plex Media Server...';

  try {
    // Save config temporarily to test
    await fetch('/api/plex/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        server_url: inputPlexUrl.value.trim(),
        token: inputPlexToken.value.trim(),
        auto_refresh_on_delete: checkPlexAutorefresh.checked
      })
    });

    const res = await fetch('/api/plex/status');
    const data = await res.json();

    if (data.connection && data.connection.connected) {
      plexTestResult.className = 'diagnostic-box success';
      const sectionsStr = data.sections && data.sections.length > 0 
        ? data.sections.map(s => `• ${s.title} (${s.type})`).join('<br>')
        : 'None detected';

      plexTestResult.innerHTML = `
        <strong>✅ Connected to ${escapeHtml(data.connection.server_name)}!</strong><br>
        Version: ${escapeHtml(data.connection.version)}<br>
        Server URL: ${escapeHtml(data.connection.server_url)}<br>
        <strong>Detected Libraries:</strong><br>${sectionsStr}
      `;
      if (plexStatusDot) plexStatusDot.className = 'status-dot dot-green';
    } else {
      plexTestResult.className = 'diagnostic-box error';
      plexTestResult.innerHTML = `<strong>❌ Connection Failed</strong><br>${escapeHtml(data.connection.error || 'Server unreachable.')}`;
      if (plexStatusDot) plexStatusDot.className = 'status-dot dot-red';
    }
  } catch (err) {
    plexTestResult.className = 'diagnostic-box error';
    plexTestResult.textContent = 'Error: ' + err.message;
  } finally {
    btnTestPlex.disabled = false;
    btnTestPlex.textContent = 'Test Connection';
  }
}

async function savePlexConfig() {
  try {
    const res = await fetch('/api/plex/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        server_url: inputPlexUrl.value.trim(),
        token: inputPlexToken.value.trim(),
        auto_refresh_on_delete: checkPlexAutorefresh.checked
      })
    });
    const data = await res.json();
    if (data.status === 'ok') {
      showToast('Plex server configuration saved!');
      modalPlex.classList.add('hidden');
      checkPlexInitialStatus();
    } else {
      alert('Failed to save config: ' + data.message);
    }
  } catch (err) {
    alert('Error saving config: ' + err.message);
  }
}

// ==========================================
// FEATURE 6: Media Library Cleaner
// ==========================================
function openCleanerModal() {
  modalCleaner.classList.remove('hidden');
  cleanerResultsContainer.classList.add('hidden');
  selectedCleanerItems.clear();

  // Populate drive selector
  selectCleanerDrive.innerHTML = availableDrives
    .map(d => `<option value="${d.root}">Drive ${d.letter}: (${d.label || 'Plex Storage'})</option>`)
    .join('');
}

async function executeCleanerScan() {
  const root = selectCleanerDrive.value;
  btnStartCleanerScan.disabled = true;
  btnStartCleanerScan.textContent = 'Scanning Drive...';

  try {
    const res = await fetch('/api/cleaner/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: root })
    });
    cleanerScanResults = await res.json();

    if (cleanerScanResults.status === 'ok') {
      cleanerResultsContainer.classList.remove('hidden');
      cleanerFoundCount.textContent = `${cleanerScanResults.total_items} items discovered`;
      cleanerReclaimVal.textContent = `Reclaimable: ${cleanerScanResults.total_reclaimable_human}`;

      document.getElementById('cnt-empty-folders').textContent = cleanerScanResults.empty_folders.length;
      document.getElementById('cnt-sample-files').textContent = cleanerScanResults.sample_files.length;
      document.getElementById('cnt-junk-files').textContent = cleanerScanResults.junk_files.length;
      document.getElementById('cnt-orphan-subs').textContent = cleanerScanResults.orphan_subtitles.length;

      // Auto check items by default
      selectedCleanerItems.clear();
      ['empty_folders', 'sample_files', 'junk_files', 'orphan_subtitles'].forEach(k => {
        (cleanerScanResults[k] || []).forEach(it => selectedCleanerItems.add(it.path));
      });

      renderCleanerItems();
    } else {
      alert('Error during cleaner scan: ' + (cleanerScanResults.message || 'Scan failed'));
    }
  } catch (err) {
    alert('Failed to scan for debris: ' + err.message);
  } finally {
    btnStartCleanerScan.disabled = false;
    btnStartCleanerScan.textContent = 'Scan Drive for Debris';
  }
}

function renderCleanerItems() {
  if (!cleanerScanResults) return;
  const items = cleanerScanResults[currentCleanerTab] || [];

  if (!items.length) {
    cleanerItemsList.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 20px;">No items in this category. Clean!</div>';
    btnCleanerExecute.disabled = selectedCleanerItems.size === 0;
    return;
  }

  cleanerItemsList.innerHTML = items.map(item => {
    const isChecked = selectedCleanerItems.has(item.path);
    return `
      <div class="cleaner-row">
        <label class="cleaner-row-left">
          <input type="checkbox" ${isChecked ? 'checked' : ''} onchange="toggleCleanerItemSelection('${escapeHtml(item.path)}')">
          <span class="cleaner-row-path" title="${escapeHtml(item.path)}">${escapeHtml(item.name)}</span>
        </label>
        <span style="color: var(--plex-gold); font-weight: 600; white-space: nowrap;">${item.size_human}</span>
      </div>
    `;
  }).join('');

  btnCleanerExecute.disabled = selectedCleanerItems.size === 0;
  btnCleanerExecute.textContent = `Clean Selected (${selectedCleanerItems.size} items) to Recycle Bin`;
}

window.toggleCleanerItemSelection = function(path) {
  if (selectedCleanerItems.has(path)) {
    selectedCleanerItems.delete(path);
  } else {
    selectedCleanerItems.add(path);
  }
  btnCleanerExecute.disabled = selectedCleanerItems.size === 0;
  btnCleanerExecute.textContent = `Clean Selected (${selectedCleanerItems.size} items) to Recycle Bin`;
};

async function executeCleanerDelete() {
  if (selectedCleanerItems.size === 0) return;
  if (!confirm(`Are you sure you want to move ${selectedCleanerItems.size} junk / orphan item(s) to the Windows Recycle Bin?`)) return;

  btnCleanerExecute.disabled = true;
  btnCleanerExecute.textContent = 'Cleaning files...';

  try {
    const items = Array.from(selectedCleanerItems);
    const res = await fetch('/api/cleaner/clean', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items, use_recycle_bin: true })
    });
    const data = await res.json();

    if (data.status === 'completed') {
      showToast(`Cleaned ${data.success_count} item(s)! Reclaimed: ${data.reclaimed_human}`);
      modalCleaner.classList.add('hidden');
      loadDrives(); // Update storage pool
    } else {
      alert('Error during cleanup: ' + data.message);
    }
  } catch (err) {
    alert('Cleanup failed: ' + err.message);
  } finally {
    btnCleanerExecute.disabled = false;
  }
}

// ==========================================
// FEATURE 7: Deletion Audit Trail
// ==========================================
async function openAuditModal() {
  modalAudit.classList.remove('hidden');
  auditTableContainer.innerHTML = '<div class="loading-placeholder">Loading deletion history...</div>';

  try {
    const res = await fetch('/api/audit/history');
    const data = await res.json();
    const records = data.records || [];

    if (!records.length) {
      auditTableContainer.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 40px;">No files have been deleted yet. Deletion history will appear here.</div>';
      return;
    }

    const rows = records.map(r => `
      <tr>
        <td><strong>${escapeHtml(r.date)}</strong></td>
        <td>${r.files_count} file(s)</td>
        <td style="color: var(--emerald); font-weight: 700;">${r.reclaimed_human}</td>
        <td>${r.use_recycle_bin ? '♻️ Recycle Bin' : 'Permanently Removed'}</td>
        <td style="font-size: 0.72rem; font-family: monospace;" title="${escapeHtml((r.items || []).map(i => i.path).join('\n'))}">
          ${escapeHtml((r.items || []).map(i => i.filename || i.path).slice(0, 2).join(', '))} ${(r.items || []).length > 2 ? '... (+' + ((r.items || []).length - 2) + ' more)' : ''}
        </td>
      </tr>
    `).join('');

    auditTableContainer.innerHTML = `
      <table class="audit-table">
        <thead>
          <tr>
            <th>Date / Time</th>
            <th>Files</th>
            <th>Space Reclaimed</th>
            <th>Safety Method</th>
            <th>Sample Files</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  } catch (err) {
    auditTableContainer.innerHTML = `<div class="error-msg">Failed to load audit records: ${err.message}</div>`;
  }
}

async function clearAuditHistory() {
  if (!confirm('Are you sure you want to clear the deletion audit log?')) return;
  try {
    await fetch('/api/audit/clear', { method: 'POST' });
    openAuditModal();
    showToast('Audit history cleared.');
  } catch (e) {}
}

// Toast Notifications
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
