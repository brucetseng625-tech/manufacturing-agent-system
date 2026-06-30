import time
import threading

class SheetsCache:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if not cls._instance:
                cls._instance = super(SheetsCache, cls).__new__(cls, *args, **kwargs)
                cls._instance._cache = {}
                cls._instance._ttl = 300  # 5 minutes TTL
            return cls._instance

    def get(self, key):
        with self._lock:
            if key in self._cache:
                timestamp, data = self._cache[key]
                if time.time() - timestamp < self._ttl:
                    return data
            return None

    def set(self, key, data):
        with self._lock:
            self._cache[key] = (time.time(), data)

    def invalidate(self, key=None):
        with self._lock:
            if key:
                self._cache.pop(key, None)
            else:
                self._cache.clear()

def get_sheets_cache():
    return SheetsCache()
