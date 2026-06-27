"""
visualizer.py - Relic Ring Protocol Interactive Visualizer
==========================================================
Member 3 Deliverable: Pygame-based Industrial Skeuomorphism UI
for the demo video showcasing M1-M4 milestones.

Design System: Industrial Skeuomorphism (Neumorphic Control Panel)
Resolution: 1400x900 (with auto-scaling for smaller screens)
"""

import sys
import os
import math
import time as time_module

# Add src to path for imports
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import pygame
from pygame import gfxdraw

from config_parser import Planet, UniverseMetadata, load_universe_config
from graph_builder import build_network_graph, NetworkGraph
from routing_engine import find_route, RouteResult
from resilience_engine import ResilienceManager
from packet_codec import (
    Packet, simulate_packet_journey, ascii_to_codex,
    codex_to_ascii, get_journey_summary, TransmissionStatus
)


# ══════════════════════════════════════════════════════════════════
# Design System Tokens
# ══════════════════════════════════════════════════════════════════

# Industrial Skeuomorphism Color Palette
COLORS = {
    'chassis':       (224, 229, 236),
    'panel':         (240, 242, 245),
    'teal_panel':    (210, 235, 230),
    'recessed':      (209, 217, 230),
    'text_primary':  (45, 52, 54),
    'text_muted':    (74, 85, 104),
    'accent':        (255, 71, 87),
    'accent_hover':  (255, 100, 110),
    'accent_fg':     (255, 255, 255),
    'shadow_dark':   (186, 190, 204),
    'shadow_light':  (255, 255, 255),
    'shadow_deep':   (163, 177, 198),
    'led_green':     (34, 197, 94),
    'led_red':       (239, 68, 68),
    'led_yellow':    (234, 179, 8),
    'header_bg':     (45, 52, 54),
    'header_text':   (224, 229, 236),
    'grid_line':     (60, 70, 80),
    'grid_bg':       (35, 45, 55),
    'route_active':  (255, 71, 87),
    'route_idle':    (100, 120, 140),
    'planet_body':   (70, 90, 110),
    'planet_ring':   (45, 52, 54),
    'planet_hover':  (90, 110, 130),
    'tower_dot':     (255, 200, 50),
    'packet_glow':   (255, 165, 0),
    'bar_fiber':     (52, 152, 219),
    'bar_tower':     (241, 196, 15),
    'bar_atmos':     (26, 188, 156),
    'bar_void':      (255, 71, 87),
    'dropdown_bg':   (200, 208, 220),
    'button_dark':   (60, 68, 80),
    'button_dark_fg':(224, 229, 236),
    'dead_node':     (180, 60, 60),
    'control_bg':    (55, 63, 75),
}

# Layout Constants (designed for 1700x950, scaled proportionally)
BASE_W, BASE_H = 1700, 950
HEADER_H = 50
CONTROL_H = 60
MAP_W_RATIO = 0.52  # Left panel takes 52% width
PANEL_PAD = 12
CARD_RADIUS = 12
SCREW_SIZE = 4
SHADOW_OFFSET = 4

# Font sizes (Enlarged for High-DPI/Legibility)
FONT_SIZES = {
    'header_title': 28,
    'header_sub': 16,
    'card_title': 18,
    'body': 16,
    'mono': 15,
    'mono_small': 14,
    'button': 18,
    'planet_label': 14,
    'led_label': 13,
}


# ══════════════════════════════════════════════════════════════════
# Neumorphic Drawing Primitives
# ══════════════════════════════════════════════════════════════════

