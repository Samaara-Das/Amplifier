// Amplifier v2 — Frontend Entry Point
// Communicates with Rust backend via Tauri invoke()

// ── Tauri API ──────────────────────────────────────

// In dev mode (served by Tauri dev server), __TAURI__ is injected.
// In production (loaded from disk), it's bundled.
// We gracefully degrade if running outside Tauri (e.g., in a browser for testing).
const isTauri = typeof window.__TAURI__ !== 'undefined';

async function invoke(command, args = {}) {
  if (isTauri) {
    return window.__TAURI__.core.invoke(command, args);
  }
  // Fallback for browser testing — return mock data
  console.warn(`[mock] invoke("${command}", ${JSON.stringify(args)})`);
  return getMockData(command, args);
}

// ── Navigation ─────────────────────────────────────

const navItems = document.querySelectorAll('.nav-item');
const pages = document.querySelectorAll('.page');

navItems.forEach(item => {
  item.addEventListener('click', (e) => {
    e.preventDefault();
    const targetPage = item.dataset.page;
    navigateTo(targetPage);
  });
});

function navigateTo(pageName) {
  // Update nav active state
  navItems.forEach(n => n.classList.remove('active'));
  const activeNav = document.querySelector(`.nav-item[data-page="${pageName}"]`);
  if (activeNav) activeNav.classList.add('active');

  // Show target page
  pages.forEach(p => p.classList.remove('active'));
  const targetPage = document.getElementById(`page-${pageName}`);
  if (targetPage) targetPage.classList.add('active');

  // Load page-specific data
  if (pageName === 'earnings') {
    loadEarnings();
  } else if (pageName === 'posts') {
    loadPosts();
  } else if (pageName === 'campaigns') {
    loadCampaigns();
  } else if (pageName === 'settings') {
    loadSettings();
  }
}

// ── Dashboard Data ─────────────────────────────────

let dashboardRefreshTimer = null;

async function refreshDashboard() {
  const refreshBtn = document.getElementById('btn-refresh');
  const dashboardPage = document.getElementById('page-dashboard');

  // Show loading state
  setDashboardLoading(true);
  if (refreshBtn) {
    refreshBtn.disabled = true;
    refreshBtn.classList.add('btn-loading');
  }

  try {
    const status = await invoke('get_status');
    if (status) {
      updateDashboardStats(status);
      updatePlatformHealth(status.platforms);
      updateRecentActivity(status.recent_activity);
      clearDashboardError();
    }
  } catch (err) {
    console.error('Failed to refresh dashboard:', err);
    showDashboardError('Unable to connect to Amplifier backend. Retrying...');
  } finally {
    setDashboardLoading(false);
    if (refreshBtn) {
      refreshBtn.disabled = false;
      refreshBtn.classList.remove('btn-loading');
    }
  }
}

function setDashboardLoading(loading) {
  const statValues = document.querySelectorAll('.stat-value');
  if (loading) {
    statValues.forEach(el => {
      if (el.textContent === '--') {
        el.classList.add('loading-shimmer');
      }
    });
  } else {
    statValues.forEach(el => el.classList.remove('loading-shimmer'));
  }
}

function showDashboardError(message) {
  let errorBanner = document.getElementById('dashboard-error');
  if (!errorBanner) {
    errorBanner = document.createElement('div');
    errorBanner.id = 'dashboard-error';
    errorBanner.className = 'dashboard-error';
    const statsGrid = document.querySelector('.stats-grid');
    if (statsGrid) {
      statsGrid.parentNode.insertBefore(errorBanner, statsGrid);
    }
  }
  errorBanner.innerHTML = `
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
    </svg>
    <span>${message}</span>
  `;
  errorBanner.style.display = 'flex';
}

function clearDashboardError() {
  const errorBanner = document.getElementById('dashboard-error');
  if (errorBanner) {
    errorBanner.style.display = 'none';
  }
}

function updateDashboardStats(data) {
  const el = (id) => document.getElementById(id);

  if (data.active_campaigns !== undefined) {
    el('stat-active-campaigns').textContent = data.active_campaigns;
  }
  if (data.pending_invitations !== undefined) {
    el('stat-pending-invitations').textContent = data.pending_invitations;
    // Update badge
    const badge = el('badge-campaigns');
    if (data.pending_invitations > 0) {
      badge.textContent = data.pending_invitations;
      badge.style.display = 'inline-block';
    } else {
      badge.style.display = 'none';
    }
  }
  if (data.posts_queued !== undefined) {
    el('stat-posts-queued').textContent = data.posts_queued;
  }
  if (data.earnings_balance !== undefined) {
    el('stat-earnings').textContent = `$${parseFloat(data.earnings_balance).toFixed(2)}`;
  }

  // Update connection status in sidebar based on logged_in
  if (data.logged_in !== undefined) {
    const statusEl = el('user-status');
    if (statusEl) {
      statusEl.textContent = data.logged_in ? 'Connected' : 'Not logged in';
    }
  }
}

function updatePlatformHealth(platforms) {
  const container = document.getElementById('platform-health');
  if (!container) return;

  const platformConfig = [
    { key: 'x', name: 'X (Twitter)', icon: 'x' },
    { key: 'linkedin', name: 'LinkedIn', icon: 'linkedin' },
    { key: 'facebook', name: 'Facebook', icon: 'facebook' },
    { key: 'reddit', name: 'Reddit', icon: 'reddit' },
  ];

  if (!platforms || Object.keys(platforms).length === 0) {
    container.innerHTML = platformConfig.map(p => `
      <div class="platform-row">
        <div class="platform-info">
          <span class="platform-icon">${getPlatformIcon(p.key)}</span>
          <span class="platform-name">${p.name}</span>
        </div>
        <div class="platform-status">
          <span class="status-dot unknown"></span>
          <span class="platform-status-label muted">Unknown</span>
        </div>
      </div>
    `).join('');
    return;
  }

  container.innerHTML = platformConfig.map(p => {
    const info = platforms[p.key] || { connected: false, health: 'red' };
    const health = info.health || 'red';
    const connected = info.connected || false;
    const statusLabel = connected ? 'Connected' : 'Not connected';
    const statusClass = health === 'green' ? 'success' : health === 'yellow' ? 'warning' : health === 'red' ? 'error' : 'muted';

    return `
      <div class="platform-row">
        <div class="platform-info">
          <span class="platform-icon">${getPlatformIcon(p.key)}</span>
          <span class="platform-name">${p.name}</span>
        </div>
        <div class="platform-status">
          <span class="status-dot ${health}"></span>
          <span class="platform-status-label ${statusClass}">${statusLabel}</span>
        </div>
      </div>
    `;
  }).join('');
}

function getPlatformIcon(platform) {
  const icons = {
    x: `<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>`,
    linkedin: `<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.064 2.064 0 1 1 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>`,
    facebook: `<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg>`,
    reddit: `<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0zm5.01 4.744c.688 0 1.25.561 1.25 1.249a1.25 1.25 0 0 1-2.498.056l-2.597-.547-.8 3.747c1.824.07 3.48.632 4.674 1.488.308-.309.73-.491 1.207-.491.968 0 1.754.786 1.754 1.754 0 .716-.435 1.333-1.01 1.614a3.111 3.111 0 0 1 .042.52c0 2.694-3.13 4.87-7.004 4.87-3.874 0-7.004-2.176-7.004-4.87 0-.183.015-.366.043-.534A1.748 1.748 0 0 1 4.028 12c0-.968.786-1.754 1.754-1.754.463 0 .898.196 1.207.49 1.207-.883 2.878-1.43 4.744-1.487l.885-4.182a.342.342 0 0 1 .14-.197.35.35 0 0 1 .238-.042l2.906.617a1.214 1.214 0 0 1 1.108-.701zM9.25 12C8.561 12 8 12.562 8 13.25c0 .687.561 1.248 1.25 1.248.687 0 1.248-.561 1.248-1.249 0-.688-.561-1.249-1.249-1.249zm5.5 0c-.687 0-1.248.561-1.248 1.25 0 .687.561 1.248 1.249 1.248.688 0 1.249-.561 1.249-1.249 0-.687-.562-1.249-1.25-1.249zm-5.466 3.99a.327.327 0 0 0-.231.094.33.33 0 0 0 0 .463c.842.842 2.484.913 2.961.913.477 0 2.105-.056 2.961-.913a.361.361 0 0 0 .029-.463.33.33 0 0 0-.464 0c-.547.533-1.684.73-2.512.73-.828 0-1.979-.196-2.512-.73a.326.326 0 0 0-.232-.095z"/></svg>`,
  };
  return icons[platform] || '';
}

