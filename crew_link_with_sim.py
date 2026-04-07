import serial
import serial.tools.list_ports
import pygame
import sys
import time
import math
import re
import os
import random

# ==========================================
# --- ENVIRONMENT CONFIGURATION TOGGLES ---
# ==========================================
RUNNING_ON_PI = True    
SIMULATION_MODE = True  

# --- GUI REFRESH RATE ---
# 0.25 = 4 FPS. Logic and hardware still run at 60Hz.
GUI_UPDATE_INTERVAL = 0.25  

# --- HARDWARE ALARM SETUP ---
hw_alarms_active = False
if RUNNING_ON_PI:
    try:
        from gpiozero import LED, PWMOutputDevice
        led = LED(4)
        buzzer1 = PWMOutputDevice(22, frequency=440, initial_value=0) 
        buzzer2 = PWMOutputDevice(26, frequency=880, initial_value=0)
        hw_alarms_active = True
        print("PI MODE: Hardware alarms initialized.")
    except Exception as e:
        print(f"PI MODE Warning: Hardware alarm failure ({e}).")

# --- GPS CONFIGURATION ---
BASE_LAT = 49.15575
BASE_LON = -123.1500

def local_to_gps(x_m, y_m):
    lat_offset = y_m / 111139.0
    m_per_deg_lon = 111139.0 * math.cos(math.radians(BASE_LAT))
    lon_offset = x_m / m_per_deg_lon
    return BASE_LAT + lat_offset, BASE_LON + lon_offset

def get_dwm_port():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if "JLink" in port.description or "USB Serial" in port.description or "ACM" in port.device:
            return port.device
    return ports[0].device if ports else None

# ==========================================
# --- 1. NEW SERIAL CONNECTION BLOCK ---
# ==========================================
ser = None
discovered_anchors = {}

if not SIMULATION_MODE:
    SERIAL_PORT = "/dev/serial0" if RUNNING_ON_PI else get_dwm_port()
    if not SERIAL_PORT:
        print("Error: No UWB module detected. Check your USB/Pins.")
    else:
        try:
            ser = serial.Serial(SERIAL_PORT, 115200, timeout=0.01)
            ser.reset_input_buffer()
            
            # 1. Wake up the module
            ser.write(b'reset\r')
            time.sleep(0.5)
            
            ser.write(b'\r\r') 
            time.sleep(1.0)
            
            # 2. Ask for the Anchor List
            ser.write(b'la\r')
            time.sleep(1.0) # Wait for the module to spit out all the anchors
            
            # 3. Read and Parse the Anchors
            la_data = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
            print(la_data)
            for line in la_data.split('\n'):
                if "id=" in line and "pos=" in line:
                    parts = line.split()
                    a_id, a_pos = "", ""
                    for p in parts:
                        if p.startswith("id="): a_id = p.split("=")[1][-4:] 
                        elif p.startswith("pos="): a_pos = p.split("=")[1]
                    if a_id and a_pos:
                        coords = a_pos.split(':')
                        if len(coords) >= 2:
                            discovered_anchors[a_id] = (float(coords[0]), float(coords[1]))
            
            print(f"SUCCESS: Connected to UWB! Found {len(discovered_anchors)} Anchors.")
            # 4. Start streaming continuous Tag locations (using CSV format)
            ser.write(b'lec\r')
            time.sleep(1.0) 
            
        except Exception as e:
            print(f"CRITICAL: Error connecting to {SERIAL_PORT}: {e}")
            ser = None

# Fallback just in case the module didn't report any anchors, or we are in Simulation Mode
if not discovered_anchors:
    print("Notice: Using default fallback anchor positions.")
    discovered_anchors = {"ANC1": (0, 0), "ANC2": (5.0, 0), "ANC3": (2.5, 8.0)}

# Calculate the exact center of the map based on the anchors
center_x = sum([pos[0] for pos in discovered_anchors.values()]) / len(discovered_anchors)
center_y = sum([pos[1] for pos in discovered_anchors.values()]) / len(discovered_anchors)
# ==========================================

POS_REGEX = re.compile(r'POS,\d+,([0-9A-Fa-f]+),([-+]?\d*\.?\d+|nan),([-+]?\d*\.?\d+|nan)', re.IGNORECASE)

