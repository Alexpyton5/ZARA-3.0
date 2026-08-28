import time
import os
from datetime import datetime

class Vigilance:
    def __init__(self, watch_paths=None, callback=None, poll_interval=5):
        self.watch_paths = watch_paths or []
        self.callback = callback or (lambda changes: None)
        self.poll_interval = poll_interval
        self.last_state = self._snapshot()
    
    def _snapshot(self):
        state = {}
        for path in self.watch_paths:
            if not os.path.exists(path):
                state[path] = None
                continue
            if os.path.isfile(path):
                stat = os.stat(path)
                state[path] = (stat.st_mtime, stat.st_size)
            else:
                # directory: simple recursive mtime of newest file
                newest = 0
                for root, dirs, files in os.walk(path):
                    for f in files:
                        fp = os.path.join(root, f)
                        try:
                            mtime = os.stat(fp).st_mtime
                            if mtime > newest:
                                newest = mtime
                        except:
                            pass
                state[path] = newest
        return state
    
    def check_changes(self):
        current = self._snapshot()
        changes = {}
        for path in set(list(self.last_state.keys()) + list(current.keys())):
            old = self.last_state.get(path)
            new = current.get(path)
            if old != new:
                changes[path] = {'old': old, 'new': new}
        if changes:
            self.callback(changes)
        self.last_state = current
        return changes
    
    def start(self):
        print(f"Vigilância iniciada em {self.watch_paths}")
        try:
            while True:
                self.check_changes()
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            print("Vigilância parada.")

if __name__ == "__main__":
    def print_changes(changes):
        print(f"[{datetime.now()}] Mudanças detectadas: {changes}")
    v = Vigilance(watch_paths=[r"C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\core"], callback=print_changes)
    v.start()