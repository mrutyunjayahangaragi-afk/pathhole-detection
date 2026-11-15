/**
 * CivicLens Navigation Component
 * ==============================
 * Manages responsive sidebar on desktop and slide-in drawer on mobile.
 * Works seamlessly whether served over HTTP or opened directly from filesystem.
 */

(function () {
  function getBasePrefix() {
    const path = window.location.pathname;
    if (path.includes('/municipal/') || path.includes('/dashboard/')) {
      return '../';
    }
    return './';
  }

  function initNavigation() {
    const prefix = getBasePrefix();
    const currentPath = window.location.pathname;

    const navItems = [
      { key: 'home', label: 'Home Portal', icon: '🏛️', href: prefix + 'index.html' },
      { key: 'citizen_dashboard', label: 'Citizen Dashboard', icon: '👤', href: prefix + 'citizen-dashboard.html' },
      { key: 'report', label: 'Report Defect', icon: '📢', href: prefix + 'citizen-report.html' },
      { key: 'my_reports', label: 'My Submissions', icon: '📋', href: prefix + 'my-reports.html' },
      { key: 'map', label: 'Public Map', icon: '🗺️', href: prefix + 'public-map.html' },
      { key: 'dashboard', label: 'Live Monitor', icon: '⚡', href: prefix + 'dashboard/dashboard.html' },
      { key: 'municipal', label: 'Municipal Triage', icon: '🛠️', href: prefix + 'municipal/dashboard.html' },
      { key: 'verification', label: 'Verification Queue', icon: '🔍', href: prefix + 'municipal/verification.html' },
    ];

    // Build sidebar markup if container exists
    const sidebarContainer = document.getElementById('cl-sidebar-container');
    if (sidebarContainer) {
      const activeKey = sidebarContainer.dataset.active || '';

      const navLinksHtml = navItems.map(item => {
        const isActive = activeKey === item.key || currentPath.endsWith(item.href.replace('./', '').replace('../', ''));
        return `
          <li>
            <a href="${item.href}" class="cl-nav-link ${isActive ? 'active' : ''}" data-nav-key="${item.key}">
              <span class="cl-nav-icon">${item.icon}</span>
              <span>${item.label}</span>
            </a>
          </li>
        `;
      }).join('');

      sidebarContainer.innerHTML = `
        <div class="cl-drawer-overlay" id="cl-drawer-backdrop" aria-hidden="true"></div>
        <aside class="cl-sidebar" id="cl-sidebar" role="navigation" aria-label="Main Navigation">
          <a href="${prefix}index.html" class="cl-sidebar-brand">
            <div class="cl-brand-logo">CL</div>
            <div>
              <h1 class="cl-brand-title">CivicLens</h1>
              <span class="cl-brand-sub">Infrastructure AI</span>
            </div>
          </a>
          <ul class="cl-nav-list">
            ${navLinksHtml}
          </ul>
          <div class="cl-nav-user-slot"></div>
          <div style="padding: 12px 16px; border-top: 1px solid var(--cl-border); font-size: 11px; color: var(--cl-text-muted);">
            <div>CivicLens v2.0</div>
            <div>BBMP & Smart Cities</div>
          </div>
        </aside>
      `;

      // Hamburger button wiring
      const hamburger = document.getElementById('cl-hamburger-toggle');
      const sidebar = document.getElementById('cl-sidebar');
      const backdrop = document.getElementById('cl-drawer-backdrop');

      function openDrawer() {
        if (sidebar && backdrop) {
          sidebar.classList.add('drawer-open');
          backdrop.classList.add('open');
          backdrop.setAttribute('aria-hidden', 'false');
          if (hamburger) hamburger.setAttribute('aria-expanded', 'true');
          document.body.style.overflow = 'hidden';
        }
      }

      function closeDrawer() {
        if (sidebar && backdrop) {
          sidebar.classList.remove('drawer-open');
          backdrop.classList.remove('open');
          backdrop.setAttribute('aria-hidden', 'true');
          if (hamburger) hamburger.setAttribute('aria-expanded', 'false');
          document.body.style.overflow = '';
        }
      }

      if (hamburger) {
        hamburger.addEventListener('click', function (e) {
          e.stopPropagation();
          if (sidebar && sidebar.classList.contains('drawer-open')) {
            closeDrawer();
          } else {
            openDrawer();
          }
        });
      }

      if (backdrop) {
        backdrop.addEventListener('click', closeDrawer);
      }

      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && sidebar && sidebar.classList.contains('drawer-open')) {
          closeDrawer();
        }
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initNavigation);
  } else {
    initNavigation();
  }
})();
