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

# --- PI CONFIGURATION & DEMO MODE ---
SIMULATION_MODE = True  # Set to False when you plug in your real Qorvo module

# --- MARINE DASHBOARD THEME ---
plt.style.use('dark_background')

def get_dwm_port():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if "JLink" in port.description or "USB Serial" in port.description or "ACM" in port.device:
            return port.device
    if ports:
        return ports[0].device 
    return None

BAUD_RATE = 115200

# Expanded limits slightly to ensure the 7000mm bow fits on screen
X_LIMITS = (-1000, 6000) 
Y_LIMITS = (-1000, 8000) 

# --- THE BOAT (GEOFENCE) ---
BOAT_COORDS = [
    (1200, 1000),  # Stern Port
    (3800, 1000),  # Stern Starboard
    (4000, 2000),  # Aft Starboard 
    (4000, 4500),  # Mid Starboard
    (3600, 5800),  # Forward Quarter Starboard
    (2500, 7000),  # Bow (Point)
    (1400, 5800),  # Forward Quarter Port
    (1000, 4500),  # Mid Port 
    (1000, 2000),  # Aft Port 
]
boat_path = Path(BOAT_COORDS)

FILTER_WINDOW = 5 
x_raw = collections.deque(maxlen=FILTER_WINDOW)
y_raw = collections.deque(maxlen=FILTER_WINDOW)
path_x = collections.deque(maxlen=100) 
path_y = collections.deque(maxlen=100)

last_valid_x = 0.0
last_valid_y = 0.0
connection_lost = False
man_overboard = False

# --- FAILSAFE TRACKERS ---
nan_count = 0  
last_data_time = time.time()
DATA_TIMEOUT = 2.0  

discovered_anchors = {} 
sim_step = 0  # Used for Demo Mode

# --- SERIAL SETUP & ANCHOR DISCOVERY ---
if not SIMULATION_MODE:
    SERIAL_PORT = get_dwm_port()
    if not SERIAL_PORT:
        print("Error: No UWB module detected. Check your USB connection.")
        sys.exit()
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.01)
        ser.reset_input_buffer()
        print(f"Connected to {SERIAL_PORT}. Waking up module...")
        ser.write(b'\r\r')
        time.sleep(1)
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
                        discovered_anchors[a_id] = (float(coords[0]) * 1000.0, float(coords[1]) * 1000.0)
                        
        print("Starting Marine Radar...")
        ser.write(b'lec\r') 
    except Exception as e:
        print(f"Error connecting: {e}")
        sys.exit()
else:
    print("Running in DEMO MODE. Simulating anchor and tag data.")
    discovered_anchors = {"ANC1": (0, 0), "ANC2": (5000, 0), "ANC3": (2500, 8000)}

# --- PLOT SETUP ---
# Formatted roughly for an 800x480 touchscreen aspect ratio
fig, ax = plt.subplots(figsize=(10, 6))
fig.canvas.manager.set_window_title("Crew Link - Captain's Dashboard")

# Make it fullscreen and hide the mouse cursor for the Pi touchscreen
try:
    manager = fig.canvas.manager
    manager.window.attributes('-fullscreen', True)
    manager.window.config(cursor="none")
except Exception:
    pass # Fails gracefully if run on a non-Tkinter backend

ax.set_title("MARINE TRACKING RADAR", fontsize=16, fontweight='bold', color='cyan')
ax.set_xlabel("X (mm)")
ax.set_ylabel("Y (mm)")
ax.grid(True, linestyle='-', color='#333333', alpha=0.7)

boat_patch = patches.Polygon(BOAT_COORDS, closed=True, fill=True, color='#0a3d62', alpha=0.6, zorder=2)
boat_outline = patches.Polygon(BOAT_COORDS, closed=True, fill=False, color='#3c6382', linewidth=2, zorder=2)
ax.add_patch(boat_patch)
ax.add_patch(boat_outline)

status_text = ax.text(0.5, 0.95, "STATUS: BOOTING...", transform=ax.transAxes, 
                      ha='center', va='top', fontsize=16, fontweight='bold', 
                      color='yellow', bbox=dict(facecolor='black', alpha=0.7, edgecolor='none'), zorder=10)

if discovered_anchors:
    anch_x = [a[0] for a in discovered_anchors.values()]
    anch_y = [a[1] for a in discovered_anchors.values()]
    ax.scatter(anch_x, anch_y, marker='^', color='cyan', s=150, label='Anchors', zorder=3)
    for a_id, a_coords in discovered_anchors.items():
        ax.text(a_coords[0] + 150, a_coords[1] + 150, a_id, fontsize=10, color='cyan', fontweight='bold')
    pad = 1500 
    ax.set_xlim(min(anch_x) - pad, max(anch_x) + pad)
    ax.set_ylim(min(anch_y) - pad, max(anch_y) + pad)
else:
    ax.set_xlim(X_LIMITS)
    ax.set_ylim(Y_LIMITS)

path_line, = ax.plot([], [], color='#2ecc71', linestyle=':', alpha=0.5, linewidth=3)
tag_spot, = ax.plot([], [], 'o', color='#2ecc71', markersize=24, markeredgecolor='white', markeredgewidth=2, label="Crew Tag", zorder=5)

ax.legend(loc='lower left', facecolor='black', edgecolor='#333333', fontsize=12)

