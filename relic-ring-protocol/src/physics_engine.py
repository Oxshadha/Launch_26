import math
from typing import Tuple, List

# To avoid circular imports or redefining, we can import from config_parser
# (assuming it's in the same directory)
from config_parser import Planet

def void_distance(p1: Planet, p2: Planet, scale_unit_km: float) -> float:
    """
    Formula 1: Void Distance (L)
    Calculates the straight-line vacuum distance between two planets,
    subtracting their radii and atmospheric thicknesses.
    """
    dx = p2.x - p1.x
    dy = p2.y - p1.y
    center_dist_km = math.sqrt(dx**2 + dy**2) * scale_unit_km
    
    p1_shell = p1.radius_km + p1.atmosphere_thickness_km
    p2_shell = p2.radius_km + p2.atmosphere_thickness_km
    
    L = center_dist_km - p1_shell - p2_shell
    return max(L, 0.0)

def void_travel_time(p1: Planet, p2: Planet, L: float, speed_of_light_kms: float) -> float:
    """
    Formula 2: Void Travel Time (Tv)
    Calculates the time to travel through p1's atmosphere, the void distance L, 
    and p2's atmosphere. Refraction index slows the signal in the atmosphere.
    Returns time in seconds.
    """
    C = speed_of_light_kms
    atm_1_time = (p1.atmosphere_thickness_km * p1.refraction_index) / C
    void_time = L / C
    atm_2_time = (p2.atmosphere_thickness_km * p2.refraction_index) / C
    
    return atm_1_time + void_time + atm_2_time

def tower_positions(planet: Planet) -> List[Tuple[float, float]]:
    """
    Returns the (x, y) coordinates of all towers relative to the planet's center.
    Towers are placed at equal angular intervals starting from the top (+y axis),
    assigned clockwise.
    """
    N = planet.active_towers
    positions = []
    for i in range(N):
        # Top is 0 degrees. Clockwise means x = sin(angle), y = cos(angle)
        angle_rad = math.radians(i * (360.0 / N))
        tx = planet.radius_km * math.sin(angle_rad)
        ty = planet.radius_km * math.cos(angle_rad)
        positions.append((tx, ty))
    return positions

def find_closest_tower_pair(p1: Planet, p2: Planet, scale_unit_km: float) -> Tuple[int, int]:
    """
    Line of Sight requirement: The tower pair that minimizes the straight-line 
    void distance between them is used for sending and receiving.
    Returns (p1_tower_index, p2_tower_index).
    """
    towers_1 = tower_positions(p1)
    towers_2 = tower_positions(p2)
    
    best_dist = float('inf')
    best_pair = (0, 0)
    
    # Absolute positions of planets
    abs_p1_x = p1.x * scale_unit_km
    abs_p1_y = p1.y * scale_unit_km
    abs_p2_x = p2.x * scale_unit_km
    abs_p2_y = p2.y * scale_unit_km

    for i, (tx1, ty1) in enumerate(towers_1):
        t1_abs_x = abs_p1_x + tx1
        t1_abs_y = abs_p1_y + ty1
        for j, (tx2, ty2) in enumerate(towers_2):
            t2_abs_x = abs_p2_x + tx2
            t2_abs_y = abs_p2_y + ty2
            
            # Distance between tower i on p1 and tower j on p2
            dist = math.sqrt((t2_abs_x - t1_abs_x)**2 + (t2_abs_y - t1_abs_y)**2)
            if dist < best_dist:
                best_dist = dist
                best_pair = (i, j)
                
    return best_pair

def crust_transit_time(planet: Planet, entry_tower: int, exit_tower: int, 
                       fiber_fraction: float, speed_of_light_kms: float, 
                       tower_delay_ms: float) -> float:
    """
    Formula 3: Internal Crust Transit Time (Tp)
    Calculates the time spent traveling internally via fiber between the entry and exit tower,
    plus the processing delay at each distinct tower hit.
    Returns time in seconds.
    """
    N = planet.active_towers
    raw_diff = abs(exit_tower - entry_tower)
    
    # Route via the shorter arc
    s = min(raw_diff, N - raw_diff)
    
    # Deduplication case: if entry == exit, m=1. Otherwise m=s+1
    m = 1 if s == 0 else s + 1
    
    # Fiber delay (using 2*pi*r / N for a single segment distance)
    arc_distance = s * (2 * math.pi * planet.radius_km / N)
    fiber_speed = fiber_fraction * speed_of_light_kms
    fiber_time = arc_distance / fiber_speed
    
    # Processing delay (convert ms to seconds)
    processing_time = m * (tower_delay_ms / 1000.0)
    
    return fiber_time + processing_time
