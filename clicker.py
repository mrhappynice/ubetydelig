import pyautogui
import time

print("Script started. Move the mouse to change the click location.")
print("Press Ctrl+C in the terminal to stop.")

try:
    while True:
        # Get the current mouse position
        x, y = pyautogui.position()
        # Click at the current position
        pyautogui.click(x, y)
        # Wait a short time before the next click (adjust as needed)
        time.sleep(5)
except KeyboardInterrupt:
    print("Script terminated by user.")
