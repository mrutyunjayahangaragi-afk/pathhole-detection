/**
 * CivicLens Session Manager
 * =========================
 * Client-side session and auth state synchronization.
 */

class SessionManager {
  constructor() {
    this.TOKEN_KEY = 'civiclens_auth_token';
    this.USER_KEY = 'civiclens_user_data';
  }

  setSession(token, user) {
    if (token) {
      localStorage.setItem(this.TOKEN_KEY, token);
    }
    if (user) {
      localStorage.setItem(this.USER_KEY, JSON.stringify(user));
    }
    // Also trigger storage event for cross-tab sync
    window.dispatchEvent(new Event('civiclens:auth_changed'));
  }

  getToken() {
    return localStorage.getItem(this.TOKEN_KEY) || null;
  }

  getUser() {
    try {
      const raw = localStorage.getItem(this.USER_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  isAuthenticated() {
    return Boolean(this.getToken() && this.getUser());
  }

  clearSession() {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.USER_KEY);
    // Also inform backend of logout
    fetch('/api/v1/auth/logout', { method: 'POST' }).catch(() => {});
    window.dispatchEvent(new Event('civiclens:auth_changed'));
  }
}

window.CivicLensSession = new SessionManager();
