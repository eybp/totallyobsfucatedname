import os
import subprocess
import sys
import time
import threading
from pystray import Icon, MenuItem
from PIL import Image

VENV_PATH = "venv"  
MAIN_SCRIPT_PATH = "main.py" 
ICON_PATH = "icon.png" 
APP_NAME = "Roblox Trading Bot" 

process = None
running = False
restart_requested = False 
stop_event = threading.Event() 

first_run_attempted = False

def create_default_icon(icon_name="default_icon.png"):
    """Creates a simple default icon if ICON_PATH is not found."""
    try:
        img = Image.new('RGB', (64, 64), color = 'blue')
        img.save(icon_name)
        print(f"Created a default icon: {icon_name}")
        return icon_name
    except Exception as e:
        print(f"Could not create default icon: {e}. Tray icon might not display.")
        return None

def run_main_script():
    """Function to run main.py within its virtual environment."""
    global process, running, first_run_attempted
    venv_python_path = os.path.join(VENV_PATH, "Scripts", "python.exe") if sys.platform == "win32" \
                       else os.path.join(VENV_PATH, "bin", "python")

    if not os.path.exists(venv_python_path):
        print(f"Error: Python executable not found in virtual environment at {venv_python_path}")
        first_run_attempted = True 
        return

    cmd = [venv_python_path, MAIN_SCRIPT_PATH]
    print(f"Starting '{MAIN_SCRIPT_PATH}'...")
    try:
        process = subprocess.Popen(cmd,
                                   cwd=os.path.dirname(os.path.abspath(MAIN_SCRIPT_PATH)),
                                   creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0)
        running = True
        first_run_attempted = True 
        print(f"'{MAIN_SCRIPT_PATH}' started with PID: {process.pid}")
        process.wait() 
        running = False
        print(f"'{MAIN_SCRIPT_PATH}' exited with code: {process.returncode}")

    except Exception as e:
        print(f"Error running '{MAIN_SCRIPT_PATH}': {e}")
        running = False
        first_run_attempted = True 

def monitor_script():
    """Monitors the main script and restarts it if it crashes."""
    global restart_requested, first_run_attempted

    while not stop_event.is_set():
        if not running and not restart_requested:

            if not first_run_attempted:
                print("Monitor: Initiating first run of main.py...")
                start_main_script_threaded()

            else:

                print(f"'{MAIN_SCRIPT_PATH}' crashed or exited unexpectedly. Restarting in 5 seconds...")
                stop_event.wait(5) 
                if not stop_event.is_set(): 
                    start_main_script_threaded() 
        time.sleep(1) 

def start_main_script_threaded():
    """Starts the main script in a new thread."""
    script_thread = threading.Thread(target=run_main_script)
    script_thread.daemon = True 
    script_thread.start()

def terminate_main_script():
    """Attempts to gracefully terminate the main script process."""
    global process, running
    if process and process.poll() is None: 
        print(f"Attempting to terminate '{MAIN_SCRIPT_PATH}' (PID: {process.pid})...")
        try:
            if sys.platform == "win32":

                subprocess.run(['taskkill', '/PID', str(process.pid), '/F', '/T'], check=False, creationflags=subprocess.CREATE_NO_WINDOW)
            else:

                process.terminate()
            process.wait(timeout=5) 
            if process.poll() is None:
                print(f"'{MAIN_SCRIPT_PATH}' did not terminate gracefully. Killing (PID: {process.pid})...")
                process.kill() 
            print(f"'{MAIN_SCRIPT_PATH}' terminated.")
        except Exception as e:
            print(f"Error terminating '{MAIN_SCRIPT_PATH}': {e}")
        finally:
            running = False
            process = None
    elif process: 
        print(f"'{MAIN_SCRIPT_PATH}' was not running or already terminated.")
        running = False
        process = None

def on_quit(icon, item):
    """Callback for the 'Quit' menu item."""
    global restart_requested
    print("Quit selected from tray icon. Stopping supervisor...")
    restart_requested = True 
    stop_event.set() 
    terminate_main_script() 
    icon.stop() 

def on_restart(icon, item):
    """Callback for the 'Restart' menu item."""
    global restart_requested
    print("Restart selected from tray icon.")
    restart_requested = True 
    terminate_main_script() 
    restart_requested = False 
    start_main_script_threaded() 

def setup_tray_icon():
    """Sets up the system tray icon."""
    try:
        if os.path.exists(ICON_PATH):
            image = Image.open(ICON_PATH)
        else:
            print(f"Warning: Icon file '{ICON_PATH}' not found. Creating a default icon.")
            default_icon_path = create_default_icon()
            if default_icon_path and os.path.exists(default_icon_path):
                image = Image.open(default_icon_path)
            else:
                image = Image.new('RGB', (64, 64), color = 'grey') 
    except Exception as e:
        print(f"Error loading/creating icon: {e}. Using a fallback grey icon.")
        image = Image.new('RGB', (64, 64), color = 'grey') 

    menu = (MenuItem('Restart', on_restart),
            MenuItem('Quit', on_quit))
    icon = Icon(APP_NAME, image, APP_NAME, menu)
    icon.run() 

if __name__ == "__main__":
    print(f"Starting {APP_NAME} Supervisor...")

    monitor_thread = threading.Thread(target=monitor_script)
    monitor_thread.daemon = True
    monitor_thread.start()

    setup_tray_icon()

    print(f"{APP_NAME} Supervisor shutting down.")
    stop_event.set() 
    if monitor_thread.is_alive():
        monitor_thread.join(timeout=5) 
    if process and process.poll() is None: 
        terminate_main_script()
    print("Goodbye!")