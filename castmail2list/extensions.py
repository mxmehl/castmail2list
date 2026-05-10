# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: Apache-2.0

"""Shared Flask extension instances for CastMail2List."""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Initialised without an app here; init_app() is called in create_app().
limiter = Limiter(key_func=get_remote_address)
