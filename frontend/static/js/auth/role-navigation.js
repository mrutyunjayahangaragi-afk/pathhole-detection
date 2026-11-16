/**
 * CivicLens Role-Based Navigation & Safe Redirect Validator
 * =========================================================
 * Enforces role-based routing and strictly validates redirect destinations
 * against open-redirect and protocol-injection vulnerabilities.
 */

class RoleNavigation {
  constructor() {
    // Whitelist of permitted application routes
    this.ALLOWED_ROUTES = new Set([
      '/frontend/citizen-report.html',
      '/frontend/my-reports.html',
      '/frontend/report-detail.html',
      '/frontend/public-map.html',
      '/dashboard/dashboard.html',
      '/frontend/citizen-dashboard.html',
      '/frontend/municipal/dashboard.html',
      '/frontend/index.html',
      '/citizen-report.html',
      '/my-reports.html',
      '/public-map.html',
      '/citizen-dashboard.html',
    ]);
  }

  /**
   * Validates a redirect parameter against open-redirect vulnerabilities.
   * Returns the clean path if valid, or null if invalid or unsafe.
   */
  sanitizeRedirectPath(rawPath) {
    if (!rawPath || typeof rawPath !== 'string') {
      return null;
    }

    const decoded = decodeURIComponent(rawPath).trim();

    // Must be a relative path starting with a single '/'
    if (!decoded.startsWith('/') || decoded.startsWith('//') || decoded.startsWith('/\\')) {
      console.warn('[RoleNav] Rejected untrusted redirect scheme/format:', decoded);
      return null;
    }

    // Reject protocol injections (javascript:, data:, vbscript:)
    if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(decoded)) {
      console.warn('[RoleNav] Rejected protocol injection in redirect:', decoded);
      return null;
    }

    // Extract path without query parameters for whitelist matching
    const basePath = decoded.split('?')[0].split('#')[0];
    if (this.ALLOWED_ROUTES.has(basePath)) {
      return decoded;
    }

    console.warn('[RoleNav] Redirect path not in allowed route whitelist:', basePath);
    return null;
  }

  getRedirectUrlForRole(role, requestedRedirect = null) {
    const isOfficial = [
      'system_admin',
      'municipal_admin',
      'dept_admin',
      'municipal_officer',
    ].includes(role);

    // Officials always route to their municipal dashboard
    if (isOfficial) {
      return '/frontend/municipal/dashboard.html';
    }

    // Citizens: If a validated safe redirect target was requested, honor it
    const safeRedirect = this.sanitizeRedirectPath(requestedRedirect);
    if (safeRedirect) {
      return safeRedirect;
    }

    // Default citizen landing portal
    return '/frontend/citizen-dashboard.html';
  }

  redirectToPortal(user, requestedRedirect = null) {
    if (!user || !user.role) {
      window.location.href = '/frontend/citizen-login.html';
      return;
    }
    const target = this.getRedirectUrlForRole(user.role, requestedRedirect);
    window.location.href = target;
  }
}

window.CivicLensRoleNav = new RoleNavigation();
