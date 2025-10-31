import tkinter as tk
from utils import resource_path, kill_previous_instance
from ui import App
from splash import show_splash

def main():
    kill_previous_instance(timeout_sec=2.0)
    
    # Create hidden root for splash screen
    root = tk.Tk()
    root.withdraw()
    
    # Show splash screen (3 seconds)
    logo_path = resource_path("logo_smp.png")
    show_splash(root, logo_path=logo_path, duration=3000)
    
    # Destroy temporary root
    root.destroy()
    
    # Start main application
    app = App(logo_path=logo_path)
    app.mainloop()

if __name__ == "__main__":
    main()
