
import os
import sys
import time

# Add the project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

# Import the functions
from core.actions.os_ops import os_volume_action, os_brightness_action, os_night_light_on_action

def test_volume():
    print("=" * 50)
    print("TESTING VOLUME CONTROL")
    print("=" * 50)
    
    # Get initial state
    print("Getting initial volume state...")
    try:
        # We need to get the current volume level somehow
        # Let's try using the os_volume_action with None to get current state
        # But the function requires level or mute parameter
        # Let's try a different approach - we'll just test if it works
        print("Attempting to set volume to 50%...")
        result = os_volume_action(level=50)
        print("Volume action result:", result)
        
        if result.success:
            print("✓ Volume control is working")
        else:
            print("✗ Volume control failed:", result.error)
            
    except Exception as e:
        print("Error during volume test:", e)

def test_brightness():
    print("\n" + "=" * 50)
    print("TESTING BRIGHTNESS CONTROL")
    print("=" * 50)
    
    try:
        print("Attempting to set brightness to 75%...")
        result = os_brightness_action(level=75)
        print("Brightness action result:", result)
        
        if result.success:
            print("✓ Brightness control is working")
        else:
            print("✗ Brightness control failed:", result.error)
            
    except Exception as e:
        print("Error during brightness test:", e)

def test_night_light():
    print("\n" + "=" * 50)
    print("TESTING NIGHT LIGHT")
    print("=" * 50)
    
    try:
        print("Attempting to turn on night light...")
        result = os_night_light_on_action()
        print("Night light action result:", result)
        
        if result.success:
            print("✓ Night light control is working")
        else:
            print("✗ Night light control failed:", result.error)
            
    except Exception as e:
        print("Error during night light test:", e)

def main():
    print("Starting ZARA PC Control Tests")
    print("Project: ZARA 3.0 CLEAN 002")
    print("Active Python:", sys.executable)
    print()
    
    test_volume()
    test_brightness()
    test_night_light()
    
    print("\n" + "=" * 50)
    print("TESTING COMPLETE")
    print("=" * 50)

if __name__ == "__main__":
    main()
