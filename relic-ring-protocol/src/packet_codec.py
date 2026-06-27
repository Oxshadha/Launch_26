"""
packet_codec.py — Relic Ring Protocol Packet Codec Engine
=========================================================
Member 3 Deliverable: Base-N ↔ ASCII translators, Packet schema,
hop_log construction, and full end-to-end packet journey simulation.

Fixes Audit Issues:
  #1: Adds destination planet entry to hop_log (routing engine omits it)
  #2: Adds payload_in_codex field to every hop_log entry
"""

import math
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from config_parser import Planet, UniverseMetadata
from routing_engine import RouteResult


# ──────────────────────────────────────────────────────────────────
# Section 1: Base-N Conversion Primitives
# ──────────────────────────────────────────────────────────────────

# Digit alphabet: 0-9 then A-Z for bases up to 36
_DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def int_to_base_n(value: int, base: int) -> str:
    """
    Converts a non-negative decimal integer to a string representation
    in the specified base (2–36).

    For bases > 10, uses uppercase letters: A=10, B=11, ..., Z=35.

    Examples:
        int_to_base_n(72, 5)  → "242"   (72 = 2×25 + 4×5 + 2×1)
        int_to_base_n(72, 14) → "52"    (72 = 5×14 + 2×1)
        int_to_base_n(72, 16) → "48"    (72 = 4×16 + 8×1)
        int_to_base_n(0, 5)   → "0"
    """
    if not (2 <= base <= 36):
        raise ValueError(f"Base must be between 2 and 36, got {base}")
    if value < 0:
        raise ValueError(f"Value must be non-negative, got {value}")
    if value == 0:
        return "0"

    digits = []
    n = value
    while n > 0:
        digits.append(_DIGITS[n % base])
        n //= base

    return "".join(reversed(digits))


def base_n_to_int(encoded: str, base: int) -> int:
    """
    Parses a base-N encoded string back to a decimal integer.
    Case-insensitive for letter digits (A-Z).

    Examples:
        base_n_to_int("242", 5)  → 72
        base_n_to_int("52", 14)  → 72
        base_n_to_int("7A", 14)  → 108
    """
    if not (2 <= base <= 36):
        raise ValueError(f"Base must be between 2 and 36, got {base}")
    if not encoded:
        raise ValueError("Encoded string cannot be empty")

    result = 0
    for ch in encoded.upper():
        digit_value = _DIGITS.index(ch)
        if digit_value >= base:
            raise ValueError(
                f"Invalid digit '{ch}' for base {base}"
            )
        result = result * base + digit_value

    return result


# ──────────────────────────────────────────────────────────────────
# Section 2: ASCII ↔ Codex Translation Layer
# ──────────────────────────────────────────────────────────────────

def ascii_to_codex(text: str, target_base: int) -> List[str]:
    """
    Converts a raw ASCII text string to a list of base-N encoded strings.
    Each character is mapped: char → ord(char) → int_to_base_n(ord, base).

    Example:
        ascii_to_codex("Hello world", 5)
        → ["242", "401", "413", "413", "421", "112", "434", "421", "424", "413", "400"]
    """
    return [int_to_base_n(ord(ch), target_base) for ch in text]


def codex_to_ascii(encoded_values: List[str], source_base: int) -> str:
    """
    Converts a list of base-N encoded strings back to an ASCII text string.
    Each value is mapped: base_n_string → int → chr(int).

    Round-trip guarantee:
        codex_to_ascii(ascii_to_codex(text, base), base) == text
    """
    return "".join(chr(base_n_to_int(val, source_base)) for val in encoded_values)


def translate_payload(encoded_values: List[str], from_base: int, to_base: int) -> List[str]:
    """
    Re-encodes a payload from one base to another.
    Pipeline: decode from from_base → decimal integers → encode to to_base.

    Used at each relay hop when the packet crosses from one planet's codex to the next.

    Example:
        # Base 5 → Base 14
        translate_payload(["242", "401", "413"], 5, 14)
        → ["52", "73", "7A"]
    """
    return [int_to_base_n(base_n_to_int(val, from_base), to_base) for val in encoded_values]


