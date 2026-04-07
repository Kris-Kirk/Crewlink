import RPi.GPIO as GPIO
import time

# --- Configuration ---
GPIO.setmode(GPIO.BCM)

LED_PIN = 17
BUZZER_1_PIN = 22
BUZZER_2_PIN = 26

# --- Setup Pins ---
GPIO.setup(LED_PIN, GPIO.OUT)
GPIO.setup(BUZZER_1_PIN, GPIO.OUT)
GPIO.setup(BUZZER_2_PIN, GPIO.OUT)

buzzer1_pwm = GPIO.PWM(BUZZER_1_PIN, 440) 
buzzer2_pwm = GPIO.PWM(BUZZER_2_PIN, 880) 

print("Starting debug sequence. Press Ctrl+C to stop.")

try:
    while True:
        # --- Phase 1: LED ON ---
        print("[DEBUG] Pi says: LED is ON  | Buzzers: B1 ON, B2 OFF")
        GPIO.output(LED_PIN, GPIO.HIGH)
        buzzer1_pwm.start(50)  
        buzzer2_pwm.stop()
        time.sleep(2.0)  # 2-second pause to let you observe

        # --- Phase 2: LED OFF ---
        print("[DEBUG] Pi says: LED is OFF | Buzzers: B1 OFF, B2 ON")
        GPIO.output(LED_PIN, GPIO.LOW)
        buzzer1_pwm.stop()     
        buzzer2_pwm.start(50)  
        time.sleep(2.0)

except KeyboardInterrupt:
    print("\nStopping sequence...")

finally:
    # --- Safe Cleanup ---
    buzzer1_pwm.stop()
    buzzer2_pwm.stop()
    
    # Force pins LOW before releasing them
    GPIO.output(LED_PIN, GPIO.LOW)
    GPIO.output(BUZZER_1_PIN, GPIO.LOW)
    GPIO.output(BUZZER_2_PIN, GPIO.LOW)
    
    GPIO.cleanup()
    print("Pins safely driven LOW and cleaned up. Goodbye!")