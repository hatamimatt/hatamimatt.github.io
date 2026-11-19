#!/usr/bin/env python3
"""Refresh the globe's data: what the scheduled GitHub Actions job runs.

1. prepare_recent.py adds the newest GFS analysis time to the past five days.
2. prepare_forecast.py builds the newest GFS and ECMWF AIFS forecasts, skipping a model
   whose newest run is already built. A forecast failure keeps the previous forecast and
   does not stop the site from publishing.

    python update.py
"""
import subprocess, sys

if __name__ == "__main__":
    recent = subprocess.run([sys.executable, "prepare_recent.py"]).returncode
    forecast = subprocess.run([sys.executable, "prepare_forecast.py"]).returncode
    if forecast:
        print("Forecast update failed; publishing with the previous forecast", flush=True)
    sys.exit(recent)
