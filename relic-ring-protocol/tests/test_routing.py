import sys
import os
import pytest

# Add src to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from config_parser import load_universe_config, Planet
from graph_builder import build_network_graph, find_bridge_nodes

@pytest.fixture
def universe_data():
    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../universe-config.json'))
    meta, planets = load_universe_config(config_path)
    return meta, planets

def test_graph_builder_lmax_filtering(universe_data):
    meta, planets = universe_data
    graph = build_network_graph(meta, planets)
    
    assert len(graph.planets) == 6
    
    Lmax = meta.max_void_hop_distance_km
    for source_id, edges in graph.adjacency.items():
        for edge in edges:
            assert edge.void_distance_km <= Lmax, \
                f"Edge {edge.source_id} -> {edge.dest_id} exceeds Lmax ({edge.void_distance_km} > {Lmax})"

def test_graph_builder_edges(universe_data):
    meta, planets = universe_data
    graph = build_network_graph(meta, planets)
    
    # Verify Aegis (0, 0) and Boreas (150, 100) are connected
    aegis_edges = graph.adjacency.get("Aegis", [])
    aegis_to_boreas = [e for e in aegis_edges if e.dest_id == "Boreas"]
    assert len(aegis_to_boreas) == 1
    edge = aegis_to_boreas[0]
    
    assert edge.source_id == "Aegis"
    assert edge.dest_id == "Boreas"
    assert edge.void_distance_km > 0
    # Towers should be valid indices
    assert 0 <= edge.source_exit_tower < graph.planets["Aegis"].active_towers
    assert 0 <= edge.dest_entry_tower < graph.planets["Boreas"].active_towers

def test_bridge_nodes(universe_data):
    meta, planets = universe_data
    graph = build_network_graph(meta, planets)
    
    # Find bridges in the default active graph
    bridges = find_bridge_nodes(graph)
    # Just verify it returns a list (may or may not contain bridges depending on topology connectivity)
    assert isinstance(bridges, list)
    for b in bridges:
        assert b in graph.planets

def test_routing_dijkstra_and_astar(universe_data):
    from routing_engine import dijkstra, a_star, find_route
    meta, planets = universe_data
    graph = build_network_graph(meta, planets)
    
    # Route from Aegis to Caelum
    res_dijkstra = dijkstra(graph, "Aegis", "Caelum")
    res_astar = a_star(graph, "Aegis", "Caelum")
    
    assert res_dijkstra.is_reachable
    assert res_astar.is_reachable
    assert res_dijkstra.path == res_astar.path
    assert abs(res_dijkstra.total_latency_s - res_astar.total_latency_s) < 1e-6
    
    # Check hop details structure
    assert len(res_dijkstra.hop_details) > 0
    for hop in res_dijkstra.hop_details:
        assert "planet_id" in hop
        assert "entry_tower" in hop
        assert "exit_tower" in hop
        assert "void_distance_km" in hop
        assert "void_time_s" in hop
        assert "crust_total_s" in hop
        
    # Check API convenience wrapper
    res_api = find_route(graph, "Aegis", "Caelum", algorithm="a_star")
    assert res_api.path == res_astar.path

def test_routing_cross_validation_all_pairs(universe_data):
    from routing_engine import cross_validate
    meta, planets = universe_data
    graph = build_network_graph(meta, planets)
    
    # Run cross-validation on all pairs
    assert cross_validate(graph)

def test_routing_unreachable(universe_data):
    from routing_engine import dijkstra
    meta, planets = universe_data
    
    # Create a graph with Aegis and Caelum but make them too far away by setting coordinates extremely large
    p1 = Planet("Aegis", 8, 0.0, 0.0, 6371.0, 8, 120.0, 1.0003)
    p2 = Planet("Caelum", 14, 9999.0, 9999.0, 58232.0, 16, 500.0, 1.3210)
    
    graph = build_network_graph(meta, [p1, p2])
    
    res = dijkstra(graph, "Aegis", "Caelum")
    assert not res.is_reachable
    assert res.total_latency_s == float('inf')

