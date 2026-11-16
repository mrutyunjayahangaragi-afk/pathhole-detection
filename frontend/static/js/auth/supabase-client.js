/**
 * CivicLens Supabase Auth Client
 * ==============================
 * Centralized, singleton client management for Supabase Auth and Google OAuth (PKCE).
 * Dynamically loads safe public configuration from /api/public/config.
 */

class CivicLensSupabaseClient {
  constructor() {
    this.client = null;
    this.config = null;
    this.initPromise = null;
  }

  /**
   * Fetches public configuration from backend and initializes the Supabase JS client.
   * Prevents race conditions by caching the in-flight initialization promise.
   */
  async getClient() {
    if (this.client) return this.client;
    if (this.initPromise) return this.initPromise;

    this.initPromise = (async () => {
      try {
        // 1. Fetch public configuration from backend
        const res = await fetch('/api/public/config');
        if (!res.ok) {
          throw new Error(`Public config endpoint returned HTTP ${res.status}`);
        }
        const configData = await res.json();
        this.config = configData;

        // 2. Validate configuration readiness
        if (!configData.supabase_ready || !configData.supabase_url || !configData.supabase_publishable_key) {
          console.warn('[SupabaseAuth] Supabase credentials not ready on server:', configData.diagnostic_code);
          return null;
        }

        // 3. Ensure official Supabase JS SDK is available in the window
        if (typeof window.supabase === 'undefined' || !window.supabase.createClient) {
          console.error('[SupabaseAuth] @supabase/supabase-js SDK script is not loaded in window.');
          return null;
        }

        // 4. Initialize client with PKCE authorization-code flow
        this.client = window.supabase.createClient(
          configData.supabase_url,
          configData.supabase_publishable_key,
          {
            auth: {
              flowType: 'pkce',
              autoRefreshToken: true,
              persistSession: true,
              detectSessionInUrl: true,
            }
          }
        );

        console.info('[SupabaseAuth] Supabase client initialized successfully with PKCE flow.');
        return this.client;
      } catch (err) {
        console.error('[SupabaseAuth] Initialization failure:', err);
        return null;
      } finally {
        this.initPromise = null;
      }
    })();

    return this.initPromise;
  }

  /**
   * Initiates Google OAuth with PKCE, preserving the user's intended redirect path.
   * @param {string} targetPortal - 'citizen' or 'municipal'
   * @param {string|null} redirectPath - e.g. '/frontend/citizen-report.html'
   */
  async signInWithGoogle(targetPortal = 'citizen', redirectPath = null) {
    const client = await this.getClient();

    // Extract intended redirect destination from URL query or argument
    const currentParams = new URLSearchParams(window.location.search);
    const intendedRedirect = redirectPath || currentParams.get('redirect') || '';

    let callbackQuery = `portal=${encodeURIComponent(targetPortal)}`;
    if (intendedRedirect) {
      callbackQuery += `&redirect=${encodeURIComponent(intendedRedirect)}`;
    }

    const redirectUrl = `${window.location.origin}/frontend/auth-callback.html?${callbackQuery}`;

    if (!client) {
      console.warn('[SupabaseAuth] Supabase client is not configured.');
      this.displayInlineWarning(
        'Login services are not configured. Please complete the Supabase setup in .env (SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY).'
      );
      return;
    }

    try {
      this.setGoogleButtonLoading(true);

      const { data, error } = await client.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: redirectUrl,
          queryParams: {
            access_type: 'offline',
            prompt: 'consent',
          }
        }
      });

      if (error) {
        throw error;
      }
      return data;
    } catch (err) {
      this.setGoogleButtonLoading(false);
      console.error('[SupabaseAuth] Google OAuth initiation failed:', err);
      this.displayInlineWarning(`OAuth Error: ${err.message || 'Unable to start Google sign in.'}`);
    }
  }

  /**
   * Displays an accessible, non-intrusive inline notification instead of native alert().
   */
  displayInlineWarning(message) {
    const alertBox = document.getElementById('auth-alert') || document.getElementById('official-alert');
    if (alertBox) {
      alertBox.textContent = message;
      alertBox.style.display = 'block';
      alertBox.className = 'auth-alert auth-alert-error';
      alertBox.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } else {
      console.warn('[SupabaseAuth Alert]:', message);
    }
  }

  setGoogleButtonLoading(isLoading) {
    const btn = document.getElementById('btn-google-login');
    if (!btn) return;
    if (isLoading) {
      btn.dataset.originalHtml = btn.innerHTML;
      btn.innerHTML = `
        <span class="cl-spinner" style="display:inline-block; width:16px; height:16px; border:2px solid #ccc; border-top-color:#3b82f6; border-radius:50%; animation:spin 1s linear infinite;"></span>
        <span>Connecting to Google...</span>
      `;
      btn.disabled = true;
    } else {
      if (btn.dataset.originalHtml) {
        btn.innerHTML = btn.dataset.originalHtml;
      }
      btn.disabled = false;
    }
  }
}

window.CivicLensSupabase = new CivicLensSupabaseClient();
