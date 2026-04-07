import tkinter as tk
from tkinter import font
import serial
import threading
import time
import math
import random

# --- CONFIGURATION FOR RASPBERRY PI ---
# Qorvo devices usually show up as ttyACM0 or ttyUSB0 on Raspberry Pi
COM_PORT = '/dev/ttyACM0' 
BAUD_RATE = 115200

# Scaled down for a standard 7" Raspberry Pi Touchscreen (800x480)
WINDOW_SIZE = 480 
SCALE_FACTOR = 20         

# SIMULATION SETTINGS
SIMULATION_MODE = True    # Set to True for your Demo!
FILTER_THRESHOLD = 0.10   

# VESSEL DIMENSIONS (METERS)
BOAT_WIDTH_M = 2.5        
BOAT_LENGTH_M = 5.0       

# COLORS
COLOR_BG = "#050A14"
COLOR_GRID = "#0F2840"
COLOR_BOAT_HULL = "#607D8B"
COLOR_BOAT_DECK = "#37474F"
COLOR_SAFE = "#00FF00"
COLOR_ALARM = "#FF0000"
COLOR_TEXT = "#00FFFF"

class MarineRadarApp:
    def __init__(self, root):
        self.root = root
        self.root.title("VESSEL PROXIMITY MONITOR - Pi Touch Edition")
        
        # Optimize for standard Pi touchscreen size
        self.root.geometry("800x480")
        self.root.configure(bg=COLOR_BG)
        
        # Start fullscreen (great for touchscreens)
        self.root.attributes('-fullscreen', True)
        
        self.anchor_data = {} 
        self.sidebar_widgets = {} 
        self.lock = threading.Lock()
        self.running = True
        self.flash_state = False
        
        # --- CONTROL VARIABLES ---
        self.safe_zone_var = tk.DoubleVar(value=8) 
        self.mode_var = tk.StringVar(value="MOB")    

        # --- FONTS ---
        self.font_header = font.Font(family="Courier New", size=12, weight="bold")
        self.font_data = font.Font(family="Courier New", size=10, weight="bold")
        self.font_alarm = font.Font(family="Arial", size=24, weight="bold")

        # --- SIDEBAR ---
        self.sidebar = tk.Frame(root, width=320, bg="#0b1626", padx=5, pady=5, relief=tk.RAISED, borderwidth=2)
        self.sidebar.pack(side=tk.RIGHT, fill=tk.Y)
        self.sidebar.pack_propagate(False) 
        
        # 0. Exit Button (Crucial for fullscreen touch devices)
        self.btn_exit = tk.Button(self.sidebar, text="EXIT SYSTEM", bg="red", fg="white", 
                                  font=("Arial", 10, "bold"), command=self.close_app)
        self.btn_exit.pack(fill=tk.X, pady=(0, 10))

        # 1. Mode Toggle
        mode_frame = tk.LabelFrame(self.sidebar, text="SYSTEM MODE", font=self.font_header, bg="#0b1626", fg="white")
        mode_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.btn_mode = tk.Button(mode_frame, text="MODE: MAN OVERBOARD\n(Safe Inside)", 
                                  bg="#152a38", fg=COLOR_SAFE, font=("Arial", 10, "bold"),
                                  command=self.toggle_mode)
        self.btn_mode.pack(fill=tk.X, padx=5, pady=5)

        # 2. Slider
        control_frame = tk.LabelFrame(self.sidebar, text="ZONE SETTING", font=self.font_header, bg="#0b1626", fg=COLOR_TEXT)
        control_frame.pack(fill=tk.X, pady=(0, 10), ipady=5)
        
        # Made slider slightly thicker for touch interaction
        self.zone_slider = tk.Scale(control_frame, from_=1, to=20, orient=tk.HORIZONTAL,
                                    variable=self.safe_zone_var, resolution=0.1,
                                    bg="#0b1626", fg="white", highlightthickness=0,
                                    troughcolor="#152a38", activebackground=COLOR_TEXT, width=25)
        self.zone_slider.pack(fill=tk.X, padx=10)
        
        self.lbl_zone_val = tk.Label(control_frame, text="RADIUS: 8.0m", font=self.font_data, bg="#0b1626", fg="white")
        self.lbl_zone_val.pack(pady=2)
        self.safe_zone_var.trace_add("write", lambda *args: self.lbl_zone_val.config(text=f"RADIUS: {self.safe_zone_var.get():.1f}m"))

        # 3. Manifest
        tk.Label(self.sidebar, text="CREW POSITIONS", font=self.font_header, bg="#0b1626", fg=COLOR_TEXT).pack()
        self.crew_list_frame = tk.Frame(self.sidebar, bg="#0b1626")
        self.crew_list_frame.pack(fill=tk.BOTH, expand=True)

        # --- RADAR ---
        self.canvas = tk.Canvas(root, bg=COLOR_BG, width=WINDOW_SIZE, height=WINDOW_SIZE, highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.cx = WINDOW_SIZE // 2
        self.cy = WINDOW_SIZE // 2

        if SIMULATION_MODE:
            threading.Thread(target=self.simulate_scenario, daemon=True).start()
        else:
            threading.Thread(target=self.read_serial, daemon=True).start()

        self.animate()

    def close_app(self):
        self.running = False
        self.root.destroy()

    def toggle_mode(self):
        if self.mode_var.get() == "MOB":
            self.mode_var.set("KEEPAWAY")
            self.btn_mode.config(text="MODE: COLLISION GUARD\n(Safe Outside)", fg="#FFB000")
        else:
            self.mode_var.set("MOB")
            self.btn_mode.config(text="MODE: MAN OVERBOARD\n(Safe Inside)", fg=COLOR_SAFE)

    def get_distance(self, data_point):
        if isinstance(data_point, tuple):
            return math.sqrt(data_point[0]**2 + data_point[1]**2)
        else:
            return float(data_point)

    def is_safe(self, data_point):
        dist = self.get_distance(data_point)
        limit = self.safe_zone_var.get()
        return dist <= limit if self.mode_var.get() == "MOB" else dist >= limit

    def draw_boat_shape(self):
        w_px = BOAT_WIDTH_M * SCALE_FACTOR
        h_px = BOAT_LENGTH_M * SCALE_FACTOR
        
        bow_y = self.cy - (h_px / 2)
        stern_y = self.cy + (h_px / 2)
        left_x = self.cx - (w_px / 2)
        right_x = self.cx + (w_px / 2)
        
        hull_coords = [
            self.cx, bow_y - 15,       
            right_x, bow_y + 20,       
            right_x, stern_y,          
            left_x, stern_y,           
            left_x, bow_y + 20         
        ]
        
        self.canvas.create_polygon(hull_coords, fill=COLOR_BOAT_HULL, outline="white", width=2)
        
        cabin_w = w_px * 0.6
        cabin_h = h_px * 0.4
        self.canvas.create_rectangle(
            self.cx - cabin_w/2, self.cy - cabin_h/2,
            self.cx + cabin_w/2, self.cy + cabin_h/2,
            fill=COLOR_BOAT_DECK, outline="white"
        )
        self.canvas.create_text(self.cx, self.cy, text="SS PI", fill="white", font=("Arial", 6, "bold"))

    def update_sidebar(self):
        with self.lock:
            active_ids = list(self.anchor_data.keys())
            
            for old_id in list(self.sidebar_widgets.keys()):
                if old_id not in active_ids:
                    self.sidebar_widgets[old_id]['frame'].destroy()
                    del self.sidebar_widgets[old_id]
            
            for a_id in active_ids:
                val = self.anchor_data[a_id]
                dist = self.get_distance(val)
                safe = self.is_safe(val)
                
                if safe:
                    bg, fg, txt = "#152a38", COLOR_SAFE, "SAFE"
                else:
                    bg = COLOR_ALARM if self.flash_state else "white"
                    fg = "white" if self.flash_state else "red"
                    txt = "ALARM!"
                
                if isinstance(val, tuple):
                    loc_txt = f"X:{val[0]:.1f} Y:{val[1]:.1f}"
                else:
                    loc_txt = f"DIST: {dist:.2f}m"
                
                if a_id in self.sidebar_widgets:
                    widgets = self.sidebar_widgets[a_id]
                    widgets['frame'].config(bg=bg)
                    widgets['lbl_id'].config(bg=bg, fg=fg)
                    widgets['lbl_dist'].config(text=loc_txt, bg=bg, fg=fg)
                    widgets['lbl_status'].config(text=txt, bg=bg, fg=fg)
                else:
                    card = tk.Frame(self.crew_list_frame, bg=bg, pady=2, padx=2, relief=tk.RIDGE, bd=1)
                    card.pack(fill=tk.X, pady=2)
                    
                    lbl_id = tk.Label(card, text=f"{a_id}", font=("Arial", 10, "bold"), bg=bg, fg=fg)
                    lbl_id.pack(side=tk.LEFT)
                    
                    right_frame = tk.Frame(card, bg=bg)
                    right_frame.pack(side=tk.RIGHT)
                    
                    lbl_dist = tk.Label(right_frame, text=loc_txt, font=("Arial", 8), bg=bg, fg=fg)
                    lbl_dist.pack(anchor="e")
                    
                    lbl_status = tk.Label(right_frame, text=txt, font=("Arial", 8, "bold"), bg=bg, fg=fg)
                    lbl_status.pack(anchor="e")
                    
                    self.sidebar_widgets[a_id] = {
                        'frame': card, 
                        'lbl_id': lbl_id, 
                        'lbl_dist': lbl_dist, 
                        'lbl_status': lbl_status
                    }

    def draw_radar(self):
        self.canvas.delete("all")
        limit = self.safe_zone_var.get()
        mode = self.mode_var.get()
        
        # Grid
        for r in range(1, 10, 2): 
            radius = r * SCALE_FACTOR 
            self.canvas.create_oval(self.cx-radius, self.cy-radius, self.cx+radius, self.cy+radius, outline=COLOR_GRID)
            self.canvas.create_text(self.cx, self.cy-radius, text=f"{r}m", fill=COLOR_GRID, font=("Arial", 8))

        # Safe Zone Boundary
        sz_px = limit * SCALE_FACTOR
        self.canvas.create_oval(self.cx-sz_px, self.cy-sz_px, self.cx+sz_px, self.cy+sz_px, 
                                outline=COLOR_TEXT, width=2, dash=(10, 10))

        self.draw_boat_shape()
        global_alarm_active = False

        # Targets
        with self.lock:
            for a_id, val in self.anchor_data.items():
                safe = self.is_safe(val)
                if not safe: global_alarm_active = True
                
                color = COLOR_SAFE if safe else (COLOR_ALARM if self.flash_state else "white")
                
                if isinstance(val, tuple):
                    x_m, y_m = val
                    px_x = self.cx + (x_m * SCALE_FACTOR)
                    px_y = self.cy - (y_m * SCALE_FACTOR)
                    
                    r = 6
                    self.canvas.create_oval(px_x-r, px_y-r, px_x+r, px_y+r, fill=color, outline="white", width=2)
                    self.canvas.create_text(px_x, px_y-12, text=a_id, fill=color, font=("Arial", 8, "bold"))
                    self.canvas.create_line(self.cx, self.cy, px_x, px_y, fill=color, dash=(2,4))
                else:
                    dist = float(val)
                    px_radius = dist * SCALE_FACTOR
                    width = 2 if safe else 4
                    self.canvas.create_oval(self.cx-px_radius, self.cy-px_radius, self.cx+px_radius, self.cy+px_radius, outline=color, width=width)
                    self.canvas.create_text(self.cx+px_radius+5, self.cy, text=f"{a_id}\n{dist:.1f}m", fill=color, font=("Arial", 8, "bold"), anchor="w")

        if global_alarm_active and self.flash_state:
            warning_text = "!!! MAN OVERBOARD !!!" if mode == "MOB" else "!!! COLLISION WARNING !!!"
            self.canvas.create_text(self.cx, 40, text=warning_text, fill=COLOR_ALARM, font=self.font_alarm)

    def animate(self):
        self.flash_state = not self.flash_state if (time.time() % 0.5 < 0.25) else False
        self.draw_radar()
        self.update_sidebar()
        self.root.after(100, self.animate)

    # --- SIMULATION DEMO MODE ---
    def simulate_scenario(self):
        step = 0
        while self.running:
            with self.lock:
                # Static Crew Member
                self.anchor_data["CPT"] = (0.0 + random.uniform(-0.05, 0.05), 1.5 + random.uniform(-0.05, 0.05))
                
                # Person pacing on the deck
                deck_x = math.sin(step * 0.05) * 1.0
                self.anchor_data["ENG"] = (deck_x, -1.0 + random.uniform(-0.1, 0.1))
                
                # Person walking towards the edge and falling off (triggers alarm)
                # They walk out 12 meters over time, then reset.
                wanderer_dist = (step % 200) * 0.08  
                wanderer_x = wanderer_dist * math.cos(math.radians(45))
                wanderer_y = wanderer_dist * math.sin(math.radians(45))
                self.anchor_data["MOB"] = (wanderer_x, wanderer_y)
            
            step += 1
            time.sleep(0.05)

    # --- SERIAL ---
    def read_serial(self):
        print(f"Connecting to {COM_PORT}...")
        try:
            ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
            ser.write(b'\r\r')
            time.sleep(1)
            ser.write(b'aurs 1 1\r')
            time.sleep(0.5)
            ser.write(b'lec\r')
            while self.running:
                try:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line.startswith("DIST"): self.parse_data(line)
                except: pass
        except Exception as e: print(f"SERIAL ERROR: {e}")

    def parse_data(self, line):
        try:
            parts = line.split(',')
            count = int(parts[1])
            current_scan_data = {}
            idx = 2
            for _ in range(count):
                if idx+5 >= len(parts): break
                a_id = parts[idx+1]
                raw_dist = float(parts[idx+5])
                current_scan_data[a_id] = raw_dist
                idx += 6
            
            with self.lock:
                current_ids = list(self.anchor_data.keys())
                for old_id in current_ids:
                    if old_id not in current_scan_data: del self.anchor_data[old_id]

                for a_id, new_dist in current_scan_data.items():
                    if a_id not in self.anchor_data:
                        self.anchor_data[a_id] = new_dist
                    else:
                        old_val = self.anchor_data[a_id]
                        if isinstance(old_val, tuple): self.anchor_data[a_id] = new_dist
                        else:
                            old_dist = float(old_val)
                            if old_dist == 0: diff = 1.0 
                            else: diff = abs(new_dist - old_dist) / old_dist
                            if diff > FILTER_THRESHOLD: self.anchor_data[a_id] = new_dist
        except: pass

if __name__ == "__main__":
    root = tk.Tk()
    # Removes the mouse cursor to feel like a real touch interface
    root.config(cursor="none") 
    app = MarineRadarApp(root)
    root.mainloop()