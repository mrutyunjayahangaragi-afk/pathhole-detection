/**
 * CivicLens Navigation Component (v2.0)
 * =====================================
 * Manages fixed desktop left sidebar and slide-in drawer on mobile.
 * Uses high-fidelity Icons8 vector assets for all navigation links.
 * Integrates application-wide multilingual language switcher (English / ಕನ್ನಡ).
 * Stationary top brand section, scrollable middle nav, stationary bottom controls.
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

    let userRole = 'public';
    try {
      const uStr = localStorage.getItem('civiclens_user');
      if (uStr) {
        const u = JSON.parse(uStr);
        userRole = u.role || 'citizen';
      }
    } catch (e) {}

    const isStaff = ['municipal_officer', 'dept_admin', 'municipal_admin', 'system_admin'].includes(userRole);
    const isCitizen = userRole === 'citizen';

    const allNavItems = [
      { key: 'home', i18nKey: 'nav.home', label: 'Home Portal', iconFile: 'home.svg', href: prefix + 'index.html', roles: ['all'] },
      { key: 'citizen_dashboard', i18nKey: 'nav.citizen_dashboard', label: 'Citizen Dashboard', iconFile: 'citizen-dashboard.svg', href: prefix + 'citizen-dashboard.html', roles: ['citizen'] },
      { key: 'report', i18nKey: 'nav.report', label: 'Report an Issue', iconFile: 'report-hazard.svg', href: prefix + 'citizen-report.html', roles: ['citizen', 'public'] },
      { key: 'my_reports', i18nKey: 'nav.my_reports', label: 'My Reports', iconFile: 'my-reports.svg', href: prefix + 'my-reports.html', roles: ['citizen'] },
      { key: 'map', i18nKey: 'nav.map', label: 'Public Map', iconFile: 'public-map.svg', href: prefix + 'public-map.html', roles: ['all'] },
      { key: 'transparency', i18nKey: 'nav.transparency', label: 'Civic Transparency', iconFile: 'transparency.svg', href: prefix + 'transparency.html', roles: ['all'] },
      { key: 'notifications', i18nKey: 'nav.notifications', label: 'Notifications', iconFile: 'notifications.svg', href: prefix + 'notifications.html', roles: ['citizen', 'staff'] },
      { key: 'municipal', i18nKey: 'nav.municipal', label: 'Municipal Triage', iconFile: 'municipal-triage.svg', href: prefix + 'municipal/dashboard.html', roles: ['staff'] },
      { key: 'verification', i18nKey: 'nav.verification', label: 'Verification Queue', iconFile: 'verification-queue.svg', href: prefix + 'municipal/verification.html', roles: ['staff'] },
      { key: 'departments', i18nKey: 'nav.departments', label: 'Departments & Officers', iconFile: 'departments.svg', href: prefix + 'municipal/departments.html', roles: ['staff'] },
      { key: 'dashboard', i18nKey: 'nav.dashboard', label: 'Live Monitor', iconFile: 'live-monitor.svg', href: '/dashboard/dashboard.html', roles: ['staff', 'public'] },
    ];

    const navItems = allNavItems.filter(it => {
      if (it.roles.includes('all')) return true;
      if (isStaff && it.roles.includes('staff')) return true;
      if (isCitizen && it.roles.includes('citizen')) return true;
      if (!isStaff && !isCitizen && it.roles.includes('public')) return true;
      return false;
    });

    // Build sidebar markup if container exists
    const sidebarContainer = document.getElementById('cl-sidebar-container');
    if (sidebarContainer) {
      const activeKey = sidebarContainer.dataset.active || '';

      const navLinksHtml = navItems.map(item => {
        const isActive = activeKey === item.key || currentPath.endsWith(item.href.replace('./', '').replace('../', ''));
        const labelText = (window.CivicLensI18n && window.CivicLensI18n.t(item.i18nKey)) || item.label;
        const iconPath = `${prefix}static/images/icons8/navigation/${item.iconFile}`;
        return `
          <li>
            <a href="${item.href}" class="cl-nav-link ${isActive ? 'active' : ''}" data-nav-key="${item.key}">
              <span class="cl-nav-icon">
                <img src="${iconPath}" alt="" width="20" height="20" aria-hidden="true">
              </span>
              <span data-i18n="${item.i18nKey}">${labelText}</span>
            </a>
          </li>
        `;
      }).join('');

      sidebarContainer.innerHTML = `
        <div class="cl-drawer-overlay" id="cl-drawer-backdrop" aria-hidden="true"></div>
        <aside class="cl-sidebar" id="cl-sidebar" role="navigation" aria-label="Main Navigation">
          <!-- 1. Stationary Brand Header -->
          <a href="${prefix}index.html" class="cl-sidebar-brand" aria-label="CivicLens Home">
            <div class="cl-brand-logo">CL</div>
            <div>
              <h1 class="cl-brand-title">CivicLens</h1>
              <span class="cl-brand-sub">BBMP AI Portal</span>
            </div>
          </a>

          <!-- 2. Middle Scrollable Navigation List -->
          <nav class="cl-sidebar-nav" aria-label="Primary Portal Navigation">
            <ul class="cl-nav-list">
              ${navLinksHtml}
            </ul>
          </nav>
          
          <!-- 3. Stationary Bottom Control Section -->
          <div class="cl-sidebar-footer">
            <!-- User Profile / Session Slot -->
            <div class="cl-nav-user-slot"></div>
            
            <!-- Multilingual Language Selector -->
            <div class="cl-lang-tray">
              <span style="font-size: 11px; color: var(--cl-text-muted); display: inline-flex; align-items: center; gap: 6px;" data-i18n="nav.language">
                <img src="${prefix}static/images/icons8/navigation/globe.svg" alt="" width="14" height="14" aria-hidden="true">
                <span>Language / ಭಾಷೆ</span>
              </span>
              <div style="display: flex; gap: 4px;">
                <button type="button" class="cl-lang-pill" data-lang="en" aria-label="English">EN</button>
                <button type="button" class="cl-lang-pill" data-lang="kn" aria-label="ಕನ್ನಡ">ಕನ್ನಡ</button>
              </div>
            </div>

            <!-- Version Information & Icons8 Mandatory Attribution -->
            <div class="cl-sidebar-version">
              <div style="font-weight: 600; color: var(--cl-text-primary);">CivicLens v2.0</div>
              <div style="color: var(--cl-text-muted);">BBMP &amp; Smart Cities</div>
              <div style="margin-top: 4px; font-size: 10px; color: var(--cl-text-muted);">
                Icons by <a href="https://icons8.com" target="_blank" rel="noopener">Icons8</a>
              </div>
            </div>
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

      // Mobile Drawer Wiring
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

      // Close drawer when a navigation link is clicked in mobile mode
      if (sidebar) {
        sidebar.querySelectorAll('.cl-nav-link').forEach(link => {
          link.addEventListener('click', function () {
            if (sidebar.classList.contains('drawer-open')) {
              closeDrawer();
            }
          });
        });
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
