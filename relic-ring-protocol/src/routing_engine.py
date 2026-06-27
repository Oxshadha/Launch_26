import heapq
import math
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass

from config_parser import Planet, UniverseMetadata
from graph_builder import NetworkGraph, EdgeInfo
from physics_engine import crust_transit_time

@dataclass
class RouteResult:
    """The result of a routing path computation."""
    path: List[str]              # Ordered list of planet IDs
    total_latency_s: float       # Sum of all Tp + Tv (in seconds)
    hop_details: List[Dict[str, Any]] # Detailed breakdown of each hop
    algorithm_used: str          # "dijkstra" | "a_star"
    is_reachable: bool           # True if a path exists, False otherwise

def euclidean_heuristic(graph: NetworkGraph, current_id: str, dest_id: str) -> float:
    """
    A* heuristic: straight-line distance / speed of light.
    ADMISSIBILITY PROOF:
    - The shortest physical distance between two planets is a straight line.
    - The fastest possible speed in the universe is the speed of light (C).
    - Actual paths go through atmospheres (slowing light down due to refraction index n > 1)
      and fiber cables (traveling at 0.67c), plus they incur tower processing delays (7ms).
    - Therefore, the actual travel time will always be greater than or equal to h(n).
    - Since h(n) never overestimates the actual cost, it is provably admissible and optimal.
    """
    meta = graph.metadata
    p_curr = graph.planets[current_id]
    p_dest = graph.planets[dest_id]
    
    dx = (p_dest.x - p_curr.x) * meta.coordinate_scale_unit_km
    dy = (p_dest.y - p_curr.y) * meta.coordinate_scale_unit_km
    straight_line_dist = math.sqrt(dx**2 + dy**2)
    
    return straight_line_dist / meta.speed_of_light_kms

