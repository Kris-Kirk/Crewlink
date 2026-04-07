import serial
import serial.tools.list_ports
import matplotlib
matplotlib.use('TkAgg') 
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.path import Path
from matplotlib.animation import FuncAnimation
from matplotlib.widgets import Button
import collections
import sys
import time
import math
import numpy as np 

# ==========================================
# --- ENVIRONMENT CONFIGURATION TOGGLES ---
# ==========================================
RUNNING_ON_PI = False    
SIMULATION_MODE = False  

# --- HARDWARE ALARM SETUP ---
hw_alarms_active = False
if RUNNING_ON_PI:
    try:
        from gpiozero import LED, TonalBuzzer
        from gpiozero.tones import Tone
        led = LED(4)
        buzzer1 = TonalBuzzer(22)
        buzzer2 = TonalBuzzer(26)
        hw_alarms_active = True
        print("PI MODE: Hardware alarms initialized.")
    except Exception as e:
        print(f"PI MODE Warning: Hardware alarm failure ({e}).")

# --- GPS CONFIGURATION ---
BASE_LAT = 49.26628096481008
BASE_LON = -123.2548719012252

plt.style.use('dark_background')

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
    if ports:
        return ports[0].device 
    return None

discovered_anchors = {}

if not SIMULATION_MODE:
    SERIAL_PORT = "/dev/serial0" if RUNNING_ON_PI else get_dwm_port()
        
    if not SERIAL_PORT:
        print("Error: No UWB module detected. Check your connections.")
        sys.exit()

    try:
        ser = serial.Serial(SERIAL_PORT, 115200, timeout=0.01)
        ser.reset_input_buffer()
        print(f"Connected to {SERIAL_PORT}. Halting data...")
        ser.write(b'\r\r')
        time.sleep(0.5)
        ser.reset_input_buffer()
        
        print("Requesting Anchor Map (la)...")
        ser.write(b'la\r')
        time.sleep(1) 
        
        la_data = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
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
                        
        print("Starting Live Radar (lec)...")
        ser.write(b'\r\r') 
        time.sleep(0.5)
        # Reverted back to the LEC comma-separated format
        ser.write(b'lec\r') 
    except Exception as e:
        print(f"Error connecting: {e}")
        sys.exit()
else:
    print("Running in DEMO MODE.")
    discovered_anchors = {"ANC1": (0, 0), "ANC2": (5.0, 0), "ANC3": (2.5, 8.0)}

# --- DYNAMIC CENTERING ---
if discovered_anchors:
    center_x = sum([pos[0] for pos in discovered_anchors.values()]) / len(discovered_anchors)
    center_y = sum([pos[1] for pos in discovered_anchors.values()]) / len(discovered_anchors)
else:
    center_x, center_y = 0.0, 0.0

# --- MULTI-TAG DATA DICTIONARY ---
active_tags = {}
CREW_ROSTER = ["Kris", "Juliana", "John", "Kyle", "Alex"]
DATA_TIMEOUT = 2.0  
serial_buffer = ""
sim_step = 0
mob_start_time = None

# --- GEOFENCE (Meters) ---
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
fig.canvas.manager.set_window_title("Dashboard")

if RUNNING_ON_PI:
    try:
        manager = fig.canvas.manager
        manager.window.attributes('-fullscreen', True)
        manager.window.config(cursor="none")
    except Exception:
        pass 

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

ax.add_patch(patches.Polygon(DYNAMIC_BOAT_COORDS, closed=True, fill=True, color='#0a3d62', alpha=0.6, zorder=2))
ax.add_patch(patches.Polygon(DYNAMIC_BOAT_COORDS, closed=True, fill=False, color='#3c6382', linewidth=2, zorder=2))
ax.add_patch(patches.Polygon(DYNAMIC_CABIN_COORDS, closed=True, fill=True, color='#15537d', alpha=0.5, zorder=2))

if discovered_anchors:
    anch_x = [pos[0] for pos in discovered_anchors.values()]
    anch_y = [pos[1] for pos in discovered_anchors.values()]
    ax.scatter(anch_x, anch_y, marker='s', color='#f39c12', s=100, zorder=4)
    for a_id, coords in discovered_anchors.items():
        ax.text(coords[0] + 0.3, coords[1], a_id, fontsize=9, color='#f39c12', fontweight='bold')

