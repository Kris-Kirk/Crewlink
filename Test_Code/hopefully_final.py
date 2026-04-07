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
import threading # Added for the surprise song

# ==========================================
# --- ENVIRONMENT CONFIGURATION TOGGLES ---
# ==========================================
RUNNING_ON_PI = True    
SIMULATION_MODE = False  

# --- HARDWARE ALARM SETUP ---
hw_alarms_active = False
buzzers_muted = False
tag_count_mode = 1 # 1 = Solo, 2 = Duo

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
    return ports[0].device if ports else None

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
        ser.reset_input_buffer()
        ser.write(b'la\r')
        time.sleep(1) 
        
        la_data = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
        for line in la_data.split('\n'):
            if "id=" in line and "pos=" in line:
                parts = line.split()
                a_id = [x for x in parts if x.startswith("id=")][0].split("=")[1][-4:]
                a_pos = [x for x in parts if x.startswith("pos=")][0].split("=")[1].split(':')
                discovered_anchors[a_id] = (float(a_pos[0]), float(a_pos[1]))
                        
        ser.write(b'\r\r') 
        time.sleep(0.5)
        ser.write(b'les\r') 
    except Exception as e:
        print(f"Error: {e}")
        sys.exit()
else:
    discovered_anchors = {"ANC1": (0, 0), "ANC2": (5.0, 0), "ANC3": (2.5, 8.0)}

# --- DYNAMIC CENTERING ---
center_x = sum([p[0] for p in discovered_anchors.values()])/len(discovered_anchors) if discovered_anchors else 0
center_y = sum([p[1] for p in discovered_anchors.values()])/len(discovered_anchors) if discovered_anchors else 0

active_tags = {}
CREW_ROSTER = ["KRIS", "JULIANA", "JOHN", "KYLE", "ALEX"]
DATA_TIMEOUT = 2.0  
serial_buffer = ""
sim_step = 0
mob_start_time = None

# --- THE BOAT (Meters) ---
BOAT_COORDS = [(0.0, 5.0), (0.5, 4.6), (1.0, 3.8), (1.3, 2.5), (1.5, 1.0), (1.5, -3.0), (1.3, -4.8), (1.2, -5.0), (0.6, -5.0), (0.6, -4.8), (-0.6, -4.8), (-0.6, -5.0), (-1.2, -5.0), (-1.3, -4.8), (-1.5, -3.0), (-1.5, 1.0), (-1.3, 2.5), (-1.0, 3.8), (-0.5, 4.6)]
DYNAMIC_BOAT_COORDS = [(x + center_x, y + center_y) for x, y in BOAT_COORDS]
boat_path = Path(DYNAMIC_BOAT_COORDS)

# --- GUI LAYOUT ---
fig = plt.figure(figsize=(12, 7))
if RUNNING_ON_PI:
    try:
        manager = fig.canvas.manager
        manager.window.attributes('-fullscreen', True); manager.window.config(cursor="none")
    except: pass 

# Expanded boat plot area (0.8 vs 0.2)
gs = fig.add_gridspec(1, 2, width_ratios=[4, 1]) 
ax = fig.add_subplot(gs[0])
ax.set_title("CREWLINK MONITORING", fontsize=14, fontweight='bold', color='cyan')
ax.set_aspect('equal')
ax.set_xlim(center_x - 8, center_x + 8); ax.set_ylim(center_y - 6, center_y + 6)

ax.add_patch(patches.Polygon(DYNAMIC_BOAT_COORDS, closed=True, fill=True, color='#0a3d62', alpha=0.6, zorder=2))
ax.add_patch(patches.Polygon(DYNAMIC_BOAT_COORDS, closed=True, fill=False, color='#3c6382', linewidth=2, zorder=2))

status_text = ax.text(0.5, 0.96, "SEARCHING...", transform=ax.transAxes, ha='center', va='top', fontsize=12, fontweight='bold', color='yellow', bbox=dict(facecolor='black', alpha=0.8), zorder=10)
gps_datum_text = ax.text(0.5, 0.04, "", transform=ax.transAxes, ha='center', fontsize=10, color='#e74c3c', fontweight='bold', zorder=10)

mob_line, = ax.plot([], [], color='#e74c3c', linestyle='--', linewidth=2, zorder=3)
safe_scatter = ax.scatter([], [], color='#2ecc71', s=80, edgecolors='white', zorder=5)
alarm_scatter = ax.scatter([], [], color='#e74c3c', s=150, edgecolors='white', linewidth=2, zorder=6)

ax_side = fig.add_subplot(gs[1])
ax_side.axis('off')
ax_side.set_title("MANIFEST", fontsize=16, fontweight='bold', color='white')
# Reduced spacing and font size to fit Pi screen
manifest_texts = [ax_side.text(0.05, 0.85 - (i * 0.15), "", color='#2ecc71', fontsize=11, fontweight='bold', family='monospace') for i in range(5)]

# --- BUTTONS ---
ax_exit = plt.axes([0.9, 0.02, 0.08, 0.06])
btn_exit = Button(ax_exit, 'EXIT', color='#440000', hovercolor='red')
btn_exit.on_clicked(lambda e: sys.exit())

ax_mute = plt.axes([0.81, 0.02, 0.08, 0.06])
btn_mute = Button(ax_mute, 'MUTE', color='#f39c12')
def toggle_mute(e):
    global buzzers_muted; buzzers_muted = not buzzers_muted
    btn_mute.label.set_text('MUTED' if buzzers_muted else 'MUTE')
