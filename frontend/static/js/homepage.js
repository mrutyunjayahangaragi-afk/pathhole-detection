/**
 * CivicLens Homepage Client Logic (v2.5)
 * =====================================
 * Integrates real-time telemetry, 5 KPI metrics, interactive Leaflet monitor,
 * live activity timeline, global search, and impact showcase.
 */

(function () {
  'use strict';

  // ─────────────────────────────────────────────────────────────
  // 1. Live Date & Time Display
  // ─────────────────────────────────────────────────────────────
  function initLiveClock() {
    const clockEl = document.getElementById('header-live-clock');
    if (!clockEl) return;

    function update() {
      const now = new Date();
      const options = {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: true
      };
      clockEl.textContent = now.toLocaleString('en-IN', options) + ' IST';
    }

    update();
    setInterval(update, 1000);
  }

  // ─────────────────────────────────────────────────────────────
  // 2. Global Public Search
  // ─────────────────────────────────────────────────────────────
  function initGlobalSearch() {
    const input = document.getElementById('header-global-search');
    const dropdown = document.getElementById('header-search-dropdown');
    if (!input || !dropdown) return;

    let debounceTimer = null;

    input.addEventListener('input', function () {
      const q = this.value.trim();
      clearTimeout(debounceTimer);

      if (q.length < 2) {
        dropdown.style.display = 'none';
        dropdown.innerHTML = '';
        return;
      }

      debounceTimer = setTimeout(async () => {
        dropdown.innerHTML = '<div style="padding: 12px 16px; font-size: 12px; color: var(--cl-text-muted);">Searching municipal database...</div>';
        dropdown.style.display = 'block';

        try {
          const res = await fetch(`/api/v2/public/search?q=${encodeURIComponent(q)}&limit=8`);
          if (!res.ok) throw new Error('Search failed');
          const data = await res.json();
          const results = data.results || [];

          if (results.length === 0) {
            dropdown.innerHTML = `
              <div style="padding: 14px 16px; font-size: 13px; color: var(--cl-text-secondary); text-align: center;">
                No matches found for "<strong>${escapeHtml(q)}</strong>". Try searching by locality, category, or reference (e.g. INC-...).
              </div>
            `;
            return;
          }

          let html = '';
          results.forEach(r => {
            const statusClass = r.status === 'resolved' ? 'cl-badge-status-resolved' : 'cl-badge-status-progress';
            html += `
              <a href="${r.link}" class="cl-search-item">
                <div style="min-width: 0; padding-right: 12px;">
                  <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 2px;">
                    <span style="font-family: var(--cl-font-mono); font-size: 11px; font-weight: 700; color: var(--cl-primary);">${r.incident_reference}</span>
                    <span class="cl-carousel-badge ${statusClass}" style="font-size: 9px; padding: 2px 6px;">${r.status}</span>
                  </div>
                  <div style="font-weight: 600; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; overflow: hidden;">
                    ${escapeHtml(r.description || r.category)}
                  </div>
                  <div style="font-size: 11px; color: var(--cl-text-muted);">
                    📍 ${escapeHtml(r.address)}
                  </div>
                </div>
                <span style="font-size: 12px; color: var(--cl-primary); font-weight: 600; flex-shrink: 0;">View &rarr;</span>
              </a>
            `;
          });

          dropdown.innerHTML = html;
        } catch (err) {
          dropdown.innerHTML = '<div style="padding: 12px 16px; font-size: 12px; color: var(--cl-severe);">Search temporarily unavailable.</div>';
        }
      }, 250);
    });

    // Close on escape or click outside
    document.addEventListener('click', function (e) {
      if (!input.contains(e.target) && !dropdown.contains(e.target)) {
        dropdown.style.display = 'none';
      }
    });

    input.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        dropdown.style.display = 'none';
      }
    });
  }

  // ─────────────────────────────────────────────────────────────
  // 3. 5 Real-Time KPI Metric Cards
  // ─────────────────────────────────────────────────────────────
  async function loadStatistics() {
    const elReports = document.getElementById('counter-reports');
    const elIncidents = document.getElementById('counter-incidents');
    const elResolved = document.getElementById('counter-resolved');
    const elPending = document.getElementById('counter-pending');
    const elDedup = document.getElementById('counter-dedup');

    try {
      const res = await fetch('/api/v2/public/statistics');
      if (!res.ok) throw new Error('Failed to load metrics');
      const data = await res.json();

      if (data && data.status === 'success') {
        if (elReports) elReports.textContent = Number(data.total_citizen_reports || 0).toLocaleString();
        if (elIncidents) elIncidents.textContent = Number(data.total_canonical_incidents || 0).toLocaleString();
        
        const resolved = (data.status_breakdown && data.status_breakdown.resolved) || 0;
        if (elResolved) elResolved.textContent = Number(resolved).toLocaleString();

        const pending = (data.status_breakdown && (data.status_breakdown.awaiting_verification || 0)) || 0;
        if (elPending) elPending.textContent = Number(pending).toLocaleString();

        const ratio = data.deduplication_ratio !== undefined ? Number(data.deduplication_ratio).toFixed(2) + 'x' : '1.00x';
        if (elDedup) elDedup.textContent = ratio;
      }
    } catch (e) {
      if (elReports) elReports.textContent = '0';
      if (elIncidents) elIncidents.textContent = '0';
      if (elResolved) elResolved.textContent = '0';
      if (elPending) elPending.textContent = '0';
      if (elDedup) elDedup.textContent = '1.00x';
    }
  }

  // ─────────────────────────────────────────────────────────────
  // 4. Live CivicLens Monitor (Leaflet Map)
  // ─────────────────────────────────────────────────────────────
  let monitorMap = null;
  let incidentMarkersLayer = null;

  async function initMonitorMap() {
    const mapContainer = document.getElementById('homepage-leaflet-map');
    if (!mapContainer || typeof L === 'undefined') return;

    const BENGALURU_CENTER = [12.9716, 77.5946];

    monitorMap = L.map('homepage-leaflet-map', {
      zoomControl: true,
      attributionControl: true
    }).setView(BENGALURU_CENTER, 12);

    // Attach basemap using centralized CivicLens provider
    if (window.CivicLensMapProvider) {
      await window.CivicLensMapProvider.attachBasemap(monitorMap, { purpose: 'public_map' });
    } else {
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 19
      }).addTo(monitorMap);
    }

    // Force size recalculation after DOM paint
    setTimeout(() => { if (monitorMap) monitorMap.invalidateSize(); }, 150);
    setTimeout(() => { if (monitorMap) monitorMap.invalidateSize(); }, 400);

    incidentMarkersLayer = L.layerGroup().addTo(monitorMap);
    await loadMapIncidents();

    // Reset view button
    const btnCenter = document.getElementById('btn-map-center');
    if (btnCenter) {
      btnCenter.addEventListener('click', () => {
        if (monitorMap) {
          monitorMap.setView(BENGALURU_CENTER, 12);
        }
      });
    }

    // Refresh map markers button
    const btnRefresh = document.getElementById('btn-map-refresh');
    if (btnRefresh) {
      btnRefresh.addEventListener('click', async () => {
        btnRefresh.classList.add('cl-spin');
        await loadMapIncidents();
        btnRefresh.classList.remove('cl-spin');
      });
    }
  }

  async function loadMapIncidents() {
    if (!incidentMarkersLayer) return;
    incidentMarkersLayer.clearLayers();

    try {
      const res = await fetch('/api/v2/public/incidents/viewport?min_lon=76.0&min_lat=12.0&max_lon=78.5&max_lat=13.5&limit=100');
      if (!res.ok) throw new Error('Viewport query failed');
      const data = await res.json();
      const items = data.items || [];

      const statusColors = {
        verified: '#ef4444',
        in_progress: '#3b82f6',
        assigned: '#3b82f6',
        on_hold: '#f59e0b',
        resolved: '#10b981',
        closed: '#10b981'
      };

      items.forEach(inc => {
        if (!inc.latitude || !inc.longitude) return;

        const color = statusColors[inc.status] || '#64748b';
        const marker = L.circleMarker([inc.latitude, inc.longitude], {
          radius: 7,
          fillColor: color,
          color: '#ffffff',
          weight: 2,
          opacity: 1,
          fillOpacity: 0.85
        });

        const popupContent = `
          <div style="font-family: var(--cl-font-sans); min-width: 180px;">
            <div style="font-family: var(--cl-font-mono); font-size: 11px; font-weight: 700; color: var(--cl-primary);">${inc.incident_reference || 'INC-SITE'}</div>
            <div style="font-weight: 700; font-size: 13px; text-transform: capitalize; margin: 2px 0;">${escapeHtml(inc.category.replace('_', ' '))}</div>
            <div style="font-size: 11px; color: var(--cl-text-secondary); margin-bottom: 6px;">📍 ${escapeHtml(inc.location_name || 'Bengaluru')}</div>
            <div style="display: flex; justify-content: space-between; align-items: center; border-top: 1px solid #e2e8f0; padding-top: 6px;">
              <span style="font-size: 10px; text-transform: uppercase; font-weight: 700; color: ${color};">${inc.status}</span>
              <a href="/public-incident.html?ref=${inc.incident_reference || inc.id}" style="color: var(--cl-primary); font-size: 11px; font-weight: 600; text-decoration: none;">Details &rarr;</a>
            </div>
          </div>
        `;

        marker.bindPopup(popupContent);
        incidentMarkersLayer.addLayer(marker);
      });

      // Update incident counter in map header if present
      const mapCountBadge = document.getElementById('map-incident-count-badge');
      if (mapCountBadge) {
        mapCountBadge.textContent = `${items.length} Sites Mapped`;
      }
    } catch (e) {
      console.warn('[HomepageMonitor] Failed to load incident markers:', e);
    }
  }

  // ─────────────────────────────────────────────────────────────
  // 5. Recent Civic Activity Feed
  // ─────────────────────────────────────────────────────────────
  async function loadRecentActivity() {
    const feedContainer = document.getElementById('activity-timeline-feed');
    if (!feedContainer) return;

    try {
      const res = await fetch('/api/v2/public/recent-activity?limit=12');
      if (!res.ok) throw new Error('Failed to load recent activity');
      const data = await res.json();
      const events = data.events || [];

      if (events.length === 0) {
        feedContainer.innerHTML = `
          <div style="padding: 24px; text-align: center; color: var(--cl-text-secondary); font-size: 13px;">
            No recent activity recorded yet today.
          </div>
        `;
        return;
      }

      let html = '';
      events.forEach(ev => {
        const timeAgo = formatRelativeTime(ev.timestamp);
        const iconSvg = getActivityIcon(ev.event_type);

        html += `
          <a href="${ev.link || '#'}" class="cl-activity-item">
            <div style="margin-top: 2px; flex-shrink: 0;">
              ${iconSvg}
            </div>
            <div style="flex: 1; min-width: 0;">
              <div style="display: flex; align-items: center; justify-content: space-between; gap: 6px; margin-bottom: 2px;">
                <span class="cl-activity-badge">${escapeHtml(ev.reference)}</span>
                <span style="font-size: 11px; color: var(--cl-text-muted);">${timeAgo}</span>
              </div>
              <div style="font-weight: 600; font-size: 13px; color: var(--cl-text-primary); line-height: 1.3;">
                ${escapeHtml(ev.title)}
              </div>
              <p style="font-size: 12px; color: var(--cl-text-secondary); margin: 2px 0 0 0; line-height: 1.35; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                ${escapeHtml(ev.description)}
              </p>
              <div style="font-size: 11px; color: var(--cl-text-muted); margin-top: 3px;">
                📍 ${escapeHtml(ev.location_name)}
              </div>
            </div>
          </a>
        `;
      });

      feedContainer.innerHTML = html;
    } catch (e) {
      feedContainer.innerHTML = `
        <div style="padding: 20px; text-align: center; color: var(--cl-text-muted); font-size: 12px;">
          Unable to refresh activity feed. <button onclick="window.CivicLensHomepage.loadRecentActivity()" class="cl-btn cl-btn-secondary cl-btn-sm" style="margin-left: 6px;">Retry</button>
        </div>
      `;
    }
  }

  function getActivityIcon(eventType) {
    if (eventType === 'incident_resolved') {
      return '<div style="width: 24px; height: 24px; border-radius: 50%; background: #ecfdf5; display: flex; align-items: center; justify-content: center; color: #059669; font-weight: 700; font-size: 12px;">✓</div>';
    } else if (eventType === 'incident_verified') {
      return '<div style="width: 24px; height: 24px; border-radius: 50%; background: #eff6ff; display: flex; align-items: center; justify-content: center; color: #1d4ed8; font-weight: 700; font-size: 12px;">🔍</div>';
    } else if (eventType === 'incident_in_progress') {
      return '<div style="width: 24px; height: 24px; border-radius: 50%; background: #fffbeb; display: flex; align-items: center; justify-content: center; color: #d97706; font-weight: 700; font-size: 12px;">⚙️</div>';
    } else {
      return '<div style="width: 24px; height: 24px; border-radius: 50%; background: #f8fafc; border: 1px solid #e2e8f0; display: flex; align-items: center; justify-content: center; color: #475569; font-size: 11px;">📌</div>';
    }
  }

  function formatRelativeTime(dateString) {
    if (!dateString) return 'recently';
    const date = new Date(dateString);
    const now = new Date();
    const diffSec = Math.floor((now - date) / 1000);

    if (diffSec < 60) return 'Just now';
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHour = Math.floor(diffMin / 60);
    if (diffHour < 24) return `${diffHour}h ago`;
    const diffDay = Math.floor(diffHour / 24);
    if (diffDay < 7) return `${diffDay}d ago`;
    return date.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' });
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // ─────────────────────────────────────────────────────────────
  // 6. Impact Showcase Cards ("Real Problems. Real Progress.")
  // ─────────────────────────────────────────────────────────────
  function initImpactShowcase() {
    const bafGrid = document.getElementById('baf-showcase-grid');
    const filterPills = document.querySelectorAll('.cl-filter-pill');
    if (!bafGrid) return;

    function loadCards(category = 'all') {
      bafGrid.innerHTML = '<div class="col-12 text-center py-4 text-muted">Loading verified improvement records...</div>';

      let url = '/api/public/homepage-showcase?limit=12';
      if (category && category !== 'all') {
        url += '&category=' + encodeURIComponent(category);
      }

      fetch(url)
        .then(r => r.json())
        .then(data => {
          const items = data.items || [];
          if (!items.length) {
            bafGrid.innerHTML = `
              <div class="col-12 text-center py-5">
                <div style="font-size: 2rem; margin-bottom: 8px;">🔍</div>
                <h4 style="font-size: 1rem; font-weight: 700;">No verified improvements in this category yet</h4>
                <p style="color: var(--cl-text-secondary); font-size: 0.85rem;">Check back soon as municipal triage teams complete work orders.</p>
              </div>
            `;
            return;
          }

          let html = '';
          items.forEach(it => {
            const catLabel = it.category.replace('_', ' ');
            const statusBadge = it.status === 'resolved' 
              ? '<span class="cl-status-pill cl-status-published">Resolved</span>' 
              : '<span class="cl-status-pill cl-status-approved">Verified Work Order</span>';

            html += `
              <div class="col-12 col-md-6 col-lg-4">
                <div class="cl-baf-card h-100">
                  <div style="height: 200px; background: #0F172A; position: relative; overflow: hidden;">
                    ${it.media_type === 'VIDEO' ? `
                      <video src="${it.media_url}" style="width: 100%; height: 100%; object-fit: cover;" muted playsinline controls></video>
                      <span style="position: absolute; top: 10px; right: 10px; background: rgba(0,0,0,0.65); color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 0.72rem; font-weight: 700;">VIDEO</span>
                    ` : `
                      <img src="${it.media_url}" alt="${escapeHtml(it.title)}" style="width: 100%; height: 100%; object-fit: cover;" onerror="this.src='./static/images/branding/civiclens-emblem-192.png'">
                    `}
                    <span class="cl-baf-tag cl-baf-tag-after">${escapeHtml(it.before_after_type)}</span>
                  </div>
                  <div class="cl-baf-content">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                      <span style="font-size: 0.75rem; font-weight: 700; text-transform: uppercase; color: var(--cl-primary);">${catLabel}</span>
                      ${statusBadge}
                    </div>
                    <h4 style="font-size: 0.98rem; font-weight: 700; margin: 0 0 6px 0; line-height: 1.3;">${escapeHtml(it.title)}</h4>
                    <p style="font-size: 0.82rem; color: var(--cl-text-secondary); margin: 0 0 10px 0; line-height: 1.4; flex: 1;">
                      ${escapeHtml(it.description || 'Verified municipal resolution and site remediation completed by civic engineering crews.')}
                    </p>
                    <div style="padding-top: 8px; border-top: 1px solid var(--cl-border); font-size: 0.78rem; color: var(--cl-text-muted); display: flex; justify-content: space-between; align-items: center;">
                      <span>📍 ${escapeHtml(it.public_location_label)}</span>
                      ${it.incident_link ? `<a href="${it.incident_link}" style="color: var(--cl-primary); font-weight: 600; text-decoration: none;">View &rarr;</a>` : ''}
                    </div>
                  </div>
                </div>
              </div>
            `;
          });

          bafGrid.innerHTML = html;
        })
        .catch(() => {
          bafGrid.innerHTML = '<div class="col-12 text-center text-muted py-4">Unable to load showcase items.</div>';
        });
    }

    filterPills.forEach(pill => {
      pill.addEventListener('click', function () {
        filterPills.forEach(p => p.classList.remove('active'));
        this.classList.add('active');
        loadCards(this.dataset.category);
      });
    });

    loadCards('all');
  }

  // ─────────────────────────────────────────────────────────────
  // 6. Hero Municipal Showcase Carousel (3s Auto-Slide)
  // ─────────────────────────────────────────────────────────────
  function initHeroCarousel() {
    const carouselEl = document.getElementById('heroMunicipalCarousel');
    if (!carouselEl || typeof bootstrap === 'undefined' || !bootstrap.Carousel) return;

    try {
      const carousel = bootstrap.Carousel.getOrCreateInstance(carouselEl, {
        interval: 3000,
        ride: 'carousel',
        pause: 'hover',
        wrap: true
      });
      carousel.cycle();
    } catch (e) {
      console.warn('Hero carousel initialization notice:', e);
    }
  }

  // ─────────────────────────────────────────────────────────────
  // DOM Ready Bootstrap
  // ─────────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', function () {
    initLiveClock();
    initGlobalSearch();
    loadStatistics();
    initMonitorMap();
    loadRecentActivity();
    initImpactShowcase();
    initHeroCarousel();
  });

  // Expose global methods for manual refresh
  window.CivicLensHomepage = {
    loadStatistics,
    loadRecentActivity,
    loadMapIncidents
  };
})();
