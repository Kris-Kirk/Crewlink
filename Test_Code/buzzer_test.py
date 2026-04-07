from gpiozero import TonalBuzzer, LED
from time import sleep

# Setup the buzzer (shifted mid_tone for higher alarm frequencies)
buzzer = TonalBuzzer(17, mid_tone=2000)

# Setup the LEDs
led_red = LED(21)
led_blue = LED(24)

print("System Armed: Visual and Audio Alarm. Press Ctrl+C to stop.")

try:
    while True:
        # Phase 1: High Pitch + Red LED
        led_blue.off()
        led_red.on()
        buzzer.play(3500)
        sleep(0.1)
        
        # Phase 2: Lower Pitch + Blue LED
        led_red.off()
        led_blue.on()
        buzzer.play(2500)
        sleep(0.1)

except KeyboardInterrupt:
    # Safe shutdown
    buzzer.stop()
    led_red.off()
    led_blue.off()
    print("\nAlarm deactivated and LEDs turned off.")