# ──────────────────────────────────────────────────────────────────
# Section 3: Packet Dataclass (Mandatory Schema)
# ──────────────────────────────────────────────────────────────────

@dataclass
class Packet:
    """
    The mandatory packet schema as defined by the challenge spec.

    Fields (mandatory per spec):
        origin_id:      Source planet node string
        destination_id: Destination planet node string
        current_id:     Current planet node string
        payload:        The raw message content
        hop_log:        Ordered array appended to by each relay node

    Additional fields:
        encoded_payload: Current codex representation of the payload
        current_codex:   Current encoding base
    """
    origin_id: str
    destination_id: str
    current_id: str
    payload: str
    hop_log: List[Dict[str, Any]] = field(default_factory=list)
    encoded_payload: List[str] = field(default_factory=list)
    current_codex: int = 10  # Default ASCII (base 10 representation)


# ──────────────────────────────────────────────────────────────────
# Section 4: Hop Log Construction
# ──────────────────────────────────────────────────────────────────

def build_hop_log_entry(
    routing_hop: Dict[str, Any],
    payload_in_codex: List[str],
    codex_base: int
) -> Dict[str, Any]:
    """
    Constructs a complete hop_log entry by merging routing engine's
    hop_details with codec translation data.

    FIX Audit #2: Adds the 'payload_in_codex' field that the routing engine omits.

    Args:
        routing_hop:     The hop detail dict from RouteResult.hop_details
        payload_in_codex: The encoded payload values at this hop
        codex_base:      The numerical base used for encoding

    Returns:
        A complete hop_log entry dict matching the challenge spec format.
    """
    entry = dict(routing_hop)  # Shallow copy to avoid mutating the original
    entry["payload_in_codex"] = list(payload_in_codex)
    entry["codex_base"] = codex_base
    return entry


def build_destination_hop_entry(
    planet: Planet,
    entry_tower: int,
    payload_in_codex: List[str],
    tower_delay_ms: float
) -> Dict[str, Any]:
    """
    Constructs the FINAL hop_log entry for the destination planet.

    FIX Audit #1: The routing engine calculates the destination planet's Tp
    and adds it to total_latency_s, but NEVER creates a hop_log entry for it.
    This function fills that gap.

    At the destination:
      - The packet arrives at entry_tower and STAYS there (no exit to another planet)
      - segments_traversed = 0, towers_hit = 1
      - No outgoing void hop (void_distance = 0, void_time = 0)
    """
    processing_time_s = round(tower_delay_ms / 1000.0, 9)

    return {
        "planet_id": planet.id,
        "entry_tower": entry_tower,
        "exit_tower": entry_tower,      # Arrives and stays at the same tower
        "segments_traversed": 0,
        "towers_hit": 1,
        "fiber_time_s": 0.0,
        "processing_time_s": processing_time_s,
        "crust_total_s": processing_time_s,
        "void_distance_km": 0.0,
        "void_time_s": 0.0,
        "payload_in_codex": list(payload_in_codex),
        "codex_base": planet.codex
    }


# ──────────────────────────────────────────────────────────────────
# Section 5: End-to-End Packet Journey Simulation
# ──────────────────────────────────────────────────────────────────

