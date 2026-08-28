import json
import threading
import os
from datetime import datetime, timedelta

class SharedMemory:
    def __init__(self, filepath="shared_memory.json"):
        self.filepath = filepath
        self.lock = threading.Lock()
        self._ensure_file()
    
    def _ensure_file(self):
        if not os.path.exists(self.filepath):
            with self.lock:
                with open(self.filepath, 'w') as f:
                    json.dump({}, f)
    
    def _load_data(self):
        with self.lock:
            with open(self.filepath, 'r') as f:
                return json.load(f)
    
    def _save_data(self, data):
        with self.lock:
            with open(self.filepath, 'w') as f:
                json.dump(data, f, indent=2)
    
    def add_fact(self, fact_id, content):
        data = self._load_data()
        data[fact_id] = {
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        self._save_data(data)
    
    def get_fact(self, fact_id):
        data = self._load_data()
        return data.get(fact_id, None)
    
    def update_fact(self, fact_id, content):
        data = self._load_data()
        if fact_id in data:
            data[fact_id]["content"] = content
            data[fact_id]["timestamp"] = datetime.now().isoformat()
            self._save_data(data)
            return True
        return False
    
    def cleanup_old_facts(self, hours=24):
        cutoff = datetime.now() - timedelta(hours=hours)
        data = self._load_data()
        to_delete = []
        
        for fact_id, fact_data in data.items():
            fact_time = datetime.fromisoformat(fact_data["timestamp"])
            if fact_time < cutoff:
                to_delete.append(fact_id)
        
        for fact_id in to_delete:
            del data[fact_id]
        
        if to_delete:
            self._save_data(data)
        
        return len(to_delete)