def dijkstra(graph: NetworkGraph, source_id: str, dest_id: str) -> RouteResult:
    """
    Finds the shortest latency path between source and destination using Dijkstra's algorithm.
    Cumulative path cost represents the total accumulated latency (seconds).
    """
    if source_id not in graph.planets or dest_id not in graph.planets:
        return RouteResult(path=[], total_latency_s=float('inf'), hop_details=[], algorithm_used="dijkstra", is_reachable=False)
        
    # Priority queue contains tuples of:
    # (cost_so_far, unique_counter, current_node_id, path_taken, hop_details_list, current_entry_tower)
    # We use a tie-breaker counter to avoid comparing lists/dicts in python when costs are identical.
    counter = 0
    pq = []
    
    # We push an initial state. For the source planet:
    # We don't have an entry tower yet because we haven't hopped to it.
    # Its cost is 0.0 initially.
    heapq.heappush(pq, (0.0, counter, source_id, [source_id], [], None))
    
    # Track the minimum cost to reach each node with a specific entry tower.
    # Since we can reach a node with different entry towers (which affect downstream Tp),
    # we use (node_id, entry_tower) as the visited key.
    best_costs = {}
    
    meta = graph.metadata
    
    while pq:
        cost, _, curr_id, path, hops, entry_tower = heapq.heappop(pq)
        
        # Check if we have already found a cheaper or equal path to this state
        state_key = (curr_id, entry_tower)
        if state_key in best_costs and best_costs[state_key] <= cost:
            continue
        best_costs[state_key] = cost
        
        # If we reached the destination planet
        if curr_id == dest_id:
            # We must add the final destination planet's processing delay.
            # The packet arrives at entry_tower and stops there, which counts as 1 tower hit.
            # If entry_tower is None (meaning source == destination), it is processed at its exit/entry tower.
            final_entry = entry_tower
            if final_entry is None:
                # If path has only 1 planet, entry and exit are the same tower (0 by default or any)
                final_entry = 0
                
            dest_planet = graph.planets[curr_id]
            Tp_dest = crust_transit_time(
                dest_planet, final_entry, final_entry,
                meta.fiber_speed_fraction, meta.speed_of_light_kms,
                meta.tower_processing_delay_ms
            )
            
            total_latency = round(cost + Tp_dest, 9)
            
            return RouteResult(
                path=path,
                total_latency_s=total_latency,
                hop_details=hops,
                algorithm_used="dijkstra",
                is_reachable=True
            )
            
        # Explore neighbors
        for edge in graph.adjacency.get(curr_id, []):
            dest_planet = graph.planets.get(edge.dest_id)
            if not dest_planet or not dest_planet.is_active:
                continue
                
            # If source planet has no incoming hop, its entry tower is its exit tower
            actual_entry = entry_tower if entry_tower is not None else edge.source_exit_tower
            
            # Compute internal crust transit time Tp on the source planet of this edge
            Tp_curr = crust_transit_time(
                graph.planets[curr_id], actual_entry, edge.source_exit_tower,
                meta.fiber_speed_fraction, meta.speed_of_light_kms,
                meta.tower_processing_delay_ms
            )
            
            # Void travel time Tv
            Tv = edge.void_travel_time_s
            
            # Total edge transition cost
            transition_cost = Tp_curr + Tv
            new_cost = cost + transition_cost
            
            # Construct hop log detail entry
            hop_log_entry = {
                "planet_id": curr_id,
                "entry_tower": actual_entry,
                "exit_tower": edge.source_exit_tower,
                # segments_traversed and towers_hit can be calculated from arc segments
                "segments_traversed": min(
                    abs(edge.source_exit_tower - actual_entry),
                    graph.planets[curr_id].active_towers - abs(edge.source_exit_tower - actual_entry)
                ),
                "towers_hit": 1 if actual_entry == edge.source_exit_tower else (
                    min(
                        abs(edge.source_exit_tower - actual_entry),
                        graph.planets[curr_id].active_towers - abs(edge.source_exit_tower - actual_entry)
                    ) + 1
                ),
                "fiber_time_s": round(
                    (min(
                        abs(edge.source_exit_tower - actual_entry),
                        graph.planets[curr_id].active_towers - abs(edge.source_exit_tower - actual_entry)
                    ) * (2 * math.pi * graph.planets[curr_id].radius_km / graph.planets[curr_id].active_towers)) / (meta.fiber_speed_fraction * meta.speed_of_light_kms),
                    9
                ),
                "processing_time_s": round(
                    (1 if actual_entry == edge.source_exit_tower else (
                        min(
                            abs(edge.source_exit_tower - actual_entry),
                            graph.planets[curr_id].active_towers - abs(edge.source_exit_tower - actual_entry)
                        ) + 1
                    )) * (meta.tower_processing_delay_ms / 1000.0),
                    9
                ),
                "crust_total_s": round(Tp_curr, 9),
                "void_distance_km": round(edge.void_distance_km, 9),
                "void_time_s": round(Tv, 9),
                "codex_base": graph.planets[curr_id].codex,
                "next_hop_entry_tower": edge.dest_entry_tower
            }
            
            counter += 1
            heapq.heappush(
                pq,
                (new_cost, counter, edge.dest_id, path + [edge.dest_id], hops + [hop_log_entry], edge.dest_entry_tower)
            )
            
    return RouteResult(path=[], total_latency_s=float('inf'), hop_details=[], algorithm_used="dijkstra", is_reachable=False)

