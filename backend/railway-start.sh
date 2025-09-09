#!/bin/bash
echo "�� Railway Backend Deployment"
cd /app
pip install --upgrade pip
pip install -r requirements.txt
python -m uvicorn backend_adapter:app --host 0.0.0.0 --port $PORT --workers 4
