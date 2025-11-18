"""Gunicorn configuration file"""

# pylint: disable=invalid-name

# Server socket
bind = "0.0.0.0:8000"

# Worker processes
workers = 1
worker_class = "sync"
timeout = 30

# Logging
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
loglevel = "debug"

# Process naming
proc_name = "castmail2list"