# --- STATE VARIABLES ---
active_tags = {}
CREW_ROSTER = ["Kris", "Juliana", "John", "Raben", "Beth", "Vanessa"]
available_names = CREW_ROSTER.copy() 
random.shuffle(available_names)

DATA_TIMEOUT = 2.0  
serial_buffer = ""
sim_step = 0
REQUIRED_TAGS = 2

mob_start_time = None
current_b1_val = 0.0
current_b2_val = 0.0
current_led_state = False
is_muted = False 

# --- THEME SONG STATE ---
playing_theme = False
theme_index = 0
theme_last_tick = 0
theme_in_gap = False

POTC_THEME = [
    ('A3', 0.15), ('C4', 0.15), ('D4', 0.30), ('D4', 0.30),
    ('D4', 0.15), ('E4', 0.15), ('F4', 0.30), ('F4', 0.30),
    ('F4', 0.15), ('G4', 0.15), ('E4', 0.30), ('E4', 0.30),
    ('D4', 0.15), ('C4', 0.15), ('D4', 0.45), ('REST', 0.15),
    ('A3', 0.15), ('C4', 0.15), ('D4', 0.30), ('D4', 0.30),
    ('D4', 0.15), ('E4', 0.15), ('F4', 0.30), ('F4', 0.30),
    ('F4', 0.15), ('G4', 0.15), ('E4', 0.30), ('E4', 0.30),
    ('D4', 0.15), ('C4', 0.15), ('C4', 0.15), ('D4', 0.30), ('REST', 0.15),
    ('A3', 0.15), ('C4', 0.15), ('D4', 0.30), ('D4', 0.30),
    ('D4', 0.15), ('F4', 0.15), ('G4', 0.30), ('G4', 0.30),
    ('G4', 0.15), ('A4', 0.15), ('Bb4', 0.30), ('Bb4', 0.30),
    ('A4', 0.15), ('G4', 0.15), ('A4', 0.15), ('D4', 0.30), ('REST', 0.15),
    ('D4', 0.15), ('E4', 0.15), ('F4', 0.30), ('F4', 0.30),
    ('G4', 0.30), ('A4', 0.30), ('D4', 0.30), ('REST', 0.15),
    ('D4', 0.15), ('F4', 0.15), ('E4', 0.30), ('E4', 0.30),
    ('F4', 0.15), ('D4', 0.15), ('E4', 0.60), ('REST', 0.15)
]

NOTE_FREQ = {
    'A3': 220, 'C4': 261, 'D4': 293, 'E4': 329, 'F4': 349, 'G4': 392, 
    'A4': 440, 'Bb4': 466, 'REST': 0
}

# --- PYGAME INITIALIZATION ---
pygame.init()
if RUNNING_ON_PI:
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN | pygame.DOUBLEBUF | pygame.HWSURFACE)
else:
    screen = pygame.display.set_mode((1280, 800))
pygame.display.set_caption("Crew Link Dashboard")

WIDTH, HEIGHT = screen.get_size()
clock = pygame.time.Clock()

SIDEBAR_WIDTH = 320
RADAR_CX = (WIDTH - SIDEBAR_WIDTH) // 2
RADAR_CY = HEIGHT // 2
PIXELS_PER_METER = 50 

C_BG, C_SIDEBAR, C_GRID = (28, 28, 30), (38, 38, 40), (50, 50, 55)
C_RADAR, C_BOAT, C_BOAT_OUTLINE = (100, 180, 255), (45, 45, 50), (100, 100, 105)
C_SAFE, C_DANGER, C_WARN, C_TEXT = (75, 210, 130), (255, 100, 100), (255, 200, 100), (240, 240, 245)

try:
    font_xlarge = pygame.font.SysFont("courier", 40, bold=True)
    font_large = pygame.font.SysFont("courier", 32, bold=True)
    font_med = pygame.font.SysFont("courier", 26, bold=True)
    font_small = pygame.font.SysFont("courier", 20)
except:
    font_xlarge = pygame.font.Font(None, 60)
    font_large = pygame.font.Font(None, 50)
    font_med = pygame.font.Font(None, 35)
    font_small = pygame.font.Font(None, 28)

