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
import threading 

# ==========================================
# --- ENVIRONMENT CONFIGURATION TOGGLES ---
# ==========================================
RUNNING_ON_PI = True    
SIMULATION_MODE = False  

# --- HARDWARE ALARM SETUP ---
hw_alarms_active = False
buzzers_muted = False
tag_count_mode = 1  # Default to 1 Tag Mode

if RUNNING_ON_PI:
    try:
        from gpiozero import LED, TonalBuzzer
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
                a_id, a_pos = "", ""
                for p in parts:
                    if p.startswith("id="): a_id = p.split("=")[1][-4:] 
                    elif p.startswith("pos="): a_pos = p.split("=")[1]
                if a_id and a_pos:
                    coords = a_pos.split(':')
                    if len(coords) >= 2:
                        discovered_anchors[a_id] = (float(coords[0]), float(coords[1]))
        
        ser.write(b'\r\r') 
        time.sleep(0.5)
        ser.write(b'lec\r') 
    except Exception as e:
        print(f"Error connecting: {e}")
        sys.exit()
else:
    discovered_anchors = {"ANC1": (0, 0), "ANC2": (5.0, 0), "ANC3": (2.5, 8.0)}

# --- DYNAMIC CENTERING ---
center_x = sum([pos[0] for pos in discovered_anchors.values()]) / len(discovered_anchors) if discovered_anchors else 0.0
center_y = sum([pos[1] for pos in discovered_anchors.values()]) / len(discovered_anchors) if discovered_anchors else 0.0

# --- MULTI-TAG DATA ---
active_tags = {}
CREW_ROSTER = ["Kris", "Juliana", "John", "Kyle", "Alex"]
DATA_TIMEOUT = 2.0  
serial_buffer = ""
sim_step = 0
mob_start_time = None

# --- THE BOAT (Meters) ---
BOAT_COORDS = [(0.0, 5.0), (0.5, 4.6), (1.0, 3.8), (1.3, 2.5), (1.5, 1.0), (1.5, -3.0), (1.3, -4.8), (1.2, -5.0), (0.6, -5.0), (0.6, -4.8), (-0.6, -4.8), (-0.6, -5.0), (-1.2, -5.0), (-1.3, -4.8), (-1.5, -3.0), (-1.5, 1.0), (-1.3, 2.5), (-1.0, 3.8), (-0.5, 4.6)]
CABIN_COORDS = [(0.0, 2.2), (0.9, 1.5), (0.9, -2.5), (-0.9, -2.5), (-0.9, 1.5)]
DYNAMIC_BOAT_COORDS = [(x + center_x, y + center_y) for x, y in BOAT_COORDS]
DYNAMIC_CABIN_COORDS = [(x + center_x, y + center_y) for x, y in CABIN_COORDS]
boat_path = Path(DYNAMIC_BOAT_COORDS)

# --- GUI LAYOUT ---
fig = plt.figure(figsize=(12, 7))
if RUNNING_ON_PI:
    try:
        manager = fig.canvas.manager
        manager.window.attributes('-fullscreen', True)
        manager.window.config(cursor="none")
    except: pass 

gs = fig.add_gridspec(1, 2, width_ratios=[3, 1.4]) 
ax = fig.add_subplot(gs[0])
ax.set_title("CREWLINK MONITORING", fontsize=16, fontweight='bold', color='cyan')
ax.set_aspect('equal')
ax.set_xlim(center_x - 8.0, center_x + 8.0)
ax.set_ylim(center_y - 6.0, center_y + 6.0)

ax.add_patch(patches.Polygon(DYNAMIC_BOAT_COORDS, closed=True, fill=True, color='#0a3d62', alpha=0.6, zorder=2))
ax.add_patch(patches.Polygon(DYNAMIC_BOAT_COORDS, closed=True, fill=False, color='#3c6382', linewidth=2, zorder=2))
ax.add_patch(patches.Polygon(DYNAMIC_CABIN_COORDS, closed=True, fill=True, color='#15537d', alpha=0.5, zorder=2))

status_text = ax.text(0.5, 0.96, "STATUS: SEARCHING...", transform=ax.transAxes, ha='center', va='top', fontsize=16, fontweight='bold', color='yellow', bbox=dict(facecolor='black', alpha=0.8, edgecolor='none'), zorder=10)
timer_text = ax.text(0.5, 0.88, "", transform=ax.transAxes, ha='center', va='top', fontsize=14, fontweight='bold', color='#f1c40f', zorder=10)

