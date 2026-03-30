import time
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class POI:
    level: float
    direction: str
    type: str
    timestamp: float
    touched: bool = False
    active_since: Optional[float] = None
    max_distance_from_poi: float = 0.0
    candles_since_touch: int = 0

class FocusManager:
    def __init__(self, config: dict):
        self.expiry_candles = config.get("EXPIRY_CANDLES", 10)
        self.expiry_distance_pct = config.get("EXPIRY_DISTANCE_PCT", 0.005)
        self.max_watchlist = config.get("MAX_WATCHLIST_SIZE", 3)
        self._touch_tolerance = 0.001

        self.active_poi: Optional[POI] = None
        self.watchlist: List[POI] = []

    def update(self, current_price: float, new_candidates: List[Dict], bias: str):
        # 1. Update active POI expiry
        if self.active_poi:
            self.active_poi.candles_since_touch += 1
            dist_pct = abs(current_price - self.active_poi.level) / self.active_poi.level
            if dist_pct > self.active_poi.max_distance_from_poi:
                self.active_poi.max_distance_from_poi = dist_pct

            if (self.active_poi.candles_since_touch > self.expiry_candles or
                self.active_poi.max_distance_from_poi > self.expiry_distance_pct):
                print(f"[FocusManager] Expired active POI at {self.active_poi.level}")
                self.active_poi = None

        # 2. Activate a watchlist POI if touched
        if self.active_poi is None:
            for poi in self.watchlist:
                if abs(current_price - poi.level) / poi.level <= self._touch_tolerance:
                    self.active_poi = poi
                    self.active_poi.touched = True
                    self.active_poi.active_since = time.time()
                    self.active_poi.candles_since_touch = 0
                    self.active_poi.max_distance_from_poi = 0.0
                    print(f"[FocusManager] Activated POI at {self.active_poi.level} ({self.active_poi.type})")
                    self.watchlist = [p for p in self.watchlist if p.level != poi.level]
                    break

        # 3. Refresh watchlist with new candidates
        fresh_pois = []
        for cand in new_candidates:
            if self.active_poi and abs(cand['level'] - self.active_poi.level) / self.active_poi.level <= self._touch_tolerance:
                continue
            if any(abs(cand['level'] - p.level) / p.level <= self._touch_tolerance for p in self.watchlist):
                continue
            poi = POI(level=cand['level'], direction=bias, type=cand['type'], timestamp=time.time())
            fresh_pois.append(poi)

        fresh_pois.sort(key=lambda p: abs(p.level - current_price))
        self.watchlist = fresh_pois[:self.max_watchlist]

    def get_state(self) -> Dict:
        return {
            'active_poi': self.active_poi.level if self.active_poi else None,
            'watchlist': [p.level for p in self.watchlist]
        }