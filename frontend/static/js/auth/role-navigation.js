/**
 * CivicLens Role-Based Navigation
 * ===============================
 * Redirects users to their permitted portal based on verified backend role.
 */

class RoleNavigation {
  getRedirectUrlForRole(role) {
    switch (role) {
      case 'system_admin':
      case 'municipal_admin':
      case 'dept_admin':
      case 'municipal_officer':
        return '/frontend/municipal/dashboard.html';
      case 'citizen':
      default:
        return '/frontend/citizen-dashboard.html';
    }
  }

  redirectToPortal(user) {
    if (!user || !user.role) {
      window.location.href = '/frontend/login.html';
      return;
    }
    const target = this.getRedirectUrlForRole(user.role);
    window.location.href = target;
  }
}

window.CivicLensRoleNav = new RoleNavigation();
