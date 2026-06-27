"""
test_codec.py — Comprehensive tests for the Packet Codec Engine
================================================================
Validates base conversion, round-trip integrity, spec example matching,
and the two audit fixes (destination hop_log entry + payload_in_codex).
"""

import sys
import os
import pytest

# Add src to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from config_parser import Planet, load_universe_config, UniverseMetadata
from packet_codec import (
    int_to_base_n,
    base_n_to_int,
    ascii_to_codex,
    codex_to_ascii,
    translate_payload,
    Packet,
    build_hop_log_entry,
    build_destination_hop_entry,
    simulate_packet_journey,
)


# ──────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────

@pytest.fixture
def universe_data():
    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../universe-config.json'))
    meta, planets = load_universe_config(config_path)
    return meta, planets


@pytest.fixture
def planets_dict(universe_data):
    meta, planets = universe_data
    return {p.id: p for p in planets}


# ──────────────────────────────────────────────────────────────────
# Test 1: int_to_base_n — basic conversions
# ──────────────────────────────────────────────────────────────────

def test_int_to_base_n_basic():
    """Validates the spec example conversions."""
    # H (ASCII 72) in Base 5 = "242" (72 = 2*25 + 4*5 + 2*1)
    assert int_to_base_n(72, 5) == "242"

    # H (ASCII 72) in Base 14 = "52" (72 = 5*14 + 2*1)
    assert int_to_base_n(72, 14) == "52"

    # H (ASCII 72) in Base 16 = "48" (72 = 4*16 + 8*1)
    assert int_to_base_n(72, 16) == "48"

    # H (ASCII 72) in Base 8 = "110" (72 = 1*64 + 1*8 + 0*1)
    assert int_to_base_n(72, 8) == "110"

    # H (ASCII 72) in Base 10 = "72"
    assert int_to_base_n(72, 10) == "72"


# ──────────────────────────────────────────────────────────────────
# Test 2: int_to_base_n — edge cases
# ──────────────────────────────────────────────────────────────────

def test_int_to_base_n_edge_cases():
    """Validates edge cases: zero, binary, hex letters."""
    # Zero
    assert int_to_base_n(0, 5) == "0"
    assert int_to_base_n(0, 16) == "0"
    assert int_to_base_n(0, 2) == "0"

    # Binary
    assert int_to_base_n(10, 2) == "1010"
    assert int_to_base_n(255, 2) == "11111111"

    # Hexadecimal with letters
    assert int_to_base_n(255, 16) == "FF"
    assert int_to_base_n(10, 16) == "A"
    assert int_to_base_n(15, 16) == "F"

    # Large value
    assert int_to_base_n(1000, 5) == "13000"

    # Error cases
    with pytest.raises(ValueError):
        int_to_base_n(-1, 5)
    with pytest.raises(ValueError):
        int_to_base_n(10, 1)
    with pytest.raises(ValueError):
        int_to_base_n(10, 37)


# ──────────────────────────────────────────────────────────────────
# Test 3: base_n_to_int — round-trip for all bases 2-36
# ──────────────────────────────────────────────────────────────────

def test_base_n_to_int_roundtrip():
    """Round-trip: base_n_to_int(int_to_base_n(v, b), b) == v for all bases."""
    test_values = [0, 1, 10, 42, 72, 100, 101, 108, 111, 119, 127, 255]

    for base in range(2, 37):
        for val in test_values:
            encoded = int_to_base_n(val, base)
            decoded = base_n_to_int(encoded, base)
            assert decoded == val, (
                f"Round-trip failed: {val} -> base {base} -> '{encoded}' -> {decoded}"
            )


# ──────────────────────────────────────────────────────────────────
# Test 4: ascii_to_codex — matches spec "Hello world" example
# ──────────────────────────────────────────────────────────────────

