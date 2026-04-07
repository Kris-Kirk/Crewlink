from gpiozero import LED, TonalBuzzer
from gpiozero.tones import Tone
from time import sleep

# --- Setup Hardware ---
led = LED(4)
buzzer1 = TonalBuzzer(22)
buzzer2 = TonalBuzzer(26)

# --- The Melody: He's a Pirate (Lower Octave) ---
# Format: ('Note', Duration in seconds)
potc_theme = [
    # Intro Build-up
    ('A3', 0.15), ('C4', 0.15), ('D4', 0.30), ('D4', 0.30),
    ('D4', 0.15), ('E4', 0.15), ('F4', 0.30), ('F4', 0.30),
    ('F4', 0.15), ('G4', 0.15), ('E4', 0.30), ('E4', 0.30),
    ('D4', 0.15), ('C4', 0.15), ('D4', 0.45), ('REST', 0.15),
    
    # Main Hook
    ('A3', 0.15), ('C4', 0.15), ('D4', 0.30), ('D4', 0.30),
    ('D4', 0.15), ('E4', 0.15), ('F4', 0.30), ('F4', 0.30),
    ('F4', 0.15), ('G4', 0.15), ('E4', 0.30), ('E4', 0.30),
    ('D4', 0.15), ('C4', 0.15), ('C4', 0.15), ('D4', 0.30), ('REST', 0.15),
    
    # The Gallop
    ('A3', 0.15), ('C4', 0.15), ('D4', 0.30), ('D4', 0.30),
    ('D4', 0.15), ('F4', 0.15), ('G4', 0.30), ('G4', 0.30),
    ('G4', 0.15), ('A4', 0.15), ('Bb4', 0.30), ('Bb4', 0.30), # Bb4 is the lower Bb
    ('A4', 0.15), ('G4', 0.15), ('A4', 0.15), ('D4', 0.30), ('REST', 0.15),

    # --- Final Verse (The Finale) ---
    ('D4', 0.15), ('E4', 0.15), ('F4', 0.30), ('F4', 0.30),
    ('G4', 0.30), ('A4', 0.30), ('D4', 0.30), ('REST', 0.15),
    ('D4', 0.15), ('F4', 0.15), ('E4', 0.30), ('E4', 0.30),
    ('F4', 0.15), ('D4', 0.15), ('E4', 0.60), ('REST', 0.15),
    
    # # Final big notes
    # ('A3', 0.15), ('C4', 0.15), ('D4', 0.60), ('D4', 0.60)
]

print("Playing the Pirate's Life for Me (Lower Octave)...", flush=True)

try:
    for index, (note, duration) in enumerate(potc_theme):
        
        if note == 'REST':
            led.off()
            buzzer1.stop()
            buzzer2.stop()
            sleep(duration)
            continue 

        led.on() 

        # Alternate buzzers
        if index % 2 == 0:
            buzzer1.play(Tone(note))
        else:
            buzzer2.play(Tone(note))

        # We use 0.82 here for a slightly punchier pirate rhythm
        sleep(duration * 0.82)

        led.off()
        buzzer1.stop()
        buzzer2.stop()
        sleep(duration * 0.18)

except KeyboardInterrupt:
    print("\nAnchors aweigh! Song stopped.")