/**
 * CivicLens Auth Callback Handler
 * ===============================
 * Completes OAuth PKCE exchange, validates session with Flask backend,
 * and routes to the permitted dashboard.
 */

document.addEventListener('DOMContentLoaded', async () => {
  const statusTitle = document.getElementById('callback-title');
  const statusMessage = document.getElementById('callback-message');
  const errorContainer = document.getElementById('callback-error-container');
  const retryBtn = document.getElementById('callback-retry-btn');
  const spinner = document.getElementById('callback-spinner');

  const urlParams = new URLSearchParams(window.location.search);
  const targetPortal = urlParams.get('portal') || 'citizen';
  const errorCode = urlParams.get('error');
  const errorDescription = urlParams.get('error_description');

  if (errorCode) {
    showError(errorDescription || 'Authentication was cancelled or failed by the provider.');
    return;
  }

  try {
    let accessToken = null;

    // 1. Try extracting token from Supabase client session
    const supaClient = await window.CivicLensSupabase.getClient();
    if (supaClient) {
      const { data, error } = await supaClient.auth.getSession();
      if (error) throw error;
      if (data && data.session) {
        accessToken = data.session.access_token;
      }
    }

    // 2. Check URL hash parameters fallback (#access_token=...)
    if (!accessToken && window.location.hash) {
      const hashParams = new URLSearchParams(window.location.hash.substring(1));
      accessToken = hashParams.get('access_token');
    }

    // 3. Check query param fallback
    if (!accessToken) {
      accessToken = urlParams.get('access_token');
    }

    if (!accessToken) {
      throw new Error('No authentication credentials were received from the identity provider.');
    }

    statusTitle.textContent = 'Verifying with CivicLens...';
    statusMessage.textContent = 'Synchronizing profile and checking municipal permissions...';

    // 4. Send token to Flask backend for signature validation and role mapping
    const res = await fetch('/api/v1/auth/supabase-verify', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${accessToken}`,
      },
      body: JSON.stringify({
        access_token: accessToken,
        target_portal: targetPortal,
      }),
    });

    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.error || 'Backend session verification failed.');
    }

    // 5. Store verified user session
    window.CivicLensSession.setSession(data.token, data.user);

    const requestedRedirect = urlParams.get('redirect');

    statusTitle.textContent = 'Welcome, ' + (data.user.display_name || 'User') + '!';
    statusMessage.textContent = 'Redirecting to your destination...';

    setTimeout(() => {
      window.CivicLensRoleNav.redirectToPortal(data.user, requestedRedirect);
    }, 800);

  } catch (err) {
    console.error('[AuthCallback] Error:', err);
    showError(err.message || 'An error occurred during authentication.');
  }

  function showError(msg) {
    if (spinner) spinner.style.display = 'none';
    if (statusTitle) statusTitle.textContent = 'Authentication Failed';
    if (statusMessage) statusMessage.textContent = msg;
    if (errorContainer) errorContainer.style.display = 'block';
  }
});
