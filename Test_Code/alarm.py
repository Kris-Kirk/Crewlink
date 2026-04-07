from gpiozero import LED, PWMOutputDevice
from time import sleep

# --- Setup Devices ---
# gpiozero uses BCM pin numbers by default
led = LED(4)

# Set up buzzers with specific frequencies. 
# initial_value=0 means they start turned OFF (0% duty cycle)
buzzer1 = PWMOutputDevice(22, frequency=440, initial_value=0) 
buzzer2 = PWMOutputDevice(26, frequency=880, initial_value=0)

# flush=True forces Python to print this instantly, helping us debug
print("Starting gpiozero sequence. Press Ctrl+C to stop.", flush=True)

try:
    while True:
        # --- Phase 1: LED ON ---
        print("[DEBUG] Pi says: LED is ON  | Buzzers: B1 ON, B2 OFF", flush=True)
        led.on()             # Turns BCM 4 HIGH
        buzzer1.value = 0.5  # Sets Buzzer 1 to 50% duty cycle (ON)
        buzzer2.value = 0.0  # Sets Buzzer 2 to 0% duty cycle (OFF)
        sleep(0.5)

        # --- Phase 2: LED OFF ---
        print("[DEBUG] Pi says: LED is OFF | Buzzers: B1 OFF, B2 ON", flush=True)
        led.off()            # Turns BCM 4 LOW
        buzzer1.value = 0.0  # OFF
        buzzer2.value = 0.5  # ON
        sleep(0.5)

except KeyboardInterrupt:
    print("\nStopping sequence... gpiozero will automatically clean up the pins!")