btn_mute.on_clicked(toggle_mute)

ax_mode = plt.axes([0.72, 0.02, 0.08, 0.06])
btn_mode = Button(ax_mode, '1 TAG', color='#3498db')
def toggle_tags(e):
    global tag_count_mode; tag_count_mode = 2 if tag_count_mode == 1 else 1
    btn_mode.label.set_text(f'{tag_count_mode} TAG')
btn_mode.on_clicked(toggle_tags)

ax_song = plt.axes([0.63, 0.02, 0.08, 0.06])
btn_song = Button(ax_song, 'SONG', color='#8e44ad')

def play_pirates():
    if not hw_alarms_active: return
    melody = [('D4', 0.15), ('D4', 0.15), ('D4', 0.30), ('E4', 0.15), ('F4', 0.30), ('F4', 0.30), ('F4', 0.30), ('G4', 0.15), ('E4', 0.30), ('E4', 0.30), ('D4', 0.15), ('C4', 0.15), ('D4', 0.40)]
    global buzzers_muted; old_mute = buzzers_muted; buzzers_muted = True
    for i, (n, d) in enumerate(melody):
        bz = buzzer1 if i % 2 == 0 else buzzer2
        try: bz.play(n)
        except: pass
        time.sleep(d * 0.85); bz.stop(); time.sleep(d * 0.15)
    buzzers_muted = old_mute
btn_song.on_clicked(lambda e: threading.Thread(target=play_pirates, daemon=True).start())

# --- ENGINE ---
def update(frame):
    global serial_buffer, sim_step, mob_start_time
    current_time, lines = time.time(), []
    
    try:
        if SIMULATION_MODE:
            sim_step += 1
            lines = [f"pos(0):[{center_x + math.sin(sim_step*0.1)*0.8}, {center_y + sim_step*0.02}]", 
                     f"pos(1):[{center_x + 5.0 if sim_step > 100 else center_x - 0.5}, {center_y + 2.0 if sim_step > 100 else center_y - 1.0}]"]
        elif ser.in_waiting > 0:
            serial_buffer += ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
            if '\n' in serial_buffer:
                tmp = serial_buffer.split('\n')
                serial_buffer, lines = tmp[-1], tmp[:-1]
    except: pass

    for line in lines:
        match = re.search(r'pos\((\w+)\).*?([-+]?\d*\.?\d+|nan)[,\s]+([-+]?\d*\.?\d+|nan)', line, re.IGNORECASE)
        if match:
            idx = int(match.group(1))
            if idx >= tag_count_mode: continue # Ignore tags not selected in mode
            
            t_id = f"TAG-{idx}"
            if t_id not in active_tags:
                active_tags[t_id] = {'name': CREW_ROSTER[idx], 'x': 0, 'y': 0, 'status': 'safe', 'last': current_time}
            
            try:
                nx, ny = float(match.group(2)), float(match.group(3))
                active_tags[t_id].update({'x': nx, 'y': ny, 'last': current_time, 'status': 'safe' if boat_path.contains_point((nx, ny)) else 'alarm'})
            except: continue

    safe_c, alarm_c, g_alarm, g_lost, tx, ty = [], [], False, False, 0, 0
    # Filter to only show relevant tags for the current mode
    for i in range(5): manifest_texts[i].set_text("")
    
    for i, (tid, d) in enumerate(active_tags.items()):
        if int(tid.split('-')[1]) >= tag_count_mode: continue # Hide extra tags
        
        if current_time - d['last'] > DATA_TIMEOUT: d['status'] = 'lost'
        
        manifest_texts[i].set_text(f"{d['name']}\n{d['status'].upper()}")
        manifest_texts[i].set_color('#2ecc71' if d['status'] == 'safe' else '#e74c3c')
        
        if d['status'] == 'safe': safe_c.append((d['x'], d['y']))
        else:
            alarm_c.append((d['x'], d['y'])); tx, ty = d['x'], d['y']
            if d['status'] == 'lost': g_lost = True
            else: g_alarm = True

    safe_scatter.set_offsets(safe_c if safe_c else np.empty((0,2)))
    alarm_scatter.set_offsets(alarm_c if alarm_c else np.empty((0,2)))

    if g_lost or g_alarm:
        if mob_start_time is None: mob_start_time = current_time
        flash = (frame % 10 < 5); clr = 'red' if g_lost else '#e74c3c'
        status_text.set_text("SIGNAL LOST" if g_lost else "MAN OVERBOARD"); status_text.set_color(clr if flash else 'white')
        
        lat, lon = local_to_gps(tx, ty)
        gps_datum_text.set_text(f"DATUM: {lat:.6f}, {lon:.6f} | DIST: {math.hypot(tx-center_x, ty-center_y):.1f}m")
        mob_line.set_data([center_x, tx], [center_y, ty]); mob_line.set_color(clr)
        
        if hw_alarms_active and not buzzers_muted:
            if flash: buzzer1.play('A5' if g_lost else 'C5')
            else: buzzer1.stop()
    else:
        mob_start_time = None; status_text.set_text("SYSTEM SECURE"); status_text.set_color('#2ecc71')
        gps_datum_text.set_text(""); mob_line.set_data([], [])
        if hw_alarms_active: buzzer1.stop()

    return (safe_scatter, alarm_scatter, status_text, gps_datum_text, mob_line) + tuple(manifest_texts)

ani = FuncAnimation(fig, update, interval=33, blit=True)
plt.show()