# --- EXIT BUTTON ---
ax_exit = plt.axes([0.85, 0.02, 0.12, 0.08])
btn_exit = Button(ax_exit, 'EXIT APP', color='#ff4757', hovercolor='#ff6b81')
btn_exit.label.set_fontsize(12)
btn_exit.label.set_fontweight('bold')

def exit_app(event):
    if not SIMULATION_MODE: ser.close()
    plt.close('all')
    sys.exit()
btn_exit.on_clicked(exit_app)

def update(frame):
    global last_valid_x, last_valid_y, connection_lost, man_overboard, nan_count, last_data_time, sim_step
    
    try:
        lines = []
        if SIMULATION_MODE:
            # --- DEMO DATA GENERATOR ---
            sim_step += 1
            time.sleep(0.05) # Throttle visual speed
            
            if sim_step < 100:
                raw_x = 2500 + math.sin(sim_step * 0.1) * 800
                raw_y = 3000 + sim_step * 20
            elif sim_step < 150:
                raw_x = 2500 + math.sin(sim_step * 0.1) * 800 + (sim_step - 100)*40 
                raw_y = 5000
            elif sim_step < 180:
                raw_x = 4500 + (sim_step - 150)*30
                raw_y = 5000 - (sim_step - 150)*30
            elif sim_step < 250:
                raw_x, raw_y = float('nan'), float('nan')
            else:
                sim_step = 0
                raw_x, raw_y = 2500, 3000
                
            raw_val_x = str(raw_x / 1000.0) if not math.isnan(raw_x) else "nan"
            raw_val_y = str(raw_y / 1000.0) if not math.isnan(raw_y) else "nan"
            lines = [f"POS,0,0,{raw_val_x},{raw_val_y}"]
            
        elif ser.in_waiting > 0:
            # --- REAL SERIAL READ ---
            raw_data = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
            lines = raw_data.split('\r\n')
            
        if lines:
            latest_pos_line = None
            for line in reversed(lines):
                if "POS" in line:
                    latest_pos_line = line
                    break
            
            if latest_pos_line:
                parts = latest_pos_line.split(',')
                if len(parts) >= 5:
                    raw_val_x = parts[3]
                    raw_val_y = parts[4]

                    # --- THE 50-NaN FILTER ---
                    if "nan" in raw_val_x.lower() or "nan" in raw_val_y.lower():
                        nan_count += 1
                        if nan_count >= 50:
                            connection_lost = True
                    else:
                        nan_count = 0
                        connection_lost = False
                        last_data_time = time.time()
                        
                        x_mm = float(raw_val_x) * 1000.0
                        y_mm = float(raw_val_y) * 1000.0
                        
                        x_raw.append(x_mm)
                        y_raw.append(y_mm)
                        smooth_x = sum(x_raw) / len(x_raw)
                        smooth_y = sum(y_raw) / len(y_raw)
                        last_valid_x, last_valid_y = smooth_x, smooth_y

                        path_x.append(smooth_x)
                        path_y.append(smooth_y)
                        
                        tag_spot.set_data([smooth_x], [smooth_y])
                        path_line.set_data(list(path_x), list(path_y))
                        
                        if boat_path.contains_point((smooth_x, smooth_y)):
                            man_overboard = False
                        else:
                            man_overboard = True
                            
                        # Dynamic camera follow if tag goes offscreen
                        cur_xlim = ax.get_xlim()
                        cur_ylim = ax.get_ylim()
                        if smooth_x < cur_xlim[0] + 500 or smooth_x > cur_xlim[1] - 500 or \
                           smooth_y < cur_ylim[0] + 500 or smooth_y > cur_ylim[1] - 500:
                            ax.set_xlim(smooth_x - 3000, smooth_x + 3000)
                            ax.set_ylim(smooth_y - 3000, smooth_y + 3000)
                            
    except Exception as e:
        pass 

    # --- WATCHDOG TIMER CHECK ---
    if time.time() - last_data_time > DATA_TIMEOUT:
        connection_lost = True

    # --- UI ALARM LOGIC ---
    if connection_lost:
        if frame % 10 < 5: 
            tag_spot.set_color('red')
            status_text.set_color('red')
        else:
            tag_spot.set_color('#8b0000') 
            status_text.set_color('#8b0000')
        status_text.set_text(f"!!! CRITICAL: SIGNAL LOST !!!\nLast Known: X {last_valid_x:.0f} | Y {last_valid_y:.0f}")
            
    elif man_overboard:
        if frame % 10 < 5:
            tag_spot.set_color('#ff9f43') 
            status_text.set_color('#ff9f43')
        else:
            tag_spot.set_color('#d35400')
            status_text.set_color('#d35400')
        status_text.set_text(f"!!! MAN OVERBOARD !!!\nTracking... Live Pos: X {last_valid_x:.0f} | Y {last_valid_y:.0f}")
            
    else:
        tag_spot.set_color('#2ecc71') 
        status_text.set_color('#2ecc71')
        status_text.set_text("STATUS: ALL CREW ON DECK")

    return tag_spot, path_line, status_text

# interval=50 sets the refresh rate to ~20 FPS. 
# This is much kinder to the Pi 3B+'s CPU than interval=20 (50 FPS).
ani = FuncAnimation(fig, update, interval=50, blit=False, cache_frame_data=False)

plt.show()
if not SIMULATION_MODE: ser.close()