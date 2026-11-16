/**
 * CivicLens Navigation Component
 * ==============================
 * Manages responsive sidebar on desktop and slide-in drawer on mobile.
 * Integrates application-wide multilingual language switcher (English / ಕನ್ನಡ).
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
      { key: 'home', i18nKey: 'nav.home', label: 'Home Portal', icon: '🏛️', href: prefix + 'index.html' },
      { key: 'citizen_dashboard', i18nKey: 'nav.citizen_dashboard', label: 'Citizen Dashboard', icon: '👤', href: prefix + 'citizen-dashboard.html' },
      { key: 'report', i18nKey: 'nav.report', label: 'Report Defect', icon: '📢', href: prefix + 'citizen-report.html' },
      { key: 'my_reports', i18nKey: 'nav.my_reports', label: 'My Submissions', icon: '📋', href: prefix + 'my-reports.html' },
      { key: 'map', i18nKey: 'nav.map', label: 'Public Map', icon: '🗺️', href: prefix + 'public-map.html' },
      { key: 'transparency', i18nKey: 'nav.transparency', label: 'Civic Transparency', icon: '📊', href: prefix + 'transparency.html' },
      { key: 'notifications', i18nKey: 'nav.notifications', label: 'Notifications', icon: '🔔', href: prefix + 'notifications.html' },
      { key: 'dashboard', i18nKey: 'nav.dashboard', label: 'Live Monitor', icon: '⚡', href: prefix + 'dashboard/dashboard.html' },
      { key: 'municipal', i18nKey: 'nav.municipal', label: 'Municipal Triage', icon: '🛠️', href: prefix + 'municipal/dashboard.html' },
      { key: 'verification', i18nKey: 'nav.verification', label: 'Verification Queue', icon: '🔍', href: prefix + 'municipal/verification.html' },
      { key: 'departments', i18nKey: 'nav.departments', label: 'Departments & Officers', icon: '🏢', href: prefix + 'municipal/departments.html' },
    ];

    // Build sidebar markup if container exists
    const sidebarContainer = document.getElementById('cl-sidebar-container');
    if (sidebarContainer) {
      const activeKey = sidebarContainer.dataset.active || '';

      const navLinksHtml = navItems.map(item => {
        const isActive = activeKey === item.key || currentPath.endsWith(item.href.replace('./', '').replace('../', ''));
        const labelText = (window.CivicLensI18n && window.CivicLensI18n.t(item.i18nKey)) || item.label;
        return `
          <li>
            <a href="${item.href}" class="cl-nav-link ${isActive ? 'active' : ''}" data-nav-key="${item.key}">
              <span class="cl-nav-icon">${item.icon}</span>
              <span data-i18n="${item.i18nKey}">${labelText}</span>
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
          
          <!-- Multilingual Language Selector -->
          <div class="cl-lang-tray" style="padding: 10px 16px; border-top: 1px solid var(--cl-border); display: flex; align-items: center; justify-content: space-between;">
            <span style="font-size: 11px; color: var(--cl-text-muted);" data-i18n="nav.language">🌐 Language / ಭಾಷೆ</span>
            <div style="display: flex; gap: 4px;">
              <button type="button" class="cl-lang-pill" data-lang="en" aria-label="English">EN</button>
              <button type="button" class="cl-lang-pill" data-lang="kn" aria-label="ಕನ್ನಡ">ಕನ್ನಡ</button>
            </div>
          </div>

          <div style="padding: 10px 16px; border-top: 1px solid var(--cl-border); font-size: 11px; color: var(--cl-text-muted);">
            <div>CivicLens v2.0</div>
            <div>BBMP & Smart Cities</div>
          </div>
        </aside>
      `;

      // Wire language pills
      function refreshPillStates() {
        const current = (window.CivicLensI18n && window.CivicLensI18n.getLanguage()) || 'en';
        document.querySelectorAll('.cl-lang-pill').forEach(pill => {
          const l = pill.getAttribute('data-lang');
          if (l === current) {
            pill.style.background = 'var(--cl-primary)';
            pill.style.color = '#ffffff';
            pill.style.fontWeight = 'bold';
            pill.style.borderColor = 'var(--cl-primary)';
          } else {
            pill.style.background = 'transparent';
            pill.style.color = 'var(--cl-text-secondary)';
            pill.style.fontWeight = 'normal';
            pill.style.borderColor = 'var(--cl-border)';
          }
        });
      }

      document.querySelectorAll('.cl-lang-pill').forEach(pill => {
        pill.style.border = '1px solid var(--cl-border)';
        pill.style.borderRadius = '4px';
        pill.style.padding = '4px 8px';
        pill.style.fontSize = '11px';
        pill.style.cursor = 'pointer';
        pill.style.transition = 'all 0.15s ease';

        pill.addEventListener('click', function () {
          const targetLang = this.getAttribute('data-lang');
          if (window.CivicLensI18n) {
            window.CivicLensI18n.setLanguage(targetLang);
            refreshPillStates();
          }
        });
      });

      refreshPillStates();
      window.addEventListener('civiclens-language-changed', refreshPillStates);

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