mob_line, = ax.plot([], [], color='#e74c3c', linestyle='--', linewidth=2, zorder=3)
mob_dist_text = ax.text(0, 0, "", color='#e74c3c', fontsize=11, fontweight='bold', zorder=7)
safe_scatter = ax.scatter([], [], color='#2ecc71', s=80, edgecolors='white', zorder=5)
alarm_scatter = ax.scatter([], [], color='#e74c3c', s=150, edgecolors='white', linewidth=2, zorder=6)

ax_side = fig.add_subplot(gs[1])
ax_side.axis('off') 
ax_side.set_title("MANIFEST", fontsize=20, fontweight='bold', color='white', y=0.98)
manifest_texts = [ax_side.text(0.05, 0.92 - (i * 0.07), "", color='#2ecc71', fontsize=18, fontweight='bold', family='monospace') for i in range(5)]

# --- BUTTONS ---
ax_exit = plt.axes([0.88, 0.02, 0.10, 0.08])
btn_exit = Button(ax_exit, 'EXIT', color='#ff4757', hovercolor='#ff6b81')
def exit_app(event):
    if not SIMULATION_MODE: ser.close()
    if hw_alarms_active: led.off(); buzzer1.stop(); buzzer2.stop()
    sys.exit()
btn_exit.on_clicked(exit_app)

ax_mute = plt.axes([0.77, 0.02, 0.10, 0.08])
btn_mute = Button(ax_mute, 'MUTE', color='#f39c12', hovercolor='#e67e22')
def toggle_mute(event):
    global buzzers_muted
    buzzers_muted = not buzzers_muted
    btn_mute.label.set_text('MUTED' if buzzers_muted else 'MUTE')
    btn_mute.color = '#7f8c8d' if buzzers_muted else '#f39c12'
    if hw_alarms_active: buzzer1.stop(); buzzer2.stop()
btn_mute.on_clicked(toggle_mute)

ax_tag_mode = plt.axes([0.64, 0.02, 0.12, 0.08])
btn_tag_mode = Button(ax_tag_mode, '1 TAG', color='#3498db', hovercolor='#2980b9')
def toggle_tags(event):
    global tag_count_mode
    tag_count_mode = 2 if tag_count_mode == 1 else 1
    btn_tag_mode.label.set_text(f'{tag_count_mode} TAGS')
btn_tag_mode.on_clicked(toggle_tags)

ax_pirate = plt.axes([0.53, 0.02, 0.10, 0.08])
btn_pirate = Button(ax_pirate, 'SONG', color='#8e44ad', hovercolor='#9b59b6')

def play_pirates():
    if not hw_alarms_active: return
    melody = [('D4', 0.15), ('D4', 0.15), ('D4', 0.30), ('E4', 0.15), ('F4', 0.30), ('F4', 0.30), ('F4', 0.30), ('G4', 0.15), ('E4', 0.30), ('E4', 0.30), ('D4', 0.15), ('C4', 0.15), ('D4', 0.40)]
    global buzzers_muted
    old_mute = buzzers_muted
    buzzers_muted = True
    for i, (n, d) in enumerate(melody):
        bz = buzzer1 if i % 2 == 0 else buzzer2
        bz.play(n) # Reverted to basic note string
        time.sleep(d * 0.85); bz.stop(); time.sleep(d * 0.15)
    buzzers_muted = old_mute

def trigger_pirate(event): threading.Thread(target=play_pirates, daemon=True).start()
btn_pirate.on_clicked(trigger_pirate)

