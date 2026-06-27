import time
import math
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass

from config_parser import Planet, UniverseMetadata
from graph_builder import NetworkGraph, build_network_graph, find_bridge_nodes, EdgeInfo
from routing_engine import RouteResult, dijkstra, a_star, _build_hop_log_entry
from physics_engine import crust_transit_time

def _compute_path_cost(graph: NetworkGraph, path: List[str]) -> Optional[RouteResult]:
    """
    Given a list of node IDs representing a path, computes the total latency cost
    and constructs the complete hop details list.
    """
    if not path:
        return None
        
    meta = graph.metadata
    
    if len(path) == 1:
        # Path with only 1 planet
        dest_planet = graph.planets.get(path[0])
        if not dest_planet:
            return None
        Tp = crust_transit_time(
            dest_planet, 0, 0,
            meta.fiber_speed_fraction, meta.speed_of_light_kms,
            meta.tower_processing_delay_ms
        )
        return RouteResult(
            path=path,
            total_latency_s=round(Tp, 9),
            hop_details=[],
            algorithm_used="yens_k_shortest",
            is_reachable=True
        )
        
    cost = 0.0
    hops = []
    entry_tower = None
    
    for idx in range(len(path) - 1):
        curr_id = path[idx]
        next_id = path[idx + 1]
        
        # Find the directed edge between curr_id and next_id
        edge = None
        for e in graph.adjacency.get(curr_id, []):
            if e.dest_id == next_id:
                edge = e
                break
                
        if not edge:
            return None  # Path contains an invalid edge
            
        actual_entry = entry_tower if entry_tower is not None else edge.source_exit_tower
        
        Tp_curr = crust_transit_time(
            graph.planets[curr_id], actual_entry, edge.source_exit_tower,
            meta.fiber_speed_fraction, meta.speed_of_light_kms,
            meta.tower_processing_delay_ms
        )
        
        Tv = edge.void_travel_time_s
        cost += Tp_curr + Tv
        
        hop_log_entry = _build_hop_log_entry(
            graph.planets[curr_id], actual_entry, edge, Tp_curr, graph.metadata
        )
        hops.append(hop_log_entry)
        entry_tower = edge.dest_entry_tower
        
    # Add final destination Tp
    dest_id = path[-1]
    final_entry = entry_tower if entry_tower is not None else 0
    Tp_dest = crust_transit_time(
        graph.planets[dest_id], final_entry, final_entry,
        meta.fiber_speed_fraction, meta.speed_of_light_kms,
        meta.tower_processing_delay_ms
    )
    cost += Tp_dest
    
    return RouteResult(
        path=path,
        total_latency_s=round(cost, 9),
        hop_details=hops,
        algorithm_used="yens_k_shortest",
        is_reachable=True
    )

def yens_k_shortest_paths(graph: NetworkGraph, source_id: str, dest_id: str, K: int = 3) -> List[RouteResult]:
    """
    Computes up to K loopless shortest paths from source_id to dest_id using Yen's Algorithm.
    """
    # Find the first shortest path
    shortest = dijkstra(graph, source_id, dest_id)
    if not shortest or not shortest.is_reachable:
        return []
        
    A = [shortest]
    B: List[RouteResult] = []
    
    for k in range(1, K):
        # The path to spur from
        prev_path = A[-1].path
        
        # Iterate over all nodes in the previous path except the destination
        for i in range(len(prev_path) - 1):
            spur_node = prev_path[i]
            root_path = prev_path[:i + 1]
            
            blocked_edges = set()
            blocked_nodes = set()
            
            # Find candidate paths that share the same root path
            for path_res in A:
                p = path_res.path
                if len(p) > i and p[:i + 1] == root_path:
                    # Remove the edge from spur_node to the next node in the path
                    blocked_edges.add((p[i], p[i+1]))
                    
            # Remove all root path nodes from the graph except the spur node
            for node in root_path[:-1]:
                blocked_nodes.add(node)
                
            # Find the spur path from spur_node to dest_id
            spur_res = dijkstra(graph, spur_node, dest_id, blocked_nodes=blocked_nodes, blocked_edges=blocked_edges)
            
            if spur_res and spur_res.is_reachable:
                # Combine root path and spur path
                total_path = root_path[:-1] + spur_res.path
                
                # Verify loopless condition
                if len(total_path) == len(set(total_path)):
                    candidate_res = _compute_path_cost(graph, total_path)
                    if candidate_res:
                        # Add to candidates list B if not already present
                        path_tuples_B = [tuple(c.path) for c in B]
                        path_tuples_A = [tuple(a.path) for a in A]
                        path_tup = tuple(candidate_res.path)
                        if path_tup not in path_tuples_B and path_tup not in path_tuples_A:
                            B.append(candidate_res)
                            
        if not B:
            break
            
        # Sort candidate paths by latency cost and pick the shortest
        B.sort(key=lambda x: x.total_latency_s)
        best_candidate = B.pop(0)
        A.append(best_candidate)
        
    return A

