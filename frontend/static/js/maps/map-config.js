/**
 * CivicLens Map Configuration Service
 * ===================================
 * Fetches safe public map configuration from the backend.
 * Caches config in memory to avoid redundant network round-trips.
 */

class MapConfigService {
  constructor() {
    this._cachedConfig = null;
    this._fetchPromise = null;
  }

  async getConfig() {
    if (this._cachedConfig) {
      return this._cachedConfig;
    }

    if (this._fetchPromise) {
      return this._fetchPromise;
    }

    this._fetchPromise = fetch('/api/public/map-config')
      .then(async (res) => {
        if (!res.ok) {
          throw new Error(`Failed to load map configuration: HTTP ${res.status}`);
        }
        const data = await res.json();
        this._cachedConfig = data;
        return data;
      })
      .catch((err) => {
        console.warn('[MapConfig] Failed to fetch server map config, falling back to local defaults:', err);
        // Safe local fallback (OSM)
        this._cachedConfig = {
          status: 'fallback',
          configured_provider: 'carto',
          active_provider: 'openstreetmap',
          carto_key_configured: false,
          fallback_active: true,
          tile_urls: {
            openstreetmap: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
            carto_voyager: 'https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png',
            carto_dark_matter: 'https://basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}.png'
          },
          styles: { public_map: 'osm', monitor: 'osm' },
          attribution: {
            openstreetmap: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a> contributors',
            carto: '&copy; OpenStreetMap contributors, &copy; CARTO'
          }
        };
        return this._cachedConfig;
      })
      .finally(() => {
        this._fetchPromise = null;
      });

    return this._fetchPromise;
  }
}

window.CivicLensMapConfig = new MapConfigService();
