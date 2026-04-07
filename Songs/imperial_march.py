from gpiozero import LED, TonalBuzzer
from gpiozero.tones import Tone
from time import sleep

# --- Setup Hardware ---
led = LED(4)
buzzer1 = TonalBuzzer(22)
buzzer2 = TonalBuzzer(26)

# --- The Melody ---
# Format: ('Musical Note', Duration in seconds)
imperial_march = [
    ('G4', 0.5), ('G4', 0.5), ('G4', 0.5),
    ('Eb4', 0.35), ('Bb4', 0.15),
    ('G4', 0.5), ('Eb4', 0.35), ('Bb4', 0.15),
    ('G4', 1.0),
    ('D5', 0.5), ('D5', 0.5), ('D5', 0.5),
    ('Eb5', 0.35), ('Bb4', 0.15),
    ('F#4', 0.5), ('Eb4', 0.35), ('Bb4', 0.15),
    ('G4', 1.0)
]

print("Playing The Imperial March! Press Ctrl+C to stop.", flush=True)

try:
    # Loop through each note in the sequence
    for index, (note, duration) in enumerate(imperial_march):
        
        led.on() # Flash the LED on

        # Alternate buzzers based on whether the index is even or odd
        if index % 2 == 0:
            buzzer1.play(Tone(note))
        else:
            buzzer2.play(Tone(note))

        # Play the note for 85% of its duration
        sleep(duration * 0.85)

        # Turn everything off for the last 15% to create a crisp gap between notes
        led.off()
        buzzer1.stop()
        buzzer2.stop()
        sleep(duration * 0.15)

except KeyboardInterrupt:
    print("\nSong stopped. gpiozero safely turned off the pins.")