# --- ENGINE ---
def update(frame):
    global serial_buffer, sim_step, mob_start_time
    current_time, lines = time.time(), []
    try:
        if SIMULATION_MODE:
            sim_step += 1
            lines = [f"POS,0,TAG-01,{center_x + math.sin(sim_step*0.1)*0.8},{center_y + sim_step*0.02}", f"POS,0,TAG-02,{center_x + 5.0 if sim_step > 100 else center_x - 0.5},{center_y + 2.0 if sim_step > 100 else center_y - 1.0}"]
        elif ser.in_waiting > 0:
            serial_buffer += ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
            if '\n' in serial_buffer:
                data = serial_buffer.split('\n')
                serial_buffer, lines = data[-1], data[:-1]
    except: pass

    for line in lines:
        if "POS" in line:
            parts = line.split(',')
            if len(parts) >= 5:
                t_id = parts[2]
                if t_id not in active_tags: 
                    tag_idx = len(active_tags)
                    active_tags[t_id] = {'name': CREW_ROSTER[tag_idx % 5], 'x': 0.0, 'y': 0.0, 'status': 'safe', 'last_time': current_time, 'nan_count': 0, 'order': tag_idx}
                
                if "nan" in parts[3].lower():
                    active_tags[t_id]['nan_count'] += 1
                    if active_tags[t_id]['nan_count'] >= 50: active_tags[t_id]['status'] = 'lost'
                else:
                    active_tags[t_id]['nan_count'], active_tags[t_id]['last_time'] = 0, current_time
                    nx, ny = float(parts[3]), float(parts[4])
                    active_tags[t_id]['x'] = nx if active_tags[t_id]['x'] == 0 else (active_tags[t_id]['x']*0.6 + nx*0.4)
                    active_tags[t_id]['y'] = ny if active_tags[t_id]['y'] == 0 else (active_tags[t_id]['y']*0.6 + ny*0.4)
                    active_tags[t_id]['status'] = 'safe' if boat_path.contains_point((active_tags[t_id]['x'], active_tags[t_id]['y'])) else 'alarm'

    safe_c, alarm_c, g_alarm, g_lost, tx, ty = [], [], False, False, 0.0, 0.0
    
    # Sort tags so the first one found is always #0
    sorted_tags = sorted(active_tags.items(), key=lambda x: x[1]['order'])
    
    for i, (t_id, d) in enumerate(sorted_tags):
        if i >= 5: break
        
        # Check Watchdog
        if current_time - d['last_time'] > DATA_TIMEOUT:
            # ONLY mark as lost if it's within the current Tag Mode count
            if i < tag_count_mode:
                d['status'] = 'lost'
            else:
                d['status'] = 'inactive'
        
        if d['status'] == 'inactive':
            manifest_texts[i].set_text(f"{d['name']:<14} [OFFLINE]")
            manifest_texts[i].set_color('#555555')
            continue

        manifest_texts[i].set_text(f"{d['name']:<14} [{d['status'].upper()}]")
        manifest_texts[i].set_color('#2ecc71' if d['status'] == 'safe' else ('#8b0000' if d['status'] == 'lost' else '#e74c3c'))
        
        if d['status'] == 'safe': 
            safe_c.append((d['x'], d['y']))
        elif d['status'] != 'inactive':
            alarm_c.append((d['x'], d['y'])); tx, ty = d['x'], d['y']
            if d['status'] == 'lost': g_lost = True
            else: g_alarm = True

    safe_scatter.set_offsets(safe_c if safe_c else np.empty((0, 2)))
    alarm_scatter.set_offsets(alarm_c if alarm_c else np.empty((0, 2)))

    if g_lost or g_alarm:
        if mob_start_time is None: mob_start_time = current_time
        flash = (frame % 10 < 5)
        clr = 'red' if g_lost else ('#e74c3c' if flash else '#c0392b')
        status_text.set_color(clr); status_text.set_text("!!! SIGNAL LOST !!!" if g_lost else "!!! MAN OVERBOARD !!!")
        timer_text.set_text(f"ELAPSED: {current_time - mob_start_time:.1f}s")
        mob_line.set_data([center_x, tx], [center_y, ty]); mob_line.set_color(clr)
        mob_dist_text.set_position(((center_x+tx)/2, (center_y+ty)/2)); mob_dist_text.set_text(f"{math.hypot(tx-center_x, ty-center_y):.1f}m"); mob_dist_text.set_color(clr)
        if hw_alarms_active:
            led.on() if flash else led.off()
            if not buzzers_muted:
                if g_lost: buzzer1.play('A5') if flash else buzzer2.play('E5')
                else: buzzer1.play('C5') if flash else buzzer1.stop()
    else:
        mob_start_time = None
        status_text.set_color('#2ecc71'); status_text.set_text("STATUS: SECURE"); timer_text.set_text("")
        mob_line.set_data([], []); mob_dist_text.set_text("")
        if hw_alarms_active: led.off(); buzzer1.stop(); buzzer2.stop()

    return (safe_scatter, alarm_scatter, status_text, timer_text, mob_line, mob_dist_text) + tuple(manifest_texts)

ani = FuncAnimation(fig, update, interval=33, blit=True, cache_frame_data=False)
plt.show()