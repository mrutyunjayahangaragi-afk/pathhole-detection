/**
 * CivicLens Centralized Map Provider
 * ==================================
 * Shared map tile provider for Public Incident Map and Live Sensor Monitor.
 * Enforces key-authenticated CARTO basemaps with automatic OpenStreetMap
 * development fallback, eliminating "API KEY REQUIRED" watermarks.
 */

class CivicLensMapProvider {
  constructor() {
    this.currentTileLayer = null;
    this.activeProviderName = 'Detecting...';
  }

  /**
   * Builds and attaches the optimal basemap tile layer to a Leaflet map.
   * @param {L.Map} map - Leaflet map instance
   * @param {Object} options - { purpose: 'public_map' | 'monitor', style: 'voyager' | 'dark_matter' | 'positron' | 'auto' }
   */
  async attachBasemap(map, options = {}) {
    const purpose = options.purpose || 'public_map';
    const config = await window.CivicLensMapConfig.getConfig();

    let tileUrl = '';
    let attribution = '';
    let providerLabel = '';

    // If CARTO has an authenticated key, use requested style
    if (config.carto_key_configured && config.active_provider === 'carto') {
      if (purpose === 'monitor' || options.style === 'dark_matter') {
        tileUrl = config.tile_urls.carto_dark_matter;
        providerLabel = 'CARTO Dark Matter';
      } else if (options.style === 'positron') {
        tileUrl = config.tile_urls.carto_positron;
        providerLabel = 'CARTO Positron';
      } else {
        tileUrl = config.tile_urls.carto_voyager;
        providerLabel = 'CARTO Voyager';
      }
      attribution = config.attribution.carto;
    } else {
      // In local dev without CARTO key, use OpenStreetMap to prevent "API KEY REQUIRED" watermarks
      tileUrl = config.tile_urls.openstreetmap;
      attribution = config.attribution.openstreetmap;
      providerLabel = config.fallback_active ? 'OpenStreetMap (Dev Fallback)' : 'OpenStreetMap';
      console.info(`[MapProvider] CARTO API key not supplied. Using ${providerLabel}.`);
    }

    this.activeProviderName = providerLabel;

    // Remove existing tile layer if replacing
    if (this.currentTileLayer && map.hasLayer(this.currentTileLayer)) {
      map.removeLayer(this.currentTileLayer);
    }

    const tileLayer = L.tileLayer(tileUrl, {
      attribution: attribution,
      maxZoom: 19,
      subdomains: 'abcd',
      crossOrigin: true,
    });

    // Tile error fallback handling: if CARTO tile fails, fall back to OpenStreetMap
    tileLayer.on('tileerror', (error) => {
      if (!tileUrl.includes('openstreetmap.org')) {
        console.warn('[MapProvider] CARTO tile error detected. Falling back to OpenStreetMap.', error);
        map.removeLayer(tileLayer);
        const osmFallback = L.tileLayer(config.tile_urls.openstreetmap, {
          attribution: config.attribution.openstreetmap,
          maxZoom: 19,
        });
        osmFallback.addTo(map);
        this.currentTileLayer = osmFallback;
        this.activeProviderName = 'OpenStreetMap (Recovery Fallback)';
        this._updateBadge(map, this.activeProviderName);
      }
    });

    tileLayer.addTo(map);
    this.currentTileLayer = tileLayer;

    this._updateBadge(map, providerLabel);
    return tileLayer;
  }

  _updateBadge(map, label) {
    const badgeEl = document.getElementById('map-provider-badge');
    if (badgeEl) {
      badgeEl.textContent = label;
      badgeEl.className = 'provider-badge ' + (label.includes('CARTO') ? 'provider-carto' : 'provider-osm');
    }
  }

  getActiveProviderLabel() {
    return this.activeProviderName;
  }
}

window.CivicLensMapProvider = new CivicLensMapProvider();
