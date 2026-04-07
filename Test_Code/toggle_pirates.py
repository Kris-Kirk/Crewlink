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
import re 

# ==========================================
# --- ENVIRONMENT CONFIGURATION TOGGLES ---
# ==========================================
RUNNING_ON_PI = True    
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
        return port.device 
    return None

discovered_anchors = {}

if not SIMULATION_MODE:
    SERIAL_PORT = "/dev/serial0" if RUNNING_ON_PI else get_dwm_port()
    if not SERIAL_PORT:
        print("Error: No UWB module detected.")
        sys.exit()
    try:
        ser = serial.Serial(SERIAL_PORT, 115200, timeout=0.01)
        ser.reset_input_buffer()
        ser.write(b'\r\r')
        time.sleep(0.5)
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
        ser.write(b'les\r')
    except Exception as e:
        print(f"Error connecting: {e}"); sys.exit()
else:
    discovered_anchors = {"ANC1": (0, 0), "ANC2": (5.0, 0), "ANC3": (2.5, 8.0)}

if discovered_anchors:
    center_x = sum([pos[0] for pos in discovered_anchors.values()]) / len(discovered_anchors)
    center_y = sum([pos[1] for pos in discovered_anchors.values()]) / len(discovered_anchors)
else:
    center_x, center_y = 0.0, 0.0

# --- GLOBAL STATE ---
active_tags = {}
CREW_ROSTER = ["Kris", "Juliana", "John", "Kyle", "Alex"]
DATA_TIMEOUT = 2.0  
serial_buffer = ""
sim_step = 0
mob_start_time = None
TAG_MONITOR_LIMIT = 2 # Default to 2, can be toggled to 1

# --- THE BOAT ---
BOAT_COORDS = [(0.0, 5.0), (0.5, 4.6), (1.0, 3.8), (1.3, 2.5), (1.5, 1.0), (1.5, -3.0), (1.3, -4.8), (1.2, -5.0), (0.6, -5.0), (0.6, -4.8), (-0.6, -4.8), (-0.6, -5.0), (-1.2, -5.0), (-1.3, -4.8), (-1.5, -3.0), (-1.5, 1.0), (-1.3, 2.5), (-1.0, 3.8), (-0.5, 4.6)]
DYNAMIC_BOAT_COORDS = [(x + center_x, y + center_y) for x, y in BOAT_COORDS]
boat_path = Path(DYNAMIC_BOAT_COORDS)

# --- GUI LAYOUT ---
fig = plt.figure(figsize=(12, 8))
gs = fig.add_gridspec(1, 2, width_ratios=[3, 1.4]) 
ax = fig.add_subplot(gs[0])
ax.set_aspect('equal')
ax.add_patch(patches.Polygon(DYNAMIC_BOAT_COORDS, closed=True, fill=True, color='#0a3d62', alpha=0.6))

# Status and GPS displays
status_text = ax.text(0.5, 0.96, "WAITING...", transform=ax.transAxes, ha='center', fontsize=14, fontweight='bold', color='yellow', bbox=dict(facecolor='black', alpha=0.8))
timer_text = ax.text(0.5, 0.90, "", transform=ax.transAxes, ha='center', fontsize=12, color='#f1c40f')
gps_display = ax.text(0.5, 0.05, "", transform=ax.transAxes, ha='center', fontsize=12, fontweight='bold', color='orange', bbox=dict(facecolor='black', alpha=0.7))

mob_line, = ax.plot([], [], color='red', linestyle='--')
mob_dist_text = ax.text(0, 0, "", color='red', fontsize=10, fontweight='bold')
safe_scatter = ax.scatter([], [], color='#2ecc71', s=80)
alarm_scatter = ax.scatter([], [], color='#e74c3c', s=150)

ax_side = fig.add_subplot(gs[1]); ax_side.axis('off')
manifest_texts = [ax_side.text(0.05, 0.85 - (i * 0.07), "", fontsize=14, family='monospace') for i in range(5)]

# --- BUTTONS ---
ax_exit = plt.axes([0.75, 0.02, 0.1, 0.05])
btn_exit = Button(ax_exit, 'EXIT', color='#ff4757')

ax_toggle = plt.axes([0.64, 0.02, 0.1, 0.05])
btn_toggle = Button(ax_toggle, '1 vs 2 TAGS', color='#2f3542', hovercolor='#57606f')
btn_toggle.label.set_color('white')

ax_music = plt.axes([0.53, 0.02, 0.1, 0.05])
btn_music = Button(ax_music, '🏴‍☠️ THEME', color='#2f3542', hovercolor='#57606f')
btn_music.label.set_color('white')