def simulate_packet_journey(
    payload: str,
    route: RouteResult,
    planets: Dict[str, Planet],
    metadata: UniverseMetadata
) -> Packet:
    """
    Simulates a complete packet journey from origin to destination,
    performing codex translations at each hop and building a complete hop_log.

    Flow:
        1. Origin planet: encode payload from ASCII to first hop's next codex
        2. At each relay: decode → ASCII → re-encode to next hop's codex
        3. Destination: final decode to ASCII, append destination hop_log entry

    Args:
        payload:   Raw ASCII text to transmit (e.g., "Hello world")
        route:     RouteResult from the routing engine
        planets:   Dictionary of planet_id → Planet objects
        metadata:  Universe metadata with physical constants

    Returns:
        Fully populated Packet with complete hop_log (including destination entry).

    Raises:
        ValueError: If the route is not reachable or path is empty.
    """
    if not route.is_reachable or not route.path:
        raise ValueError("Cannot simulate journey on an unreachable route")

    path = route.path
    hop_details = route.hop_details

    # Initialize the packet at the origin
    origin_planet = planets[path[0]]
    packet = Packet(
        origin_id=path[0],
        destination_id=path[-1],
        current_id=path[0],
        payload=payload,
    )

    # ── Special case: source == destination (single planet path) ──
    if len(path) == 1:
        # Encode into the planet's own codex
        encoded = ascii_to_codex(payload, origin_planet.codex)
        packet.encoded_payload = encoded
        packet.current_codex = origin_planet.codex

        # Build destination hop entry (FIX #1)
        dest_entry = build_destination_hop_entry(
            origin_planet,
            entry_tower=0,
            payload_in_codex=encoded,
            tower_delay_ms=metadata.tower_processing_delay_ms
        )
        packet.hop_log.append(dest_entry)
        packet.current_id = path[0]
        return packet

    # ── Multi-hop journey ──
    # Step 1: At the origin, encode payload for the NEXT hop's codex
    # The origin's routing hop tells us what base the NEXT planet expects
    # But per the spec, we encode into the NEXT HOP's codex before transmitting
    if len(hop_details) > 0:
        # The first hop_detail's codex_base is the origin planet's codex
        # We need to encode to the NEXT planet's codex for transmission
        next_planet_id = path[1]
        next_planet = planets[next_planet_id]
        current_encoded = ascii_to_codex(payload, next_planet.codex)
        current_base = next_planet.codex
    else:
        current_encoded = ascii_to_codex(payload, origin_planet.codex)
        current_base = origin_planet.codex

    packet.encoded_payload = list(current_encoded)
    packet.current_codex = current_base

    # Step 2: Process each transit hop (origin → ... → last relay before destination)
    for i, hop in enumerate(hop_details):
        current_planet_id = hop["planet_id"]
        packet.current_id = current_planet_id

        # The payload_in_codex at this hop is what was encoded for this planet's
        # reception (the current codex). For the origin, it's encoded into
        # the next hop's codex (since origin sends to next).
        if i == 0:
            # Origin planet: show encoding into next hop's codex
            hop_codex_values = list(current_encoded)
            hop_codex_base = current_base
        else:
            # Relay planet: payload was re-encoded into this next hop's codex
            hop_codex_values = list(current_encoded)
            hop_codex_base = current_base

        # Build the enriched hop_log entry (FIX #2: adds payload_in_codex)
        enriched_hop = build_hop_log_entry(
            routing_hop=hop,
            payload_in_codex=hop_codex_values,
            codex_base=hop_codex_base
        )
        packet.hop_log.append(enriched_hop)

        # Re-encode for the next hop (if there is one)
        if i < len(hop_details) - 1:
            # Next planet in the path
            next_planet_id = path[i + 2]
            next_planet = planets[next_planet_id]
            # Translate: current base → next planet's codex
            current_encoded = translate_payload(current_encoded, current_base, next_planet.codex)
            current_base = next_planet.codex
            packet.encoded_payload = list(current_encoded)
            packet.current_codex = current_base

    # Step 3: At the destination, decode back to ASCII
    dest_planet = planets[path[-1]]

    # Final encoding at destination: translate into destination's codex
    final_encoded = translate_payload(current_encoded, current_base, dest_planet.codex)

    # Verify round-trip integrity
    decoded_payload = codex_to_ascii(final_encoded, dest_planet.codex)
    if decoded_payload != payload:
        raise RuntimeError(
            f"Codec integrity check FAILED! "
            f"Original: '{payload}', Decoded: '{decoded_payload}'"
        )

    # Build the destination planet's hop_log entry (FIX #1)
    # Determine the entry tower at the destination
    if hop_details:
        dest_entry_tower = hop_details[-1].get("next_hop_entry_tower", 0)
    else:
        dest_entry_tower = 0

    dest_hop = build_destination_hop_entry(
        dest_planet,
        entry_tower=dest_entry_tower,
        payload_in_codex=final_encoded,
        tower_delay_ms=metadata.tower_processing_delay_ms
    )
    packet.hop_log.append(dest_hop)

    # Update packet final state
    packet.encoded_payload = final_encoded
    packet.current_codex = dest_planet.codex
    packet.current_id = dest_planet.id

    return packet


