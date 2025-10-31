from utils import resource_path, kill_previous_instance
from ui import App

def main():
    kill_previous_instance(timeout_sec=2.0)
    app = App(logo_path=resource_path("logo.ico"))
    app.mainloop()

if __name__ == "__main__":
    main()