def test_ascii_to_codex_hello():
    """Validates the exact spec example: 'Hello world' in Base 5."""
    result = ascii_to_codex("Hello world", 5)
    expected = ["242", "401", "413", "413", "421", "112", "434", "421", "424", "413", "400"]
    assert result == expected, f"Base 5 mismatch:\n  Got:      {result}\n  Expected: {expected}"

    # Also validate Base 14 from spec
    result_14 = ascii_to_codex("Hello world", 14)
    expected_14 = ["52", "73", "7A", "7A", "7D", "24", "87", "7D", "82", "7A", "72"]
    assert result_14 == expected_14, f"Base 14 mismatch:\n  Got:      {result_14}\n  Expected: {expected_14}"


# ──────────────────────────────────────────────────────────────────
# Test 5: codex_to_ascii — round-trip for all 6 planet codexes
# ──────────────────────────────────────────────────────────────────

def test_codex_to_ascii_roundtrip():
    """codex_to_ascii(ascii_to_codex(text, b), b) == text for all planet codexes."""
    text = "Hello world"
    planet_codexes = [5, 6, 8, 10, 14, 16]

    for base in planet_codexes:
        encoded = ascii_to_codex(text, base)
        decoded = codex_to_ascii(encoded, base)
        assert decoded == text, f"Round-trip failed for base {base}: '{decoded}' != '{text}'"


# ──────────────────────────────────────────────────────────────────
# Test 6: Full "Hello world" journey (Aegis -> Boreas -> Caelum)
# ──────────────────────────────────────────────────────────────────

def test_full_hello_world_journey(universe_data, planets_dict):
    """Complete multi-hop journey with exact encoding verification."""
    meta, planets_list = universe_data

    # Import routing to get an actual route
    from graph_builder import build_network_graph
    from routing_engine import find_route

    graph = build_network_graph(meta, planets_list)
    route = find_route(graph, "Aegis", "Caelum", algorithm="a_star")

    assert route.is_reachable, "Route Aegis -> Caelum should be reachable"
    assert len(route.path) >= 2, "Route should have at least 2 planets"

    # Simulate the journey
    packet = simulate_packet_journey("Hello world", route, planets_dict, meta)

    # Verify the decoded payload matches original
    final_text = codex_to_ascii(packet.encoded_payload, packet.current_codex)
    assert final_text == "Hello world", f"Final decoded text: '{final_text}'"

    # Verify packet schema
    assert packet.origin_id == "Aegis"
    assert packet.destination_id == "Caelum"
    assert packet.payload == "Hello world"
    assert len(packet.hop_log) > 0


# ──────────────────────────────────────────────────────────────────
# Test 7: Packet schema has all mandatory fields
# ──────────────────────────────────────────────────────────────────

def test_packet_schema_fields():
    """Validates Packet dataclass has all mandatory fields from the spec."""
    packet = Packet(
        packet_id="TEST-01",
        origin_id="Aegis",
        destination_id="Caelum",
        current_id="Aegis",
        payload="Test",
    )

    # Mandatory fields per spec
    assert hasattr(packet, "origin_id")
    assert hasattr(packet, "destination_id")
    assert hasattr(packet, "current_id")
    assert hasattr(packet, "payload")
    assert hasattr(packet, "hop_log")

    # Additional fields
    assert hasattr(packet, "encoded_payload")
    assert hasattr(packet, "current_codex")

    # Default values
    assert packet.hop_log == []
    assert packet.encoded_payload == []


# ──────────────────────────────────────────────────────────────────
# Test 8: hop_log entries have payload_in_codex (Audit Fix #2)
# ──────────────────────────────────────────────────────────────────

