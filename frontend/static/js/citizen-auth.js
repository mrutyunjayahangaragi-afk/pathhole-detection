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
    return localStorage.getItem(TOKEN_KEY) || "";
  }

  function setSession(token, user) {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
    updateNavUserPill();
  }

  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    updateNavUserPill();
  }

  function getUser() {
    try {
      const data = localStorage.getItem(USER_KEY);
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
    const base = isFrontendPrefix ? "/frontend/citizen-login.html" : "/citizen-login.html";
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

    userContainers.forEach((slot) => {
      if (user) {
        slot.innerHTML = `
          <div style="padding: 12px 14px; border-top: 1px solid var(--cl-border); display: flex; align-items: center; justify-content: space-between;">
            <div style="overflow: hidden;">
              <div style="font-weight: 600; font-size: 13px; color: var(--cl-text-primary); text-overflow: ellipsis; white-space: nowrap; overflow: hidden;">
                ${user.display_name}
              </div>
              <div style="font-size: 11px; color: var(--cl-text-muted); text-transform: capitalize;">
                ${user.role.replace("_", " ")}
              </div>
            </div>
            <button onclick="CivicAuth.logout()" class="cl-btn cl-btn-secondary cl-btn-sm" style="padding: 2px 8px; font-size: 11px;" title="Log out">
              Exit
            </button>
          </div>
        `;
      } else {
        const loginUrl = getLoginUrl();
        slot.innerHTML = `
          <div style="padding: 12px 14px; border-top: 1px solid var(--cl-border);">
            <a href="${loginUrl}" class="cl-btn cl-btn-primary cl-btn-sm" style="width: 100%;">
              Sign In / Register
            </a>
          </div>
        `;
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    updateNavUserPill();
  });

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
