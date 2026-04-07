import serial
import serial.tools.list_ports
import matplotlib
matplotlib.use('TkAgg') 
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.path import Path
from matplotlib.animation import FuncAnimation
import collections
import sys
import time
import math
from gpiozero import TonalBuzzer, LED

# --- HARDWARE SETUP ---
try:
    # Set mid_tone high for the alarm frequencies
    buzzer = TonalBuzzer(17, mid_tone=2000)
    led_red = LED(23)
    led_blue = LED(24)
    hardware_active = True
    print("Hardware initialized successfully.")
except Exception as e:
    print(f"Hardware not detected (Running in GUI-only mode): {e}")
    hardware_active = False

# --- GPS CONFIGURATION ---
BASE_LAT = 49.26628096481008
BASE_LON = -123.2548719012252

plt.style.use('dark_background')

def local_to_gps(x_m, y_m):
    lat_offset = y_m / 111139.0
    m_per_deg_lon = 111139.0 * math.cos(math.radians(BASE_LAT))
    lon_offset = x_m / m_per_deg_lon
    return BASE_LAT + lat_offset, BASE_LON + lon_offset

# --- SERIAL & HARDWARE SETUP ---
def get_dwm_port():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if "JLink" in port.description or "USB Serial" in port.description or "ACM" in port.device:
            return port.device
    if ports:
        return ports[0].device 
    return None

SERIAL_PORT = get_dwm_port()
if not SERIAL_PORT:
    print("Error: No UWB module detected. Check your USB connection.")
    sys.exit()

BAUD_RATE = 115200
discovered_anchors = {}

try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.01)
    ser.reset_input_buffer()
    
    print(f"Connected to {SERIAL_PORT}. Halting any active data streams...")
    ser.write(b'\r\r')
    time.sleep(0.5)
    ser.reset_input_buffer()
    
    print("Requesting Anchor Map (la)...")
    ser.write(b'la\r')
    time.sleep(1) 
    
    la_data = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
    print("\n--- ANCHOR LOCATIONS ---")
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
                    a_x = float(coords[0]) 
                    a_y = float(coords[1]) 
                    discovered_anchors[a_id] = (a_x, a_y)
                    print(f"Found Anchor {a_id} at X: {a_x:.2f}m, Y: {a_y:.2f}m")
    print("------------------------\n")
                    
    print("Starting Live Marine Radar (lec)...")
    ser.write(b'\r\r') 
    time.sleep(0.5)
    ser.write(b'lec\r') 
except Exception as e:
    print(f"Error connecting: {e}")
    sys.exit()

# --- DYNAMIC CENTERING LOGIC ---
if discovered_anchors:
    center_x = sum([pos[0] for pos in discovered_anchors.values()]) / len(discovered_anchors)
    center_y = sum([pos[1] for pos in discovered_anchors.values()]) / len(discovered_anchors)
    print(f"Dynamic Center established at X: {center_x:.2f}m, Y: {center_y:.2f}m\n")
else:
    center_x, center_y = 0.0, 0.0

# --- TRACKING & FAILSAFE VARIABLES ---
FILTER_WINDOW = 5 
x_raw = collections.deque(maxlen=FILTER_WINDOW)
y_raw = collections.deque(maxlen=FILTER_WINDOW)

last_valid_x = center_x
last_valid_y = center_y
connection_lost = False
man_overboard = False

nan_count = 0  
last_data_time = time.time()
DATA_TIMEOUT = 2.0  
serial_buffer = ""

CREW_ROSTER = ["Kris", "Juliana", "John", "Kyle"]
active_tags = {}

# --- THE ZONES (Meters) ---
BOAT_COORDS = [
    (0.0, 5.0),     (0.5, 4.6),     (1.0, 3.8),     
    (1.3, 2.5),     (1.5, 1.0),     (1.5, -3.0),    
    (1.3, -4.8),    (1.2, -5.0),    (0.6, -5.0),    
    (0.6, -4.8),    (-0.6, -4.8),   (-0.6, -5.0),   
    (-1.2, -5.0),   (-1.3, -4.8),   (-1.5, -3.0),   
    (-1.5, 1.0),    (-1.3, 2.5),    (-1.0, 3.8),    
    (-0.5, 4.6),    
]
CABIN_COORDS = [(0.0, 2.2), (0.9, 1.5), (0.9, -2.5), (-0.9, -2.5), (-0.9, 1.5)]

DYNAMIC_BOAT_COORDS = [(x + center_x, y + center_y) for x, y in BOAT_COORDS]
DYNAMIC_CABIN_COORDS = [(x + center_x, y + center_y) for x, y in CABIN_COORDS]
boat_path = Path(DYNAMIC_BOAT_COORDS)

# --- GUI LAYOUT ---
fig = plt.figure(figsize=(12, 7))
fig.canvas.manager.set_window_title(f"Active Monitor - {SERIAL_PORT}")
gs = fig.add_gridspec(1, 2, width_ratios=[3, 1.4]) 