class ResilienceManager:
    """
    ResilienceManager monitors the active state of nodes and handles dynamic path recalculation
    and convergence logging for the Chaos Test.
    """
    def __init__(self, metadata: UniverseMetadata, planets: List[Planet]):
        self.metadata = metadata
        self.all_planets = {p.id: p for p in planets}
        self.dead_nodes: set[str] = set()
        self.graph: NetworkGraph = build_network_graph(metadata, planets)
        self.route_cache: Dict[Tuple[str, str], List[RouteResult]] = {}
        self.pending_packets: List[Dict[str, Any]] = []
        self.convergence_log: List[Dict[str, Any]] = []
        
        # Pre-compute routes for all active planet pairs
        self._precompute_all_routes()
        
    def _precompute_all_routes(self):
        """Precomputes the top 3 (K=3) shortest paths for all active planet pairs."""
        self.route_cache.clear()
        active_ids = [pid for pid, p in self.all_planets.items() if p.is_active]
        
        for src in active_ids:
            for dest in active_ids:
                if src == dest:
                    continue
                routes = yens_k_shortest_paths(self.graph, src, dest, K=3)
                self.route_cache[(src, dest)] = routes
                
    def kill_node(self, node_id: str) -> Dict[str, Any]:
        """
        Simulates the death of a planet node (Chaos Test).
        Rebuilds the network graph, updates the route cache, and logs the convergence time.
        """
        start_time = time.perf_counter()
        
        if node_id not in self.all_planets:
            raise ValueError(f"Unknown planet node: {node_id}")
            
        self.all_planets[node_id].is_active = False
        self.dead_nodes.add(node_id)
        
        # Rebuild graph considering only active nodes
        active_planets = [p for p in self.all_planets.values() if p.is_active]
        self.graph = build_network_graph(self.metadata, active_planets)
        
        # Re-precompute routes
        self._precompute_all_routes()
        
        end_time = time.perf_counter()
        convergence_ms = (end_time - start_time) * 1000.0
        
        log_entry = {
            "action": "kill_node",
            "node_id": node_id,
            "convergence_time_ms": round(convergence_ms, 3),
            "remaining_active": len(active_planets),
            "dead_nodes": list(self.dead_nodes)
        }
        self.convergence_log.append(log_entry)
        return log_entry
        
    def revive_node(self, node_id: str) -> Dict[str, Any]:
        """
        Simulates the recovery of a planet node.
        Rebuilds the network graph, updates the route cache, flushes the DTN queue,
        and logs the convergence time.
        """
        start_time = time.perf_counter()
        
        if node_id not in self.all_planets:
            raise ValueError(f"Unknown planet node: {node_id}")
            
        self.all_planets[node_id].is_active = True
        self.dead_nodes.discard(node_id)
        
        # Rebuild graph
        active_planets = [p for p in self.all_planets.values() if p.is_active]
        self.graph = build_network_graph(self.metadata, active_planets)
        
        # Re-precompute routes
        self._precompute_all_routes()
        
        # Flush the Delay Tolerant Networking (DTN) queue
        flushed_count = self._flush_pending_packets()
        
        end_time = time.perf_counter()
        convergence_ms = (end_time - start_time) * 1000.0
        
        log_entry = {
            "action": "revive_node",
            "node_id": node_id,
            "convergence_time_ms": round(convergence_ms, 3),
            "remaining_active": len(active_planets),
            "dead_nodes": list(self.dead_nodes),
            "packets_flushed": flushed_count
        }
        self.convergence_log.append(log_entry)
        return log_entry
        
    def get_route(self, source_id: str, dest_id: str) -> Optional[RouteResult]:
        """
        Returns the best route from source to destination.
        Attempts to read from precomputed K-shortest paths cache to enable O(1) failover.
        Falls back to a live A* query if needed.
        """
        cache_key = (source_id, dest_id)
        if cache_key in self.route_cache:
            for route in self.route_cache[cache_key]:
                # Verify that no node in the path has been killed
                if not any(node in self.dead_nodes for node in route.path):
                    return route
                    
        # Fallback to live A* calculation
        res = a_star(self.graph, source_id, dest_id)
        return res if res and res.is_reachable else None
        
    def queue_undeliverable(self, source_id: str, dest_id: str, payload: str):
        """DTN Queueing: Stores packet payload if no route exists."""
        self.pending_packets.append({
            "source_id": source_id,
            "dest_id": dest_id,
            "payload": payload,
            "timestamp": time.time()
        })
        
    def _flush_pending_packets(self) -> int:
        """Attempts to route queued packets after a network change."""
        still_pending = []
        flushed_count = 0
        
        for packet in self.pending_packets:
            route = self.get_route(packet["source_id"], packet["dest_id"])
            if route and route.is_reachable:
                # Successfully routed/delivered
                flushed_count += 1
            else:
                still_pending.append(packet)
                
        self.pending_packets = still_pending
        return flushed_count
        
    def get_network_status(self) -> Dict[str, Any]:
        """Returns the current network health, active nodes, dead nodes, and bridge nodes."""
        active = [pid for pid, p in self.all_planets.items() if p.is_active]
        bridges = find_bridge_nodes(self.graph)
        
        total_edges = sum(len(edges) for edges in self.graph.adjacency.values())
        
        return {
            "active_nodes": active,
            "dead_nodes": list(self.dead_nodes),
            "total_edges": total_edges,
            "bridge_nodes": bridges,
            "pending_packets": len(self.pending_packets),
            "convergence_log": self.convergence_log
        }
