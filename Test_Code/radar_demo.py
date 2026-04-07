import matplotlib
matplotlib.use('TkAgg') 
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.path import Path
from matplotlib.animation import FuncAnimation
import numpy as np
import random
import math
from gpiozero import TonalBuzzer, LED

# --- HARDWARE ---
try:
    buzzer = TonalBuzzer(17, mid_tone=2000)
    led_red = LED(23); led_blue = LED(24)
    hardware_active = True
except:
    hardware_active = False

# --- ORIGINAL BOAT GEOMETRY ---
BOAT_COORDS = [
    (0.0, 5.0), (0.5, 4.6), (1.0, 3.8), (1.3, 2.5), (1.5, 1.0), 
    (1.5, -3.0), (1.3, -4.8), (1.2, -5.0), (0.6, -5.0), (0.6, -4.8), 
    (-0.6, -4.8), (-0.6, -5.0), (-1.2, -5.0), (-1.3, -4.8), (-1.5, -3.0), 
    (-1.5, 1.0), (-1.3, 2.5), (-1.0, 3.8), (-0.5, 4.6), (0.0, 5.0)
]
boat_path = Path(BOAT_COORDS)

# --- CREW DATA WITH DRIFT LOGIC ---
CREW_NAMES = ["Alex", "Beth", "Charlie", "Diana", "Ethan", "John", "Juliana", "Kris"]
crew_data = []
for n in CREW_NAMES:
    crew_data.append({
        'name': n, 
        'x': random.uniform(-0.5, 0.5), 
        'y': random.uniform(-2, 2), 
        'in_water': False,
        'drift_dir': random.uniform(0, 2 * math.pi) 
    })

# --- UI SETUP ---
plt.style.use('dark_background')
fig = plt.figure(figsize=(12, 7))
gs = fig.add_gridspec(1, 2, width_ratios=[3, 1.2])

ax = fig.add_subplot(gs[0])
ax.set_facecolor('#000000')
ax.set_xlim(-10, 10); ax.set_ylim(-10, 10)
ax.set_aspect('equal')
ax.grid(True, color='#222222', linestyle='--')

# Static Boat Hull
ax.add_patch(patches.Polygon(BOAT_COORDS, closed=True, fc='#0a3d62', ec='#3c6382', lw=2, alpha=0.7))

# Visual Elements
safe_scatter = ax.scatter([], [], c='#2ecc71', s=100, edgecolors='white', animated=True)
alarm_scatter = ax.scatter([], [], c='#e74c3c', s=200, edgecolors='white', animated=True, marker='X')
status_text = ax.text(0.5, 0.95, "", transform=ax.transAxes, ha='center', weight='bold', size=14, animated=True)

ax_side = fig.add_subplot(gs[1])
ax_side.axis('off')
manifest_texts = [ax_side.text(0.05, 0.9 - (i*0.07), "", color='#2ecc71', family='monospace', animated=True) for i in range(len(crew_data))]

def update(frame):
    s_pts, a_pts = [], []
    alarm_active = False

    for i, p in enumerate(crew_data):
        if not p['in_water']:
            # Normal movement: small random steps
            p['x'] += random.uniform(-0.15, 0.15)
            p['y'] += random.uniform(-0.15, 0.15)
            
            # Check if they just crossed the line
            if not boat_path.contains_point((p['x'], p['y'])):
                p['in_water'] = True
                print(f"ALERT: {p['name']} has fallen overboard!")
        
        else:
            # Water movement: drifting away from the boat
            p['x'] += math.cos(p['drift_dir']) * 0.1
            p['y'] += math.sin(p['drift_dir']) * 0.1
            
            # If they drift too far off screen, respawn them on the boat for the demo
            if abs(p['x']) > 9 or abs(p['y']) > 9:
                p['x'], p['y'] = 0, 0
                p['in_water'] = False

        # Update lists and Sidebar
        if p['in_water']:
            a_pts.append([p['x'], p['y']])
            alarm_active = True
            manifest_texts[i].set_text(f"{p['name']:<10} [MOB!]")
            manifest_texts[i].set_color('#e74c3c')
        else:
            s_pts.append([p['x'], p['y']])
            manifest_texts[i].set_text(f"{p['name']:<10} [OK]")
            manifest_texts[i].set_color('#2ecc71')

    # Hardware Control - Sync to the 0.5s interval
    if hardware_active:
        if alarm_active:
            if frame % 2 == 0:
                buzzer.play(1800); led_red.on(); led_blue.off()
            else:
                buzzer.play(1200); led_red.off(); led_blue.on()
        else:
            buzzer.stop(); led_red.off(); led_blue.off()

    safe_scatter.set_offsets(s_pts if s_pts else np.empty((0, 2)))
    alarm_scatter.set_offsets(a_pts if a_pts else np.empty((0, 2)))
    status_text.set_text("!!! MAN OVERBOARD !!!" if alarm_active else "SYSTEMS SECURE")
    status_text.set_color('#e74c3c' if alarm_active else '#2ecc71')

    return [safe_scatter, alarm_scatter, status_text] + manifest_texts

ani = FuncAnimation(fig, update, frames=range(20000), interval=500, blit=True)

plt.show()