"""
Tests for Public Map Configuration Endpoint
===========================================
Verifies that /api/public/map-config delivers safe public map parameters
and never leaks private credentials or database connection strings.
"""


def test_map_config_endpoint_success(client):
    res = client.get("/api/public/map-config")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert "active_provider" in data
    assert "tile_urls" in data
    assert "styles" in data
    assert "attribution" in data


def test_map_config_never_leaks_secrets(client):
    res = client.get("/api/public/map-config")
    raw_text = res.get_data(as_text=True)

    # Ensure sensitive secrets are NEVER present
    assert "DATABASE_URL" not in raw_text
    assert "postgresql://" not in raw_text
    assert "SUPABASE_SERVICE_ROLE_KEY" not in raw_text
    assert "service_role" not in raw_text
    assert "SECRET_KEY" not in raw_text
    assert "password" not in raw_text.lower()


def test_map_config_osm_fallback_behavior(client):
    # When CARTO key is missing and OSM fallback is allowed
    client.application.config["CARTO_BASEMAP_API_KEY"] = ""
    client.application.config["CARTO_API_KEY"] = ""
    client.application.config["ALLOW_OSM_DEV_FALLBACK"] = True
    client.application.config["MAP_TILE_PROVIDER"] = "carto"

    res = client.get("/api/public/map-config")
    data = res.get_json()
    assert data["active_provider"] == "openstreetmap"
    assert data["fallback_active"] is True
    assert data["carto_key_configured"] is False
