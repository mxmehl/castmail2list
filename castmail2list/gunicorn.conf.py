# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: Apache-2.0

"""Gunicorn configuration file"""

# pylint: disable=invalid-name

# Server socket
bind = "0.0.0.0:2278"

# Worker processes
workers = 1
worker_class = "sync"
timeout = 30

# Logging
accesslog = "-"  # Log to stdout
errorlog = "-"  # Log to stderr
loglevel = "info"

# Process naming
proc_name = "castmail2list"
