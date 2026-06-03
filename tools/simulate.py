"""
Beetter — sensor data simulator.

Sends fake temperature, humidity, sound and light readings to the local Flask API,
mimicking what the LoRa receiver would do in production.

Usage:
    python simulate.py                          # one beehive (id=1), every 10s
    python simulate.py --ids 1 2 3              # three beehives
    python simulate.py --interval 5             # send every 5 seconds
    python simulate.py --url http://localhost:5000
    python simulate.py --burst 200              # inject 200 past points at once (fill charts)
"""

import argparse
import math
import random
import time
from datetime import datetime, timezone, timedelta

import requests

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_URL      = "http://localhost:5000"
DEFAULT_IDS      = [1]
DEFAULT_INTERVAL = 10   # seconds between readings

# ── Realistic beehive ranges ──────────────────────────────────────────────────
TEMP_BASE = 35.0   # °C  (brood nest is ~35 °C)
TEMP_AMP  = 2.0    # daily oscillation amplitude
HUM_BASE  = 60.0   # %
HUM_AMP   = 8.0

# Sound: peak frequency (Hz) and its amplitude (relative 0..1)
SOUND_FREQ_BASE = 230.0   # Hz  (healthy colony hum ~200-300 Hz)
SOUND_FREQ_AMP  = 40.0
SOUND_AMP_BASE  = 0.35
SOUND_AMP_AMP   = 0.15

# Light: exterior light level (%), day/night cycle
LIGHT_DAY_MAX = 100.0


def simulate_reading(beehive_id: int, when: datetime) -> dict:
    """Generate a realistic reading with sinusoidal drift + noise."""
    hour = when.hour + when.minute / 60
    phase = 2 * math.pi * hour / 24

    temp_int = TEMP_BASE + TEMP_AMP * math.sin(phase) + random.gauss(0, 0.3)
    hum_int  = HUM_BASE  - HUM_AMP  * math.sin(phase) + random.gauss(0, 1.0)
    # Exterior follows the day cycle more strongly and is cooler/drier
    temp_ext = 15.0 + 8.0 * math.sin(phase) + random.gauss(0, 0.5)
    hum_ext  = 70.0 - 20.0 * math.sin(phase) + random.gauss(0, 2.0)

    # Microphones: peak frequency (Hz) + amplitude of that peak
    sf_int = SOUND_FREQ_BASE + SOUND_FREQ_AMP * math.sin(phase) + random.gauss(0, 8)
    sa_int = SOUND_AMP_BASE  + SOUND_AMP_AMP  * math.sin(phase) + random.gauss(0, 0.03)
    sf_ext = 120.0 + 30.0 * math.sin(phase) + random.gauss(0, 10)
    sa_ext = 0.10  + 0.05 * math.sin(phase) + random.gauss(0, 0.02)

    # Photoresistor: bright at midday (100%), ~0 at night
    light = max(0.0, min(100.0, LIGHT_DAY_MAX * math.sin(math.pi * hour / 24) + random.gauss(0, 2)))

    return {
        "beehive_id": beehive_id,
        "temperature_int": round(temp_int, 2),
        "humidity_int":    round(max(0, min(100, hum_int)), 2),
        "temperature_ext": round(temp_ext, 2),
        "humidity_ext":    round(max(0, min(100, hum_ext)), 2),
        "sound_freq_int":  round(max(0, sf_int), 2),
        "sound_amp_int":   round(max(0, min(1, sa_int)), 3),
        "sound_freq_ext":  round(max(0, sf_ext), 2),
        "sound_amp_ext":   round(max(0, min(1, sa_ext)), 3),
        "light_ext":       round(light, 1),
        "timestamp":   when.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def send(url: str, payload: dict) -> bool:
    try:
        r = requests.post(f"{url}/api/data", json=payload, timeout=5)
        if r.ok:
            print(f"  ✓  beehive={payload['beehive_id']}  "
                  f"Tint={payload['temperature_int']}°C Hint={payload['humidity_int']}%  "
                  f"Text={payload['temperature_ext']}°C Hext={payload['humidity_ext']}%  "
                  f"Sint={payload['sound_freq_int']}Hz/{payload['sound_amp_int']}  "
                  f"L={payload['light_ext']}%  @ {payload['timestamp']}")
            return True
        print(f"  ✗  HTTP {r.status_code}: {r.text}")
        return False
    except requests.RequestException as e:
        print(f"  ✗  {e}")
        return False


def run_live(url: str, ids: list[int], interval: int):
    print(f"Sending live data to {url} every {interval}s — Ctrl+C to stop\n")
    while True:
        now = datetime.now(timezone.utc)
        for bid in ids:
            send(url, simulate_reading(bid, now))
        time.sleep(interval)


def run_burst(url: str, ids: list[int], points: int):
    """Inject `points` historical readings spread over the last 24 h."""
    print(f"Injecting {points} historical points per beehive into {url}\n")
    step = timedelta(hours=24) / points
    start = datetime.now(timezone.utc) - timedelta(hours=24)

    for bid in ids:
        print(f"Beehive {bid}:")
        ok = 0
        for i in range(points):
            when = start + step * i
            if send(url, simulate_reading(bid, when)):
                ok += 1
        print(f"  → {ok}/{points} points written\n")


def main():
    parser = argparse.ArgumentParser(description="Beetter sensor simulator")
    parser.add_argument("--url",      default=DEFAULT_URL, help="Flask app base URL")
    parser.add_argument("--ids",      nargs="+", type=int, default=DEFAULT_IDS,
                        metavar="ID", help="Beehive IDs to simulate")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                        metavar="SEC", help="Seconds between live readings")
    parser.add_argument("--burst",    type=int, default=0, metavar="N",
                        help="Inject N historical points then exit")
    args = parser.parse_args()

    if args.burst > 0:
        run_burst(args.url, args.ids, args.burst)
    else:
        run_live(args.url, args.ids, args.interval)


if __name__ == "__main__":
    main()