ax = fig.add_subplot(gs[0])
ax.set_title("ACTIVE MONITORING", fontsize=16, fontweight='bold', color='cyan')
ax.set_xlabel("Local X (meters)")
ax.set_ylabel("Local Y (meters)")
ax.grid(True, linestyle='-', color='#333333', alpha=0.7)
ax.set_aspect('equal')

BASE_X_LIMIT = 8.0  
BASE_Y_LIMIT = 6.0   
ax.set_xlim(center_x - BASE_X_LIMIT, center_x + BASE_X_LIMIT)
ax.set_ylim(center_y - BASE_Y_LIMIT, center_y + BASE_Y_LIMIT)

boat_patch = patches.Polygon(DYNAMIC_BOAT_COORDS, closed=True, fill=True, color='#0a3d62', alpha=0.6, zorder=2)
boat_outline = patches.Polygon(DYNAMIC_BOAT_COORDS, closed=True, fill=False, color='#3c6382', linewidth=2, zorder=2)
ax.add_patch(boat_patch)
ax.add_patch(boat_outline)

cabin_patch = patches.Polygon(DYNAMIC_CABIN_COORDS, closed=True, fill=True, color='#15537d', alpha=0.5, zorder=2)
cabin_outline = patches.Polygon(DYNAMIC_CABIN_COORDS, closed=True, fill=False, color='#4a81a8', linewidth=1.5, zorder=2)
ax.add_patch(cabin_patch)
ax.add_patch(cabin_outline)

if discovered_anchors:
    anch_x = [pos[0] for pos in discovered_anchors.values()]
    anch_y = [pos[1] for pos in discovered_anchors.values()]
    ax.scatter(anch_x, anch_y, marker='s', color='#f39c12', s=100, label='UWB Anchors', zorder=4)
    for a_id, coords in discovered_anchors.items():
        ax.text(coords[0] + 0.3, coords[1], a_id, fontsize=9, color='#f39c12', fontweight='bold')

status_text = ax.text(0.5, 0.96, "STATUS: WAITING FOR TAG...", transform=ax.transAxes, 
                      ha='center', va='top', fontsize=16, fontweight='bold', 
                      color='yellow', bbox=dict(facecolor='black', alpha=0.8, edgecolor='none'), zorder=10)

timer_text = ax.text(0.5, 0.88, "", transform=ax.transAxes, 
                     ha='center', va='top', fontsize=14, fontweight='bold', 
                     color='#f1c40f', bbox=dict(facecolor='black', alpha=0.8, edgecolor='none'), zorder=10)

mob_line, = ax.plot([], [], color='#e74c3c', linestyle='--', linewidth=2, zorder=3)
mob_dist_text = ax.text(0, 0, "", color='#e74c3c', fontsize=11, fontweight='bold', zorder=7,
                        bbox=dict(facecolor='black', alpha=0.7, edgecolor='none', pad=2))

safe_scatter = ax.scatter([], [], color='#2ecc71', s=80, edgecolors='white', zorder=5)
alarm_scatter = ax.scatter([], [], color='#e74c3c', s=150, edgecolors='white', linewidth=2, zorder=6)

ax_side = fig.add_subplot(gs[1])
ax_side.axis('off') 
ax_side.set_title("MANIFEST", fontsize=20, fontweight='bold', color='white', y=0.98)

MAX_TAGS = 5
manifest_texts = []
start_y = 0.92
spacing = 0.07 
for i in range(MAX_TAGS):
    t = ax_side.text(0.05, start_y - (i * spacing), "", color='#2ecc71', fontsize=18, fontweight='bold', family='monospace')
    manifest_texts.append(t)