# Pre-render
surf_title_radar = font_xlarge.render("CREWLINK ACTIVE MONITORING", True, C_RADAR)
rect_title_radar = surf_title_radar.get_rect(center=(RADAR_CX, 30))
surf_title_crew = font_xlarge.render("CREWLINK", True, C_RADAR)
rect_title_crew = surf_title_crew.get_rect(center=(WIDTH - SIDEBAR_WIDTH // 2, 40))
surf_manifest = font_med.render("", True, C_TEXT)
surf_status_secure = font_large.render("ALL ON BOARD", True, C_SAFE)
rect_status_secure = surf_status_secure.get_rect(center=(RADAR_CX, 80))

# --- BOAT GEOMETRY (WIDER VERSION) ---
# This makes the boat 5 meters wide instead of 3 meters wide, keeping the 10m length.
BOAT_COORDS = [
    (0.0, 5.0), (0.8, 4.6), (1.6, 3.8), (2.1, 2.5), 
    (2.5, 1.0), (2.5, -3.0), (2.1, -4.8), (2.0, -5.0), 
    (1.0, -5.0), (1.0, -4.8), (-1.0, -4.8), (-1.0, -5.0), 
    (-2.0, -5.0), (-2.1, -4.8), (-2.5, -3.0), (-2.5, 1.0), 
    (-2.1, 2.5), (-1.6, 3.8), (-0.8, 4.6)
]

# Expanding the cabin to match the new wider hull
CABIN_COORDS = [
    (0.0, 2.2), (1.5, 1.5), (1.5, -2.5), (-1.5, -2.5), (-1.5, 1.5)
]

def meter_to_pixel(m_x, m_y):
    px = RADAR_CX + int((m_x - center_x) * PIXELS_PER_METER)
    py = RADAR_CY - int((m_y - center_y) * PIXELS_PER_METER)
    return (px, py)

poly_boat = [meter_to_pixel(x + center_x, y + center_y) for x, y in BOAT_COORDS]
poly_cabin = [meter_to_pixel(x + center_x, y + center_y) for x, y in CABIN_COORDS]

def is_point_in_polygon(x, y, poly):
    n = len(poly)
    inside = False
    p1x, p1y = poly[0]
    for i in range(n + 1):
        p2x, p2y = poly[i % n]
        if y > min(p1y, p2y) and y <= max(p1y, p2y) and x <= max(p1x, p2x):
            if p1y != p2y: xints = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
            if p1x == p2x or x <= xints: inside = not inside
        p1x, p1y = p2x, p2y
    return inside

class Button:
    def __init__(self, x, y, w, h, text, color, hover_color):
        self.rect = pygame.Rect(x, y, w, h)
        self.text, self.color, self.hover_color = text, color, hover_color
        self.is_hovered = False
    def draw(self, surface):
        pygame.draw.rect(surface, self.hover_color if self.is_hovered else self.color, self.rect, border_radius=5)
        text_surf = font_med.render(self.text, True, (255, 255, 255))
        surface.blit(text_surf, text_surf.get_rect(center=self.rect.center))
    def check_hover(self, pos): self.is_hovered = self.rect.collidepoint(pos)
    def handle_click(self, pos): return self.rect.collidepoint(pos)

btn_y = HEIGHT - 180
btn_tag = Button(WIDTH - SIDEBAR_WIDTH + 20, btn_y, 130, 60, "TAGS: 2", (47, 53, 66), (87, 96, 111))
btn_mute = Button(WIDTH - 150, btn_y, 130, 60, "MUTE", (225, 177, 44), (251, 197, 49))
btn_pirate = Button(WIDTH - SIDEBAR_WIDTH + 20, btn_y + 80, 130, 60, "PIRATE", (47, 53, 66), (87, 96, 111))
btn_exit = Button(WIDTH - 150, btn_y + 80, 130, 60, "EXIT", (232, 65, 24), (255, 71, 87))

def toggle_pirate_theme():
    global playing_theme, theme_index, theme_last_tick, theme_in_gap
    playing_theme = not playing_theme
    theme_index, theme_last_tick, theme_in_gap = 0, time.time(), False
    if not playing_theme and hw_alarms_active:
        buzzer1.value = buzzer2.value = 0
        led.off()

def update_theme_logic():
    global playing_theme, theme_index, theme_last_tick, theme_in_gap
    if not playing_theme or not hw_alarms_active: return
    if theme_index >= len(POTC_THEME):
        playing_theme = False
        led.off()
        return

    now = time.time()
    note, duration = POTC_THEME[theme_index]
    elapsed = now - theme_last_tick

    if theme_in_gap or note == 'REST':
        if elapsed >= (duration if note == 'REST' else duration * 0.18):
            theme_index += 1
            theme_last_tick, theme_in_gap = now, False
        else:
            buzzer1.value = buzzer2.value = 0
            led.off()
    else:
        if elapsed >= duration * 0.82:
            theme_in_gap, theme_last_tick = True, now
            buzzer1.value = buzzer2.value = 0
            led.off()
        else:
            led.on() # LED on during the note
            target, other = (buzzer1, buzzer2) if theme_index % 2 == 0 else (buzzer2, buzzer1)
            target.frequency, target.value, other.value = NOTE_FREQ.get(note, 440), 0.5, 0

def cleanup_and_exit():
    if not SIMULATION_MODE and 'ser' in globals(): ser.close()
    if hw_alarms_active: led.off(); buzzer1.value = buzzer2.value = 0
    pygame.quit(); sys.exit()

# --- MAIN LOOP ---
running, frame_count, last_gui_update = True, 0, 0
while running:
    current_time = time.time()
    frame_count += 1
    
    # ==========================================
    # 1. FAST LOOP (60Hz): Logic & Hardware
    # ==========================================
    mouse_pos = pygame.mouse.get_pos()
    for btn in [btn_tag, btn_pirate, btn_mute, btn_exit]: btn.check_hover(mouse_pos)
    for event in pygame.event.get():
        if event.type == pygame.QUIT: cleanup_and_exit()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if btn_tag.handle_click(mouse_pos):
                REQUIRED_TAGS = 1 if REQUIRED_TAGS == 2 else 2
                btn_tag.text = f"TAGS: {REQUIRED_TAGS}"
            elif btn_pirate.handle_click(mouse_pos): toggle_pirate_theme()
            elif btn_mute.handle_click(mouse_pos):
                is_muted = not is_muted
                btn_mute.text = "UNMUTE" if is_muted else "MUTE"
                btn_mute.color = (232, 65, 24) if is_muted else (47, 53, 66)
            elif btn_exit.handle_click(mouse_pos): cleanup_and_exit()

    lines = []
    if SIMULATION_MODE:
        # 15-Second Auto-Looping Simulation
        cycle_time = current_time % 15.0 
        if cycle_time < 5.0:
            t0_x, t0_y = center_x, center_y # Safe in center
        else:
            drift = cycle_time - 5.0
            drift_amp = 1.0 + (drift * 0.3) 
            t0_x = center_x + (drift * 0.4)  
            t0_y = center_y + math.sin(drift * 0.4) * drift_amp
            
        # UPDATED: Formatted to exactly mimic the real DWM1001 output
        # Using A001 and B002 as fake Hex IDs so the Regex catches them!
        lines = [
            f"POS,0,A001,{t0_x:.2f},{t0_y:.2f},1.00,100,x0B", 
            f"POS,0,B002,{center_x-0.5:.2f},{center_y+0.5:.2f},1.00,100,x0B"
        ]
        
    elif ser is not None and ser.is_open and ser.in_waiting > 0:
        serial_buffer += ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
        if '\n' in serial_buffer:
            lines = serial_buffer.split('\n'); serial_buffer = lines[-1]; lines = lines[:-1]

    global_alarm, global_lost = False, False
    active_count, mob_coords = 0, None
    for line in lines:
        print(f"RAW: {line}")
        match = POS_REGEX.search(line)
        if match:
            tag_id = f"TAG-{match.group(1).zfill(2)}"
            if tag_id not in active_tags:
                # Pick a name: if we have shuffled names left, pop one. 
                # Otherwise, just use the Tag ID as a fallback.
                if available_names:
                    assigned_name = available_names.pop()
                else:
                    assigned_name = tag_id 

                active_tags[tag_id] = {
                    'name': assigned_name, 
                    'px': RADAR_CX, 
                    'py': RADAR_CY, 
                    'path': [], 
                    'status': 'safe', 
                    'last_time': current_time
                }
            raw_x, raw_y = match.group(2), match.group(3)
            if "nan" not in raw_x.lower():
                px, py = meter_to_pixel(float(raw_x), float(raw_y))
                stat = 'safe' if is_point_in_polygon(px, py, poly_boat) else 'MOB'
                active_tags[tag_id]['path'].append((px, py))
                if len(active_tags[tag_id]['path']) > 20: active_tags[tag_id]['path'].pop(0)
                active_tags[tag_id].update({'x': float(raw_x), 'y': float(raw_y), 'px': px, 'py': py, 'status': stat, 'last_time': current_time})

    for i, (t_id, data) in enumerate(active_tags.items()):
        if current_time - data['last_time'] > DATA_TIMEOUT: data['status'] = 'lost'
        if active_count < REQUIRED_TAGS:
            active_count += 1
            if data['status'] == 'lost': 
                global_lost = True
                mob_coords = (data['x'], data['y'], data['px'], data['py'])
            elif data['status'] == 'MOB': 
                global_alarm = True
                mob_coords = (data['x'], data['y'], data['px'], data['py'])

    if global_alarm or global_lost:
        playing_theme = False
        if mob_start_time is None: mob_start_time = current_time
        if hw_alarms_active:
            target_led = (frame_count % 12 < 6)
            if target_led != current_led_state: led.on() if target_led else led.off(); current_led_state = target_led
            b1 = b2 = 0.0
            if not is_muted:
                if global_lost: b1 = 0.5 if (frame_count % 60) in range(0, 10) or (frame_count % 60) in range(20, 30) else 0.0
                else: b1, b2 = (0.5, 0.0) if frame_count % 30 < 15 else (0.0, 0.5)
            buzzer1.value, buzzer2.value = b1, b2
    else:
        mob_start_time = None
        update_theme_logic() 
        if not playing_theme and hw_alarms_active:
            led.off(); buzzer1.value = buzzer2.value = 0

    # ==========================================
    # 2. SLOW LOOP (GUI Refresh @ 4 FPS)
    # ==========================================
    if current_time - last_gui_update >= GUI_UPDATE_INTERVAL:
        last_gui_update = current_time
        screen.fill(C_BG)
        
        # JUMBO Title Update
        surf_title_radar = font_xlarge.render("CREWLINK ACTIVE MONITORING", True, C_RADAR)
        rect_title_radar = surf_title_radar.get_rect(center=(RADAR_CX, 40))
        screen.blit(surf_title_radar, rect_title_radar)
        
        for r in [5, 10, 15, 20]:
            radius = r * PIXELS_PER_METER
            pygame.draw.circle(screen, C_GRID, (RADAR_CX, RADAR_CY), radius, 1)
            screen.blit(font_small.render(f"{r}m", True, C_GRID), (RADAR_CX + radius + 5, RADAR_CY + 5))
            
        pygame.draw.line(screen, C_GRID, (RADAR_CX, RADAR_CY - 1000), (RADAR_CX, RADAR_CY + 1000), 1)
        pygame.draw.line(screen, C_GRID, (RADAR_CX - 1000, RADAR_CY), (RADAR_CX + 1000, RADAR_CY), 1)
        pygame.draw.polygon(screen, C_BOAT, poly_boat)
        pygame.draw.polygon(screen, C_BOAT_OUTLINE, poly_boat, 2)
        pygame.draw.polygon(screen, C_BOAT_OUTLINE, poly_cabin, 1)
        
        for i, (t_id, data) in enumerate(active_tags.items()):
            if i >= REQUIRED_TAGS: continue
            tag_color = C_SAFE if data['status'] == 'safe' else (C_DANGER if data['status'] == 'MOB' else C_WARN)
            pygame.draw.circle(screen, tag_color, (data['px'], data['py']), 12)
            if data['status'] != 'safe' and int(current_time * 2) % 2 == 0: pygame.draw.circle(screen, tag_color, (data['px'], data['py']), 18, 3)
            
        if global_alarm or global_lost:    
            # --- ADDED BACK: MOB DISTANCE TRACKING LINE ---
            if mob_coords:
                # 1. Draw the laser line from the boat to the tag
                line_color = C_DANGER if int(current_time * 2) % 2 == 0 else (200, 50, 50)
                pygame.draw.line(screen, line_color, (RADAR_CX, RADAR_CY), (mob_coords[2], mob_coords[3]), 3)
                
                # 2. Calculate the physical distance in meters
                dist_meters = math.hypot(mob_coords[0] - center_x, mob_coords[1] - center_y)
                
                # 3. Find the exact midpoint of the pixel line
                mid_x = (RADAR_CX + mob_coords[2]) // 2
                mid_y = (RADAR_CY + mob_coords[3]) // 2
                
                # 4. Draw a nice "pill" background so the text is readable over the radar grid
                dist_surf = font_large.render(f"{dist_meters:.1f}m", True, (255, 255, 255))
                dist_rect = dist_surf.get_rect(center=(mid_x, mid_y))
                
                pygame.draw.rect(screen, C_BG, dist_rect.inflate(12, 8), border_radius=5)
                pygame.draw.rect(screen, line_color, dist_rect.inflate(12, 8), 1, border_radius=5)
                screen.blit(dist_surf, dist_rect)
            # ----------------------------------------------

            # Draw the Main Banner
            banner_color = C_DANGER if int(current_time * 2) % 2 == 0 else (150, 0, 0)
            banner_surf = font_large.render("!!! MAN OVERBOARD !!!" if global_alarm else "!!! SIGNAL LOST !!!", True, C_TEXT)
            pygame.draw.rect(screen, banner_color, banner_surf.get_rect(center=(RADAR_CX, 100)).inflate(20, 10))
            screen.blit(banner_surf, banner_surf.get_rect(center=(RADAR_CX, 100)))
        else: 
            rect_status_secure = surf_status_secure.get_rect(center=(RADAR_CX, 100))
            screen.blit(surf_status_secure, rect_status_secure)
            
        # 1. Draw Sidebar Background FIRST
        pygame.draw.rect(screen, C_SIDEBAR, (WIDTH - SIDEBAR_WIDTH, 0, SIDEBAR_WIDTH, HEIGHT))
        screen.blit(surf_title_crew, rect_title_crew)
        screen.blit(surf_manifest, (WIDTH - SIDEBAR_WIDTH + 20, 90))
        
        # 2. Draw Manifest
        y_off = 130
        for i, (t_id, data) in enumerate(active_tags.items()):
            if i >= REQUIRED_TAGS: break
            screen.blit(font_med.render(f"{data['name']:<10} [{data['status'].upper()}]", True, C_SAFE if data['status'] == 'safe' else C_DANGER), (WIDTH - SIDEBAR_WIDTH + 20, y_off))
            y_off += 40
            
        # 3. Draw Emergency GPS Box ON TOP of the sidebar background
        if (global_alarm or global_lost) and mob_coords:
            lat, lon = local_to_gps(mob_coords[0], mob_coords[1])
            flash_color = (220, 20, 20) if int(current_time * 2) % 2 == 0 else (120, 0, 0)
            
            gps_box = pygame.Rect(WIDTH - SIDEBAR_WIDTH + 15, y_off + 20, SIDEBAR_WIDTH - 30, 160)
            pygame.draw.rect(screen, flash_color, gps_box, border_radius=8)
            pygame.draw.rect(screen, (255, 255, 255), gps_box, 3, border_radius=8) 
            
            screen.blit(font_med.render("MOB LOCATION", True, (255, 255, 255)), (WIDTH - SIDEBAR_WIDTH + 25, y_off + 30))
            screen.blit(font_med.render(f"LAT: {lat:.6f}", True, (255, 255, 255)), (WIDTH - SIDEBAR_WIDTH + 25, y_off + 70))
            screen.blit(font_med.render(f"LON: {lon:.6f}", True, (255, 255, 255)), (WIDTH - SIDEBAR_WIDTH + 25, y_off + 105))
            
            # --- THE ACCURATE COUNTER ---
            # This subtracts the start time from the CURRENT system time
            # It will always be real-world seconds, even if the GUI is lagging.
            elapsed_seconds = int(current_time - mob_start_time)
            
            # Display as "DURATION: X seconds"
            timer_text = f"DURATION: {elapsed_seconds}s"
            screen.blit(font_med.render(timer_text, True, (255, 200, 100)), (WIDTH - SIDEBAR_WIDTH + 25, y_off + 140))

        # 4. Draw Buttons
        # for btn in [btn_tag, btn_pirate, btn_mute, btn_exit]: btn.draw(screen)
        for btn in [btn_tag, btn_mute, btn_exit]: btn.draw(screen)
        pygame.display.flip()
        
    clock.tick(60)