def a_star(graph: NetworkGraph, source_id: str, dest_id: str) -> RouteResult:
    """
    Finds the shortest latency path between source and destination using the A* Search algorithm
    guided by the admissible Euclidean heuristic.
    """
    if source_id not in graph.planets or dest_id not in graph.planets:
        return RouteResult(path=[], total_latency_s=float('inf'), hop_details=[], algorithm_used="a_star", is_reachable=False)
        
    meta = graph.metadata
    
    # Priority queue contains:
    # (f_score, unique_counter, g_score, current_node_id, path_taken, hop_details_list, current_entry_tower)
    counter = 0
    h_start = euclidean_heuristic(graph, source_id, dest_id)
    pq = []
    heapq.heappush(pq, (h_start, counter, 0.0, source_id, [source_id], [], None))
    
    best_g_costs = {}
    
    while pq:
        _, _, g_cost, curr_id, path, hops, entry_tower = heapq.heappop(pq)
        
        state_key = (curr_id, entry_tower)
        if state_key in best_g_costs and best_g_costs[state_key] <= g_cost:
            continue
        best_g_costs[state_key] = g_cost
        
        if curr_id == dest_id:
            final_entry = entry_tower
            if final_entry is None:
                final_entry = 0
                
            dest_planet = graph.planets[curr_id]
            Tp_dest = crust_transit_time(
                dest_planet, final_entry, final_entry,
                meta.fiber_speed_fraction, meta.speed_of_light_kms,
                meta.tower_processing_delay_ms
            )
            
            total_latency = round(g_cost + Tp_dest, 9)
            
            return RouteResult(
                path=path,
                total_latency_s=total_latency,
                hop_details=hops,
                algorithm_used="a_star",
                is_reachable=True
            )
            
        # Explore neighbors
        for edge in graph.adjacency.get(curr_id, []):
            dest_planet = graph.planets.get(edge.dest_id)
            if not dest_planet or not dest_planet.is_active:
                continue
                
            actual_entry = entry_tower if entry_tower is not None else edge.source_exit_tower
            
            Tp_curr = crust_transit_time(
                graph.planets[curr_id], actual_entry, edge.source_exit_tower,
                meta.fiber_speed_fraction, meta.speed_of_light_kms,
                meta.tower_processing_delay_ms
            )
            
            Tv = edge.void_travel_time_s
            new_g = g_cost + Tp_curr + Tv
            h_next = euclidean_heuristic(graph, edge.dest_id, dest_id)
            new_f = new_g + h_next
            
            # Construct hop log detail entry
            hop_log_entry = {
                "planet_id": curr_id,
                "entry_tower": actual_entry,
                "exit_tower": edge.source_exit_tower,
                "segments_traversed": min(
                    abs(edge.source_exit_tower - actual_entry),
                    graph.planets[curr_id].active_towers - abs(edge.source_exit_tower - actual_entry)
                ),
                "towers_hit": 1 if actual_entry == edge.source_exit_tower else (
                    min(
                        abs(edge.source_exit_tower - actual_entry),
                        graph.planets[curr_id].active_towers - abs(edge.source_exit_tower - actual_entry)
                    ) + 1
                ),
                "fiber_time_s": round(
                    (min(
                        abs(edge.source_exit_tower - actual_entry),
                        graph.planets[curr_id].active_towers - abs(edge.source_exit_tower - actual_entry)
                    ) * (2 * math.pi * graph.planets[curr_id].radius_km / graph.planets[curr_id].active_towers)) / (meta.fiber_speed_fraction * meta.speed_of_light_kms),
                    9
                ),
                "processing_time_s": round(
                    (1 if actual_entry == edge.source_exit_tower else (
                        min(
                            abs(edge.source_exit_tower - actual_entry),
                            graph.planets[curr_id].active_towers - abs(edge.source_exit_tower - actual_entry)
                        ) + 1
                    )) * (meta.tower_processing_delay_ms / 1000.0),
                    9
                ),
                "crust_total_s": round(Tp_curr, 9),
                "void_distance_km": round(edge.void_distance_km, 9),
                "void_time_s": round(Tv, 9),
                "codex_base": graph.planets[curr_id].codex,
                "next_hop_entry_tower": edge.dest_entry_tower
            }
            
            counter += 1
            heapq.heappush(
                pq,
                (new_f, counter, new_g, edge.dest_id, path + [edge.dest_id], hops + [hop_log_entry], edge.dest_entry_tower)
            )
            
    return RouteResult(path=[], total_latency_s=float('inf'), hop_details=[], algorithm_used="a_star", is_reachable=False)

def cross_validate(graph: NetworkGraph) -> bool:
    """
    Runs both Dijkstra and A* on all active directed planet pairs
    and asserts that they return identical path costs (total latency).
    """
    active_planets = [p.id for p in graph.planets.values() if p.is_active]
    
    for src in active_planets:
        for dest in active_planets:
            if src == dest:
                continue
                
            res_dijkstra = dijkstra(graph, src, dest)
            res_astar = a_star(graph, src, dest)
            
            assert res_dijkstra.is_reachable == res_astar.is_reachable, \
                f"Reachability mismatch between Dijkstra and A* from {src} to {dest}"
                
            if res_dijkstra.is_reachable:
                # Allow minor floating-point discrepancy up to 1 microsecond (1e-6 s)
                diff = abs(res_dijkstra.total_latency_s - res_astar.total_latency_s)
                assert diff < 1e-6, \
                    f"Cost mismatch from {src} to {dest}: Dijkstra={res_dijkstra.total_latency_s}s, A*={res_astar.total_latency_s}s"
                    
    return True

def find_route(graph: NetworkGraph, source_id: str, dest_id: str, algorithm: str = "a_star") -> RouteResult:
    """
    API for routing packets across the network using the specified algorithm.
    """
    if algorithm == "a_star":
        return a_star(graph, source_id, dest_id)
    elif algorithm == "dijkstra":
        return dijkstra(graph, source_id, dest_id)
    else:
        raise ValueError(f"Unknown routing algorithm: {algorithm}")