# --- ANIMATION LOOP ---
def update(frame):
    global last_valid_x, last_valid_y, connection_lost, man_overboard, nan_count, last_data_time, serial_buffer
    
    try:
        if ser.in_waiting > 0:
            serial_buffer += ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
            
            if '\n' in serial_buffer:
                lines = serial_buffer.split('\n')
                serial_buffer = lines[-1] 
                
                latest_pos_line = None
                for line in reversed(lines[:-1]):
                    if "POS" in line:
                        latest_pos_line = line
                        break
                
                if latest_pos_line:
                    parts = latest_pos_line.split(',')
                    if len(parts) >= 5:
                        tag_id = parts[2]
                        raw_val_x = parts[3]
                        raw_val_y = parts[4]
                        
                        if tag_id not in active_tags and len(active_tags) < MAX_TAGS:
                            assigned_name = CREW_ROSTER[len(active_tags) % len(CREW_ROSTER)]
                            active_tags[tag_id] = {'name': assigned_name, 'status': 'safe'}

                        if "nan" in raw_val_x.lower() or "nan" in raw_val_y.lower():
                            nan_count += 1
                            if nan_count >= 50:
                                connection_lost = True
                        else:
                            nan_count = 0
                            connection_lost = False
                            last_data_time = time.time()
                            
                            x_m = float(raw_val_x)
                            y_m = float(raw_val_y)
                            
                            x_raw.append(x_m)
                            y_raw.append(y_m)
                            smooth_x = sum(x_raw) / len(x_raw)
                            smooth_y = sum(y_raw) / len(y_raw)
                            last_valid_x, last_valid_y = smooth_x, smooth_y
                            
                            if boat_path.contains_point((smooth_x, smooth_y)):
                                man_overboard = False
                                if tag_id in active_tags: active_tags[tag_id]['status'] = 'safe'
                            else:
                                man_overboard = True
                                if tag_id in active_tags: active_tags[tag_id]['status'] = 'alarm'
                            
    except Exception as e:
        pass 

    if time.time() - last_data_time > DATA_TIMEOUT and active_tags:
        connection_lost = True

    # --- UPDATE MANIFEST UI ---
    for i, (t_id, data) in enumerate(active_tags.items()):
        if i >= MAX_TAGS: break
        if connection_lost:
            manifest_texts[i].set_text(f"{data['name']:<14} [LOST]")
            manifest_texts[i].set_color('#8b0000')
        elif data['status'] == 'safe':
            manifest_texts[i].set_text(f"{data['name']:<14} [SAFE]")
            manifest_texts[i].set_color('#2ecc71')
        else:
            manifest_texts[i].set_text(f"{data['name']:<14} [DANGER]")
            manifest_texts[i].set_color('#e74c3c')

    # --- UPDATE RADAR UI & HARDWARE ---
    if not active_tags:
        return safe_scatter, alarm_scatter, status_text, timer_text, mob_line, mob_dist_text

    mob_lat, mob_lon = local_to_gps(last_valid_x, last_valid_y)
    distance_m = math.hypot(last_valid_x - center_x, last_valid_y - center_y)

    if connection_lost or man_overboard:
        safe_scatter.set_offsets([])
        alarm_scatter.set_offsets([(last_valid_x, last_valid_y)])
        
        if getattr(update, 'mob_start_time', None) is None:
            update.mob_start_time = time.time()
        elapsed_seconds = time.time() - update.mob_start_time
        
        # --- HARDWARE ALARM TRIGGER ---
        if hardware_active:
            if frame % 10 < 5:
                buzzer.play(3500)
                led_red.on()
                led_blue.off()
            else:
                buzzer.play(2500)
                led_red.off()
                led_blue.on()

        flash_color = '#e74c3c' if (frame % 10 < 5) else '#c0392b'
        if connection_lost: flash_color = 'red' if (frame % 10 < 5) else '#8b0000'

        status_text.set_color(flash_color)
        alarm_scatter.set_color(flash_color)
        mob_line.set_color(flash_color)
        mob_dist_text.set_color(flash_color)
        
        if connection_lost:
            status_text.set_text(f"!!! CRITICAL: SIGNAL LOST !!!\nLAST KNOWN: {mob_lat:.6f}, {mob_lon:.6f}")
        else:
            status_text.set_text(f"!!! PERIMETER BREACH !!!\nLIVE LOCATION: {mob_lat:.6f}, {mob_lon:.6f}")
            
        timer_text.set_text(f"TIME SINCE EVENT: {elapsed_seconds:.1f}s")
        
        mob_line.set_data([center_x, last_valid_x], [center_y, last_valid_y])
        mob_dist_text.set_position(((center_x + last_valid_x) / 2, (center_y + last_valid_y) / 2))
        mob_dist_text.set_text(f"{distance_m:.1f}m")
        
        required_zoom = max(abs(last_valid_x - center_x)/BASE_X_LIMIT, abs(last_valid_y - center_y)/BASE_Y_LIMIT) + 0.5
        target_zoom = max(1.0, required_zoom)
        
    else:
        # --- SAFE STATE: SILENCE HARDWARE ---
        if hardware_active:
            buzzer.stop()
            led_red.off()
            led_blue.off()
            
        update.mob_start_time = None
        safe_scatter.set_offsets([(last_valid_x, last_valid_y)])
        alarm_scatter.set_offsets([])
        
        status_text.set_color('#2ecc71')
        status_text.set_text(f"STATUS: SECURE ZONE")
        timer_text.set_text("")
        mob_line.set_data([], [])
        mob_dist_text.set_text("")
        target_zoom = 1.0

    if not hasattr(update, 'current_zoom'): update.current_zoom = 1.0
    update.current_zoom += (target_zoom - update.current_zoom) * 0.1
    ax.set_xlim(center_x - BASE_X_LIMIT * update.current_zoom, center_x + BASE_X_LIMIT * update.current_zoom)
    ax.set_ylim(center_y - BASE_Y_LIMIT * update.current_zoom, center_y + BASE_Y_LIMIT * update.current_zoom)

    return safe_scatter, alarm_scatter, status_text, timer_text, mob_line, mob_dist_text

ani = FuncAnimation(fig, update, interval=33, blit=False, cache_frame_data=False)

plt.show()

# Clean up hardware on exit
if hardware_active:
    buzzer.stop()
    led_red.off()
    led_blue.off()
    
try:
    ser.close()
except:
    pass