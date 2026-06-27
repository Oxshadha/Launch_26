import sys
import os
import math
import pytest

# Add src to the path so we can import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from config_parser import Planet, load_universe_config
from physics_engine import (
    void_distance,
    void_travel_time,
    tower_positions,
    find_closest_tower_pair,
    crust_transit_time
)

@pytest.fixture
def sample_planets():
    aegis = Planet(
        id="Aegis", codex=8, x=0, y=0, radius_km=6371, 
        active_towers=8, atmosphere_thickness_km=120, refraction_index=1.0003
    )
    boreas = Planet(
        id="Boreas", codex=5, x=150, y=100, radius_km=3389, 
        active_towers=4, atmosphere_thickness_km=85, refraction_index=1.0520
    )
    return aegis, boreas

def test_void_distance(sample_planets):
    aegis, boreas = sample_planets
    S = 100000.0  # coordinate_scale_unit_km
    
    # Expected: center_dist = sqrt(150^2 + 100^2) * 100000 = 18027756.377
    # Shell A = 6371 + 120 = 6491
    # Shell B = 3389 + 85 = 3474
    # L = 18027756.377 - 6491 - 3474 = 18017791.377
    L = void_distance(aegis, boreas, S)
    assert abs(L - 18017791.377) < 1.0

def test_void_travel_time(sample_planets):
    aegis, boreas = sample_planets
    C = 300000.0
    L = 18017791.377
    
    # Tv = (120*1.0003)/C + L/C + (85*1.0520)/C
    # Tv = 120.036/C + L/C + 89.42/C
    # Tv = 0.0004 + 60.0593 + 0.000298 = ~60.06
    Tv = void_travel_time(aegis, boreas, L, C)
    expected_tv = (120.036 + L + 89.42) / C
    assert abs(Tv - expected_tv) < 1e-6

def test_tower_positions():
    # Test a planet with 4 towers (0, 90, 180, 270 degrees)
    p = Planet("Test", codex=2, x=0, y=0, radius_km=1000, 
               active_towers=4, atmosphere_thickness_km=0, refraction_index=1)
    pos = tower_positions(p)
    assert len(pos) == 4
    
    # Tower 0 is at top: (0, 1000)
    assert abs(pos[0][0] - 0) < 1e-6
    assert abs(pos[0][1] - 1000) < 1e-6
    
    # Tower 1 is at 90 deg clockwise: (1000, 0)
    assert abs(pos[1][0] - 1000) < 1e-6
    assert abs(pos[1][1] - 0) < 1e-6

def test_crust_transit_time_dedup():
    p = Planet("Test", codex=2, x=0, y=0, radius_km=1000, 
               active_towers=4, atmosphere_thickness_km=0, refraction_index=1)
    
    # Entry == Exit
    Tp = crust_transit_time(p, entry_tower=2, exit_tower=2, 
                            fiber_fraction=0.67, speed_of_light_kms=300000.0, 
                            tower_delay_ms=7.0)
    
    # Distance = 0, so fiber time = 0.
    # m = 1 (dedup), so processing time = 1 * 7ms = 0.007s
    assert abs(Tp - 0.007) < 1e-6

def test_crust_transit_time_shortest_arc():
    # 8 towers, distance from 0 to 6 is shorter going counter-clockwise (2 segments)
    # than clockwise (6 segments)
    p = Planet("Test", codex=2, x=0, y=0, radius_km=1000, 
               active_towers=8, atmosphere_thickness_km=0, refraction_index=1)
    
    Tp_0_to_6 = crust_transit_time(p, entry_tower=0, exit_tower=6, 
                                   fiber_fraction=0.67, speed_of_light_kms=300000.0, 
                                   tower_delay_ms=7.0)
    
    Tp_0_to_2 = crust_transit_time(p, entry_tower=0, exit_tower=2, 
                                   fiber_fraction=0.67, speed_of_light_kms=300000.0, 
                                   tower_delay_ms=7.0)
    
    # Both paths are 2 segments. The time should be exactly the same.
    assert abs(Tp_0_to_6 - Tp_0_to_2) < 1e-6
    
    # Ensure m = 3 (s=2, m=s+1=3)
    # fiber_time = 2 * (2*pi*1000 / 8) / (0.67*300000) 
    # processing = 3 * 0.007 = 0.021s
    expected_fiber = 2 * (2 * math.pi * 1000 / 8) / (0.67 * 300000)
    expected_processing = 0.021
    assert abs(Tp_0_to_6 - (expected_fiber + expected_processing)) < 1e-6