status_text = ax.text(0.5, 0.96, "STATUS: WAITING FOR TAGS...", transform=ax.transAxes, 
                      ha='center', va='top', fontsize=16, fontweight='bold', 
                      color='yellow', bbox=dict(facecolor='black', alpha=0.8, edgecolor='none'), zorder=10)

timer_text = ax.text(0.5, 0.88, "", transform=ax.transAxes, 
                     ha='center', va='top', fontsize=14, fontweight='bold', color='#f1c40f', zorder=10)

mob_line, = ax.plot([], [], color='#e74c3c', linestyle='--', linewidth=2, zorder=3)
mob_dist_text = ax.text(0, 0, "", color='#e74c3c', fontsize=11, fontweight='bold', zorder=7)

safe_scatter = ax.scatter([], [], color='#2ecc71', s=80, edgecolors='white', zorder=5)
alarm_scatter = ax.scatter([], [], color='#e74c3c', s=150, edgecolors='white', linewidth=2, zorder=6)

ax_side = fig.add_subplot(gs[1])
ax_side.axis('off') 
ax_side.set_title("SYSTEM MANIFEST", fontsize=20, fontweight='bold', color='white', y=0.98)

MAX_TAGS = 5
manifest_texts = []
start_y = 0.92
spacing = 0.07 
for i in range(MAX_TAGS):
    t = ax_side.text(0.05, start_y - (i * spacing), "", color='#2ecc71', fontsize=18, fontweight='bold', family='monospace')
    manifest_texts.append(t)

ax_exit = plt.axes([0.85, 0.02, 0.12, 0.08])
btn_exit = Button(ax_exit, 'EXIT APP', color='#ff4757', hovercolor='#ff6b81')
btn_exit.label.set_fontsize(12)
btn_exit.label.set_fontweight('bold')

def exit_app(event):
    if not SIMULATION_MODE: ser.close()
    if hw_alarms_active: led.off(); buzzer1.stop(); buzzer2.stop()
    sys.exit()
btn_exit.on_clicked(exit_app)