def toggle_tags(event):
    global TAG_MONITOR_LIMIT, active_tags
    TAG_MONITOR_LIMIT = 1 if TAG_MONITOR_LIMIT == 2 else 2
    # Clean up tags that are no longer being monitored
    keys_to_remove = [t_id for i, t_id in enumerate(active_tags.keys()) if i >= TAG_MONITOR_LIMIT]
    for k in keys_to_remove: del active_tags[k]
    print(f"Monitoring limit set to: {TAG_MONITOR_LIMIT}")

def play_pirates(event):
    print("Yarr! Playing the Captain's theme...")
    if hw_alarms_active:
        melody = [('D4', 0.2), ('F4', 0.2), ('G4', 0.4), ('G4', 0.2), ('G4', 0.2), ('A4', 0.2), ('Bb4', 0.4), ('Bb4', 0.2), ('Bb4', 0.2), ('C5', 0.2), ('A4', 0.4), ('A4', 0.2), ('G4', 0.2), ('F4', 0.2), ('G4', 0.6)]
        for note, dur in melody:
            buzzer1.play(Tone(note))
            time.sleep(dur)
            buzzer1.stop()

btn_exit.on_clicked(lambda e: sys.exit())
btn_toggle.on_clicked(toggle_tags)
btn_music.on_clicked(play_pirates)

def update(frame):
    global serial_buffer, sim_step, mob_start_time
    current_time = time.time()
    lines = []
    
    if SIMULATION_MODE:
        sim_step += 1
        t1_x, t1_y = center_x + math.sin(sim_step * 0.1), center_y + 1.0
        t2_x, t2_y = (center_x + 6.0, center_y + 2.0) if sim_step > 60 else (center_x - 1.0, center_y)
        lines = [f"pos(0) : {t1_x}, {t1_y}", f"pos(1) : {t2_x}, {t2_y}"]
    elif ser.in_waiting > 0:
        serial_buffer += ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
        if '\n' in serial_buffer:
            parts = serial_buffer.split('\n')
            lines, serial_buffer = parts[:-1], parts[-1]

    for line in lines:
        match = re.search(r'pos\((\w+)\).*?([-+]?\d*\.?\d+|nan)[,\s]+([-+]?\d*\.?\d+|nan)', line, re.IGNORECASE)
        if match:
            idx = int(match.group(1))
            if idx >= TAG_MONITOR_LIMIT: continue # Ignore if toggled off
            
            tag_id = f"TAG-{str(idx).zfill(2)}"
            if tag_id not in active_tags:
                active_tags[tag_id] = {'name': CREW_ROSTER[idx], 'x': 0.0, 'y': 0.0, 'status': 'safe', 'last_time': current_time}
            
            raw_x, raw_y = match.group(2), match.group(3)
            if "nan" not in raw_x.lower():
                active_tags[tag_id]['x'], active_tags[tag_id]['y'] = float(raw_x), float(raw_y)
                active_tags[tag_id]['last_time'] = current_time
                active_tags[tag_id]['status'] = 'safe' if boat_path.contains_point((float(raw_x), float(raw_y))) else 'alarm'

    safe_coords, alarm_coords = [], []
    mob_tag = None

    for i, (t_id, data) in enumerate(active_tags.items()):
        if i >= TAG_MONITOR_LIMIT: continue
        
        # Check Timeout
        if current_time - data['last_time'] > DATA_TIMEOUT: data['status'] = 'lost'

        if data['status'] == 'safe':
            safe_coords.append((data['x'], data['y']))
            manifest_texts[i].set_text(f"{data['name']:<10} [SAFE]"); manifest_texts[i].set_color('#2ecc71')
        else:
            alarm_coords.append((data['x'], data['y']))
            mob_tag = data
            manifest_texts[i].set_text(f"{data['name']:<10} [{data['status'].upper()}]"); manifest_texts[i].set_color('red')

    safe_scatter.set_offsets(safe_coords if safe_coords else np.empty((0, 2)))
    alarm_scatter.set_offsets(alarm_coords if alarm_coords else np.empty((0, 2)))

    if mob_tag:
        if mob_start_time is None: mob_start_time = current_time
        lat, lon = local_to_gps(mob_tag['x'], mob_tag['y'])
        status_text.set_text(f"!!! {mob_tag['name'].upper()} OVERBOARD !!!")
        gps_display.set_text(f"MOB GPS: {lat:.8f}, {lon:.8f}")
        timer_text.set_text(f"ELAPSED: {current_time - mob_start_time:.1f}s")
        mob_line.set_data([center_x, mob_tag['x']], [center_y, mob_tag['y']])
    else:
        mob_start_time = None
        status_text.set_text("STATUS: ALL CREW SAFE")
        gps_display.set_text(""); timer_text.set_text(""); mob_line.set_data([], [])

    return (safe_scatter, alarm_scatter, status_text, timer_text, gps_display) + tuple(manifest_texts)

ani = FuncAnimation(fig, update, interval=100, blit=True)
plt.show()
