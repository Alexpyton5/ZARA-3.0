
import os
import sys

# Add the project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

# Import the functions directly
from core.actions.windows_radios import os_wifi_status_action, os_wifi_on_action, os_wifi_off_action, os_bluetooth_status_action, os_bluetooth_on_action, os_bluetooth_off_action

def main():
    print("Starting ZARA Wi-Fi/Bluetooth Tests")
    print("Project: ZARA 3.0 CLEAN 002")
    print()
    
    print("=" * 50)
    print("TESTING WIFI CONTROL")
    print("=" * 50)
    
    try:
        print("Getting initial WiFi state...")
        result = os_wifi_status_action()
        print("WiFi status result:", result)
        
        if result.success:
            print("✓ WiFi status check is working")
        else:
            print("✗ WiFi status check failed:", result.error)
            
        print("Attempting to enable WiFi...")
        result = os_wifi_on_action()
        print("WiFi on result:", result)
        
        if result.success:
            print("✓ WiFi enable is working")
        else:
            print("✗ WiFi enable failed:", result.error)
            
        print("Attempting to disable WiFi...")
        result = os_wifi_off_action()
        print("WiFi off result:", result)
        
        if result.success:
            print("✓ WiFi disable is working")
        else:
            print("✗ WiFi disable failed:", result.error)
            
    except Exception as e:
        print("Error during WiFi test:", e)

def test_bluetooth():
    print("\n" + "=" * 50)
    print("TESTING BLUETOOTH CONTROL")
    print("=" * 50)
    
    try:
        print("Getting initial Bluetooth state...")
        result = os_bluetooth_status_action()
        print("Bluetooth status result:", result)
        
        if result.success:
            print("✓ Bluetooth status check is working")
        else:
            print("✗ Bluetooth status check failed:", result.error)
            
        print("Attempting to enable Bluetooth...")
        result = os_bluetooth_on_action()
        print("Bluetooth on result:", result)
        
        if result.success:
            print("✓ Bluetooth enable is working")
        else:
            print("✗ Bluetooth enable failed:", result.error)
            
        print("Attempting to disable Bluetooth...")
        result = os_bluetooth_off_action()
        print("Bluetooth off result:", result)
        
        if result.success:
            print("✓ Bluetooth disable is working")
        else:
            print("✗ Bluetooth disable failed:", result.error)
            
    except Exception as e:
        print("Error during Bluetooth test:", e)

def main():
    print("Starting ZARA Wi-Fi/Bluetooth Tests")
    print("Project: ZARA 3.0 CLEAN 002")
    print()
    
    test_wifi()
    test_bluetooth()
    
    print("\n" + "=" * 50)
    print("TESTING COMPLETE")
    print("=" * 50)

if __name__ == "__main__":
    main()
