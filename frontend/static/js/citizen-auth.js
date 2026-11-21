/**
 * CivicLens Citizen Client-Side Authentication Manager
 * ====================================================
 * Manages JWT Bearer tokens, active session state, user pills in nav,
 * and authenticated API fetch wrappers.
 */

const CivicAuth = (function () {
  const TOKEN_KEY = "civiclens_auth_token";
  const USER_KEY = "civiclens_user_data";

  function getToken() {
    return localStorage.getItem(TOKEN_KEY) || localStorage.getItem("civiclens_token") || "";
  }

  function setSession(token, user) {
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
      localStorage.setItem("civiclens_token", token);
    }
    if (user) {
      localStorage.setItem(USER_KEY, JSON.stringify(user));
      localStorage.setItem("civiclens_user", JSON.stringify(user));
    }
    updateNavUserPill();
  }

  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem("civiclens_token");
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem("civiclens_user");
    updateNavUserPill();
  }

  function getUser() {
    try {
      const data = localStorage.getItem(USER_KEY) || localStorage.getItem("civiclens_user");
      return data ? JSON.parse(data) : null;
    } catch (e) {
      return null;
    }
  }

  function isAuthenticated() {
    return !!getToken() && !!getUser();
  }

  function getLoginUrl(redirectPath) {
    const isFrontendPrefix = window.location.pathname.startsWith("/frontend/");
    const base = isFrontendPrefix ? "/frontend/login.html" : "/login.html";
    if (redirectPath) {
      return `${base}?redirect=${encodeURIComponent(redirectPath)}`;
    }
    return base;
  }

  function getHomeUrl() {
    return window.location.pathname.startsWith("/frontend/") ? "/frontend/index.html" : "/";
  }

  async function apiFetch(url, options = {}) {
    options.headers = options.headers || {};
    const token = getToken();
    if (token) {
      if (options.headers instanceof Headers) {
        options.headers.set("Authorization", `Bearer ${token}`);
      } else {
        options.headers["Authorization"] = `Bearer ${token}`;
      }
    }
    const res = await fetch(url, options);
    if (res.status === 401) {
      clearSession();
      if (!window.location.pathname.includes("citizen-login")) {
        window.location.href = getLoginUrl(window.location.pathname + window.location.search);
      }
    }
    return res;
  }

  async function logout() {
    try {
      await apiFetch("/api/v1/auth/logout", { method: "POST" });
    } catch (e) {
      /* ignore offline */
    }
    clearSession();
    window.location.href = getHomeUrl();
  }

  function updateNavUserPill() {
    const user = getUser();
    const userContainers = document.querySelectorAll(".cl-nav-user-slot");
    const headerAuthContainer = document.getElementById("header-auth-container");
    const prefix = window.location.pathname.includes('/municipal/') || window.location.pathname.includes('/dashboard/') ? '../' : './';

    // 1. Update Top Header Bar if present
    if (headerAuthContainer) {
      if (user) {
        const initial = (user.display_name || user.email || 'U').charAt(0).toUpperCase();
        const roleName = (user.role || 'citizen').replace("_", " ");
        const isStaff = ['municipal_officer', 'dept_admin', 'municipal_admin', 'system_admin'].includes(user.role);
        const dashUrl = isStaff ? `${prefix}municipal/dashboard.html` : `${prefix}citizen-dashboard.html`;
        headerAuthContainer.innerHTML = `
          <div style="display: flex; align-items: center; gap: 8px;">
            <a href="${dashUrl}" class="cl-header-user-badge" title="Go to Dashboard (${roleName})">
              <span class="cl-header-avatar">${initial}</span>
              <span class="cl-header-username">${user.display_name || user.email}</span>
            </a>
            <button onclick="CivicAuth.logout()" class="cl-btn-header-logout" title="Log out of CivicLens">
              <span>Exit</span>
            </button>
          </div>
        `;
      } else {
        headerAuthContainer.innerHTML = `
          <a href="${prefix}citizen-login.html" class="cl-btn-header-login">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"></path><polyline points="10 17 15 12 10 7"></polyline><line x1="15" y1="12" x2="3" y2="12"></line></svg>
            <span>Log In</span>
          </a>
          <a href="${prefix}citizen-login.html?tab=register" class="cl-btn-header-register">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="8.5" cy="7" r="4"></circle><line x1="20" y1="8" x2="20" y2="14"></line><line x1="23" y1="11" x2="17" y2="11"></line></svg>
            <span>Sign Up</span>
          </a>
        `;
      }
    }

    // 2. Update Sidebar User Slots
    userContainers.forEach((slot) => {
      if (user) {
        const initial = (user.display_name || user.email || 'U').charAt(0).toUpperCase();
        slot.innerHTML = `
          <div style="padding: 10px 14px; display: flex; align-items: center; justify-content: space-between; gap: 8px;">
            <div style="display: flex; align-items: center; gap: 8px; min-width: 0; overflow: hidden;">
              <div style="width: 28px; height: 28px; border-radius: 50%; background: var(--cl-primary); color: white; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 12px; flex-shrink: 0;">
                ${initial}
              </div>
              <div style="min-width: 0; overflow: hidden;">
                <div style="font-weight: 600; font-size: 12px; color: var(--cl-text-primary); text-overflow: ellipsis; white-space: nowrap; overflow: hidden;">
                  ${user.display_name || user.email}
                </div>
                <div style="font-size: 10px; color: var(--cl-text-muted); text-transform: capitalize;">
                  ${(user.role || 'citizen').replace("_", " ")}
                </div>
              </div>
            </div>
            <button onclick="CivicAuth.logout()" class="cl-btn cl-btn-secondary cl-btn-sm" style="padding: 3px 8px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px; flex-shrink: 0;" title="Log out">
              <img src="${prefix}static/images/icons8/navigation/logout.svg" alt="" width="12" height="12" aria-hidden="true">
              <span>Exit</span>
            </button>
          </div>
        `;
      } else {
        slot.innerHTML = `
          <div style="padding: 10px 12px; display: flex; gap: 8px;">
            <a href="${prefix}citizen-login.html" class="cl-btn cl-btn-secondary cl-btn-sm" style="flex: 1; text-align: center; justify-content: center; font-size: 12px; padding: 6px 8px; border-color: var(--cl-border); color: var(--cl-text-primary);">
              Log In
            </a>
            <a href="${prefix}citizen-login.html?tab=register" class="cl-btn cl-btn-primary cl-btn-sm" style="flex: 1; text-align: center; justify-content: center; font-size: 12px; padding: 6px 8px;">
              Sign Up
            </a>
          </div>
        `;
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener("DOMContentLoaded", updateNavUserPill);
  } else {
    updateNavUserPill();
  }

  return {
    getToken,
    getUser,
    setSession,
    clearSession,
    isAuthenticated,
    apiFetch,
    logout,
    updateNavUserPill,
  };
})();
