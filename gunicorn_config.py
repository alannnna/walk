# Gunicorn configuration for production deployment
import os

port = os.getenv("PORT", "5001")
bind = f"0.0.0.0:{port}"
workers = 2
timeout = 120