def test_hop_log_structure(universe_data, planets_dict):
    """Each hop_log entry must have payload_in_codex and codex_base fields."""
    meta, planets_list = universe_data

    from graph_builder import build_network_graph
    from routing_engine import find_route

    graph = build_network_graph(meta, planets_list)
    route = find_route(graph, "Aegis", "Caelum")

    packet = simulate_packet_journey("Hello world", route, planets_dict, meta)

    for i, hop in enumerate(packet.hop_log):
        assert "payload_in_codex" in hop, f"Hop {i} ({hop['planet_id']}) missing payload_in_codex"
        assert "codex_base" in hop, f"Hop {i} ({hop['planet_id']}) missing codex_base"
        assert isinstance(hop["payload_in_codex"], list), f"Hop {i}: payload_in_codex should be a list"
        assert len(hop["payload_in_codex"]) > 0, f"Hop {i}: payload_in_codex should not be empty"
        assert isinstance(hop["codex_base"], int), f"Hop {i}: codex_base should be int"
        assert hop["codex_base"] >= 2, f"Hop {i}: codex_base should be >= 2"


# ──────────────────────────────────────────────────────────────────
# Test 9: hop_log includes destination planet (Audit Fix #1)
# ──────────────────────────────────────────────────────────────────

def test_hop_log_includes_destination(universe_data, planets_dict):
    """The FINAL hop_log entry must be the destination planet."""
    meta, planets_list = universe_data

    from graph_builder import build_network_graph
    from routing_engine import find_route

    graph = build_network_graph(meta, planets_list)
    route = find_route(graph, "Aegis", "Caelum")

    packet = simulate_packet_journey("Hello world", route, planets_dict, meta)

    # The last hop_log entry should be Caelum (destination)
    last_hop = packet.hop_log[-1]
    assert last_hop["planet_id"] == "Caelum", (
        f"Last hop_log entry should be destination 'Caelum', got '{last_hop['planet_id']}'"
    )

    # Destination entry properties
    assert last_hop["segments_traversed"] == 0, "Destination: segments should be 0"
    assert last_hop["towers_hit"] == 1, "Destination: towers_hit should be 1"
    assert last_hop["void_distance_km"] == 0.0, "Destination: void_distance should be 0"
    assert last_hop["void_time_s"] == 0.0, "Destination: void_time should be 0"
    assert last_hop["entry_tower"] == last_hop["exit_tower"], "Destination: entry == exit tower"
    assert last_hop["codex_base"] == 14, "Caelum's codex is Base 14"


# ──────────────────────────────────────────────────────────────────
# Test 10: Special characters in payload
# ──────────────────────────────────────────────────────────────────

def test_special_characters():
    """Validates encoding/decoding of punctuation, spaces, and numbers."""
    test_strings = [
        "Test 123!",
        "Hello, World!",
        "IEEE CS UoK",
        "Zeta-26",
        "a",
        " ",
        "~!@#$%",
    ]

    for text in test_strings:
        for base in [5, 6, 8, 10, 14, 16]:
            encoded = ascii_to_codex(text, base)
            decoded = codex_to_ascii(encoded, base)
            assert decoded == text, (
                f"Round-trip failed for '{text}' in base {base}: got '{decoded}'"
            )


# ──────────────────────────────────────────────────────────────────
# Test 11: All planet codexes — comprehensive round-trip
# ──────────────────────────────────────────────────────────────────

def test_all_planet_codexes():
    """Round-trip through every base used in the universe: 5, 6, 8, 10, 14, 16."""
    text = "The Relic Ring Protocol reconnects Zeta-26!"
    planet_codexes = [5, 6, 8, 10, 14, 16]

    for base in planet_codexes:
        encoded = ascii_to_codex(text, base)
        decoded = codex_to_ascii(encoded, base)
        assert decoded == text, f"Failed for base {base}"

    # Cross-translate between all pairs
    for from_base in planet_codexes:
        encoded = ascii_to_codex(text, from_base)
        for to_base in planet_codexes:
            translated = translate_payload(encoded, from_base, to_base)
            decoded = codex_to_ascii(translated, to_base)
            assert decoded == text, (
                f"Cross-translate failed: base {from_base} -> base {to_base}"
            )
