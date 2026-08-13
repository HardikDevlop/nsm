#!/bin/bash
cd /home/agnigate/Desktop/NMS/hardik
source .venv/bin/activate
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
