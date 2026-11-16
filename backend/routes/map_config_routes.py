"""
Public Map Configuration Routes
===============================
Provides safe, public configuration for frontend map components (Leaflet, CARTO, OSM).
Guarantees zero exposure of private database secrets, passwords, or service-role keys.
"""

from flask import Blueprint, jsonify, current_app
from backend.config import get_config

map_config_bp = Blueprint("map_config_bp", __name__, url_prefix="/api/public")


@map_config_bp.route("/map-config", methods=["GET"])
def get_map_config():
    """
    Returns public mapping configuration for Leaflet / CARTO / OSM providers.
    """
    try:
        has_carto_key = bool(current_app.config.get("CARTO_BASEMAP_API_KEY") or current_app.config.get("CARTO_API_KEY"))
        allow_osm = bool(current_app.config.get("ALLOW_OSM_DEV_FALLBACK", True))
        configured_provider = str(current_app.config.get("MAP_TILE_PROVIDER", "carto")).strip().lower()
        carto_key = current_app.config.get("CARTO_BASEMAP_API_KEY") or current_app.config.get("CARTO_API_KEY", "")
    except RuntimeError:
        cfg = get_config()
        has_carto_key = bool(cfg.CARTO_BASEMAP_API_KEY)
        allow_osm = cfg.ALLOW_OSM_DEV_FALLBACK
        configured_provider = cfg.MAP_TILE_PROVIDER
        carto_key = cfg.CARTO_BASEMAP_API_KEY

    # Determine active tile provider:
    # If CARTO is selected but no key is present, fallback to OpenStreetMap in dev
    if configured_provider == "carto" and not has_carto_key:
        active_provider = "openstreetmap" if allow_osm else "carto"
        fallback_active = allow_osm
    else:
        active_provider = configured_provider
        fallback_active = False

    # Tile URL templates
    # Voyager / Positron for public map, Dark Matter for live sensor monitor
    carto_key_query = f"?key={carto_key}" if has_carto_key and carto_key else ""
    tile_urls = {
        "carto_voyager": f"https://basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}.png{carto_key_query}",
        "carto_positron": f"https://basemaps.cartocdn.com/rastertiles/light_all/{{z}}/{{x}}/{{y}}.png{carto_key_query}",
        "carto_dark_matter": f"https://basemaps.cartocdn.com/rastertiles/dark_all/{{z}}/{{x}}/{{y}}.png{carto_key_query}",
        "openstreetmap": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    }

    return jsonify({
        "status": "success",
        "configured_provider": configured_provider,
        "active_provider": active_provider,
        "carto_key_configured": has_carto_key,
        "osm_fallback_allowed": allow_osm,
        "fallback_active": fallback_active,
        "tile_urls": tile_urls,
        "styles": {
            "public_map": "voyager" if has_carto_key else "osm",
            "monitor": "dark_matter" if has_carto_key else "osm",
        },
        "attribution": {
            "carto": "&copy; <a href=\"https://www.openstreetmap.org/copyright\" target=\"_blank\">OpenStreetMap</a> contributors, &copy; <a href=\"https://carto.com/attributions\" target=\"_blank\">CARTO</a>",
            "openstreetmap": "&copy; <a href=\"https://www.openstreetmap.org/copyright\" target=\"_blank\">OpenStreetMap</a> contributors"
        }
    }), 200
