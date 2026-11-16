/**
 * CivicLens Supabase Auth Client
 * ==============================
 * Initializes Supabase JS client and coordinates OAuth with PKCE flow.
 */

class CivicLensSupabaseClient {
  constructor() {
    this.client = null;
    this.initPromise = null;
  }

  async getClient() {
    if (this.client) return this.client;
    if (this.initPromise) return this.initPromise;

    this.initPromise = (async () => {
      // In browser, ensure supabase-js is available
      if (typeof window.supabase !== 'undefined' && window.supabase.createClient) {
        // Fetch public keys from backend or environment injection
        let supabaseUrl = window.ENV_SUPABASE_URL || '';
        let supabaseAnonKey = window.ENV_SUPABASE_ANON_KEY || '';

        if (!supabaseUrl || !supabaseAnonKey) {
          try {
            const res = await fetch('/api/public/map-config');
            // Safe config endpoint
          } catch (e) {
            // ignore
          }
        }

        if (supabaseUrl && supabaseAnonKey) {
          this.client = window.supabase.createClient(supabaseUrl, supabaseAnonKey, {
            auth: {
              flowType: 'pkce',
              autoRefreshToken: true,
              persistSession: true,
              detectSessionInUrl: true,
            }
          });
        }
      }
      return this.client;
    })();

    return this.initPromise;
  }

  /**
   * Initiates Google OAuth with PKCE.
   * @param {string} targetPortal - 'citizen' or 'municipal'
   */
  async signInWithGoogle(targetPortal = 'citizen') {
    const client = await this.getClient();
    const redirectUrl = `${window.location.origin}/frontend/auth-callback.html?portal=${encodeURIComponent(targetPortal)}`;

    if (!client) {
      console.warn('[SupabaseAuth] Supabase client not initialized or credentials missing. Using local gateway.');
      // If Supabase credentials are not yet configured by user, notify cleanly
      alert('Google OAuth requires Supabase credentials to be configured in .env. Please configure SUPABASE_URL and SUPABASE_ANON_KEY.');
      return;
    }

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
  }
}

window.CivicLensSupabase = new CivicLensSupabaseClient();