function updateRecentActivity(activity) {
  const container = document.getElementById('recent-activity');
  if (!container) return;

  if (!activity || activity.length === 0) {
    container.innerHTML = `
      <div class="empty-state compact">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="1.5">
          <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
        </svg>
        <p>No recent activity yet.</p>
        <p class="text-muted">Activity will appear here once you start accepting campaigns.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = activity.map(event => {
    const icon = getActivityIcon(event.type);
    const iconClass = getActivityIconClass(event.type);
    return `
      <div class="activity-item">
        <div class="activity-icon ${iconClass}">
          ${icon}
        </div>
        <div class="activity-content">
          <span class="activity-description">${escapeHtml(event.description)}</span>
          <span class="activity-time">${escapeHtml(event.time)}</span>
        </div>
      </div>
    `;
  }).join('');
}

function getActivityIcon(type) {
  switch (type) {
    case 'campaign_accepted':
      return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
    case 'campaign_rejected':
      return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
    case 'post_published':
      return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13"/><path d="M22 2L15 22 11 13 2 9z"/></svg>';
    case 'earning_received':
      return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>';
    default:
      return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/></svg>';
  }
}

function getActivityIconClass(type) {
  switch (type) {
    case 'campaign_accepted': return 'activity-icon-success';
    case 'campaign_rejected': return 'activity-icon-error';
    case 'post_published': return 'activity-icon-primary';
    case 'earning_received': return 'activity-icon-success';
    default: return 'activity-icon-muted';
  }
}

function escapeHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ── Posts Tab ────────────────────────────────────────

let postsData = null;
let postsRefreshTimer = null;
let activePostsTab = 'pending_review';

// Platform character limits
const PLATFORM_CHAR_LIMITS = {
  x: 280,
  linkedin: 3000,
  facebook: 63206,
  reddit: 40000,
};

const PLATFORM_DISPLAY_NAMES = {
  x: 'X',
  linkedin: 'LinkedIn',
  facebook: 'Facebook',
  reddit: 'Reddit',
  tiktok: 'TikTok',
  instagram: 'Instagram',
};

async function loadPosts() {
  const refreshBtn = document.getElementById('btn-refresh-posts');
  if (refreshBtn) {
    refreshBtn.disabled = true;
    refreshBtn.classList.add('btn-loading');
  }

  try {
    const data = await invoke('get_posts');
    postsData = data;
    updatePostsCounts(data);
    renderPostsSection(activePostsTab, data);
  } catch (err) {
    console.error('Failed to load posts:', err);
    showToast('Failed to load posts data.', 'error');
  } finally {
    if (refreshBtn) {
      refreshBtn.disabled = false;
      refreshBtn.classList.remove('btn-loading');
    }
  }
}

function refreshPosts() {
  loadPosts();
}

function switchPostsTab(tabName) {
  activePostsTab = tabName;

  // Update tab active state
  document.querySelectorAll('.posts-tab').forEach(t => t.classList.remove('active'));
  const activeTab = document.querySelector(`.posts-tab[data-posts-tab="${tabName}"]`);
  if (activeTab) activeTab.classList.add('active');

  // Show section
  document.querySelectorAll('.posts-section').forEach(s => s.classList.remove('active'));
  const section = document.getElementById(`posts-section-${tabName}`);
  if (section) section.classList.add('active');

  // Re-render with cached data
  if (postsData) {
    renderPostsSection(tabName, postsData);
  }
}

function updatePostsCounts(data) {
  const counts = {
    pending_review: (data.pending_review || []).length,
    scheduled: (data.scheduled || []).length,
    posted: (data.posted || []).length,
    failed: (data.failed || []).length,
  };

  for (const [key, count] of Object.entries(counts)) {
    const el = document.getElementById(`posts-count-${key}`);
    if (el) el.textContent = count;
  }

  // Update nav badge for posts
  const totalPending = counts.pending_review;
  const postsNav = document.querySelector('.nav-item[data-page="posts"]');
  if (postsNav) {
    let badge = postsNav.querySelector('.badge');
    if (totalPending > 0) {
      if (!badge) {
        badge = document.createElement('span');
        badge.className = 'badge';
        postsNav.appendChild(badge);
      }
      badge.textContent = totalPending;
      badge.style.display = 'inline-block';
    } else if (badge) {
      badge.style.display = 'none';
    }
  }
}

function renderPostsSection(tabName, data) {
  switch (tabName) {
    case 'pending_review':
      renderPendingReview(data.pending_review || []);
      break;
    case 'scheduled':
      renderScheduled(data.scheduled || []);
      break;
    case 'posted':
      renderPosted(data.posted || []);
      break;
    case 'failed':
      renderFailed(data.failed || []);
      break;
  }
}

// ── Pending Review ──

function renderPendingReview(items) {
  const container = document.getElementById('posts-pending-list');
  if (!items || items.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="1.5">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
        </svg>
        <h3>No posts pending review</h3>
        <p class="text-muted">AI-generated content will appear here for your approval.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = items.map((item, idx) => renderPendingCard(item, idx)).join('');
}

function renderPendingCard(item, idx) {
  const campaignTitle = escapeHtml(item.campaign_title || 'Untitled Campaign');
  const platforms = item.platforms || {};
  const platformKeys = Object.keys(platforms);
  const firstPlatform = platformKeys[0] || 'x';
  const qualityScore = item.quality_score || 0;
  const qualityClass = qualityScore >= 70 ? 'high' : qualityScore >= 50 ? 'medium' : 'low';
  const campaignUpdated = item.campaign_updated || false;

  const updatedBanner = campaignUpdated ? `
    <div class="campaign-updated-banner">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
      <span>Campaign updated by company -- please re-review content</span>
    </div>
  ` : '';

  const platformTabs = platformKeys.map((p, i) => {
    const isActive = i === 0 ? 'active' : '';
    const platformClass = `platform-${p}`;
    return `<button class="platform-tab ${isActive} ${platformClass}" data-platform="${p}" onclick="window.switchPlatformTab(${idx}, '${p}')">
      ${getPlatformIcon(p)}
      <span>${PLATFORM_DISPLAY_NAMES[p] || p}</span>
    </button>`;
  }).join('');

  const platformPanels = platformKeys.map((p, i) => {
    const isActive = i === 0 ? 'active' : '';
    const content = platforms[p]?.text || '';
    const charLimit = PLATFORM_CHAR_LIMITS[p] || 10000;
    const charCount = content.length;
    const isOver = charCount > charLimit;
    const charClass = isOver ? 'over-limit' : '';

    return `
      <div class="platform-content-panel ${isActive}" id="panel-${idx}-${p}" data-platform="${p}">
        <div class="content-preview" id="preview-${idx}-${p}">${escapeHtml(content)}</div>
        <textarea class="content-edit-area" id="edit-${idx}-${p}"
          data-card-idx="${idx}" data-platform="${p}"
          oninput="window.updateCharCount(${idx}, '${p}')">${escapeHtml(content)}</textarea>
        <div class="char-count ${charClass}" id="charcount-${idx}-${p}">${charCount} / ${charLimit}</div>
        <div class="content-actions">
          <button class="btn btn-secondary btn-sm" onclick="window.toggleEditMode(${idx}, '${p}')">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
            </svg>
            Edit
          </button>
          <button class="btn btn-secondary btn-sm" onclick="window.saveEdit(${idx}, '${p}')">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            Save
          </button>
          <button class="btn btn-secondary btn-sm" onclick="window.regeneratePlatform(${item.campaign_id}, '${p}')">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
            </svg>
            Regenerate
          </button>
          <button class="btn btn-success btn-sm" onclick="window.approvePlatform(${item.campaign_id}, '${p}')">
            Approve
          </button>
        </div>
      </div>
    `;
  }).join('');

  return `
    <div class="post-card" id="post-card-${idx}">
      <div class="post-card-header">
        <span class="post-card-title">${campaignTitle}</span>
        <div class="post-card-meta">
          <span class="quality-badge ${qualityClass}">${qualityScore}/100</span>
        </div>
      </div>
      ${updatedBanner}
      <div class="platform-tabs">${platformTabs}</div>
      <div class="platform-content-panels">${platformPanels}</div>
      <div class="post-card-footer">
        <button class="btn btn-ghost btn-sm" onclick="window.skipContent(${item.campaign_id})">Skip</button>
        <button class="btn btn-success" onclick="window.approveAll(${item.campaign_id})">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
          Approve All
        </button>
      </div>
    </div>
  `;
}

function switchPlatformTab(cardIdx, platform) {
  const card = document.getElementById(`post-card-${cardIdx}`);
  if (!card) return;

  // Switch tab active state
  card.querySelectorAll('.platform-tab').forEach(t => t.classList.remove('active'));
  const activeTab = card.querySelector(`.platform-tab[data-platform="${platform}"]`);
  if (activeTab) activeTab.classList.add('active');

  // Switch content panel
  card.querySelectorAll('.platform-content-panel').forEach(p => p.classList.remove('active'));
  const panel = document.getElementById(`panel-${cardIdx}-${platform}`);
  if (panel) panel.classList.add('active');
}

function toggleEditMode(cardIdx, platform) {
  const preview = document.getElementById(`preview-${cardIdx}-${platform}`);
  const editArea = document.getElementById(`edit-${cardIdx}-${platform}`);
  if (!preview || !editArea) return;

  if (editArea.classList.contains('visible')) {
    // Switch back to preview
    editArea.classList.remove('visible');
    preview.style.display = '';
  } else {
    // Enter edit mode
    editArea.classList.add('visible');
    preview.style.display = 'none';
    editArea.focus();
  }
}

function updateCharCount(cardIdx, platform) {
  const editArea = document.getElementById(`edit-${cardIdx}-${platform}`);
  const countEl = document.getElementById(`charcount-${cardIdx}-${platform}`);
  if (!editArea || !countEl) return;

  const charLimit = PLATFORM_CHAR_LIMITS[platform] || 10000;
  const charCount = editArea.value.length;
  countEl.textContent = `${charCount} / ${charLimit}`;
  countEl.className = charCount > charLimit ? 'char-count over-limit' : 'char-count';
}

async function saveEdit(cardIdx, platform) {
  const editArea = document.getElementById(`edit-${cardIdx}-${platform}`);
  const preview = document.getElementById(`preview-${cardIdx}-${platform}`);
  if (!editArea) return;

  const newText = editArea.value;

  // Find the campaign_id from postsData
  const pending = postsData?.pending_review || [];
  const item = pending[cardIdx];
  if (!item) return;

  try {
    await invoke('edit_content', {
      campaign_id: item.campaign_id,
      platform: platform,
      text: newText,
    });

    // Update preview
    if (preview) preview.textContent = newText;
    editArea.classList.remove('visible');
    if (preview) preview.style.display = '';

    showToast(`${PLATFORM_DISPLAY_NAMES[platform] || platform} content saved.`, 'success');
  } catch (err) {
    console.error('Failed to save edit:', err);
    showToast('Failed to save content edit.', 'error');
  }
}

async function regeneratePlatform(campaignId, platform) {
  const btn = event.target.closest('.btn');
  if (btn) {
    btn.disabled = true;
    btn.classList.add('btn-loading');
  }

  try {
    await invoke('regenerate_content', {
      campaign_id: campaignId,
      platform: platform,
    });
    showToast(`Regenerating ${PLATFORM_DISPLAY_NAMES[platform] || platform} content...`, 'info');
    // Reload after a short delay to let regeneration complete
    setTimeout(() => loadPosts(), 2000);
  } catch (err) {
    console.error('Regenerate failed:', err);
    showToast('Failed to regenerate content.', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.classList.remove('btn-loading');
    }
  }
}

async function approvePlatform(campaignId, platform) {
  try {
    await invoke('approve_content', {
      campaign_id: campaignId,
      platform: platform,
      approve_all: false,
    });
    showToast(`${PLATFORM_DISPLAY_NAMES[platform] || platform} post approved.`, 'success');
    await loadPosts();
  } catch (err) {
    console.error('Approve failed:', err);
    showToast('Failed to approve post.', 'error');
  }
}

async function approveAll(campaignId) {
  try {
    await invoke('approve_content', {
      campaign_id: campaignId,
      approve_all: true,
    });
    showToast('All platforms approved and scheduled for posting.', 'success');
    await loadPosts();
  } catch (err) {
    console.error('Approve all failed:', err);
    showToast('Failed to approve posts.', 'error');
  }
}

async function skipContent(campaignId) {
  try {
    await invoke('skip_content', { campaign_id: campaignId });
    showToast('Campaign content skipped.', 'info');
    await loadPosts();
  } catch (err) {
    console.error('Skip failed:', err);
    showToast('Failed to skip content.', 'error');
  }
}

// ── Scheduled Section ──

function renderScheduled(items) {
  const container = document.getElementById('posts-scheduled-list');
  if (!items || items.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="1.5">
          <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
        </svg>
        <h3>No scheduled posts</h3>
        <p class="text-muted">Approved posts waiting to be published will appear here.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = items.map(item => {
    const title = escapeHtml(item.campaign_title || 'Untitled Campaign');
    const platform = item.platform || 'unknown';
    const platformName = PLATFORM_DISPLAY_NAMES[platform] || platform;
    const scheduledTime = formatScheduledTime(item.scheduled_at);
    const preview = escapeHtml((item.content || '').substring(0, 120) + (item.content?.length > 120 ? '...' : ''));
    const scheduleId = item.id || item.schedule_id;

    return `
      <div class="scheduled-card">
        <div class="scheduled-card-info">
          <div class="scheduled-card-title">${title}</div>
          <div class="scheduled-card-details">
            <span class="platform-icon-inline">${getPlatformIcon(platform)} ${platformName}</span>
          </div>
          <div class="scheduled-card-preview">${preview}</div>
        </div>
        <div class="scheduled-card-time">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
          </svg>
          ${scheduledTime}
        </div>
        <div class="scheduled-card-actions">
          <button class="btn btn-secondary btn-sm" disabled title="Reschedule (coming soon)">Reschedule</button>
          <button class="btn btn-ghost btn-sm" onclick="window.cancelScheduled(${scheduleId})">Cancel</button>
        </div>
      </div>
    `;
  }).join('');
}

function formatScheduledTime(isoString) {
  if (!isoString) return 'Unknown time';
  try {
    const d = new Date(isoString);
    const now = new Date();
    const diff = d - now;

    // Show relative time if within 24h
    if (diff > 0 && diff < 86400000) {
      const hours = Math.floor(diff / 3600000);
      const mins = Math.floor((diff % 3600000) / 60000);
      if (hours > 0) return `In ${hours}h ${mins}m`;
      return `In ${mins}m`;
    }

    return d.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    });
  } catch {
    return 'Unknown time';
  }
}

async function cancelScheduled(scheduleId) {
  try {
    await invoke('cancel_scheduled', { schedule_id: scheduleId });
    showToast('Scheduled post cancelled and moved back to review.', 'info');
    await loadPosts();
  } catch (err) {
    console.error('Cancel scheduled failed:', err);
    showToast('Failed to cancel scheduled post.', 'error');
  }
}

// ── Posted Section ──

function renderPosted(items) {
  const container = document.getElementById('posts-posted-list');
  if (!items || items.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="1.5">
          <path d="M22 2L11 13"/><path d="M22 2L15 22 11 13 2 9z"/>
        </svg>
        <h3>No published posts</h3>
        <p class="text-muted">Successfully published posts will appear here with engagement metrics.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = items.map(item => {
    const title = escapeHtml(item.campaign_title || 'Untitled Campaign');
    const platform = item.platform || 'unknown';
    const platformName = PLATFORM_DISPLAY_NAMES[platform] || platform;
    const postUrl = item.post_url || '';
    const postedTime = formatDate(item.posted_at);
    const status = item.status || 'live';
    const statusClass = status === 'live' ? 'live' : status === 'deleted' ? 'deleted' : status === 'flagged' ? 'flagged' : 'collecting';
    const statusLabel = status === 'live' ? 'Live' : status === 'deleted' ? 'Deleted' : status === 'flagged' ? 'Flagged' : 'Collecting';

    const hasMetrics = item.impressions !== null && item.impressions !== undefined;
    const metricsHtml = hasMetrics ? `
      <div class="posted-card-metrics">
        <div class="metric-item">
          <span class="metric-value">${formatCompactNumber(item.impressions || 0)}</span>
          <span class="metric-label">Impressions</span>
        </div>
        <div class="metric-item">
          <span class="metric-value">${formatCompactNumber(item.likes || 0)}</span>
          <span class="metric-label">Likes</span>
        </div>
        <div class="metric-item">
          <span class="metric-value">${formatCompactNumber(item.reposts || 0)}</span>
          <span class="metric-label">Reposts</span>
        </div>
        <div class="metric-item">
          <span class="metric-value">${formatCompactNumber(item.comments || 0)}</span>
          <span class="metric-label">Comments</span>
        </div>
      </div>
    ` : `
      <div class="posted-card-metrics">
        <span class="text-muted" style="font-size: 13px;">Collecting metrics...</span>
      </div>
    `;

    const linkHtml = postUrl
      ? `<a class="posted-card-link" href="${escapeHtml(postUrl)}" target="_blank" rel="noopener">${escapeHtml(postUrl)}</a>`
      : '<span class="text-muted" style="font-size: 13px;">No URL available</span>';

    return `
      <div class="posted-card">
        <div class="posted-card-top">
          <div class="posted-card-left">
            <span class="posted-card-title">${title}</span>
            <span class="posted-card-platform">${getPlatformIcon(platform)} ${platformName}</span>
          </div>
          <div style="display: flex; align-items: center; gap: 10px;">
            <span class="status-badge ${statusClass}"><span class="status-badge-dot"></span>${statusLabel}</span>
            <span class="posted-card-time">${postedTime}</span>
          </div>
        </div>
        <div style="margin-bottom: 8px;">${linkHtml}</div>
        ${metricsHtml}
      </div>
    `;
  }).join('');
}

// ── Failed Section ──

function renderFailed(items) {
  const container = document.getElementById('posts-failed-list');
  if (!items || items.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="1.5">
          <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
        </svg>
        <h3>No failed posts</h3>
        <p class="text-muted">Posts that fail to publish will appear here with retry options.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = items.map(item => {
    const title = escapeHtml(item.campaign_title || 'Untitled Campaign');
    const platform = item.platform || 'unknown';
    const platformName = PLATFORM_DISPLAY_NAMES[platform] || platform;
    const errorMsg = escapeHtml(item.error_message || 'Unknown error');
    const failedTime = formatDate(item.failed_at || item.actual_posted_at);
    const scheduleId = item.id || item.schedule_id;
    const isSessionError = (item.error_message || '').toLowerCase().includes('session');

    const sessionLink = isSessionError
      ? `<button class="btn btn-ghost btn-sm" onclick="window.navigateTo('settings')">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4"/>
          </svg>
          Session Health
        </button>`
      : '';

    return `
      <div class="failed-card">
        <div class="failed-card-top">
          <div class="failed-card-left">
            <span class="failed-card-title">${title}</span>
            <span class="failed-card-platform">${getPlatformIcon(platform)} ${platformName}</span>
          </div>
        </div>
        <div class="failed-card-error">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <span>${errorMsg}</span>
        </div>
        <div class="failed-card-footer">
          <span class="failed-card-time">${failedTime}</span>
          <div class="failed-card-actions">
            ${sessionLink}
            <button class="btn btn-primary btn-sm" onclick="window.retryFailed(${scheduleId})">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
              </svg>
              Retry
            </button>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

async function retryFailed(scheduleId) {
  try {
    await invoke('retry_failed', { schedule_id: scheduleId });
    showToast('Post queued for retry.', 'info');
    await loadPosts();
  } catch (err) {
    console.error('Retry failed:', err);
    showToast('Failed to retry post.', 'error');
  }
}

// ── Campaigns Tab ────────────────────────────────────

let campaignsData = null;
let activeCampaignsTab = 'invitations';
let expiryCountdownInterval = null;

async function loadCampaigns() {
  const refreshBtn = document.getElementById('btn-refresh-campaigns');
  if (refreshBtn) {
    refreshBtn.disabled = true;
    refreshBtn.classList.add('btn-loading');
  }

  try {
    // Fetch all three sections in parallel
    const [invitationsResult, activeCampaignsResult, completedResult] = await Promise.all([
      invoke('get_invitations'),
      invoke('get_campaigns'),
      invoke('get_completed_campaigns'),
    ]);

    campaignsData = {
      invitations: invitationsResult.invitations || [],
      active: activeCampaignsResult.campaigns || [],
      completed: completedResult.campaigns || [],
    };

    updateCampaignsCounts(campaignsData);
    renderCampaignsSection(activeCampaignsTab, campaignsData);
    updateMaxCampaignsWarning(campaignsData.active.length);
    startExpiryCountdowns();
  } catch (err) {
    console.error('Failed to load campaigns:', err);
    showToast('Failed to load campaigns data.', 'error');
  } finally {
    if (refreshBtn) {
      refreshBtn.disabled = false;
      refreshBtn.classList.remove('btn-loading');
    }
  }
}

function refreshCampaigns() {
  loadCampaigns();
}

function switchCampaignsTab(tabName) {
  activeCampaignsTab = tabName;

  // Update tab active state
  document.querySelectorAll('.campaigns-tab').forEach(t => t.classList.remove('active'));
  const activeTab = document.querySelector(`.campaigns-tab[data-campaigns-tab="${tabName}"]`);
  if (activeTab) activeTab.classList.add('active');

  // Show section
  document.querySelectorAll('.campaigns-section').forEach(s => s.classList.remove('active'));
  const section = document.getElementById(`campaigns-section-${tabName}`);
  if (section) section.classList.add('active');

  // Re-render with cached data
  if (campaignsData) {
    renderCampaignsSection(tabName, campaignsData);
  }
}

function updateCampaignsCounts(data) {
  const counts = {
    invitations: (data.invitations || []).length,
    active: (data.active || []).length,
    completed: (data.completed || []).length,
  };

  for (const [key, count] of Object.entries(counts)) {
    const el = document.getElementById(`campaigns-count-${key}`);
    if (el) el.textContent = count;
  }

  // Update sidebar badge with invitation count
  const badge = document.getElementById('badge-campaigns');
  if (counts.invitations > 0) {
    badge.textContent = counts.invitations;
    badge.style.display = 'inline-block';
  } else {
    badge.style.display = 'none';
  }
}

function updateMaxCampaignsWarning(activeCount) {
  const warning = document.getElementById('campaigns-max-warning');
  if (warning) {
    warning.style.display = activeCount >= 5 ? 'flex' : 'none';
  }
}

function renderCampaignsSection(tabName, data) {
  switch (tabName) {
    case 'invitations':
      renderInvitations(data.invitations || []);
      break;
    case 'active':
      renderActiveCampaigns(data.active || []);
      break;
    case 'completed':
      renderCompletedCampaigns(data.completed || []);
      break;
  }
}

// ── Invitations ──

function renderInvitations(items) {
  const container = document.getElementById('campaigns-invitations-list');
  if (!items || items.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="1.5">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>
        </svg>
        <h3>No new campaign invitations</h3>
        <p class="text-muted">Campaign invitations will appear here when you are matched to new campaigns.</p>
      </div>
    `;
    return;
  }

  const maxActive = campaignsData ? (campaignsData.active || []).length >= 5 : false;

  container.innerHTML = items.map(inv => renderInvitationCard(inv, maxActive)).join('');
}

function renderInvitationCard(inv, maxActive) {
  const title = escapeHtml(inv.title || 'Untitled Campaign');
  const brief = escapeHtml(inv.brief || '');
  const invId = inv.server_id || inv.assignment_id || inv.campaign_id;

  // Parse payout rules
  let payoutRules = {};
  if (typeof inv.payout_rules === 'string') {
    try { payoutRules = JSON.parse(inv.payout_rules); } catch { payoutRules = {}; }
  } else if (inv.payout_rules) {
    payoutRules = inv.payout_rules;
  }

  const rateImp = payoutRules.rate_per_1k_impressions || 0;
  const rateLike = payoutRules.rate_per_like || 0;
  const rateRepost = payoutRules.rate_per_repost || 0;
  const rateClick = payoutRules.rate_per_click || 0;

  const payoutHtml = buildPayoutRatesHtml(rateImp, rateLike, rateRepost, rateClick);

  // Parse platforms from targeting or platforms_required
  let platforms = [];
  if (inv.platforms_required) {
    platforms = Array.isArray(inv.platforms_required) ? inv.platforms_required : [];
  } else if (inv.targeting) {
    let targeting = inv.targeting;
    if (typeof targeting === 'string') {
      try { targeting = JSON.parse(targeting); } catch { targeting = {}; }
    }
    platforms = targeting.required_platforms || [];
  }

  const platformBadgesHtml = platforms.map(p => {
    const name = PLATFORM_DISPLAY_NAMES[p] || p;
    return `<span class="platform-badge ${p}">${name}</span>`;
  }).join('');

  // Estimated earnings (rough: assume 5K impressions + 200 likes + 20 reposts + 50 clicks per platform)
  const estPerPlatform = (rateImp * 5) + (rateLike * 200) + (rateRepost * 20) + (rateClick * 50);
  const estTotal = estPerPlatform * Math.max(platforms.length, 1);
  const estHtml = estTotal > 0
    ? `<span class="estimated-earnings">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
        ~$${estTotal.toFixed(0)} est.
      </span>`
    : '';

  // Expiry countdown
  const expiryHtml = buildExpiryHtml(inv.expires_at, invId);

  const disabledAttr = maxActive ? 'disabled' : '';
  const disabledTitle = maxActive ? 'title="Max 5 active campaigns reached"' : '';

  return `
    <div class="invitation-card" id="invitation-${invId}">
      <div class="invitation-card-header">
        <span class="invitation-card-title">${title}</span>
        ${expiryHtml}
      </div>
      <div class="invitation-card-brief">${brief}</div>
      <div class="invitation-card-details">
        <div class="payout-rates">${payoutHtml}</div>
        <div class="platform-badges">${platformBadgesHtml}</div>
        ${estHtml}
      </div>
      <div class="invitation-card-footer">
        <div class="invitation-card-meta">
        </div>
        <div class="invitation-card-actions">
          <button class="btn btn-details btn-sm" onclick="window.viewInvitationDetails(${invId})">View Details</button>
          <button class="btn btn-reject btn-sm" onclick="window.rejectInvitation(${invId})" id="btn-reject-${invId}">Reject</button>
          <button class="btn btn-accept btn-sm" onclick="window.acceptInvitation(${invId})" id="btn-accept-${invId}" ${disabledAttr} ${disabledTitle}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            Accept
          </button>
        </div>
      </div>
    </div>
  `;
}

function buildPayoutRatesHtml(rateImp, rateLike, rateRepost, rateClick) {
  const parts = [];
  if (rateImp > 0) {
    parts.push(`<span class="payout-rate"><span class="rate-value">$${rateImp.toFixed(2)}</span>/1K imp</span>`);
  }
  if (rateLike > 0) {
    parts.push(`<span class="payout-rate"><span class="rate-value">$${rateLike.toFixed(2)}</span>/like</span>`);
  }
  if (rateRepost > 0) {
    parts.push(`<span class="payout-rate"><span class="rate-value">$${rateRepost.toFixed(2)}</span>/repost</span>`);
  }
  if (rateClick > 0) {
    parts.push(`<span class="payout-rate"><span class="rate-value">$${rateClick.toFixed(2)}</span>/click</span>`);
  }
  if (parts.length === 0) {
    parts.push('<span class="payout-rate">Payout rates TBD</span>');
  }
  return parts.join('');
}

function buildExpiryHtml(expiresAt, invId) {
  if (!expiresAt) return '';

  const expiryText = getExpiryText(expiresAt);
  const expiryClass = getExpiryClass(expiresAt);

  return `<span class="invitation-card-expiry ${expiryClass}" data-expires-at="${escapeHtml(expiresAt)}" id="expiry-${invId}">
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
    ${expiryText}
  </span>`;
}

function getExpiryText(expiresAt) {
  if (!expiresAt) return '';
  try {
    const expiry = new Date(expiresAt);
    const now = new Date();
    const diff = expiry - now;

    if (diff <= 0) return 'Expired';

    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(hours / 24);
    const remainingHours = hours % 24;

    if (days > 0) return `Expires in ${days}d ${remainingHours}h`;
    if (hours > 0) {
      const mins = Math.floor((diff % 3600000) / 60000);
      return `Expires in ${hours}h ${mins}m`;
    }
    const mins = Math.floor(diff / 60000);
    return `Expires in ${mins}m`;
  } catch {
    return '';
  }
}

function getExpiryClass(expiresAt) {
  if (!expiresAt) return 'normal';
  try {
    const expiry = new Date(expiresAt);
    const now = new Date();
    const diff = expiry - now;
    if (diff <= 0) return 'expired';
    if (diff < 12 * 3600000) return 'urgent'; // < 12 hours
    return 'normal';
  } catch {
    return 'normal';
  }
}

function startExpiryCountdowns() {
  // Clear existing interval
  if (expiryCountdownInterval) {
    clearInterval(expiryCountdownInterval);
  }
  // Update every 60 seconds
  expiryCountdownInterval = setInterval(() => {
    document.querySelectorAll('[data-expires-at]').forEach(el => {
      const expiresAt = el.getAttribute('data-expires-at');
      const text = getExpiryText(expiresAt);
      const cls = getExpiryClass(expiresAt);
      // Update text (skip the SVG icon)
      const svgHtml = el.querySelector('svg') ? el.querySelector('svg').outerHTML : '';
      el.innerHTML = svgHtml + '\n    ' + text;
      el.className = `invitation-card-expiry ${cls}`;
    });
  }, 60000);
}

// ── Accept / Reject handlers ──

async function acceptInvitation(invitationId) {
  const acceptBtn = document.getElementById(`btn-accept-${invitationId}`);
  const rejectBtn = document.getElementById(`btn-reject-${invitationId}`);

  if (acceptBtn) {
    acceptBtn.disabled = true;
    acceptBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="spin-icon"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg> Accepting...';
  }
  if (rejectBtn) rejectBtn.disabled = true;

  try {
    const result = await invoke('accept_invitation', { invitation_id: invitationId });
    if (result && result.success) {
      showToast('Campaign accepted! Content generation will begin shortly.', 'success');
      // Remove card with animation
      const card = document.getElementById(`invitation-${invitationId}`);
      if (card) {
        card.style.opacity = '0';
        card.style.transform = 'translateX(20px)';
        card.style.transition = 'all 0.3s ease';
        setTimeout(() => card.remove(), 300);
      }
      // Reload campaigns after a short delay
      setTimeout(() => loadCampaigns(), 500);
    } else {
      const errorMsg = (result && result.error) || 'Failed to accept campaign.';
      showToast(errorMsg, 'error');
      if (acceptBtn) {
        acceptBtn.disabled = false;
        acceptBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Accept';
      }
      if (rejectBtn) rejectBtn.disabled = false;
    }
  } catch (err) {
    console.error('Accept invitation failed:', err);
    showToast('Failed to accept campaign invitation.', 'error');
    if (acceptBtn) {
      acceptBtn.disabled = false;
      acceptBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Accept';
    }
    if (rejectBtn) rejectBtn.disabled = false;
  }
}

async function rejectInvitation(invitationId) {
  const acceptBtn = document.getElementById(`btn-accept-${invitationId}`);
  const rejectBtn = document.getElementById(`btn-reject-${invitationId}`);

  if (rejectBtn) {
    rejectBtn.disabled = true;
    rejectBtn.textContent = 'Rejecting...';
  }
  if (acceptBtn) acceptBtn.disabled = true;

  try {
    const result = await invoke('reject_invitation', { invitation_id: invitationId });
    if (result && result.success) {
      showToast('Campaign rejected.', 'info');
      // Remove card with animation
      const card = document.getElementById(`invitation-${invitationId}`);
      if (card) {
        card.style.opacity = '0';
        card.style.transform = 'translateX(-20px)';
        card.style.transition = 'all 0.3s ease';
        setTimeout(() => card.remove(), 300);
      }
      setTimeout(() => loadCampaigns(), 500);
    } else {
      const errorMsg = (result && result.error) || 'Failed to reject campaign.';
      showToast(errorMsg, 'error');
      if (rejectBtn) { rejectBtn.disabled = false; rejectBtn.textContent = 'Reject'; }
      if (acceptBtn) acceptBtn.disabled = false;
    }
  } catch (err) {
    console.error('Reject invitation failed:', err);
    showToast('Failed to reject campaign invitation.', 'error');
    if (rejectBtn) { rejectBtn.disabled = false; rejectBtn.textContent = 'Reject'; }
    if (acceptBtn) acceptBtn.disabled = false;
  }
}

function viewInvitationDetails(invitationId) {
  // Find the invitation in cached data
  if (!campaignsData) return;
  const inv = campaignsData.invitations.find(i =>
    (i.server_id || i.assignment_id || i.campaign_id) === invitationId
  );
  if (!inv) return;

  // Show a detail toast for now (full modal can come later)
  const title = inv.title || 'Campaign';
  const guidance = inv.content_guidance || 'No specific content guidance provided.';
  showToast(`${title}: ${guidance.substring(0, 100)}${guidance.length > 100 ? '...' : ''}`, 'info');
}

// ── Active Campaigns ──

function renderActiveCampaigns(items) {
  const container = document.getElementById('campaigns-active-list');
  if (!items || items.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="1.5">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
        </svg>
        <h3>No active campaigns</h3>
        <p class="text-muted">Accept a campaign invitation to get started.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = items.map((campaign, idx) => renderActiveCampaignCard(campaign, idx)).join('');
}

function renderActiveCampaignCard(campaign, idx) {
  const title = escapeHtml(campaign.title || 'Untitled Campaign');
  const brief = escapeHtml(campaign.brief || '');
  const campaignId = campaign.server_id || campaign.campaign_id;
  const status = campaign.status || 'assigned';

  // Determine pipeline stage from status
  const stages = ['generating', 'review', 'approved', 'scheduled', 'posted', 'paid'];
  const stageLabels = ['Generating', 'Review', 'Approved', 'Scheduled', 'Posted', 'Paid'];
  const currentStageIdx = mapStatusToStageIndex(status);

  const pipelineHtml = buildPipelineHtml(stages, stageLabels, currentStageIdx);

  // Per-platform status
  const platformStatuses = campaign.platform_statuses || {};
  const platformDetailRows = Object.entries(platformStatuses).map(([platform, platformStatus]) => {
    const name = PLATFORM_DISPLAY_NAMES[platform] || platform;
    const stageClass = platformStatus || 'generating';
    const stageLabel = stageClass.charAt(0).toUpperCase() + stageClass.slice(1);
    return `
      <div class="platform-status-row">
        <div class="platform-status-left">
          <span class="platform-icon">${getPlatformIcon(platform)}</span>
          <span class="platform-status-name">${name}</span>
        </div>
        <span class="platform-stage-badge ${stageClass}">${stageLabel}</span>
      </div>
    `;
  }).join('');

  // If no platform_statuses, show generic message
  const detailsContent = platformDetailRows || '<p class="text-muted" style="padding: 12px 0; font-size: 13px;">Platform details will appear once content generation begins.</p>';

  return `
    <div class="active-campaign-card" id="active-campaign-${idx}">
      <div class="active-campaign-card-main" onclick="window.toggleCampaignExpand(${idx})">
        <div class="active-campaign-card-header">
          <span class="active-campaign-card-title">${title}</span>
          <div class="active-campaign-card-toggle">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </div>
        </div>
        <div class="active-campaign-card-brief">${brief}</div>
        <div class="pipeline-container">
          ${pipelineHtml}
        </div>
      </div>
      <div class="active-campaign-details">
        ${detailsContent}
      </div>
      <div class="active-campaign-card-footer">
        <button class="btn btn-primary btn-sm" onclick="event.stopPropagation(); window.viewCampaignPosts(${campaignId})">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
          </svg>
          View Posts
        </button>
      </div>
    </div>
  `;
}

function mapStatusToStageIndex(status) {
  const statusMap = {
    'assigned': 0,
    'active': 0,
    'in_progress': 0,
    'accepted': 0,
    'generating': 0,
    'content_generated': 1,
    'pending_review': 1,
    'review': 1,
    'approved': 2,
    'scheduled': 3,
    'posted': 4,
    'completed': 5,
    'paid': 5,
  };
  return statusMap[status] || 0;
}

function buildPipelineHtml(stages, labels, currentIdx) {
  let html = '<div class="status-pipeline">';

  for (let i = 0; i < stages.length; i++) {
    let dotClass = 'pending';
    let labelClass = '';
    let dotContent = '';

    if (i < currentIdx) {
      dotClass = 'completed';
      labelClass = 'completed';
      dotContent = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
    } else if (i === currentIdx) {
      dotClass = 'current';
      labelClass = 'current';
      dotContent = `<span style="font-size: 8px; font-weight: 700;">${i + 1}</span>`;
    } else {
      dotContent = `<span style="font-size: 8px; color: var(--text-muted);">${i + 1}</span>`;
    }

    html += `<div class="pipeline-stage">
      <div class="pipeline-dot ${dotClass}">${dotContent}</div>
      <span class="pipeline-stage-label ${labelClass}">${labels[i]}</span>`;

    // Add connecting line between stages (except after last)
    if (i < stages.length - 1) {
      const lineClass = i < currentIdx ? 'completed' : '';
      html += `<div class="pipeline-line ${lineClass}"></div>`;
    }

    html += '</div>';
  }

  html += '</div>';
  return html;
}

function toggleCampaignExpand(idx) {
  const card = document.getElementById(`active-campaign-${idx}`);
  if (card) {
    card.classList.toggle('expanded');
  }
}

function viewCampaignPosts(campaignId) {
  // Navigate to Posts tab (filtered view can come later)
  navigateTo('posts');
}

// ── Completed Campaigns ──

function renderCompletedCampaigns(items) {
  const container = document.getElementById('campaigns-completed-list');
  if (!items || items.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="1.5">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
        </svg>
        <h3>No completed campaigns</h3>
        <p class="text-muted">Completed campaigns with final metrics and earnings will appear here.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = items.map(campaign => renderCompletedCampaignCard(campaign)).join('');
}

function renderCompletedCampaignCard(campaign) {
  const title = escapeHtml(campaign.title || 'Untitled Campaign');
  const startDate = formatDate(campaign.started_at || campaign.created_at);
  const endDate = formatDate(campaign.completed_at || campaign.updated_at);
  const impressions = campaign.total_impressions || 0;
  const engagement = campaign.total_engagement || 0;
  const earned = campaign.total_earned || 0;

  return `
    <div class="completed-campaign-card">
      <div class="completed-campaign-top">
        <span class="completed-campaign-title">${title}</span>
        <span class="completed-campaign-dates">${startDate} - ${endDate}</span>
      </div>
      <div class="completed-campaign-metrics">
        <div class="completed-metric">
          <span class="completed-metric-value">${formatCompactNumber(impressions)}</span>
          <span class="completed-metric-label">Impressions</span>
        </div>
        <div class="completed-metric">
          <span class="completed-metric-value">${formatCompactNumber(engagement)}</span>
          <span class="completed-metric-label">Engagement</span>
        </div>
        <div class="completed-metric">
          <span class="completed-metric-value earned">$${parseFloat(earned).toFixed(2)}</span>
          <span class="completed-metric-label">Earned</span>
        </div>
      </div>
    </div>
  `;
}

// ── Number Formatting ────────────────────────────────

function formatCurrency(amount) {
  const num = parseFloat(amount) || 0;
  return '$' + num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatCompactNumber(num) {
  num = parseInt(num) || 0;
  if (num >= 1000000) return (num / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
  if (num >= 1000) return (num / 1000).toFixed(1).replace(/\.0$/, '') + 'K';
  return num.toString();
}

function formatDate(isoString) {
  if (!isoString) return '--';
  try {
    const d = new Date(isoString);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return '--';
  }
}

// ── Earnings Page ────────────────────────────────────

let currentEarningsData = null;

async function loadEarnings() {
  const refreshBtn = document.getElementById('btn-refresh-earnings');
  if (refreshBtn) {
    refreshBtn.disabled = true;
    refreshBtn.classList.add('btn-loading');
  }

  try {
    const data = await invoke('get_earnings');
    currentEarningsData = data;
    renderEarningsSummary(data);
    renderPerCampaign(data.per_campaign || []);
    renderPerPlatform(data.per_platform || {});
    renderPayoutHistory(data.payout_history || []);
    updateWithdrawButton(data.current_balance || data.balance || 0);
  } catch (err) {
    console.error('Failed to load earnings:', err);
    showToast('Failed to load earnings data.', 'error');
  } finally {
    if (refreshBtn) {
      refreshBtn.disabled = false;
      refreshBtn.classList.remove('btn-loading');
    }
  }
}

function renderEarningsSummary(data) {
  const balance = data.current_balance !== undefined ? data.current_balance : (data.balance || 0);
  const total = data.total_earned !== undefined ? data.total_earned : (data.total || 0);
  const pending = data.pending || 0;

  document.getElementById('earnings-balance').textContent = formatCurrency(balance);
  document.getElementById('earnings-total').textContent = formatCurrency(total);
  document.getElementById('earnings-pending').textContent = formatCurrency(pending);
}

function renderPerCampaign(campaigns) {
  const container = document.getElementById('earnings-per-campaign');
  if (!campaigns || campaigns.length === 0) {
    container.innerHTML = `
      <div class="empty-state compact">
        <p class="text-muted">No campaign earnings yet.</p>
      </div>
    `;
    return;
  }

  const rows = campaigns.map(c => {
    const title = escapeHtml(c.campaign_title || 'Untitled');
    const displayTitle = title.length > 30 ? title.substring(0, 27) + '...' : title;
    const statusClass = c.status || 'pending';
    return `
      <tr>
        <td title="${title}">${displayTitle}</td>
        <td class="text-center">${c.posts || 0}</td>
        <td class="text-center">${formatCompactNumber(c.impressions || 0)}</td>
        <td class="text-center">${formatCompactNumber(c.engagement || 0)}</td>
        <td class="text-right amount">${formatCurrency(c.earned || 0)}</td>
        <td class="text-center"><span class="status-badge ${statusClass}"><span class="status-badge-dot"></span>${statusClass}</span></td>
      </tr>
    `;
  }).join('');

  container.innerHTML = `
    <table class="earnings-table">
      <thead>
        <tr>
          <th>Campaign</th>
          <th class="text-center">Posts</th>
          <th class="text-center">Impressions</th>
          <th class="text-center">Engagement</th>
          <th class="text-right">Earned</th>
          <th class="text-center">Status</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderPerPlatform(platformData) {
  const container = document.getElementById('earnings-per-platform');

  const entries = Object.entries(platformData);
  if (!entries || entries.length === 0) {
    container.innerHTML = `
      <div class="empty-state compact">
        <p class="text-muted">No platform earnings yet.</p>
      </div>
    `;
    return;
  }

  // Sort by amount descending
  entries.sort((a, b) => b[1] - a[1]);
  const maxAmount = entries[0][1] || 1;

  const platformNames = {
    x: 'X',
    linkedin: 'LinkedIn',
    facebook: 'Facebook',
    reddit: 'Reddit',
    tiktok: 'TikTok',
    instagram: 'Instagram',
  };

  const bars = entries.map(([platform, amount]) => {
    const pct = Math.max((amount / maxAmount) * 100, 2);
    const label = platformNames[platform] || platform;
    const cssClass = platform.toLowerCase();
    return `
      <div class="platform-bar-row">
        <span class="platform-bar-label">${escapeHtml(label)}</span>
        <div class="platform-bar-track">
          <div class="platform-bar-fill ${cssClass}" style="width: ${pct}%;"></div>
        </div>
        <span class="platform-bar-amount">${formatCurrency(amount)}</span>
      </div>
    `;
  }).join('');

  container.innerHTML = bars;
}

function renderPayoutHistory(payouts) {
  const container = document.getElementById('earnings-payout-history');
  if (!payouts || payouts.length === 0) {
    container.innerHTML = `
      <div class="empty-state compact">
        <p class="text-muted">No payouts yet. Request a withdrawal when your balance exceeds $10.00.</p>
      </div>
    `;
    return;
  }

  const rows = payouts.map(p => {
    const statusClass = p.status || 'pending';
    return `
      <tr>
        <td>${formatDate(p.requested_at)}</td>
        <td class="amount">${formatCurrency(p.amount)}</td>
        <td><span class="status-badge ${statusClass}"><span class="status-badge-dot"></span>${statusClass}</span></td>
      </tr>
    `;
  }).join('');

  container.innerHTML = `
    <table class="earnings-table">
      <thead>
        <tr>
          <th>Date</th>
          <th>Amount</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function updateWithdrawButton(balance) {
  const btn = document.getElementById('btn-withdraw');
  const hint = document.getElementById('withdraw-hint');
  const amount = parseFloat(balance) || 0;

  if (amount >= 10) {
    btn.disabled = false;
    hint.textContent = `${formatCurrency(amount)} available for withdrawal`;
  } else {
    btn.disabled = true;
    hint.textContent = `Minimum withdrawal: $10.00 (current balance: ${formatCurrency(amount)})`;
  }
}

// ── Withdraw Modal ─────────────────────────────────

function openWithdrawModal() {
  const balance = currentEarningsData
    ? (currentEarningsData.current_balance !== undefined ? currentEarningsData.current_balance : (currentEarningsData.balance || 0))
    : 0;

  document.getElementById('withdraw-amount').textContent = formatCurrency(balance);
  document.getElementById('withdraw-modal').style.display = 'flex';
}

function closeWithdrawModal() {
  document.getElementById('withdraw-modal').style.display = 'none';
}

async function confirmWithdraw() {
  const balance = currentEarningsData
    ? (currentEarningsData.current_balance !== undefined ? currentEarningsData.current_balance : (currentEarningsData.balance || 0))
    : 0;

  if (balance < 10) {
    showToast('Insufficient balance for withdrawal.', 'error');
    closeWithdrawModal();
    return;
  }

  const confirmBtn = document.getElementById('btn-confirm-withdraw');
  confirmBtn.disabled = true;
  confirmBtn.textContent = 'Processing...';

  try {
    const result = await invoke('request_payout', { amount: balance });
    if (result && result.success) {
      showToast(`Withdrawal of ${formatCurrency(balance)} requested successfully!`, 'success');
      closeWithdrawModal();
      // Refresh earnings data
      await loadEarnings();
    } else {
      const errorMsg = (result && result.error) || 'Withdrawal request failed.';
      showToast(errorMsg, 'error');
    }
  } catch (err) {
    console.error('Withdraw failed:', err);
    showToast('Withdrawal request failed. Please try again.', 'error');
  } finally {
    confirmBtn.disabled = false;
    confirmBtn.textContent = 'Confirm Withdrawal';
  }
}

// Close modal on overlay click
document.addEventListener('click', (e) => {
  if (e.target && e.target.id === 'withdraw-modal') {
    closeWithdrawModal();
  }
});

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeWithdrawModal();
  }
});

// ── Toast Notifications ──────────────────────────────

function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;

  const icon = type === 'success'
    ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'
    : type === 'error'
    ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>'
    : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>';

  toast.innerHTML = `${icon}<span>${escapeHtml(message)}</span>`;
  container.appendChild(toast);

  // Remove after animation completes
  setTimeout(() => {
    if (toast.parentNode) toast.parentNode.removeChild(toast);
  }, 4000);
}

// ── Connection Status ──────────────────────────────

async function checkConnection() {
  const dot = document.getElementById('connection-dot');
  const text = document.getElementById('connection-text');

  try {
    const result = await invoke('ping_sidecar');
    if (result && result.status === 'connected') {
      dot.className = 'status-dot green';
      text.textContent = 'Connected';
    } else if (result && result.status === 'unhealthy') {
      dot.className = 'status-dot yellow';
      text.textContent = 'Sidecar unhealthy';
    } else {
      dot.className = 'status-dot red';
      text.textContent = 'Disconnected';
    }
  } catch (err) {
    dot.className = 'status-dot red';
    text.textContent = 'Disconnected';
  }
}

// ── Mock Data (for browser testing without Tauri) ──

function getMockData(command, _args) {
  const mocks = {
    get_status: {
      logged_in: false,
      onboarding_done: false,
      email: '',
      active_campaigns: 3,
      pending_invitations: 2,
      posts_queued: 5,
      earnings_balance: 47.50,
      platforms: {
        x: { connected: true, health: 'green' },
        linkedin: { connected: true, health: 'green' },
        facebook: { connected: false, health: 'red' },
        reddit: { connected: true, health: 'green' },
      },
      recent_activity: [
        { type: 'campaign_accepted', description: "Accepted 'Trading Tools Launch'", time: '2h ago' },
        { type: 'post_published', description: 'Posted to LinkedIn for \'SaaS Analytics Pro\'', time: '5h ago' },
        { type: 'earning_received', description: 'Earned $12.50 from \'Crypto Tracker Campaign\'', time: '1d ago' },
        { type: 'post_published', description: 'Posted to X for \'Trading Tools Launch\'', time: '1d ago' },
        { type: 'campaign_rejected', description: "Rejected 'Diet Pills Direct'", time: '3d ago' },
      ],
    },
    ping_sidecar: { status: 'connected' },
    get_invitations: {
      invitations: [
        {
          server_id: 101,
          assignment_id: 201,
          title: 'Trading Tools Launch Campaign',
          brief: 'Promote our new suite of AI-powered trading tools designed for retail traders. Focus on the backtesting feature that helps traders validate strategies before risking real money.',
          payout_rules: { rate_per_1k_impressions: 0.50, rate_per_like: 0.02, rate_per_repost: 0.10, rate_per_click: 0.15 },
          platforms_required: ['x', 'linkedin', 'reddit'],
          content_guidance: 'Educational tone, focus on data-driven insights. Must include disclaimer about trading risks.',
          expires_at: new Date(Date.now() + 2 * 86400000 + 14 * 3600000).toISOString(),
          invited_at: new Date(Date.now() - 86400000).toISOString(),
        },
        {
          server_id: 102,
          assignment_id: 202,
          title: 'SaaS Analytics Pro - Product Hunt Launch',
          brief: 'We are launching on Product Hunt next week. Need influencers to create buzz around our analytics platform that helps SaaS companies understand user behavior.',
          payout_rules: { rate_per_1k_impressions: 0.75, rate_per_like: 0.03, rate_per_repost: 0.15, rate_per_click: 0.20 },
          platforms_required: ['x', 'linkedin'],
          content_guidance: 'Casual, startup-friendly tone. Highlight the free tier and ease of integration.',
          expires_at: new Date(Date.now() + 10 * 3600000).toISOString(),
          invited_at: new Date(Date.now() - 4 * 3600000).toISOString(),
        },
      ],
    },
    get_campaigns: {
      campaigns: [
        {
          server_id: 50,
          title: 'Crypto Tracker Campaign',
          brief: 'Promote real-time crypto portfolio tracking with AI-powered alerts and market sentiment analysis.',
          status: 'content_generated',
          platform_statuses: { x: 'review', linkedin: 'review', reddit: 'generating' },
          created_at: '2026-03-20T10:00:00Z',
        },
        {
          server_id: 51,
          title: 'AI Writing Assistant Beta',
          brief: 'Drive signups for AI writing tool that helps content creators write better, faster.',
          status: 'posted',
          platform_statuses: { x: 'posted', linkedin: 'posted', facebook: 'scheduled' },
          created_at: '2026-03-18T08:00:00Z',
        },
        {
          server_id: 52,
          title: 'Smart Money Signals Pro',
          brief: 'Market intelligence platform for retail traders with institutional-grade data.',
          status: 'approved',
          platform_statuses: { x: 'scheduled', linkedin: 'approved' },
          created_at: '2026-03-22T14:00:00Z',
        },
      ],
    },
    get_completed_campaigns: {
      campaigns: [
        {
          server_id: 30,
          title: 'DevTools Unlimited Launch',
          created_at: '2026-02-15T10:00:00Z',
          completed_at: '2026-03-10T18:00:00Z',
          total_impressions: 45200,
          total_engagement: 2180,
          total_earned: 85.50,
        },
        {
          server_id: 31,
          title: 'CodeReview AI Campaign',
          created_at: '2026-02-20T10:00:00Z',
          completed_at: '2026-03-15T18:00:00Z',
          total_impressions: 28300,
          total_engagement: 1420,
          total_earned: 52.75,
        },
      ],
    },
    get_earnings: {
      total_earned: 175.98,
      current_balance: 45.00,
      pending: 12.50,
      per_campaign: [
        { campaign_id: 1, campaign_title: 'Trading Tools Launch', posts: 4, impressions: 5200, engagement: 250, earned: 35.00, status: 'calculated' },
        { campaign_id: 2, campaign_title: 'Smart Money Signals Pro', posts: 2, impressions: 2100, engagement: 120, earned: 15.00, status: 'paid' },
        { campaign_id: 3, campaign_title: 'Crypto Tracker Campaign', posts: 6, impressions: 8400, engagement: 410, earned: 55.98, status: 'paid' },
        { campaign_id: 4, campaign_title: 'SaaS Analytics Pro', posts: 3, impressions: 3600, engagement: 180, earned: 28.50, status: 'pending' },
        { campaign_id: 5, campaign_title: 'AI Writing Assistant', posts: 5, impressions: 6000, engagement: 340, earned: 41.50, status: 'paid' },
      ],
      per_platform: {
        x: 65.00,
        linkedin: 48.50,
        facebook: 35.98,
        reddit: 26.50,
      },
      payout_history: [
        { id: 1, amount: 50.00, status: 'paid', requested_at: '2026-03-20T14:30:00Z' },
        { id: 2, amount: 30.00, status: 'paid', requested_at: '2026-03-15T09:15:00Z' },
        { id: 3, amount: 50.98, status: 'pending', requested_at: '2026-03-22T16:45:00Z' },
      ],
    },
    request_payout: { success: true, payout_id: 99, amount: 45.00, status: 'pending', new_balance: 0.0 },
    get_settings: {
      mode: 'semi_auto',
      email: 'user@example.com',
      notifications: { invitations: true, failures: true, earnings: true },
      platforms: {
        x: { connected: true, health: 'green', followers: 1520, engagement_rate: 0.035 },
        linkedin: { connected: true, health: 'yellow', followers: 480, engagement_rate: 0.021 },
        facebook: { connected: false, health: 'red', followers: 0, engagement_rate: 0 },
        reddit: { connected: true, health: 'green', followers: 2100, engagement_rate: 0.042 },
      },
      niches: ['finance', 'tech', 'trading'],
      last_scraped: '2026-03-24T10:00:00Z',
      trust_score: 78,
      stats: {
        campaigns_completed: 5,
        campaigns_total: 8,
        best_platform: 'reddit',
        best_platform_engagement: 0.042,
        post_success_rate: { x: 0.95, linkedin: 0.88, facebook: 0.0, reddit: 0.92 },
        earnings_30d: [0, 0, 5.2, 0, 12.5, 0, 8.3, 0, 0, 15.0, 0, 3.1, 0, 22.1, 0, 0, 7.4, 0, 11.8, 0, 4.5, 0, 0, 18.3, 0, 6.7, 0, 9.2, 0, 14.0],
      },
    },
    update_settings: { success: true },
    disconnect_platform: { success: true },
    poll_campaigns: { success: true },
    get_posts: {
      pending_review: [
        {
          campaign_id: 1,
          campaign_title: 'Trading Tools Launch',
          quality_score: 85,
          campaign_updated: false,
          platforms: {
            x: { text: "Most traders lose money on fake reversals because they use RSI wrong.\n\nHere's the one thing they're missing: RSI divergence only works in trending markets.\n\nI backtested 500+ trades and found a 73% win rate with this simple filter.\n\nThread below #Trading #RSI", draft_id: 1 },
            linkedin: { text: "I spent 6 months backtesting RSI divergence strategies across 500+ trades.\n\nThe result? A 73% win rate — but only when you add one crucial filter that most traders ignore.\n\nHere's what the data shows:\n\n1. RSI divergence in ranging markets = coin flip\n2. RSI divergence in trending markets = edge\n3. Adding a trend filter (20 EMA slope) improved accuracy by 31%\n\nThe takeaway: Don't use RSI in isolation. Context is everything.\n\nWhat's your experience with RSI? Drop a comment below.", draft_id: 2 },
            reddit: { text: "I backtested 500+ RSI divergence trades and found something interesting\n\nMost people use RSI divergence as a standalone signal. I tested this across different market conditions and here's what I found:\n\n- In ranging markets: ~50% accuracy (basically random)\n- In trending markets: 73% accuracy\n- With a 20 EMA slope filter: accuracy improved by 31%\n\nThe key insight: RSI divergence is NOT a standalone signal. You need to confirm the trend first.\n\nHappy to share the full backtest data if anyone's interested.", draft_id: 3 },
          },
        },
        {
          campaign_id: 4,
          campaign_title: 'SaaS Analytics Pro',
          quality_score: 62,
          campaign_updated: true,
          platforms: {
            x: { text: "Stop guessing which features your users actually want.\n\nSaaS Analytics Pro tracks every click, scroll, and drop-off point — then tells you exactly what to build next.\n\n14-day free trial, no credit card required.", draft_id: 4 },
            linkedin: { text: "Product teams waste an average of 40% of their sprint on features nobody uses.\n\nI've seen this play out at company after company. The problem isn't the team — it's the data.\n\nSaaS Analytics Pro solves this by tracking real user behavior:\n- Heatmaps show where users click vs. where they don't\n- Funnel analysis reveals exact drop-off points\n- AI-powered recommendations prioritize your backlog\n\nResult: Ship features people actually want. Try it free for 14 days.", draft_id: 5 },
          },
        },
      ],
      scheduled: [
        {
          id: 101, campaign_title: 'Crypto Tracker Campaign', platform: 'x',
          scheduled_at: new Date(Date.now() + 3600000).toISOString(),
          content: "The crypto market moves 24/7 but you can't watch it 24/7. Here's what smart money uses to never miss a move...",
        },
        {
          id: 102, campaign_title: 'Trading Tools Launch', platform: 'linkedin',
          scheduled_at: new Date(Date.now() + 7200000).toISOString(),
          content: "I analyzed 3 years of market data and found that most retail traders enter positions at the worst possible time...",
        },
      ],
      posted: [
        {
          id: 201, campaign_title: 'Smart Money Signals Pro', platform: 'x',
          post_url: 'https://x.com/user/status/123456789',
          posted_at: '2026-03-23T14:30:00Z', status: 'live',
          impressions: 5200, likes: 128, reposts: 34, comments: 22,
        },
        {
          id: 202, campaign_title: 'Smart Money Signals Pro', platform: 'linkedin',
          post_url: 'https://linkedin.com/posts/user_activity-123',
          posted_at: '2026-03-23T15:00:00Z', status: 'live',
          impressions: 2100, likes: 85, reposts: 12, comments: 15,
        },
        {
          id: 203, campaign_title: 'AI Writing Assistant', platform: 'reddit',
          post_url: 'https://reddit.com/r/sideprojects/comments/abc123',
          posted_at: '2026-03-22T20:00:00Z', status: 'live',
          impressions: null, likes: null, reposts: null, comments: null,
        },
      ],
      failed: [
        {
          id: 301, campaign_title: 'Crypto Tracker Campaign', platform: 'facebook',
          error_message: 'Session expired — Facebook login required. Please re-authenticate in Settings.',
          failed_at: '2026-03-23T18:30:00Z',
        },
      ],
    },
    approve_content: { success: true },
    skip_content: { success: true },
    edit_content: { success: true },
    regenerate_content: { success: true },
    cancel_scheduled: { success: true },
    retry_failed: { success: true },
    register: { access_token: 'mock_token_123', email: _args?.email || 'user@example.com' },
    login: { access_token: 'mock_token_123', email: _args?.email || 'user@example.com' },
    connect_platform: { success: true, platform: _args?.platform },
    scrape_platform: {
      platform: _args?.platform || 'x',
      follower_count: 1520,
      following_count: 340,
      bio: 'Building tools for traders. Data-driven insights on markets and tech.',
      display_name: 'Mock User',
      recent_posts: new Array(12).fill({ text: 'Sample post', likes: 25 }),
      engagement_rate: 0.035,
      posting_frequency: 0.4,
    },
    classify_niches: { niches: ['finance', 'tech'] },
    save_onboarding: { success: true },
  };
  return mocks[command] || {};
}

// ── Settings Tab ────────────────────────────────────

let settingsData = null;
let disconnectPlatformTarget = null;

async function loadSettings() {
  try {
    const data = await invoke('get_settings');
    settingsData = data;
    renderSettingsMode(data.mode);
    renderSettingsPlatforms(data.platforms);
    renderSettingsNotifications(data.notifications);
    renderSettingsAccount(data.email);
    renderSettingsProfileSummary(data.platforms, data.niches, data.last_scraped);
    renderSettingsStatistics(data);
  } catch (err) {
    console.error('Failed to load settings:', err);
    showToast('Failed to load settings.', 'error');
  }
}

// ── Operating Mode ──

function renderSettingsMode(mode) {
  const radios = document.querySelectorAll('input[name="operating-mode"]');
  radios.forEach(radio => {
    radio.checked = (radio.value === mode);
    radio.addEventListener('change', async () => {
      if (radio.checked) {
        try {
          await invoke('update_settings', { settings: { mode: radio.value } });
          showToast(`Operating mode changed to ${radio.value.replace('_', ' ')}.`, 'success');
        } catch (err) {
          console.error('Failed to update mode:', err);
          showToast('Failed to update operating mode.', 'error');
        }
      }
    });
  });
}

// ── Connected Platforms ──

function renderSettingsPlatforms(platforms) {
  const container = document.getElementById('settings-platforms');
  if (!platforms || Object.keys(platforms).length === 0) {
    container.innerHTML = '<div class="empty-state compact"><p class="text-muted">No platform data available.</p></div>';
    return;
  }

  const platformConfig = [
    { key: 'x', name: 'X (Twitter)' },
    { key: 'linkedin', name: 'LinkedIn' },
    { key: 'facebook', name: 'Facebook' },
    { key: 'reddit', name: 'Reddit' },
  ];

  container.innerHTML = platformConfig.map(p => {
    const info = platforms[p.key] || { connected: false, health: 'red' };
    const connected = info.connected || false;
    const health = info.health || 'red';
    const connectionLabel = connected ? 'Connected' : 'Not connected';
    const connectionDotClass = connected ? 'green' : 'red';
    const healthLabel = health === 'green' ? 'Healthy' : health === 'yellow' ? 'Expiring' : 'Expired';
    const healthLabelClass = `health-label-${health}`;

    const actions = connected
      ? `<button class="btn btn-secondary btn-sm" onclick="window.reauthPlatform('${p.key}')">Re-authenticate</button>
         <button class="btn btn-ghost btn-sm" onclick="window.confirmDisconnect('${p.key}', '${p.name}')">Disconnect</button>`
      : `<button class="btn btn-primary btn-sm" onclick="window.connectPlatform('${p.key}')">Connect</button>`;

    return `
      <div class="platform-settings-row">
        <div class="platform-settings-info">
          <div class="platform-settings-icon">${getPlatformIcon(p.key)}</div>
          <div class="platform-settings-details">
            <span class="platform-settings-name">${p.name}</span>
            <div class="platform-settings-status">
              <span class="status-dot ${connectionDotClass}"></span>
              <span>${connectionLabel}</span>
              ${connected ? `
                <span class="platform-settings-health">
                  <span class="status-dot ${health}"></span>
                  <span class="${healthLabelClass}">${healthLabel}</span>
                </span>
              ` : ''}
            </div>
          </div>
        </div>
        <div class="platform-settings-actions">
          ${actions}
        </div>
      </div>
    `;
  }).join('');
}

async function reauthPlatform(platform) {
  showToast(`Opening browser for ${PLATFORM_DISPLAY_NAMES[platform] || platform} re-authentication...`, 'info');
  try {
    await invoke('connect_platform', { platform: platform });
    showToast(`Re-authentication complete. Refreshing...`, 'success');
    await loadSettings();
  } catch (err) {
    console.error('Re-auth failed:', err);
    showToast('Re-authentication failed.', 'error');
  }
}

async function connectPlatform(platform) {
  showToast(`Opening browser for ${PLATFORM_DISPLAY_NAMES[platform] || platform} login...`, 'info');
  try {
    await invoke('connect_platform', { platform: platform });
    showToast(`${PLATFORM_DISPLAY_NAMES[platform] || platform} connected. Refreshing...`, 'success');
    await loadSettings();
  } catch (err) {
    console.error('Connect failed:', err);
    showToast('Platform connection failed.', 'error');
  }
}

function confirmDisconnect(platform, displayName) {
  disconnectPlatformTarget = platform;
  document.getElementById('disconnect-platform-name').textContent = displayName;
  document.getElementById('disconnect-modal').style.display = 'flex';
}

function closeDisconnectModal() {
  document.getElementById('disconnect-modal').style.display = 'none';
  disconnectPlatformTarget = null;
}

async function executeDisconnect() {
  if (!disconnectPlatformTarget) return;
  const platform = disconnectPlatformTarget;
  closeDisconnectModal();

  try {
    await invoke('disconnect_platform', { platform: platform });
    showToast(`${PLATFORM_DISPLAY_NAMES[platform] || platform} disconnected.`, 'info');
    await loadSettings();
  } catch (err) {
    console.error('Disconnect failed:', err);
    showToast('Failed to disconnect platform.', 'error');
  }
}

// ── Profile Summary ──

function renderSettingsProfileSummary(platforms, niches, lastScraped) {
  const container = document.getElementById('settings-profile-summary');
  if (!platforms || Object.keys(platforms).length === 0) {
    container.innerHTML = '<div class="empty-state compact"><p class="text-muted">No profile data yet. Connect platforms to scrape.</p></div>';
    return;
  }

  const platformConfig = [
    { key: 'x', name: 'X' },
    { key: 'linkedin', name: 'LinkedIn' },
    { key: 'facebook', name: 'Facebook' },
    { key: 'reddit', name: 'Reddit' },
  ];

  const rows = platformConfig
    .filter(p => platforms[p.key] && platforms[p.key].connected)
    .map(p => {
      const info = platforms[p.key];
      const followers = info.followers || 0;
      const engRate = info.engagement_rate || 0;
      return `
        <div class="profile-platform-row">
          <div class="profile-platform-icon">${getPlatformIcon(p.key)}</div>
          <div class="profile-platform-stats">
            <div class="profile-stat">
              <span class="profile-stat-value">${formatCompactNumber(followers)}</span>
              <span class="profile-stat-label">Followers</span>
            </div>
            <div class="profile-stat">
              <span class="profile-stat-value">${(engRate * 100).toFixed(1)}%</span>
              <span class="profile-stat-label">Engagement</span>
            </div>
          </div>
        </div>
      `;
    });

  if (rows.length === 0) {
    container.innerHTML = '<div class="empty-state compact"><p class="text-muted">No connected platforms with profile data.</p></div>';
    return;
  }

  const nichePills = (niches || []).map(n =>
    `<span class="niche-pill">${escapeHtml(n)}</span>`
  ).join('');

  const scrapedTime = lastScraped ? `Last scraped: ${formatDate(lastScraped)}` : 'Never scraped';

  container.innerHTML = `
    ${rows.join('')}
    ${nichePills ? `<div class="profile-niches">${nichePills}</div>` : ''}
    <div class="profile-last-scraped">${scrapedTime}</div>
  `;
}

async function refreshAllProfiles() {
  const btn = document.getElementById('btn-refresh-profile');
  if (btn) {
    btn.disabled = true;
    btn.classList.add('btn-loading');
  }
  showToast('Refreshing profile data... This may take a minute.', 'info');
  try {
    // Refresh each connected platform
    const platforms = ['x', 'linkedin', 'facebook', 'reddit'];
    for (const p of platforms) {
      try {
        await invoke('refresh_profile', { platform: p });
      } catch (_) {
        // Individual platform failures are OK
      }
    }
    showToast('Profile refresh complete.', 'success');
    await loadSettings();
  } catch (err) {
    console.error('Profile refresh failed:', err);
    showToast('Profile refresh failed.', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.classList.remove('btn-loading');
    }
  }
}

// ── Notifications ──

function renderSettingsNotifications(notifications) {
  if (!notifications) return;
  const notifObj = typeof notifications === 'object' ? notifications : { invitations: true, failures: true, earnings: true };
  const invEl = document.getElementById('notif-invitations');
  const failEl = document.getElementById('notif-failures');
  const earnEl = document.getElementById('notif-earnings');
  if (invEl) invEl.checked = notifObj.invitations !== false;
  if (failEl) failEl.checked = notifObj.failures !== false;
  if (earnEl) earnEl.checked = notifObj.earnings !== false;
}

async function saveNotification(key, value) {
  try {
    const current = settingsData?.notifications || {};
    const updated = typeof current === 'object' ? { ...current } : { invitations: true, failures: true, earnings: true };
    updated[key] = value;
    await invoke('update_settings', { settings: { notifications: JSON.stringify(updated) } });
  } catch (err) {
    console.error('Failed to save notification setting:', err);
    showToast('Failed to save notification preference.', 'error');
  }
}

// ── Account ──

function renderSettingsAccount(email) {
  const el = document.getElementById('settings-email');
  if (el) el.textContent = email || 'Not set';
}

function confirmDeleteAccount() {
  document.getElementById('delete-account-modal').style.display = 'flex';
}

function closeDeleteAccountModal() {
  document.getElementById('delete-account-modal').style.display = 'none';
}

async function executeDeleteAccount() {
  closeDeleteAccountModal();
  showToast('Account deletion is not yet implemented.', 'info');
}

// ── Statistics ──

function renderSettingsStatistics(data) {
  renderTrustScore(data.trust_score);
  renderCampaignCompletion(data.stats);
  renderBestPlatform(data.stats);
  renderEngagementRates(data.platforms);
  renderPostSuccessRate(data.stats?.post_success_rate);
  renderEarningsSparkline(data.stats?.earnings_30d);
}

function renderTrustScore(score) {
  const el = document.getElementById('settings-trust-score');
  const hintEl = document.getElementById('settings-trust-hint');
  if (!el) return;

  if (score === undefined || score === null) {
    el.textContent = '--';
    el.className = 'stat-lg-value';
    return;
  }

  el.textContent = score;
  if (score > 70) {
    el.className = 'stat-lg-value trust-green';
    if (hintEl) hintEl.textContent = 'Good standing. Keep posting quality content.';
  } else if (score >= 40) {
    el.className = 'stat-lg-value trust-yellow';
    if (hintEl) hintEl.textContent = 'Fair. Improve engagement and complete more campaigns.';
  } else {
    el.className = 'stat-lg-value trust-red';
    if (hintEl) hintEl.textContent = 'Low trust. Complete campaigns and avoid post deletions.';
  }
}

function renderCampaignCompletion(stats) {
  const el = document.getElementById('settings-campaign-completion');
  const hintEl = document.getElementById('settings-campaign-hint');
  if (!el || !stats) return;

  const completed = stats.campaigns_completed || 0;
  const total = stats.campaigns_total || 0;
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;

  el.textContent = `${pct}%`;
  if (hintEl) hintEl.textContent = `${completed} / ${total} campaigns completed`;
}

function renderBestPlatform(stats) {
  const el = document.getElementById('settings-best-platform');
  const hintEl = document.getElementById('settings-best-platform-hint');
  if (!el || !stats) return;

  const best = stats.best_platform;
  const engagement = stats.best_platform_engagement || 0;

  if (best) {
    el.textContent = PLATFORM_DISPLAY_NAMES[best] || best;
    if (hintEl) hintEl.textContent = `${(engagement * 100).toFixed(1)}% avg engagement rate`;
  }
}

function renderEngagementRates(platforms) {
  const container = document.getElementById('settings-engagement-rates');
  if (!container) return;

  if (!platforms || Object.keys(platforms).length === 0) {
    container.innerHTML = '<div class="empty-state compact"><p class="text-muted">No engagement data yet.</p></div>';
    return;
  }

  const platformConfig = [
    { key: 'x', name: 'X' },
    { key: 'linkedin', name: 'LinkedIn' },
    { key: 'facebook', name: 'Facebook' },
    { key: 'reddit', name: 'Reddit' },
  ];

  const entries = platformConfig
    .filter(p => platforms[p.key] && platforms[p.key].connected)
    .map(p => ({
      key: p.key,
      name: p.name,
      rate: platforms[p.key].engagement_rate || 0,
    }));

  if (entries.length === 0) {
    container.innerHTML = '<div class="empty-state compact"><p class="text-muted">No connected platforms with engagement data.</p></div>';
    return;
  }

  const maxRate = Math.max(...entries.map(e => e.rate), 0.01);

  container.innerHTML = entries.map(e => {
    const pct = Math.max((e.rate / maxRate) * 100, 4);
    const rateStr = (e.rate * 100).toFixed(1) + '%';
    return `
      <div class="engagement-bar-row">
        <span class="engagement-bar-label">${e.name}</span>
        <div class="engagement-bar-track">
          <div class="engagement-bar-fill ${e.key}" style="width: ${pct}%;"></div>
        </div>
        <span class="engagement-bar-value">${rateStr}</span>
      </div>
    `;
  }).join('');
}

function renderPostSuccessRate(rates) {
  const container = document.getElementById('settings-post-success');
  if (!container) return;

  if (!rates || Object.keys(rates).length === 0) {
    container.innerHTML = '<div class="empty-state compact"><p class="text-muted">No post data yet.</p></div>';
    return;
  }

  const platformNames = { x: 'X', linkedin: 'LinkedIn', facebook: 'Facebook', reddit: 'Reddit' };

  container.innerHTML = Object.entries(rates)
    .filter(([_, rate]) => rate > 0)
    .map(([platform, rate]) => {
      const pct = Math.round(rate * 100);
      const name = platformNames[platform] || platform;
      return `
        <div class="success-rate-row">
          <span class="success-rate-label">${name}</span>
          <div class="success-rate-track">
            <div class="success-rate-fill" style="width: ${pct}%;"></div>
          </div>
          <span class="success-rate-value">${pct}%</span>
        </div>
      `;
    }).join('');
}

function renderEarningsSparkline(earnings30d) {
  const container = document.getElementById('settings-earnings-sparkline');
  if (!container) return;

  if (!earnings30d || earnings30d.length === 0 || earnings30d.every(v => v === 0)) {
    container.innerHTML = '<div class="empty-state compact"><p class="text-muted">No earnings data yet.</p></div>';
    container.style.height = 'auto';
    return;
  }

  container.style.height = '80px';
  container.style.display = 'flex';
  container.style.alignItems = 'flex-end';
  container.style.gap = '2px';

  const maxVal = Math.max(...earnings30d, 0.01);

  container.innerHTML = earnings30d.map(val => {
    if (val === 0) {
      return '<div class="sparkline-zero"></div>';
    }
    const heightPct = Math.max((val / maxVal) * 100, 4);
    return `<div class="sparkline-bar" style="height: ${heightPct}%;" data-value="$${val.toFixed(2)}"></div>`;
  }).join('');
}

// ── Close modals on overlay click and Escape ──

document.addEventListener('click', (e) => {
  if (e.target && e.target.id === 'delete-account-modal') closeDeleteAccountModal();
  if (e.target && e.target.id === 'disconnect-modal') closeDisconnectModal();
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeDeleteAccountModal();
    closeDisconnectModal();
  }
});


// ══════════════════════════════════════════════════════
// Onboarding Wizard
// ══════════════════════════════════════════════════════

let obCurrentStep = 1;
const OB_TOTAL_STEPS = 7;
let obConnectedPlatforms = {}; // { x: true, linkedin: false, ... }
let obScrapeResults = {};       // { x: { follower_count, ... }, ... }
let obDetectedNiches = [];
let obSelectedNiches = [];
let obUserEmail = '';

const OB_PLATFORM_NAMES = {
  x: 'X (Twitter)',
  linkedin: 'LinkedIn',
  facebook: 'Facebook',
  reddit: 'Reddit',
};

const OB_ALL_NICHES = [
  'finance', 'tech', 'ai', 'beauty', 'fashion', 'fitness', 'gaming',
  'food', 'travel', 'education', 'lifestyle', 'business',
  'health', 'entertainment', 'crypto',
];

const OB_REGION_LABELS = {
  global: 'Global',
  us: 'United States',
  uk: 'United Kingdom',
  india: 'India',
  eu: 'European Union',
  latam: 'Latin America',
  sea: 'Southeast Asia',
};

const OB_MODE_LABELS = {
  semi_auto: 'Semi-Auto',
  full_auto: 'Full Auto',
  manual: 'Manual',
};

// Show / hide onboarding vs dashboard
function showOnboarding(fromStep) {
  document.getElementById('onboarding').style.display = 'flex';
  document.getElementById('app').style.display = 'none';
  obCurrentStep = fromStep || 1;
  obRenderStep();
}

function hideOnboarding() {
  document.getElementById('onboarding').style.display = 'none';
  document.getElementById('app').style.display = 'grid';
}

// Step navigation
function obRenderStep() {
  // Update step dots
  document.querySelectorAll('.step-dot').forEach(dot => {
    const step = parseInt(dot.dataset.step);
    dot.classList.remove('active', 'completed');
    if (step === obCurrentStep) dot.classList.add('active');
    else if (step < obCurrentStep) dot.classList.add('completed');
  });

  // Update step lines
  const lines = document.querySelectorAll('.step-line');
  lines.forEach((line, idx) => {
    line.classList.toggle('completed', idx + 1 < obCurrentStep);
  });

  // Show correct step panel
  document.querySelectorAll('.onboarding-step').forEach(s => s.classList.remove('active'));
  const stepEl = document.getElementById(`ob-step-${obCurrentStep}`);
  if (stepEl) stepEl.classList.add('active');

  // Show/hide navigation buttons
  const backBtn = document.getElementById('ob-btn-back');
  const nextBtn = document.getElementById('ob-btn-next');
  const finishBtn = document.getElementById('ob-btn-finish');

  // Step 1 (auth): no back/next -- form submit handles advance
  // Step 3 (scraping): no next -- auto-advances or shows next after done
  backBtn.style.display = obCurrentStep > 1 && obCurrentStep !== 3 ? 'inline-flex' : 'none';

  if (obCurrentStep === 1) {
    nextBtn.style.display = 'none';
    finishBtn.style.display = 'none';
  } else if (obCurrentStep === 2) {
    nextBtn.style.display = 'inline-flex';
    nextBtn.disabled = !obHasConnectedPlatform();
    finishBtn.style.display = 'none';
  } else if (obCurrentStep === 3) {
    nextBtn.style.display = 'none'; // auto-advances when scraping done
    finishBtn.style.display = 'none';
  } else if (obCurrentStep === 7) {
    nextBtn.style.display = 'none';
    finishBtn.style.display = 'inline-flex';
    obBuildSummary();
  } else {
    nextBtn.style.display = 'inline-flex';
    nextBtn.disabled = false;
    finishBtn.style.display = 'none';
  }

  // Step-specific setup
  if (obCurrentStep === 2) obRefreshPlatformStatuses();
  if (obCurrentStep === 3) obStartScraping();
  if (obCurrentStep === 4) obBuildNicheGrid();
}

function obGoNext() {
  if (obCurrentStep === 2 && !obHasConnectedPlatform()) return;
  if (obCurrentStep < OB_TOTAL_STEPS) {
    obCurrentStep++;
    obRenderStep();
  }
}

function obGoBack() {
  if (obCurrentStep > 1) {
    // Skip step 3 (scraping) when going back from step 4
    if (obCurrentStep === 4) {
      obCurrentStep = 2;
    } else {
      obCurrentStep--;
    }
    obRenderStep();
  }
}

function obHasConnectedPlatform() {
  return Object.values(obConnectedPlatforms).some(v => v === true);
}

// ── Step 1: Auth ──

function obSwitchAuth(mode) {
  const regTab = document.getElementById('ob-tab-register');
  const loginTab = document.getElementById('ob-tab-login');
  const regForm = document.getElementById('ob-form-register');
  const loginForm = document.getElementById('ob-form-login');

  if (mode === 'register') {
    regTab.classList.add('active');
    loginTab.classList.remove('active');
    regForm.style.display = 'flex';
    loginForm.style.display = 'none';
  } else {
    loginTab.classList.add('active');
    regTab.classList.remove('active');
    loginForm.style.display = 'flex';
    regForm.style.display = 'none';
  }
}

function obClearErrors(prefix) {
  document.querySelectorAll(`[id^="${prefix}"][id$="-error"]`).forEach(el => {
    el.textContent = '';
  });
}

async function obSubmitRegister(event) {
  event.preventDefault();
  obClearErrors('ob-reg');

  const email = document.getElementById('ob-reg-email').value.trim();
  const password = document.getElementById('ob-reg-password').value;
  const confirm = document.getElementById('ob-reg-confirm').value;

  // Client-side validation
  let hasError = false;
  if (!email || !email.includes('@')) {
    document.getElementById('ob-reg-email-error').textContent = 'Please enter a valid email address.';
    hasError = true;
  }
  if (password.length < 8) {
    document.getElementById('ob-reg-password-error').textContent = 'Password must be at least 8 characters.';
    hasError = true;
  }
  if (password !== confirm) {
    document.getElementById('ob-reg-confirm-error').textContent = 'Passwords do not match.';
    hasError = true;
  }
  if (hasError) return;

  const btn = document.getElementById('ob-btn-register');
  btn.disabled = true;
  btn.textContent = 'Creating account...';

  try {
    const result = await invoke('register', { email, password });
    if (result && result.error) {
      document.getElementById('ob-reg-global-error').textContent = result.error;
      btn.disabled = false;
      btn.textContent = 'Create Account';
      return;
    }
    obUserEmail = email;
    obCurrentStep = 2;
    obRenderStep();
  } catch (err) {
    const msg = typeof err === 'string' ? err : (err.message || 'Registration failed. Please try again.');
    document.getElementById('ob-reg-global-error').textContent = msg;
    btn.disabled = false;
    btn.textContent = 'Create Account';
  }
}

async function obSubmitLogin(event) {
  event.preventDefault();
  obClearErrors('ob-login');

  const email = document.getElementById('ob-login-email').value.trim();
  const password = document.getElementById('ob-login-password').value;

  let hasError = false;
  if (!email || !email.includes('@')) {
    document.getElementById('ob-login-email-error').textContent = 'Please enter a valid email address.';
    hasError = true;
  }
  if (!password) {
    document.getElementById('ob-login-password-error').textContent = 'Please enter your password.';
    hasError = true;
  }
  if (hasError) return;

  const btn = document.getElementById('ob-btn-login');
  btn.disabled = true;
  btn.textContent = 'Logging in...';

  try {
    const result = await invoke('login', { email, password });
    if (result && result.error) {
      document.getElementById('ob-login-global-error').textContent = result.error;
      btn.disabled = false;
      btn.textContent = 'Log In';
      return;
    }
    obUserEmail = email;
    obCurrentStep = 2;
    obRenderStep();
  } catch (err) {
    const msg = typeof err === 'string' ? err : (err.message || 'Login failed. Please try again.');
    document.getElementById('ob-login-global-error').textContent = msg;
    btn.disabled = false;
    btn.textContent = 'Log In';
  }
}

// ── Step 2: Connect Platforms ──

async function obConnectPlatform(platform) {
  const btn = document.getElementById(`ob-connect-${platform}`);
  const statusEl = document.getElementById(`ob-status-${platform}`);
  const card = document.getElementById(`ob-platform-${platform}`);

  if (btn) {
    btn.textContent = 'Connecting...';
    btn.classList.add('connecting');
  }
  if (statusEl) statusEl.textContent = 'Opening browser...';

  try {
    await invoke('connect_platform', { platform });
    obConnectedPlatforms[platform] = true;
    if (card) card.classList.add('connected');
    if (statusEl) statusEl.textContent = 'Connected';
    if (btn) {
      btn.textContent = 'Connected';
      btn.classList.remove('connecting');
      btn.classList.add('connected');
    }
  } catch (err) {
    console.error(`Failed to connect ${platform}:`, err);
    if (statusEl) statusEl.textContent = 'Connection failed';
    if (btn) {
      btn.textContent = 'Retry';
      btn.classList.remove('connecting');
    }
  }

  // Update next button state
  const nextBtn = document.getElementById('ob-btn-next');
  if (nextBtn && obCurrentStep === 2) {
    nextBtn.disabled = !obHasConnectedPlatform();
  }

  // Update hint
  const hint = document.getElementById('ob-platforms-hint');
  if (hint) {
    const count = Object.values(obConnectedPlatforms).filter(v => v).length;
    if (count > 0) {
      hint.textContent = `${count} platform${count > 1 ? 's' : ''} connected. You can connect more or continue.`;
      hint.style.color = 'var(--success)';
    }
  }
}

function obRefreshPlatformStatuses() {
  // On entering step 2, check existing platform health to pre-populate
  // statuses for platforms that may already be connected
  const platforms = ['x', 'linkedin', 'facebook', 'reddit'];
  platforms.forEach(async (platform) => {
    if (obConnectedPlatforms[platform]) {
      const card = document.getElementById(`ob-platform-${platform}`);
      const statusEl = document.getElementById(`ob-status-${platform}`);
      const btn = document.getElementById(`ob-connect-${platform}`);
      if (card) card.classList.add('connected');
      if (statusEl) statusEl.textContent = 'Connected';
      if (btn) {
        btn.textContent = 'Connected';
        btn.classList.add('connected');
      }
    }
  });
}

// ── Step 3: Profile Scraping ──

async function obStartScraping() {
  const list = document.getElementById('ob-scrape-list');
  const connected = Object.entries(obConnectedPlatforms).filter(([_, v]) => v);

  if (connected.length === 0) {
    list.innerHTML = '<p class="ob-hint">No platforms connected.</p>';
    return;
  }

  // Build scraping UI
  list.innerHTML = connected.map(([platform]) => {
    const name = OB_PLATFORM_NAMES[platform] || platform;
    return `
      <div class="ob-scrape-item" id="ob-scrape-${platform}" data-platform="${platform}">
        <div class="ob-scrape-icon">
          <svg class="ob-spinner" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
          </svg>
        </div>
        <div class="ob-scrape-info">
          <div class="ob-scrape-title">Scraping ${name}...</div>
          <div class="ob-scrape-detail">Waiting to start</div>
        </div>
      </div>
    `;
  }).join('');

  // Scrape each platform sequentially
  let allDone = true;
  for (const [platform] of connected) {
    const item = document.getElementById(`ob-scrape-${platform}`);
    const name = OB_PLATFORM_NAMES[platform] || platform;

    // Mark as scraping
    if (item) {
      item.classList.add('scraping');
      item.querySelector('.ob-scrape-detail').textContent = 'Scraping profile data...';
    }

    try {
      const result = await invoke('scrape_platform', { platform });
      obScrapeResults[platform] = result;

      // Show results
      if (item) {
        item.classList.remove('scraping');
        item.classList.add('done');
        item.querySelector('.ob-scrape-icon').innerHTML = `
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
        `;
        item.querySelector('.ob-scrape-title').textContent = `${name} -- Done`;

        const followers = result.follower_count || 0;
        const posts = (result.recent_posts || []).length;
        const engagement = result.engagement_rate || 0;
        const bio = result.bio ? result.bio.substring(0, 60) + (result.bio.length > 60 ? '...' : '') : '';

        let detailHtml = '';
        if (followers > 0) detailHtml += `<span class="ob-metric">${formatCompactNumber(followers)} followers</span>`;
        if (posts > 0) detailHtml += `<span class="ob-metric">${posts} posts scraped</span>`;
        if (engagement > 0) detailHtml += `<span class="ob-metric">${(engagement * 100).toFixed(1)}% engagement</span>`;
        if (bio) detailHtml += `<br/><span style="color: var(--text-muted);">"${escapeHtml(bio)}"</span>`;

        item.querySelector('.ob-scrape-detail').innerHTML = detailHtml || 'Profile scraped successfully.';
      }
    } catch (err) {
      console.error(`Scrape ${platform} failed:`, err);
      allDone = false;
      if (item) {
        item.classList.remove('scraping');
        item.classList.add('error');
        item.querySelector('.ob-scrape-icon').innerHTML = `
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
          </svg>
        `;
        item.querySelector('.ob-scrape-title').textContent = `${name} -- Failed`;
        item.querySelector('.ob-scrape-detail').textContent = 'Could not scrape profile. You can retry later in Settings.';
      }
    }
  }

  // Run niche classification
  try {
    const niches = await invoke('classify_niches');
    if (niches && Array.isArray(niches.niches)) {
      obDetectedNiches = niches.niches;
    } else if (niches && Array.isArray(niches)) {
      obDetectedNiches = niches;
    }
  } catch (err) {
    console.error('Niche classification failed:', err);
  }

  // Show next button after scraping completes
  const nextBtn = document.getElementById('ob-btn-next');
  const backBtn = document.getElementById('ob-btn-back');
  nextBtn.style.display = 'inline-flex';
  nextBtn.disabled = false;
  backBtn.style.display = 'inline-flex';
}

// ── Step 4: Niche Confirmation ──

function obBuildNicheGrid() {
  const grid = document.getElementById('ob-niche-grid');
  obSelectedNiches = [...obDetectedNiches]; // Start with AI-detected niches pre-selected

  grid.innerHTML = OB_ALL_NICHES.map(niche => {
    const isSelected = obSelectedNiches.includes(niche);
    return `
      <div class="ob-niche-item ${isSelected ? 'selected' : ''}" data-niche="${niche}" onclick="window.obToggleNiche('${niche}', this)">
        <div class="ob-niche-checkbox">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
        </div>
        <span class="ob-niche-label">${niche}</span>
      </div>
    `;
  }).join('');
}

function obToggleNiche(niche, el) {
  const idx = obSelectedNiches.indexOf(niche);
  if (idx >= 0) {
    obSelectedNiches.splice(idx, 1);
    el.classList.remove('selected');
  } else {
    obSelectedNiches.push(niche);
    el.classList.add('selected');
  }
}

// ── Step 6: Mode Selection ──

function obSelectMode(radio) {
  document.querySelectorAll('.ob-mode-option').forEach(opt => {
    opt.classList.toggle('selected', opt.querySelector('input').checked);
  });
}

// ── Step 7: Summary ──

function obBuildSummary() {
  const emailEl = document.getElementById('ob-summary-email');
  const platformsEl = document.getElementById('ob-summary-platforms');
  const nichesEl = document.getElementById('ob-summary-niches');
  const regionEl = document.getElementById('ob-summary-region');
  const modeEl = document.getElementById('ob-summary-mode');

  if (emailEl) emailEl.textContent = obUserEmail || '--';

  if (platformsEl) {
    const connected = Object.entries(obConnectedPlatforms)
      .filter(([_, v]) => v)
      .map(([k]) => OB_PLATFORM_NAMES[k] || k);
    platformsEl.textContent = connected.length > 0 ? connected.join(', ') : 'None';
  }

  if (nichesEl) {
    nichesEl.textContent = obSelectedNiches.length > 0 ? obSelectedNiches.join(', ') : 'None selected';
  }

  if (regionEl) {
    const regionValue = document.getElementById('ob-region-select').value;
    regionEl.textContent = OB_REGION_LABELS[regionValue] || regionValue;
  }

  if (modeEl) {
    const modeRadio = document.querySelector('input[name="ob-mode"]:checked');
    const modeValue = modeRadio ? modeRadio.value : 'semi_auto';
    modeEl.textContent = OB_MODE_LABELS[modeValue] || modeValue;
  }
}

// ── Finish Onboarding ──

async function obFinish() {
  const finishBtn = document.getElementById('ob-btn-finish');
  finishBtn.disabled = true;
  finishBtn.textContent = 'Setting up...';

  const region = document.getElementById('ob-region-select').value;
  const modeRadio = document.querySelector('input[name="ob-mode"]:checked');
  const mode = modeRadio ? modeRadio.value : 'semi_auto';

  try {
    await invoke('save_onboarding', {
      niches: obSelectedNiches,
      region: region,
      mode: mode,
    });
  } catch (err) {
    console.error('save_onboarding failed:', err);
    // Non-fatal -- continue to dashboard even if save fails
  }

  hideOnboarding();

  // Initialize the dashboard
  await checkConnection();
  await refreshDashboard();
  startDashboardTimers();
}

// ── Expose to global scope for inline handlers ─────

window.refreshDashboard = refreshDashboard;
window.refreshCampaigns = refreshCampaigns;
window.switchCampaignsTab = switchCampaignsTab;
window.acceptInvitation = acceptInvitation;
window.rejectInvitation = rejectInvitation;
window.viewInvitationDetails = viewInvitationDetails;
window.toggleCampaignExpand = toggleCampaignExpand;
window.viewCampaignPosts = viewCampaignPosts;
window.refreshPosts = refreshPosts;
window.switchPostsTab = switchPostsTab;
window.switchPlatformTab = switchPlatformTab;
window.toggleEditMode = toggleEditMode;
window.updateCharCount = updateCharCount;
window.saveEdit = saveEdit;
window.regeneratePlatform = regeneratePlatform;
window.approvePlatform = approvePlatform;
window.approveAll = approveAll;
window.skipContent = skipContent;
window.cancelScheduled = cancelScheduled;
window.retryFailed = retryFailed;
window.navigateTo = navigateTo;
window.refreshEarnings = loadEarnings;
window.openWithdrawModal = openWithdrawModal;
window.closeWithdrawModal = closeWithdrawModal;
window.confirmWithdraw = confirmWithdraw;
window.loadSettings = loadSettings;
window.reauthPlatform = reauthPlatform;
window.connectPlatform = connectPlatform;
window.confirmDisconnect = confirmDisconnect;
window.closeDisconnectModal = closeDisconnectModal;
window.executeDisconnect = executeDisconnect;
window.refreshAllProfiles = refreshAllProfiles;
window.saveNotification = saveNotification;
window.confirmDeleteAccount = confirmDeleteAccount;
window.closeDeleteAccountModal = closeDeleteAccountModal;
window.executeDeleteAccount = executeDeleteAccount;
window.showToast = showToast;

// Onboarding handlers
window.obSwitchAuth = obSwitchAuth;
window.obSubmitRegister = obSubmitRegister;
window.obSubmitLogin = obSubmitLogin;
window.obConnectPlatform = obConnectPlatform;
window.obToggleNiche = obToggleNiche;
window.obSelectMode = obSelectMode;
window.obGoNext = obGoNext;
window.obGoBack = obGoBack;
window.obFinish = obFinish;

async function logoutUser() {
  if (!confirm('Are you sure you want to logout?')) return;
  try {
    if (isTauri) {
      await invoke('save_onboarding', { niches: [], region: '', mode: '' });
    }
  } catch (e) { /* ignore */ }
  // Clear local auth file by writing empty state
  try {
    if (isTauri) {
      await invoke('logout');
    }
  } catch (e) { /* ignore */ }
  // Show onboarding
  showOnboarding();
}
window.logoutUser = logoutUser;

// ── Dashboard Timer Setup (extracted for reuse) ─────

function startDashboardTimers() {
  // Refresh dashboard every 60 seconds
  if (!dashboardRefreshTimer) {
    dashboardRefreshTimer = setInterval(refreshDashboard, 60 * 1000);
  }

  // Auto-refresh posts every 60 seconds if on the posts page
  if (!postsRefreshTimer) {
    postsRefreshTimer = setInterval(() => {
      const postsPage = document.getElementById('page-posts');
      if (postsPage && postsPage.classList.contains('active')) {
        loadPosts();
      }
    }, 60 * 1000);
  }

  // Auto-refresh campaigns every 60 seconds if on the campaigns page
  setInterval(() => {
    const campaignsPage = document.getElementById('page-campaigns');
    if (campaignsPage && campaignsPage.classList.contains('active')) {
      loadCampaigns();
    }
  }, 60 * 1000);

  // Poll connection status every 30 seconds
  setInterval(checkConnection, 30000);

  // Poll for new campaigns every 10 minutes
  setInterval(async () => {
    try {
      await invoke('poll_campaigns');
      await refreshDashboard();
    } catch (err) {
      console.error('Campaign poll failed:', err);
    }
  }, 10 * 60 * 1000);
}

// ── Init ───────────────────────────────────────────

async function init() {
  // Check sidecar connection first
  await checkConnection();

  // Determine app state: onboarding or dashboard
  try {
    const status = await invoke('get_status');

    if (!status.logged_in) {
      // Not logged in → show onboarding from step 1
      showOnboarding(1);
      return;
    }

    // Logged in — check if onboarding was completed
    if (status.onboarding_done === false) {
      // Logged in but onboarding incomplete → show from step 2
      // Pre-populate connected platforms from status
      if (status.platforms) {
        for (const [platform, info] of Object.entries(status.platforms)) {
          if (info && info.connected) {
            obConnectedPlatforms[platform] = true;
          }
        }
      }
      obUserEmail = status.email || '';
      showOnboarding(2);
      return;
    }

    // Fully set up → show dashboard
    hideOnboarding();
    await refreshDashboard();
    startDashboardTimers();

  } catch (err) {
    console.error('Init failed, showing dashboard:', err);
    // If we can't determine state (e.g., sidecar not running in dev),
    // default to showing dashboard
    hideOnboarding();
    await refreshDashboard();
    startDashboardTimers();
  }
}

// Start when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
