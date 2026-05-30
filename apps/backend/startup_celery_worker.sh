#!/bin/bash
# Start Celery worker with Beat scheduler
# This should be run on Render as a separate worker service

cd src
export APP_ENV=production
export PYTHON_VERSION=3.12.0
export DEBUG=false

echo "Starting Celery worker with Beat scheduler..."
celery -A pandapower.workers.celery_app worker -B --loglevel=info --concurrency=2