# --- THE LIGHTWEIGHT UPDATE ENGINE ---
def update(frame):
    global serial_buffer, sim_step, mob_start_time
    
    current_time = time.time()
    lines = []
    
    if SIMULATION_MODE:
        sim_step += 1
        t1_x = center_x + math.sin(sim_step * 0.1) * 0.8
        t1_y = center_y + sim_step * 0.02
        t2_x = center_x - 0.5
        t2_y = center_y - 1.0 + (sim_step * 0.05) if sim_step > 50 else center_y - 1.0
        
        if sim_step > 100: t2_x, t2_y = center_x + 5.0, center_y + 2.0 
        
        # Simulating standard LEC formatting
        lines = [
            f"POS,0,TAG-01,{t1_x},{t1_y}",
            f"POS,0,TAG-02,{t2_x},{t2_y}"
        ]
        
    elif ser.in_waiting > 0:
        serial_buffer += ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
        if '\n' in serial_buffer:
            lines = serial_buffer.split('\n')
            serial_buffer = lines[-1] 
            lines = lines[:-1]
            
    # --- RESTORED CSV PARSING BLOCK ---
    # This loop processes EVERY line in the buffer sequentially.
    for line in lines:
        if "POS" in line:
            parts = line.split(',')
            # Ensure the line has enough data to prevent indexing errors
            if len(parts) >= 5:
                tag_id = parts[2]
                raw_val_x = parts[3]
                raw_val_y = parts[4]
                
                if tag_id not in active_tags and len(active_tags) < MAX_TAGS:
                    assigned_name = CREW_ROSTER[len(active_tags) % len(CREW_ROSTER)]
                    active_tags[tag_id] = {'name': assigned_name, 'x': 0.0, 'y': 0.0, 'status': 'safe', 'last_time': current_time, 'nan_count': 0}

                if "nan" in raw_val_x.lower() or "nan" in raw_val_y.lower():
                    active_tags[tag_id]['nan_count'] += 1
                    if active_tags[tag_id]['nan_count'] >= 50:
                        active_tags[tag_id]['status'] = 'lost'
                else:
                    active_tags[tag_id]['nan_count'] = 0
                    active_tags[tag_id]['last_time'] = current_time
                    
                    try:
                        x_m, y_m = float(raw_val_x), float(raw_val_y)
                        old_x, old_y = active_tags[tag_id]['x'], active_tags[tag_id]['y']
                        new_x = x_m if old_x == 0.0 else (old_x * 0.6) + (x_m * 0.4)
                        new_y = y_m if old_y == 0.0 else (old_y * 0.6) + (y_m * 0.4)
                        
                        active_tags[tag_id]['x'], active_tags[tag_id]['y'] = new_x, new_y
                        
                        if boat_path.contains_point((new_x, new_y)):
                            active_tags[tag_id]['status'] = 'safe'
                        else:
                            active_tags[tag_id]['status'] = 'alarm'
                    except ValueError:
                        pass # Ignore malformed float conversions safely

    for t_id, data in active_tags.items():
        if current_time - data['last_time'] > DATA_TIMEOUT:
            data['status'] = 'lost'

    safe_coords, alarm_coords = [], []
    global_alarm, global_lost = False, False
    target_mob_x, target_mob_y = 0.0, 0.0

    for i, (t_id, data) in enumerate(active_tags.items()):
        if i >= MAX_TAGS: break
        
        if data['status'] == 'lost':
            global_lost = True
            alarm_coords.append((data['x'], data['y']))
            target_mob_x, target_mob_y = data['x'], data['y']
            manifest_texts[i].set_text(f"{data['name']:<14} [LOST]")
            manifest_texts[i].set_color('#8b0000')
        elif data['status'] == 'safe':
            safe_coords.append((data['x'], data['y']))
            manifest_texts[i].set_text(f"{data['name']:<14} [SAFE]")
            manifest_texts[i].set_color('#2ecc71')
        else:
            global_alarm = True
            alarm_coords.append((data['x'], data['y']))
            target_mob_x, target_mob_y = data['x'], data['y']
            manifest_texts[i].set_text(f"{data['name']:<14} [DANGER]")
            manifest_texts[i].set_color('#e74c3c')

    safe_scatter.set_offsets(safe_coords if safe_coords else np.empty((0, 2)))
    alarm_scatter.set_offsets(alarm_coords if alarm_coords else np.empty((0, 2)))

    if global_lost or global_alarm:
        if mob_start_time is None: mob_start_time = current_time
        flash = (frame % 10 < 5)
        color = 'red' if global_lost else ('#e74c3c' if flash else '#c0392b')
        
        status_text.set_color(color)
        alarm_scatter.set_color(color)
        mob_line.set_color(color)
        mob_dist_text.set_color(color)
        
        if global_lost:
            status_text.set_text("!!! CRITICAL: SIGNAL LOST !!!")
            if hw_alarms_active:
                led.on() if flash else led.off()
                if flash: buzzer1.play(Tone('A5')); buzzer2.stop()
                else: buzzer1.stop(); buzzer2.play(Tone('E5'))
        else:
            status_text.set_text("!!! BOUNDARY ALARM !!!")
            if hw_alarms_active:
                led.on() if flash else led.off()
                if flash: buzzer1.play(Tone('C5')); buzzer2.stop()
                else: buzzer1.stop(); buzzer2.stop()
            
        timer_text.set_text(f"TIME SINCE EVENT: {current_time - mob_start_time:.1f}s")
        mob_line.set_data([center_x, target_mob_x], [center_y, target_mob_y])
        mob_dist_text.set_position(((center_x + target_mob_x) / 2, (center_y + target_mob_y) / 2))
        mob_dist_text.set_text(f"{math.hypot(target_mob_x - center_x, target_mob_y - center_y):.1f}m")
        
    else:
        mob_start_time = None
        status_text.set_color('#2ecc71')
        status_text.set_text(f"STATUS: SECURE")
        timer_text.set_text("")
        mob_line.set_data([], [])
        mob_dist_text.set_text("")
        if hw_alarms_active: led.off(); buzzer1.stop(); buzzer2.stop()

    return (safe_scatter, alarm_scatter, status_text, timer_text, mob_line, mob_dist_text) + tuple(manifest_texts)

ani = FuncAnimation(fig, update, interval=33, blit=True, cache_frame_data=False)

plt.show()