# ──────────────────────────────────────────────────────────────────
# Section 6: Utility Functions
# ──────────────────────────────────────────────────────────────────

def get_journey_summary(packet: Packet) -> str:
    """
    Returns a human-readable summary of a packet's journey,
    useful for terminal output and demo narration.
    """
    lines = []
    lines.append(f"+== PACKET JOURNEY: {packet.origin_id} -> {packet.destination_id} ==+")
    lines.append(f"| Payload: \"{packet.payload}\"")
    lines.append(f"| Hops: {len(packet.hop_log)}")
    lines.append(f"+== HOP LOG ==+")

    for i, hop in enumerate(packet.hop_log):
        planet_id = hop["planet_id"]
        codex_base = hop["codex_base"]
        entry_t = hop["entry_tower"]
        exit_t = hop["exit_tower"]
        payload_preview = hop.get("payload_in_codex", [])[:3]
        preview_str = ", ".join(payload_preview)
        if len(hop.get("payload_in_codex", [])) > 3:
            preview_str += ", ..."

        is_dest = (hop["void_distance_km"] == 0.0 and hop["void_time_s"] == 0.0
                   and i == len(packet.hop_log) - 1)
        marker = " [DESTINATION]" if is_dest else ""

        lines.append(
            f"| [{i}] {planet_id:10s} | T{entry_t}->T{exit_t} | "
            f"Base {codex_base:2d}: [{preview_str}]{marker}"
        )

    lines.append(f"+== RESULT ==+")
    lines.append(f"| Final decoded: \"{codex_to_ascii(packet.encoded_payload, packet.current_codex)}\"")
    lines.append(f"+{'=' * 60}+")

    return "\n".join(lines)


if __name__ == "__main__":
    # Quick standalone test matching the challenge spec example
    print("=== Packet Codec Self-Test ===\n")

    # Test 1: Base conversion
    assert int_to_base_n(72, 5) == "242", f"Expected '242', got '{int_to_base_n(72, 5)}'"
    assert int_to_base_n(72, 14) == "52", f"Expected '52', got '{int_to_base_n(72, 14)}'"
    assert base_n_to_int("242", 5) == 72
    assert base_n_to_int("52", 14) == 72
    print("[PASS] Base conversion")

    # Test 2: ASCII ↔ Codex round-trip
    text = "Hello world"
    for base in [5, 6, 8, 10, 14, 16]:
        encoded = ascii_to_codex(text, base)
        decoded = codex_to_ascii(encoded, base)
        assert decoded == text, f"Round-trip failed for base {base}"
    print("[PASS] Round-trip (all codexes)")

    # Test 3: Spec example validation
    encoded_b5 = ascii_to_codex("Hello world", 5)
    expected_b5 = ["242", "401", "413", "413", "421", "112", "434", "421", "424", "413", "400"]
    assert encoded_b5 == expected_b5, f"Base 5 mismatch:\n  Got:      {encoded_b5}\n  Expected: {expected_b5}"
    print("[PASS] Spec example (Base 5)")

    encoded_b14 = ascii_to_codex("Hello world", 14)
    expected_b14 = ["52", "73", "7A", "7A", "7D", "24", "87", "7D", "82", "7A", "72"]
    assert encoded_b14 == expected_b14, f"Base 14 mismatch:\n  Got:      {encoded_b14}\n  Expected: {expected_b14}"
    print("[PASS] Spec example (Base 14)")

    # Test 4: Translate payload across bases
    translated = translate_payload(encoded_b5, 5, 14)
    assert translated == expected_b14, f"Translation B5->B14 failed:\n  Got:      {translated}\n  Expected: {expected_b14}"
    print("[PASS] Translate Base 5 -> Base 14")

    print("\nAll self-tests passed!")