def draw_neumorphic_rect(surface, rect, color, raised=True, radius=12, shadow_offset=4):
    """Draw a rectangle with dual-shadow neumorphic effect."""
    x, y, w, h = rect
    if raised:
        # Light shadow (top-left)
        pygame.draw.rect(surface, COLORS['shadow_light'],
                         (x - shadow_offset, y - shadow_offset, w, h), border_radius=radius)
        # Dark shadow (bottom-right)
        pygame.draw.rect(surface, COLORS['shadow_dark'],
                         (x + shadow_offset, y + shadow_offset, w, h), border_radius=radius)
    else:
        # Inset: dark top-left, light bottom-right
        pygame.draw.rect(surface, COLORS['shadow_dark'],
                         (x - shadow_offset // 2, y - shadow_offset // 2, w, h), border_radius=radius)
        pygame.draw.rect(surface, COLORS['shadow_light'],
                         (x + shadow_offset // 2, y + shadow_offset // 2, w, h), border_radius=radius)
    # Main surface
    pygame.draw.rect(surface, color, (x, y, w, h), border_radius=radius)


def draw_screw_head(surface, cx, cy, size=4):
    """Draw a small Phillips screw head at the given position."""
    # Outer circle
    pygame.draw.circle(surface, COLORS['shadow_dark'], (cx, cy), size)
    pygame.draw.circle(surface, (195, 200, 210), (cx, cy), size - 1)
    # Cross slot
    pygame.draw.line(surface, COLORS['shadow_deep'], (cx - 2, cy), (cx + 2, cy), 1)
    pygame.draw.line(surface, COLORS['shadow_deep'], (cx, cy - 2), (cx, cy + 2), 1)


def draw_card_with_screws(surface, rect, color=None, title=None, title_font=None):
    """Draw a neumorphic card panel with corner screws and optional title."""
    if color is None:
        color = COLORS['panel']
    x, y, w, h = rect
    draw_neumorphic_rect(surface, rect, color, raised=True, radius=CARD_RADIUS)

    # Corner screws
    inset = 10
    draw_screw_head(surface, x + inset, y + inset)
    draw_screw_head(surface, x + w - inset, y + inset)
    draw_screw_head(surface, x + inset, y + h - inset)
    draw_screw_head(surface, x + w - inset, y + h - inset)

    # Title bar
    if title and title_font:
        title_surf = title_font.render(title, True, COLORS['text_muted'])
        surface.blit(title_surf, (x + 22, y + 8))


def draw_led(surface, cx, cy, color, pulsing=False, tick=0):
    """Draw a glowing LED indicator."""
    if pulsing:
        alpha = int(128 + 127 * math.sin(tick * 0.05))
        glow_color = (*color[:3], max(30, min(alpha, 200)))
    else:
        glow_color = color

    # Outer glow
    glow_surf = pygame.Surface((20, 20), pygame.SRCALPHA)
    pygame.draw.circle(glow_surf, (*glow_color[:3], 40), (10, 10), 8)
    pygame.draw.circle(glow_surf, (*glow_color[:3], 80), (10, 10), 5)
    surface.blit(glow_surf, (cx - 10, cy - 10))
    # Core
    pygame.draw.circle(surface, glow_color[:3], (cx, cy), 4)
    pygame.draw.circle(surface, (255, 255, 255), (cx - 1, cy - 1), 1)


# ══════════════════════════════════════════════════════════════════
# Interactive UI Elements
# ══════════════════════════════════════════════════════════════════

class NeuButton:
    """Neumorphic button with press animation."""
    def __init__(self, rect, label, color=None, fg_color=None, font=None):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.color = color or COLORS['accent']
        self.fg_color = fg_color or COLORS['accent_fg']
        self.font = font
        self.pressed = False
        self.hover = False

    def draw(self, surface):
        r = self.rect
        offset = 2 if self.pressed else 0
        draw_rect = (r.x + offset, r.y + offset, r.w, r.h)

        if not self.pressed:
            draw_neumorphic_rect(surface, (r.x, r.y, r.w, r.h),
                                 self.color, raised=True, radius=8, shadow_offset=3)
        else:
            draw_neumorphic_rect(surface, draw_rect,
                                 self.color, raised=False, radius=8, shadow_offset=2)

        if self.font:
            txt = self.font.render(self.label, True, self.fg_color)
            tx = r.x + offset + (r.w - txt.get_width()) // 2
            ty = r.y + offset + (r.h - txt.get_height()) // 2
            surface.blit(txt, (tx, ty))

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.pressed = True
                return True
        elif event.type == pygame.MOUSEBUTTONUP:
            self.pressed = False
        elif event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        return False


class DropdownSelect:
    """Neumorphic recessed dropdown selector — opens UPWARD."""
    def __init__(self, rect, options, selected_idx=0, font=None):
        self.rect = pygame.Rect(rect)
        self.options = options
        self.selected_idx = selected_idx
        self.font = font
        self.open = False

    @property
    def value(self):
        return self.options[self.selected_idx]

    def _get_menu_rects(self):
        """Calculate menu item rects (opening upward)."""
        r = self.rect
        rects = []
        n = len(self.options)
        for i in range(n):
            # Items stack upward: item 0 is closest to the button (just above it)
            item_y = r.y - (i + 1) * r.h - 2
            rects.append(pygame.Rect(r.x, item_y, r.w, r.h))
        return rects

    def draw(self, surface):
        r = self.rect
        # Recessed background
        draw_neumorphic_rect(surface, (r.x, r.y, r.w, r.h),
                             COLORS['recessed'], raised=False, radius=6, shadow_offset=2)

        if self.font:
            txt = self.font.render(self.value, True, COLORS['text_primary'])
            surface.blit(txt, (r.x + 8, r.y + (r.h - txt.get_height()) // 2))
            # Arrow (pointing up when open)
            arrow_char = "^" if self.open else "v"
            arrow = self.font.render(arrow_char, True, COLORS['text_muted'])
            surface.blit(arrow, (r.x + r.w - 18, r.y + (r.h - arrow.get_height()) // 2))

        # Dropdown menu (opens UPWARD)
        if self.open:
            menu_rects = self._get_menu_rects()
            # Draw background panel behind all items
            if menu_rects:
                top_y = menu_rects[-1].y - 4
                panel_h = r.y - top_y
                pygame.draw.rect(surface, COLORS['panel'],
                                 (r.x - 2, top_y, r.w + 4, panel_h),
                                 border_radius=6)
                pygame.draw.rect(surface, COLORS['shadow_dark'],
                                 (r.x - 2, top_y, r.w + 4, panel_h),
                                 1, border_radius=6)

            for i, item_rect in enumerate(menu_rects):
                bg = COLORS['accent'] if i == self.selected_idx else COLORS['panel']
                fg = COLORS['accent_fg'] if i == self.selected_idx else COLORS['text_primary']
                pygame.draw.rect(surface, bg, item_rect, border_radius=4)
                if self.font:
                    txt = self.font.render(self.options[i], True, fg)
                    surface.blit(txt, (item_rect.x + 8,
                                       item_rect.y + (item_rect.h - txt.get_height()) // 2))

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.open = not self.open
                return False
            elif self.open:
                menu_rects = self._get_menu_rects()
                for i, item_rect in enumerate(menu_rects):
                    if item_rect.collidepoint(event.pos):
                        self.selected_idx = i
                        self.open = False
                        return True
                self.open = False
        return False


class TextInput:
    """Neumorphic recessed text input field."""
    def __init__(self, rect, default_text="Hello world", font=None):
        self.rect = pygame.Rect(rect)
        self.text = default_text
        self.font = font
        self.active = False
        self.cursor_visible = True
        self.cursor_timer = 0

    def draw(self, surface, tick=0):
        r = self.rect
        border_color = COLORS['accent'] if self.active else COLORS['shadow_dark']
        draw_neumorphic_rect(surface, (r.x, r.y, r.w, r.h),
                             COLORS['recessed'], raised=False, radius=6, shadow_offset=2)
        pygame.draw.rect(surface, border_color, (r.x, r.y, r.w, r.h), 1, border_radius=6)

        if self.font:
            display_text = self.text
            txt = self.font.render(display_text, True, COLORS['text_primary'])
            surface.blit(txt, (r.x + 8, r.y + (r.h - txt.get_height()) // 2))

            # Blinking cursor
            if self.active and (tick // 30) % 2 == 0:
                cx = r.x + 8 + txt.get_width() + 2
                cy = r.y + 6
                pygame.draw.line(surface, COLORS['text_primary'], (cx, cy), (cx, cy + r.h - 12), 1)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
        elif event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key == pygame.K_RETURN:
                self.active = False
                return True
            elif event.key == pygame.K_ESCAPE:
                self.active = False
            elif len(event.unicode) > 0 and 32 <= ord(event.unicode) <= 126:
                self.text += event.unicode
        return False


# ══════════════════════════════════════════════════════════════════
# Main Visualizer Class
# ══════════════════════════════════════════════════════════════════

class RelicRingVisualizer:
    """
    Interactive Pygame-based visualizer for the Relic Ring Protocol.
    Implements the Industrial Skeuomorphism design system.
    """

    def __init__(self, config_path: str):
        self.config_path = config_path

        # Auto-scale for screen
        pygame.init()
        info = pygame.display.Info()
        screen_w, screen_h = info.current_w, info.current_h

        # Clamp to screen with margins
        self.win_w = min(BASE_W, screen_w - 80)
        self.win_h = min(BASE_H, screen_h - 80)
        
        # Compute scale factor
        self.scale = min(self.win_w / BASE_W, self.win_h / BASE_H)

        self.screen = pygame.display.set_mode((self.win_w, self.win_h), pygame.RESIZABLE)
        pygame.display.set_caption("RELIC RING PROTOCOL  -  Zeta-26 Star System")

        # Fonts
        self._init_fonts()

        # Layout regions
        self._calculate_layout()

        # State
        self.current_route = None
        self.current_packet = None
        self.kill_mode = False
        self.hovered_planet = None
        self.tick = 0

        # Animation state
        self.anim_active = False
        self.anim_progress = 0.0
        self.anim_speed = 0.008   # per tick (about 3s per hop at 60fps)
        self.anim_path_coords = []
        
        self.judge_mode = False
        self.judge_step = 0
        self.transmission_status = TransmissionStatus.READY
        self.packet_counter = 0
        
        # Toasts
        self.toasts = []
        
        self.clock = pygame.time.Clock()

        # M1: Execute Real Boot Sequence
        self._run_boot_sequence()

        # Planet screen positions
        self._calculate_planet_positions()

        # UI Elements
        self._init_ui_elements()

    def _draw_boot_frame(self, title: str, messages: list):
        self.screen.fill(COLORS['chassis'])
        
        # Center coordinates
        cx, cy = self.win_w // 2, self.win_h // 2
        
        # Title
        title_surf = self.font_title.render("RELIC RING PROTOCOL", True, COLORS['accent'])
        self.screen.blit(title_surf, (cx - title_surf.get_width() // 2, cy - 100))
        
        sub_surf = self.font_sub.render(title, True, COLORS['text_muted'])
        self.screen.blit(sub_surf, (cx - sub_surf.get_width() // 2, cy - 60))
        
        # Messages
        for i, msg in enumerate(messages):
            msg_surf = self.font_mono.render(msg, True, COLORS['text_primary'])
            self.screen.blit(msg_surf, (cx - 150, cy + i * 25))
            
        pygame.display.flip()

    def _run_boot_sequence(self):
        messages = []
        self._draw_boot_frame("Initializing Zeta-26 Star System...", messages)
        time_module.sleep(0.5)
        
        # Step 1: Read JSON
        messages.append("Loading universe-config.json...")
        self._draw_boot_frame("Reading metadata", messages)
        self.metadata, self.planets_list = load_universe_config(self.config_path)
        self.planets = {p.id: p for p in self.planets_list}
        time_module.sleep(0.5)
        
        messages[-1] = f"[OK] Metadata loaded: {self.metadata.system_name}"
        messages.append(f"Creating {len(self.planets_list)} planets...")
        self._draw_boot_frame("Constructing celestial bodies", messages)
        time_module.sleep(0.5)
        
        # Step 2: Build Graph
        messages[-1] = f"[OK] {len(self.planets_list)} planet objects initialized"
        messages.append("Building network graph...")
        self._draw_boot_frame("Mapping hyperspace topology", messages)
        self.graph = build_network_graph(self.metadata, self.planets_list)
        edges = sum(len(e) for e in self.graph.adjacency.values())
        time_module.sleep(0.5)
        
        # Step 3: Load Resilience Engine
        messages[-1] = f"[OK] Network graph built with {edges} directed edges"
        messages.append("Loading Resilience Engine...")
        self._draw_boot_frame("Initializing routing algorithms", messages)
        self.resilience = ResilienceManager(self.metadata, self.planets_list)
        time_module.sleep(0.5)
        
        messages[-1] = "[OK] Resilience Engine active"
        messages.append("System Ready.")
        self._draw_boot_frame("All systems nominal", messages)
        time_module.sleep(1.0)

    def _init_fonts(self):
        """Initialize fonts - use system monospace."""
        s = self.scale
        try:
            self.font_title = pygame.font.SysFont("Consolas", int(FONT_SIZES['header_title'] * s), bold=True)
            self.font_sub = pygame.font.SysFont("Consolas", int(FONT_SIZES['header_sub'] * s))
            self.font_card_title = pygame.font.SysFont("Consolas", int(FONT_SIZES['card_title'] * s), bold=True)
            self.font_body = pygame.font.SysFont("Consolas", int(FONT_SIZES['body'] * s))
            self.font_mono = pygame.font.SysFont("Consolas", int(FONT_SIZES['mono'] * s))
            self.font_mono_sm = pygame.font.SysFont("Consolas", int(FONT_SIZES['mono_small'] * s))
            self.font_btn = pygame.font.SysFont("Consolas", int(FONT_SIZES['button'] * s), bold=True)
            self.font_planet = pygame.font.SysFont("Consolas", int(FONT_SIZES['planet_label'] * s), bold=True)
            self.font_led = pygame.font.SysFont("Consolas", int(FONT_SIZES['led_label'] * s))
        except Exception:
            # Fallback to default
            self.font_title = pygame.font.Font(None, int(22 * s))
            self.font_sub = pygame.font.Font(None, int(16 * s))
            self.font_card_title = pygame.font.Font(None, int(16 * s))
            self.font_body = pygame.font.Font(None, int(14 * s))
            self.font_mono = pygame.font.Font(None, int(14 * s))
            self.font_mono_sm = pygame.font.Font(None, int(13 * s))
            self.font_btn = pygame.font.Font(None, int(16 * s))
            self.font_planet = pygame.font.Font(None, int(13 * s))
            self.font_led = pygame.font.Font(None, int(12 * s))

    def _calculate_layout(self):
        """Calculate layout regions based on window size."""
        s = self.scale
        hdr_h = int(HEADER_H * s)
        ctrl_h = int(CONTROL_H * s)
        pad = int(PANEL_PAD * s)

        self.header_rect = (0, 0, self.win_w, hdr_h)

        body_top = hdr_h
        body_h = self.win_h - hdr_h - ctrl_h

        map_w = int(self.win_w * MAP_W_RATIO)
        self.map_rect = (pad, body_top + pad, map_w - 2 * pad, body_h - 2 * pad)

        panel_x = map_w
        panel_w = self.win_w - map_w - 2 * pad
        
        # 5 panels layout
        # Row 1 (top): Packet Status (left 50%), Universe Meta (right 50%) - 20% height
        row1_h = int((body_h - 5 * pad) * 0.20)
        half_w = (panel_w - pad) // 2
        
        self.packet_status_rect = (panel_x, body_top + pad, half_w, row1_h)
        self.universe_meta_rect = (panel_x + half_w + pad, body_top + pad, half_w, row1_h)
        
        # Row 2: Hop log - 28% height
        row2_h = int((body_h - 5 * pad) * 0.28)
        self.hop_panel_rect = (panel_x, body_top + 2 * pad + row1_h, panel_w, row2_h)
        
        # Row 3: Latency - 28% height
        row3_h = int((body_h - 5 * pad) * 0.28)
        self.latency_panel_rect = (panel_x, body_top + 3 * pad + row1_h + row2_h, panel_w, row3_h)
        
        # Row 4: Codec - Remaining height
        row4_h = body_h - 5 * pad - row1_h - row2_h - row3_h
        self.codec_panel_rect = (panel_x, body_top + 4 * pad + row1_h + row2_h + row3_h, panel_w, row4_h)

        self.control_rect = (0, self.win_h - ctrl_h, self.win_w, ctrl_h)

    def _calculate_planet_positions(self):
        """Map planet (x,y) coordinates to screen space."""
        # Find bounding box of planet coords
        xs = [p.x for p in self.planets.values()]
        ys = [p.y for p in self.planets.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        # Add margins
        margin = 60 * self.scale
        mx, my, mw, mh = self.map_rect
        usable_x = mw - 2 * margin
        usable_y = mh - 2 * margin

        range_x = max(max_x - min_x, 1)
        range_y = max(max_y - min_y, 1)

        self.planet_screen_pos = {}
        for pid, planet in self.planets.items():
            sx = mx + margin + ((planet.x - min_x) / range_x) * usable_x
            sy = my + margin + ((planet.y - min_y) / range_y) * usable_y
            self.planet_screen_pos[pid] = (int(sx), int(sy))

    def _init_ui_elements(self):
        """Initialize interactive UI elements."""
        s = self.scale
        cx, cy, cw, ch = self.control_rect

        planet_names = list(self.planets.keys())

        # Layout: LABEL  [SRC ▼]   LABEL  [DST ▼]   [PAYLOAD INPUT]   [SEND]  [KILL]  [REVIVE]
        element_y = cy + int(12 * s)
        element_h = int(32 * s)
        x_cursor = int(15 * s)

        # Source dropdown
        self.src_dropdown = DropdownSelect(
            (x_cursor, element_y, int(110 * s), element_h),
            planet_names, selected_idx=0, font=self.font_body
        )
        x_cursor += int(120 * s)

        # Destination dropdown
        self.dst_dropdown = DropdownSelect(
            (x_cursor, element_y, int(110 * s), element_h),
            planet_names, selected_idx=len(planet_names) - 1, font=self.font_body
        )
        x_cursor += int(120 * s)

        # Payload text input
        self.payload_input = TextInput(
            (x_cursor, element_y, int(200 * s), element_h),
            default_text="Hello world", font=self.font_mono
        )
        x_cursor += int(210 * s)

        # Send button
        self.send_btn = NeuButton(
            (x_cursor, element_y, int(160 * s), element_h),
            "SEND PACKET", color=COLORS['accent'], font=self.font_btn
        )
        x_cursor += int(170 * s)

        # Kill Node button
        self.kill_btn = NeuButton(
            (x_cursor, element_y, int(140 * s), element_h),
            "KILL NODE", color=COLORS['button_dark'],
            fg_color=COLORS['led_red'], font=self.font_btn
        )
        x_cursor += int(150 * s)

        # Revive All button
        self.revive_btn = NeuButton(
            (x_cursor, element_y, int(150 * s), element_h),
            "REVIVE ALL", color=COLORS['button_dark'],
            fg_color=COLORS['led_green'], font=self.font_btn
        )
        x_cursor += int(160 * s)
        
        # Judge Mode button
        self.judge_btn = NeuButton(
            (x_cursor, element_y, int(150 * s), element_h),
            "JUDGE MODE", color=COLORS['button_dark'],
            fg_color=COLORS['button_dark_fg'], font=self.font_btn
        )

    # ──────────────────────────────────────────────────────────────
    # Drawing Methods
    # ──────────────────────────────────────────────────────────────

    def _draw_header(self):
        """Draw the dark header strip with title and status LEDs."""
        x, y, w, h = self.header_rect
        pygame.draw.rect(self.screen, COLORS['header_bg'], (x, y, w, h))

        # Title
        title = self.font_title.render("RELIC RING PROTOCOL", True, COLORS['header_text'])
        self.screen.blit(title, (int(15 * self.scale), y + (h - title.get_height()) // 2))

        # System name
        sys_name = self.font_sub.render(f"// {self.metadata.system_name}", True, COLORS['text_muted'])
        self.screen.blit(sys_name, (int(300 * self.scale), y + (h - sys_name.get_height()) // 2))

        # Status LEDs
        status = self.resilience.get_network_status()
        active_count = len(status.get("active_nodes", []))
        dead_count = status.get("dead_nodes_count", len(status.get("dead_nodes", [])))

        led_x = int(self.win_w - 350 * self.scale)
        led_y = y + h // 2

        # System LED
        sys_color = COLORS['led_green'] if dead_count == 0 else COLORS['led_yellow']
        draw_led(self.screen, led_x, led_y, sys_color, pulsing=True, tick=self.tick)
        label = self.font_led.render("SYS ONLINE" if dead_count == 0 else "DEGRADED", True, COLORS['header_text'])
        self.screen.blit(label, (led_x + 10, led_y - label.get_height() // 2))

        # Node count
        led_x2 = led_x + int(130 * self.scale)
        node_txt = self.font_led.render(f"NODES: {active_count}/{len(self.planets)}", True, COLORS['header_text'])
        self.screen.blit(node_txt, (led_x2, led_y - node_txt.get_height() // 2))

        # Kill mode indicator
        if self.kill_mode:
            led_x3 = led_x2 + int(130 * self.scale)
            draw_led(self.screen, led_x3, led_y, COLORS['led_red'], pulsing=True, tick=self.tick)
            km_txt = self.font_led.render("KILL MODE", True, COLORS['led_red'])
            self.screen.blit(km_txt, (led_x3 + 10, led_y - km_txt.get_height() // 2))

    def _draw_star_map(self):
        """Draw the universe star map with planets, edges, and animation."""
        mx, my, mw, mh = self.map_rect

        # Blueprint grid background
        pygame.draw.rect(self.screen, COLORS['grid_bg'], (mx, my, mw, mh), border_radius=8)

        # Grid lines
        grid_spacing = int(40 * self.scale)
        for gx in range(mx, mx + mw, grid_spacing):
            pygame.draw.line(self.screen, COLORS['grid_line'], (gx, my), (gx, my + mh), 1)
        for gy in range(my, my + mh, grid_spacing):
            pygame.draw.line(self.screen, COLORS['grid_line'], (mx, gy), (mx + mw, gy), 1)

        # Border
        pygame.draw.rect(self.screen, COLORS['shadow_deep'], (mx, my, mw, mh), 2, border_radius=8)

        # Draw edges
        self._draw_edges()

        # Draw planets
        mouse_pos = pygame.mouse.get_pos()
        self.hovered_planet = None
        for pid, pos in self.planet_screen_pos.items():
            planet = self.planets[pid]
            is_active = planet.is_active
            dist = math.hypot(mouse_pos[0] - pos[0], mouse_pos[1] - pos[1])
            is_hovered = dist < 30 * self.scale
            if is_hovered:
                self.hovered_planet = pid
            self._draw_planet_node(planet, pos, is_active, is_hovered)

        # Draw packet animation
        if self.anim_active and self.anim_path_coords:
            self._draw_packet_animation()

        # Map title overlay
        map_title = self.font_card_title.render("UNIVERSE STAR MAP", True, (150, 160, 170))
        self.screen.blit(map_title, (mx + 10, my + 6))
        
        # Draw Tooltip overlay if hovering is handled at the end of the render loop

    def _draw_edges(self):
        """Draw route edges between connected planets."""
        drawn = set()
        active_path = set()
        if self.current_route and self.current_route.is_reachable:
            path = self.current_route.path
            for i in range(len(path) - 1):
                active_path.add((path[i], path[i + 1]))
                active_path.add((path[i + 1], path[i]))

        for pid in self.graph.adjacency:
            for edge in self.graph.adjacency[pid]:
                pair = tuple(sorted([edge.source_id, edge.dest_id]))
                if pair in drawn:
                    continue
                drawn.add(pair)

                p1 = self.planet_screen_pos.get(edge.source_id)
                p2 = self.planet_screen_pos.get(edge.dest_id)
                if not p1 or not p2:
                    continue

                src_active = self.planets[edge.source_id].is_active
                dst_active = self.planets[edge.dest_id].is_active

                if not src_active or not dst_active:
                    # Dead edge - dashed
                    self._draw_dashed_line(self.screen, COLORS['led_red'], p1, p2, dash_len=8)
                elif (edge.source_id, edge.dest_id) in active_path:
                    # Active route - glowing
                    pygame.draw.line(self.screen, (*COLORS['route_active'], 80), p1, p2, 4)
                    pygame.draw.line(self.screen, COLORS['route_active'], p1, p2, 2)
                else:
                    # Idle route
                    pygame.draw.line(self.screen, COLORS['route_idle'], p1, p2, 1)

    def _draw_dashed_line(self, surface, color, p1, p2, dash_len=8):
        """Draw a dashed line between two points."""
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        dist = max(math.hypot(dx, dy), 1)
        num_dashes = int(dist / dash_len)
        for i in range(0, num_dashes, 2):
            t1 = i / num_dashes
            t2 = min((i + 1) / num_dashes, 1.0)
            x1 = int(p1[0] + dx * t1)
            y1 = int(p1[1] + dy * t1)
            x2 = int(p1[0] + dx * t2)
            y2 = int(p1[1] + dy * t2)
            pygame.draw.line(surface, color, (x1, y1), (x2, y2), 1)

    def _draw_planet_node(self, planet, pos, is_active, is_hovered):
        """Draw a planet with atmospheric ring, tower dots, label, and LED."""
        s = self.scale
        cx, cy = pos
        base_radius = int(22 * s)
        atm_radius = int(28 * s)

        # Atmospheric ring (semi-transparent)
        atm_surf = pygame.Surface((atm_radius * 2 + 4, atm_radius * 2 + 4), pygame.SRCALPHA)
        atm_color = (100, 140, 180, 40) if is_active else (180, 60, 60, 40)
        pygame.draw.circle(atm_surf, atm_color, (atm_radius + 2, atm_radius + 2), atm_radius)
        self.screen.blit(atm_surf, (cx - atm_radius - 2, cy - atm_radius - 2))

        # Planet body
        body_color = COLORS['planet_hover'] if is_hovered else (COLORS['planet_body'] if is_active else COLORS['dead_node'])
        pygame.draw.circle(self.screen, body_color, (cx, cy), base_radius)
        pygame.draw.circle(self.screen, COLORS['planet_ring'], (cx, cy), base_radius, 2)

        # Tower dots
        n_towers = planet.active_towers
        tower_radius = base_radius + int(6 * s)
        
        used_towers = set()
        if self.current_packet and self.current_packet.hop_log:
            for hop in self.current_packet.hop_log:
                if hop['planet_id'] == planet.id:
                    used_towers.add(hop['entry_tower'])
                    used_towers.add(hop['exit_tower'])
                    
        for i in range(n_towers):
            tower_id = i + 1
            angle = (2 * math.pi * i / n_towers) - math.pi / 2  # Start from top
            tx = int(cx + tower_radius * math.cos(angle))
            ty = int(cy + tower_radius * math.sin(angle))
            
            t_color = COLORS['accent'] if tower_id in used_towers else COLORS['tower_dot']
            t_rad = int(4 * s) if tower_id in used_towers else int(2.5 * s)
            pygame.draw.circle(self.screen, t_color, (tx, ty), t_rad)
            if tower_id in used_towers:
                pygame.draw.circle(self.screen, COLORS['packet_glow'], (tx, ty), t_rad + 2, 1)

        # Label
        label = self.font_planet.render(planet.id.upper(), True, (200, 210, 220))
        self.screen.blit(label, (cx - label.get_width() // 2, cy + base_radius + int(8 * s)))

        # Codex badge
        codex_txt = self.font_led.render(f"B{planet.codex}", True, COLORS['text_muted'])
        self.screen.blit(codex_txt, (cx - codex_txt.get_width() // 2, cy + base_radius + int(20 * s)))

        # Status LED
        led_color = COLORS['led_green'] if is_active else COLORS['led_red']
        draw_led(self.screen, cx + base_radius - 2, cy - base_radius + 2, led_color, pulsing=not is_active, tick=self.tick)

        # Kill mode crosshair
        if self.kill_mode and is_hovered and is_active:
            pygame.draw.circle(self.screen, COLORS['led_red'], (cx, cy), base_radius + 8, 2)
            pygame.draw.line(self.screen, COLORS['led_red'], (cx - 15, cy), (cx + 15, cy), 1)
            pygame.draw.line(self.screen, COLORS['led_red'], (cx, cy - 15), (cx, cy + 15), 1)

    def _draw_planet_tooltip(self, planet, mouse_pos):
        """Draws a tooltip with detailed planet info."""
        header_text = f"+---- {planet.id.upper()} ----+"
        status_text = "ACTIVE" if planet.is_active else "OFFLINE"
        
        lines = [
            header_text,
            f"Base: {planet.codex}",
            f"Radius: {planet.radius_km:,.0f} km",
            f"Atmosphere: {planet.atmosphere_thickness_km:,.0f} km",
            f"Refraction: {planet.refraction_index:.3f}",
            f"Towers: {planet.active_towers}",
            f"Coordinates: ({planet.x:,.0f}, {planet.y:,.0f})",
            f"Status: {status_text}"
        ]
        
        box_w = int(240 * self.scale)
        box_h = int(150 * self.scale)
        box_x = mouse_pos[0] + 15
        box_y = mouse_pos[1] + 15
        
        # Keep tooltip on screen
        if box_x + box_w > self.win_w: box_x = mouse_pos[0] - box_w - 15
        if box_y + box_h > self.win_h: box_y = mouse_pos[1] - box_h - 15
        
        # Tooltip BG
        pygame.draw.rect(self.screen, COLORS['control_bg'], (box_x, box_y, box_w, box_h), border_radius=6)
        pygame.draw.rect(self.screen, COLORS['shadow_deep'], (box_x, box_y, box_w, box_h), 1, border_radius=6)
        
        # Text
        ty = box_y + 12
        for line in lines:
            if line == header_text:
                color = COLORS['accent']
            elif line.startswith("Status:"):
                color = COLORS['led_green'] if planet.is_active else COLORS['led_red']
            else:
                color = COLORS['header_text']
                
            txt = self.font_mono_sm.render(line, True, color)
            self.screen.blit(txt, (box_x + 12, ty))
            ty += int(16 * self.scale)

    def _draw_packet_animation(self):
        """Draw the animated packet dot traveling along the route."""
        coords = self.anim_path_coords
        if not coords or len(coords) < 2:
            return

        total_segments = len(coords) - 1
        seg_progress = self.anim_progress * total_segments
        seg_idx = min(int(seg_progress), total_segments - 1)
        local_t = seg_progress - seg_idx

        # Ease-in-out
        t = local_t * local_t * (3 - 2 * local_t)

        x1, y1 = coords[seg_idx]
        x2, y2 = coords[seg_idx + 1]
        px = int(x1 + (x2 - x1) * t)
        py = int(y1 + (y2 - y1) * t)

        # Trail (fading dots)
        trail_count = 8
        for i in range(trail_count):
            trail_progress = max(0, self.anim_progress - i * 0.005)
            tp = trail_progress * total_segments
            ti = min(int(tp), total_segments - 1)
            tl = tp - ti
            tx = int(coords[ti][0] + (coords[min(ti + 1, total_segments)][0] - coords[ti][0]) * tl)
            ty = int(coords[ti][1] + (coords[min(ti + 1, total_segments)][1] - coords[ti][1]) * tl)
            alpha = max(20, 200 - i * 25)
            trail_surf = pygame.Surface((12, 12), pygame.SRCALPHA)
            pygame.draw.circle(trail_surf, (*COLORS['packet_glow'], alpha), (6, 6), max(2, 5 - i // 2))
            self.screen.blit(trail_surf, (tx - 6, ty - 6))

        # Main packet dot with glow
        glow_surf = pygame.Surface((40, 40), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (*COLORS['packet_glow'], 50), (20, 20), 16)
        pygame.draw.circle(glow_surf, (*COLORS['packet_glow'], 100), (20, 20), 10)
        pygame.draw.circle(glow_surf, (*COLORS['accent'], 200), (20, 20), 5)
        self.screen.blit(glow_surf, (px - 20, py - 20))

    def _draw_packet_status_panel(self):
        """Draw the TRANSMISSION STATUS panel."""
        draw_card_with_screws(self.screen, self.packet_status_rect,
                              title="TRANSMISSION STATUS", title_font=self.font_card_title)
        x, y, w, h = self.packet_status_rect
        
        src_id = self.src_dropdown.value
        dst_id = self.dst_dropdown.value
        src_active = self.planets[src_id].is_active
        dst_active = self.planets[dst_id].is_active
        
        src_color = COLORS['led_green'] if src_active else COLORS['led_red']
        src_icon = "✓" if src_active else "✖ Offline"
        dst_color = COLORS['led_green'] if dst_active else COLORS['led_red']
        dst_icon = "✓" if dst_active else "✖ Offline"
        
        self.screen.blit(self.font_mono_sm.render(f"Source:      {src_id} {src_icon}", True, src_color), (x + 22, y + 35))
        self.screen.blit(self.font_mono_sm.render(f"Destination: {dst_id} {dst_icon}", True, dst_color), (x + 22, y + 55))
        
        pkt = self.current_packet
        status_color = COLORS['text_muted']
        if not pkt:
            status_text = "Awaiting Transmission"
        else:
            status_text = pkt.status.value
            if pkt.status in (TransmissionStatus.BLOCKED, TransmissionStatus.ABORTED, TransmissionStatus.UNDELIVERABLE, TransmissionStatus.FAILED):
                status_color = COLORS['led_red']
                if not src_active:
                    status_text += " (Source Offline)"
                elif not dst_active:
                    status_text += " (Destination Offline)"
            elif pkt.status == TransmissionStatus.DELIVERED:
                status_color = COLORS['led_green']
            else:
                status_color = COLORS['accent']
                
        self.screen.blit(self.font_body.render(f"Status: {status_text}", True, status_color), (x + 22, y + 80))
        
        if pkt and pkt.status not in (TransmissionStatus.BLOCKED, TransmissionStatus.ABORTED):
            self.screen.blit(self.font_mono_sm.render(f"Packet ID: #{pkt.packet_id}", True, COLORS['text_muted']), (x + 22, y + 105))
            if self.current_route:
                self.screen.blit(self.font_mono_sm.render(f"Latency: {self.current_route.total_latency_s:.5f}s", True, COLORS['text_primary']), (x + 22, y + 125))

    def _draw_universe_meta_panel(self):
        """Draw the UNIVERSE METRICS panel."""
        draw_card_with_screws(self.screen, self.universe_meta_rect,
                              title="UNIVERSE METRICS", title_font=self.font_card_title)
        x, y, w, h = self.universe_meta_rect
        
        meta = self.metadata
        speed_txt = self.font_mono_sm.render(f"Light Speed: {meta.speed_of_light_kms:,.0f} km/s", True, COLORS['text_primary'])
        self.screen.blit(speed_txt, (x + 22, y + 35))
        
        lmax_txt = self.font_mono_sm.render(f"Max Void Hop (Lmax): {meta.max_void_hop_distance_km:,.0f} km", True, COLORS['text_primary'])
        self.screen.blit(lmax_txt, (x + 22, y + 55))
        
        fiber_txt = self.font_mono_sm.render(f"Fiber Speed: {meta.fiber_speed_fraction}c", True, COLORS['text_primary'])
        self.screen.blit(fiber_txt, (x + 22, y + 75))

    def _draw_hop_log_panel(self):
        """Draw the HOP LOG panel with a scrollable table."""
        draw_card_with_screws(self.screen, self.hop_panel_rect,
                              title="HOP LOG", title_font=self.font_card_title)
        x, y, w, h = self.hop_panel_rect

        if not self.current_packet or not self.current_packet.hop_log:
            empty = self.font_mono_sm.render("No route data. Send a packet.", True, COLORS['text_muted'])
            self.screen.blit(empty, (x + 22, y + 35))
            return

        # Table header
        headers = ["Planet", "Next", "TIn", "TOut", "Fiber", "Tower", "Atmos", "Void", "Total"]
        col_widths = [int(c * self.scale) for c in [70, 70, 40, 40, 70, 70, 70, 70, 80]]
        row_h = int(18 * self.scale)
        table_x = x + 22
        table_y = y + 30

        for i, hdr in enumerate(headers):
            col_x = table_x + sum(col_widths[:i])
            txt = self.font_mono_sm.render(hdr, True, COLORS['text_muted'])
            self.screen.blit(txt, (col_x, table_y))

        pygame.draw.line(self.screen, COLORS['shadow_dark'],
                         (table_x, table_y + row_h), (table_x + sum(col_widths), table_y + row_h), 1)

        # Table rows
        max_rows = (h - 55) // row_h
        for row_idx, hop in enumerate(self.current_packet.hop_log[:max_rows]):
            ry = table_y + row_h * (row_idx + 1) + 4
            is_dest = (hop["void_distance_km"] == 0 and row_idx == len(self.current_packet.hop_log) - 1)

            row_color = COLORS['text_primary']
            if is_dest:
                # Highlight destination
                pygame.draw.rect(self.screen, (*COLORS['accent'], 20),
                                 (table_x - 2, ry - 2, sum(col_widths) + 4, row_h), border_radius=3)
                row_color = COLORS['accent']
            
            hop_total = hop['fiber_time_s'] + hop['processing_time_s'] + hop.get('atmosphere_time_s', 0) + hop.get('pure_void_time_s', 0)
            
            values = [
                hop["planet_id"][:7],
                hop.get("next_hop", "---")[:7],
                f"T{hop['entry_tower']}",
                f"T{hop['exit_tower']}",
                f"{hop['fiber_time_s']:.4f}",
                f"{hop['processing_time_s']:.4f}",
                f"{hop.get('atmosphere_time_s', 0):.4f}",
                f"{hop.get('pure_void_time_s', 0):.2f}",
                f"{hop_total:.4f}"
            ]

            for i, val in enumerate(values):
                col_x = table_x + sum(col_widths[:i])
                txt = self.font_mono_sm.render(val, True, row_color)
                self.screen.blit(txt, (col_x, ry))

    def _draw_latency_panel(self):
        """Draw the LATENCY BREAKDOWN panel with horizontal bars."""
        draw_card_with_screws(self.screen, self.latency_panel_rect,
                              title="LATENCY BREAKDOWN", title_font=self.font_card_title)
        x, y, w, h = self.latency_panel_rect

        if not self.current_route or not self.current_route.hop_details:
            empty = self.font_mono_sm.render("Send a packet to see breakdown.", True, COLORS['text_muted'])
            self.screen.blit(empty, (x + 22, y + 35))
            return

        # Aggregate latency components
        total_fiber = sum(h_d.get("fiber_time_s", 0) for h_d in self.current_route.hop_details)
        total_proc = sum(h_d.get("processing_time_s", 0) for h_d in self.current_route.hop_details)
        total_void = sum(h_d.get("pure_void_time_s", 0) for h_d in self.current_route.hop_details)
        total_atmos = sum(h_d.get("atmosphere_time_s", 0) for h_d in self.current_route.hop_details)
        total_all = self.current_route.total_latency_s

        components = [
            ("Void",    total_void, COLORS['bar_void'], "L / c"),
            ("Fiber",   total_fiber, COLORS['bar_fiber'], "S*2piR / N / 0.67c"),
            ("Tower",   total_proc, COLORS['bar_tower'], "M * 7ms"),
            ("Atmos",   total_atmos, COLORS['bar_atmos'], "(atm * n) / c"),
        ]

        inner_pad = 22
        right_pad = 22
        bar_x = x + inner_pad
        bar_y = y + 35
        usable_w = w - inner_pad - right_pad  # total usable width inside card
        label_w = int(55 * self.scale)         # space for "Void  " etc.
        value_w = int(95 * self.scale)         # space for "188.5260s" etc.
        formula_w = int(180 * self.scale)      # space for formulas
        bar_area_w = usable_w - label_w - value_w - formula_w - 8  # remaining for the bar itself
        bar_h = int(14 * self.scale)
        gap = int(6 * self.scale)

        max_val = max(total_all, 0.001)

        for i, (label, value, color, formula) in enumerate(components):
            by = bar_y + i * (bar_h + gap)
            # Label (left)
            lbl = self.font_mono_sm.render(f"{label:6s}", True, COLORS['text_muted'])
            self.screen.blit(lbl, (bar_x, by + 1))

            # Formula (next to label)
            fx = bar_x + label_w
            frm = self.font_mono_sm.render(formula, True, (120, 130, 140))
            self.screen.blit(frm, (fx, by + 1))

            # Bar (middle)
            bx = fx + formula_w
            bw = int((value / max_val) * bar_area_w)
            pygame.draw.rect(self.screen, COLORS['recessed'], (bx, by, bar_area_w, bar_h), border_radius=4)
            pygame.draw.rect(self.screen, color, (bx, by, max(bw, 2), bar_h), border_radius=4)

            # Value label (right)
            val_str = f"{value:.4f}s"
            val_txt = self.font_mono_sm.render(val_str, True, COLORS['text_primary'])
            val_x = bx + bar_area_w + 6
            self.screen.blit(val_txt, (val_x, by + 1))

        # Total
        total_y = bar_y + len(components) * (bar_h + gap) + 4
        pygame.draw.line(self.screen, COLORS['shadow_dark'], (bar_x, total_y), (bar_x + usable_w, total_y), 1)
        total_txt = self.font_mono.render(f"TOTAL: {total_all:.4f}s", True, COLORS['accent'])
        self.screen.blit(total_txt, (bar_x, total_y + 4))

    def _draw_codec_panel(self):
        """Draw the PACKET CODEC panel showing Base-N translations."""
        draw_card_with_screws(self.screen, self.codec_panel_rect,
                              title="PACKET CODEC", title_font=self.font_card_title)
        x, y, w, h = self.codec_panel_rect

        if not self.current_packet or not self.current_packet.hop_log:
            empty = self.font_mono_sm.render("Codec translations appear here.", True, COLORS['text_muted'])
            self.screen.blit(empty, (x + 22, y + 35))
            return

        line_y = y + 30
        line_h = int(16 * self.scale)

        # Original ASCII
        ascii_txt = self.font_mono_sm.render(f'ASCII: "{self.current_packet.payload}"', True, COLORS['text_primary'])
        self.screen.blit(ascii_txt, (x + 22, line_y))
        line_y += line_h + 4

        pygame.draw.line(self.screen, COLORS['shadow_dark'], (x + 22, line_y), (x + w - 22, line_y), 1)
        line_y += 6

        # Per-hop codex translations
        max_hops = (h - 70) // (line_h * 3)
        for i, hop in enumerate(self.current_packet.hop_log[:max_hops]):
            codex_vals = hop.get("payload_in_codex", [])
            bin_stream = hop.get("binary_stream", "")
            asc_val = hop.get("payload_ascii", "")
            
            preview = " ".join(codex_vals[:8])
            if len(codex_vals) > 8: preview += " ..."
            
            bin_preview = bin_stream[:40]
            if len(bin_stream) > 40: bin_preview += "..."
            
            asc_preview = asc_val[:20]
            if len(asc_val) > 20: asc_preview += "..."

            is_dest = (hop["void_distance_km"] == 0 and i == len(self.current_packet.hop_log) - 1)
            color = COLORS['accent'] if is_dest else COLORS['text_primary']

            line1 = f"[{hop['planet_id'][:6]:6s}] Base {hop['codex_base']:2d}: {preview}"
            line2 = f"         Binary : {bin_preview}"
            line3 = f"         ASCII  : {asc_preview}"
            
            self.screen.blit(self.font_mono_sm.render(line1, True, color), (x + 22, line_y))
            line_y += line_h
            self.screen.blit(self.font_mono_sm.render(line2, True, COLORS['text_muted']), (x + 22, line_y))
            line_y += line_h
            self.screen.blit(self.font_mono_sm.render(line3, True, COLORS['text_muted']), (x + 22, line_y))
            line_y += line_h + 4

    def _draw_control_bar(self):
        """Draw the bottom control bar."""
        x, y, w, h = self.control_rect
        pygame.draw.rect(self.screen, COLORS['control_bg'], (x, y, w, h))
        pygame.draw.line(self.screen, COLORS['shadow_deep'], (x, y), (x + w, y), 1)

        # Labels
        s = self.scale
        label_y = y + int(4 * s)
        src_x = int(15 * s)
        dst_x = int(135 * s)
        pay_x = int(255 * s)

        src_label = self.font_led.render("SOURCE:", True, COLORS['header_text'])
        dst_label = self.font_led.render("DEST:", True, COLORS['header_text'])
        pay_label = self.font_led.render("PAYLOAD:", True, COLORS['header_text'])

        self.screen.blit(src_label, (src_x, label_y))
        self.screen.blit(dst_label, (dst_x, label_y))
        self.screen.blit(pay_label, (pay_x, label_y))

        # Draw elements
        self.src_dropdown.draw(self.screen)
        self.dst_dropdown.draw(self.screen)
        self.payload_input.draw(self.screen, self.tick)
        self.send_btn.draw(self.screen)
        self.kill_btn.draw(self.screen)
        self.revive_btn.draw(self.screen)
        self.judge_btn.draw(self.screen)

    # ──────────────────────────────────────────────────────────────
    # Action Handlers
    # ──────────────────────────────────────────────────────────────

    def _action_send_packet(self):
        """Handle SEND PACKET button press."""
        src = self.src_dropdown.value
        dst = self.dst_dropdown.value
        payload = self.payload_input.text.strip()

        if not payload:
            payload = "Hello world"

        if src == dst:
            return

        # Pre-flight endpoint validation
        if not self.planets[src].is_active or not self.planets[dst].is_active:
            self.transmission_status = TransmissionStatus.BLOCKED
            self.packet_counter += 1
            self.current_packet = Packet(
                packet_id=f"{self.packet_counter:03d}",
                origin_id=src,
                destination_id=dst,
                current_id=src,
                payload=payload,
                status=TransmissionStatus.BLOCKED
            )
            self.current_route = None
            self.anim_active = False
            return

        # Get route
        route = self.resilience.get_route(src, dst)
        if route is None:
            self.current_route = None
            self.transmission_status = TransmissionStatus.UNDELIVERABLE
            if self.current_packet:
                self.current_packet.status = TransmissionStatus.UNDELIVERABLE
            return

        self.current_route = route
        self.transmission_status = TransmissionStatus.IN_TRANSIT

        # Simulate packet journey
        try:
            if self.judge_mode and self.judge_step == 2:
                self.judge_step = 5  # Step 3, 4, 5 complete instantly on re-route
                
            packet = simulate_packet_journey(payload, route, self.planets, self.metadata)
            self.packet_counter += 1
            packet.packet_id = f"{self.packet_counter:03d}"
            self.current_packet = packet
            
            # Auto-save report
            os.makedirs("reports", exist_ok=True)
            report_path = f"reports/transmission_{packet.packet_id}.txt"
            with open(report_path, "w") as f:
                f.write(f"Packet ID: {packet.packet_id}\n")
                f.write(get_journey_summary(packet))
                f.write(f"\nTotal Latency: {route.total_latency_s:.9f}s\n")
                
            self._add_toast(f"Packet #{packet.packet_id} routed to {dst}", "success")

        except Exception as e:
            print(f"[ERROR] Packet simulation failed: {e}")
            self.current_packet = None
            self._add_toast("Routing Failed!", "error")

        # Start animation
        self.anim_path_coords = [self.planet_screen_pos[pid] for pid in route.path if pid in self.planet_screen_pos]
        self.anim_progress = 0.0
        self.anim_active = True

    def _action_kill_node(self, planet_id):
        """Kill a planet node for Chaos Test."""
        try:
            log = self.resilience.kill_node(planet_id)
            self.planets[planet_id].is_active = False
            self.graph = build_network_graph(self.metadata,
                [p for p in self.planets.values() if p.is_active])
            print(f"\n[CHAOS] Killed node: {planet_id}")
            print(f"  Convergence: {log.get('convergence_time_ms', 0):.2f}ms")
            self._add_toast(f"Killed {planet_id}", "error")

            # Check if this kill affects the current transmission endpoints
            if self.current_packet:
                if planet_id == self.current_packet.origin_id or planet_id == self.current_packet.destination_id:
                    self.current_packet.status = TransmissionStatus.ABORTED
                    self.transmission_status = TransmissionStatus.ABORTED
                    self.anim_active = False
                    if self.current_route:
                        self.current_route.is_reachable = False
                    self._add_toast("Transmission Aborted", "error")
                    return

            # Judge Mode vs Auto-reroute for intermediate nodes
            if self.judge_mode:
                if self.current_route and planet_id in self.current_route.path:
                    self.current_route.is_reachable = False
                    if self.current_packet:
                        self.current_packet.destination_id = "UNDELIVERABLE"
                        self.current_packet.status = TransmissionStatus.BLOCKED
                    self.transmission_status = TransmissionStatus.BLOCKED
                    self.anim_active = False
                    self.judge_step = 2
                    self._add_toast("ROUTE INVALID. Waiting for recomputation...", "error")
            else:
                # Seamless Auto-reroute if there's a current route
                if self.current_route and planet_id in self.current_route.path:
                    self._action_send_packet()
        except Exception as e:
            print(f"[ERROR] Kill failed: {e}")

    def _action_revive_all(self):
        """Revive all dead nodes."""
        for pid, planet in self.planets.items():
            if not planet.is_active:
                try:
                    self.resilience.revive_node(pid)
                    planet.is_active = True
                    print(f"[REVIVE] Node restored: {pid}")
                except Exception:
                    pass
        self.graph = build_network_graph(self.metadata, list(self.planets.values()))
        self._add_toast("All nodes revived", "success")
        if self.current_route:
            self._action_send_packet()

    # ──────────────────────────────────────────────────────────────
    # Toast Notifications
    # ──────────────────────────────────────────────────────────────

    def _add_toast(self, message, type="info"):
        # types: info, success, error
        self.toasts.append({
            "msg": message,
            "type": type,
            "timer": 180  # 3 seconds at 60fps
        })

    def _draw_toasts(self):
        y_offset = 20
        active_toasts = []
        for t in self.toasts:
            t["timer"] -= 1
            if t["timer"] > 0:
                active_toasts.append(t)
                
                # Draw
                color = COLORS['led_green'] if t['type'] == 'success' else (COLORS['led_red'] if t['type'] == 'error' else COLORS['header_text'])
                txt = self.font_body.render(t["msg"], True, color)
                
                # Fade out last 30 frames
                alpha = 255 if t["timer"] > 30 else int((t["timer"] / 30) * 255)
                
                bg_w = txt.get_width() + 40
                bg_h = 40
                bg_x = self.win_w // 2 - bg_w // 2
                
                surf = pygame.Surface((bg_w, bg_h), pygame.SRCALPHA)
                pygame.draw.rect(surf, (*COLORS['header_bg'], alpha), (0, 0, bg_w, bg_h), border_radius=8)
                pygame.draw.rect(surf, (*color, alpha), (0, 0, bg_w, bg_h), 1, border_radius=8)
                
                txt_surf = pygame.Surface(txt.get_size(), pygame.SRCALPHA)
                txt_surf.blit(txt, (0, 0))
                txt_surf.set_alpha(alpha)
                
                surf.blit(txt_surf, (20, 10))
                self.screen.blit(surf, (bg_x, y_offset))
                
                y_offset += bg_h + 10
                
        self.toasts = active_toasts

    # ──────────────────────────────────────────────────────────────
    # Main Event Loop
    # ──────────────────────────────────────────────────────────────

    def run(self):
        """Main Pygame event loop."""
        running = True

        try:
            while running:
                self.tick += 1

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                        
                    if event.type == pygame.VIDEORESIZE:
                        # Prevent window from becoming too small
                        self.win_w = max(1024, event.w)
                        self.win_h = max(720, event.h)
                        self.scale = min(self.win_w / BASE_W, self.win_h / BASE_H)
                        self.screen = pygame.display.set_mode((self.win_w, self.win_h), pygame.RESIZABLE)
                        self._init_fonts()
                        self._calculate_layout()
                        self._calculate_planet_positions()
                        self._init_ui_elements()
                        continue
                        
                    if self.transmission_status == TransmissionStatus.DELIVERED:
                        if event.type == pygame.MOUSEBUTTONDOWN:
                            self.transmission_status = TransmissionStatus.READY
                        continue

                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        if self.kill_mode:
                            self.kill_mode = False
                        elif self.payload_input.active:
                            self.payload_input.active = False
                        else:
                            running = False

                    # Text input gets priority when active
                    if self.payload_input.active:
                        if self.payload_input.handle_event(event):
                            self._action_send_packet()
                        continue

                    # Dropdowns (check for selection change)
                    self.src_dropdown.handle_event(event)
                    self.dst_dropdown.handle_event(event)

                    # Buttons
                    if self.send_btn.handle_event(event):
                        self._action_send_packet()

                    if self.kill_btn.handle_event(event):
                        self.kill_mode = not self.kill_mode

                    if self.revive_btn.handle_event(event):
                        self._action_revive_all()
                        
                    if self.judge_btn.handle_event(event):
                        self.judge_mode = not self.judge_mode
                        if self.judge_mode:
                            self.judge_btn.fg_color = COLORS['led_green']
                            self.anim_speed = 0.003
                            self.judge_step = 0
                            self._add_toast("Judge Mode Enabled", "info")
                        else:
                            self.judge_btn.fg_color = COLORS['button_dark_fg']
                            self.anim_speed = 0.008
                            self._add_toast("Judge Mode Disabled", "info")
                            
                    # Planet click for kill mode
                    if (event.type == pygame.MOUSEBUTTONDOWN and
                            event.button == 1 and self.kill_mode and self.hovered_planet):
                        self._action_kill_node(self.hovered_planet)
                        self.kill_mode = False

                    # Payload input activation
                    self.payload_input.handle_event(event)

                # Update animation
                if self.anim_active:
                    self.anim_progress += self.anim_speed
                    if self.anim_progress >= 1.0:
                        self.anim_progress = 1.0
                        self.anim_active = False
                        if self.current_route and self.current_route.is_reachable:
                            if self.current_packet:
                                self.current_packet.status = TransmissionStatus.DELIVERED
                            self.transmission_status = TransmissionStatus.DELIVERED

                # -- Draw everything --
                self.screen.fill(COLORS['chassis'])

                self._draw_header()
                self._draw_star_map()
                self._draw_packet_status_panel()
                self._draw_universe_meta_panel()
                self._draw_hop_log_panel()
                self._draw_latency_panel()
                self._draw_codec_panel()
                self._draw_control_bar()
                
                # Draw Tooltips on top of panels
                if self.hovered_planet:
                    self._draw_planet_tooltip(self.planets[self.hovered_planet], pygame.mouse.get_pos())
                
                if self.judge_mode:
                    self._draw_judge_panels()
                    
                if self.transmission_status == TransmissionStatus.DELIVERED:
                    self._draw_transmission_complete_dialog()

                self._draw_toasts()

                pygame.display.flip()
                self.clock.tick(60)

        except KeyboardInterrupt:
            print("\n[EXIT] Shutting down gracefully...")

        pygame.quit()
        
    def _draw_judge_panels(self):
        """Draws the Routing Engine and Judge Checklist panels."""
        s = self.scale
        pad = int(10 * s)
        
        # 1. Sequence Indicator Checklist (Floating on right, at Hop Log level)
        check_w = int(240 * s)
        check_h = int(140 * s)
        cx = self.win_w - check_w - pad
        cy = self.hop_panel_rect[1]
        
        draw_card_with_screws(self.screen, (cx, cy, check_w, check_h), color=COLORS['teal_panel'], title="JUDGE MODE", title_font=self.font_card_title)
        src_active = self.planets[self.src_dropdown.value].is_active
        dst_active = self.planets[self.dst_dropdown.value].is_active
        
        if not src_active:
            steps = ["Kill Node", "Source Offline", "Transmission Blocked"]
        elif not dst_active:
            steps = ["Kill Node", "Destination Offline", "Transmission Blocked"]
        else:
            steps = [
                "Kill Node",
                "Route Invalid",
                "Run Dijkstra/A*",
                "Route Found",
                "Resume Transmission"
            ]
        
        y_offset = cy + int(30 * s)
        for i, text in enumerate(steps, 1):
            if not src_active or not dst_active:
                # In offline sequences, all displayed steps are complete
                is_checked = True
            else:
                is_checked = self.judge_step >= i
                
            color = COLORS['led_green'] if is_checked else COLORS['text_muted']
            box = "[✓]" if is_checked else "[ ]"
            txt = self.font_mono_sm.render(f"{box} STEP {i}: {text}", True, color)
            self.screen.blit(txt, (cx + 15, y_offset))
            y_offset += int(18 * s)
            
        # 2. Routing Engine Panel (Floating on bottom right)
        panel_w = int(240 * s)
        panel_h = int(160 * s)
        
        rx = self.win_w - panel_w - pad
        ry = self.win_h - int(CONTROL_H * s) - panel_h - pad
        
        draw_card_with_screws(self.screen, (rx, ry, panel_w, panel_h), color=COLORS['teal_panel'], title="ROUTING ENGINE", title_font=self.font_card_title)
        
        if self.current_route:
            r = self.current_route
            lines = [
                f"Algorithm: {r.algorithm_used}",
                f"Source:    {r.route_source}",
                f"Visited:   {r.visited_nodes}",
                f"Edges:     {r.edges_checked}",
                f"Exec Time: {r.execution_time_ms:.2f}ms"
            ]
            
            y_offset = ry + int(30 * s)
            for line in lines:
                txt = self.font_mono_sm.render(line, True, COLORS['text_primary'])
                self.screen.blit(txt, (rx + 15, y_offset))
                y_offset += int(18 * s)
                
            path_txt = " ↓ ".join(r.path)
            # Truncate if too long to fit
            if len(path_txt) > 28:
                path_txt = path_txt[:25] + "..."
                
            path_surf = self.font_mono_sm.render(path_txt, True, COLORS['accent'])
            self.screen.blit(path_surf, (rx + 15, y_offset + 5))
        else:
            txt = self.font_mono_sm.render("Awaiting Route", True, COLORS['text_muted'])
            self.screen.blit(txt, (rx + 15, ry + int(35 * s)))
            
    def _draw_transmission_complete_dialog(self):
        """Draws the Transmission Complete dialog."""
        if not self.current_route or not self.current_packet:
            return
            
        s = self.scale
        cw = int(360 * s)
        ch = int(220 * s)
        cx = (self.win_w - cw) // 2
        cy = (self.win_h - ch) // 2
        
        # Darken bg
        overlay = pygame.Surface((self.win_w, self.win_h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))
        
        pygame.draw.rect(self.screen, COLORS['panel'], (cx, cy, cw, ch), border_radius=12)
        pygame.draw.rect(self.screen, COLORS['shadow_deep'], (cx, cy, cw, ch), 2, border_radius=12)
        
        title_surf = self.font_card_title.render("TRANSMISSION COMPLETE", True, COLORS['text_muted'])
        self.screen.blit(title_surf, (cx + 22, cy + 15))
        
        pkt = self.current_packet
        r = self.current_route
        path_str = " ↓ ".join(r.path)
        if len(path_str) > 40:
            path_str = path_str[:37] + "..."
            
        lines = [
            f"Packet:    PKT-{pkt.packet_id}",
            f"Route:     {path_str}",
            f"Algorithm: {r.algorithm_used}",
            f"Latency:   {r.total_latency_s:.2f} s",
            f"Status:    ✓ Delivered"
        ]
        
        y_offset = cy + int(45 * s)
        for line in lines:
            color = COLORS['text_primary']
            if "✓" in line:
                color = COLORS['led_green']
            
            txt = self.font_mono_sm.render(line, True, color)
            self.screen.blit(txt, (cx + 20, y_offset))
            y_offset += int(25 * s)
            
        hint = self.font_mono_sm.render("Click anywhere to continue", True, COLORS['text_muted'])
        self.screen.blit(hint, (cx + (cw - hint.get_width()) // 2, cy + ch - 30))

# ══════════════════════════════════════════════════════════════════
# Standalone Runner (for testing without main.py)
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    config_path = os.path.join(os.path.dirname(__file__), "..", "universe-config.json")
    config_path = os.path.abspath(config_path)

    print("Loading universe config...")
    meta, planets = load_universe_config(config_path)

    print("Initializing resilience manager...")
    manager = ResilienceManager(meta, planets)

    print("Starting visualizer...")
    viz = RelicRingVisualizer(meta, planets, manager)
    viz.run()
