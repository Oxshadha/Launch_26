import json
import os
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class UniverseMetadata:
    system_name: str
    speed_of_light_kms: float
    max_void_hop_distance_km: float
    coordinate_scale_unit_km: float
    tower_processing_delay_ms: float
    fiber_speed_fraction: float

@dataclass
class Planet:
    id: str
    codex: int
    x: float
    y: float
    radius_km: float
    active_towers: int
    atmosphere_thickness_km: float
    refraction_index: float
    is_active: bool = True  # Used later for chaos testing

def load_universe_config(file_path: str) -> tuple[UniverseMetadata, List[Planet]]:
    """
    Parses the universe-config.json file, applies default physical constants
    if missing, and returns the Metadata and a list of Planet objects.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Configuration file not found: {file_path}")

    with open(file_path, 'r') as f:
        data = json.load(f)

    raw_meta = data.get("universe_metadata", {})
    
    # Extract metadata with spec-defined defaults
    meta = UniverseMetadata(
        system_name=raw_meta.get("system_name", "Unknown System"),
        speed_of_light_kms=float(raw_meta.get("speed_of_light_kms", 300000.0)),
        max_void_hop_distance_km=float(raw_meta.get("max_void_hop_distance_km", 50000000.0)),
        coordinate_scale_unit_km=float(raw_meta.get("coordinate_scale_unit_km", 100000.0)),
        tower_processing_delay_ms=float(raw_meta.get("tower_processing_delay_ms", 7.0)),
        fiber_speed_fraction=float(raw_meta.get("fiber_speed_fraction", 0.67))
    )

    planets = []
    for raw_node in data.get("nodes", []):
        planet = Planet(
            id=raw_node["id"],
            codex=int(raw_node["codex"]),
            x=float(raw_node["x"]),
            y=float(raw_node["y"]),
            radius_km=float(raw_node["radius_km"]),
            active_towers=int(raw_node["active_towers"]),
            atmosphere_thickness_km=float(raw_node["atmosphere_thickness_km"]),
            refraction_index=float(raw_node["refraction_index"])
        )
        planets.append(planet)

    return meta, planets

if __name__ == "__main__":
    # Simple test when run directly
    try:
        m, p = load_universe_config("../universe-config.json")
        print(f"Loaded {m.system_name} with {len(p)} planets.")
        print(f"Speed of light: {m.speed_of_light_kms} km/s")
    except Exception as e:
        print(f"Error: {e}")
