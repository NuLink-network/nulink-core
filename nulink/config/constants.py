"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

from collections import namedtuple
from pathlib import Path

import os
from appdirs import AppDirs

from maya import MayaDT

import nulink

# Environment variables
NULINK_ENVVAR_KEYSTORE_PASSWORD = "NULINK_KEYSTORE_PASSWORD"
NULINK_ENVVAR_OPERATOR_ADDRESS = "NULINK_OPERATOR_ADDRESS"
NULINK_ENVVAR_OPERATOR_ETH_PASSWORD = "NULINK_OPERATOR_ETH_PASSWORD"
NULINK_ENVVAR_STAKING_PROVIDER_ETH_PASSWORD = "NULINK_STAKING_PROVIDER_ETH_PASSWORD"
NULINK_ENVVAR_ALICE_ETH_PASSWORD = "NULINK_ALICE_ETH_PASSWORD"
NULINK_ENVVAR_BOB_ETH_PASSWORD = "NULINK_BOB_ETH_PASSWORD"
NULINK_ENVVAR_ETH_PROVIDER_URI = "NULINK_ETH_PROVIDER_URI"

NULINK_ENVVAR_STAKING_PROVIDERS_PAGINATION_SIZE_LIGHT_NODE = "NULINK_STAKING_PROVIDERS_PAGINATION_SIZE_LIGHT_NODE"
NULINK_ENVVAR_STAKING_PROVIDERS_PAGINATION_SIZE = "NULINK_STAKING_PROVIDERS_PAGINATION_SIZE"

# Base Filepaths
NULINK_PACKAGE = Path(nulink.__file__).parent.resolve()
BASE_DIR = NULINK_PACKAGE.parent.resolve()
DEPLOY_DIR = BASE_DIR / 'deploy'
NULINK_TEST_DIR = BASE_DIR / 'tests'

# User Application Filepaths
APP_DIR = AppDirs(nulink.__title__, nulink.__author__)
DEFAULT_CONFIG_ROOT = Path(os.getenv('NULINK_CONFIG_ROOT', default=APP_DIR.user_data_dir))
USER_LOG_DIR = Path(os.getenv('NULINK_USER_LOG_DIR', default=APP_DIR.user_log_dir))
DEFAULT_LOG_FILENAME = "nulink.log"
DEFAULT_JSON_LOG_FILENAME = "nulink.json"
# Static Seednodes
SeednodeMetadata = namedtuple('seednode', ['checksum_address', 'rest_host', 'rest_port'])
SEEDNODES = tuple()

# Sentry (Add your public key and user ID below)
NULINK_SENTRY_PUBLIC_KEY = ""
NULINK_SENTRY_USER_ID = ""
NULINK_SENTRY_ENDPOINT = f"https://{NULINK_SENTRY_PUBLIC_KEY}@sentry.io/{NULINK_SENTRY_USER_ID}"

# Web
CLI_ROOT = NULINK_PACKAGE / 'network' / 'templates'
TEMPLATES_DIR = CLI_ROOT / 'templates'
MAX_UPLOAD_CONTENT_LENGTH = 1024 * 50

# Dev Mode
TEMPORARY_DOMAIN = ":temporary-domain:"  # for use with `--dev` node runtimes

# Event Blocks Throttling
NULINK_EVENTS_THROTTLE_MAX_BLOCKS = 'NULINK_EVENTS_THROTTLE_MAX_BLOCKS'

# Probationary period
END_OF_POLICIES_PROBATIONARY_PERIOD = MayaDT.from_iso8601('2022-6-16T23:59:59.0Z')

WEB3_ETH_MAX_RESPONSE_CONTENT_SIZE = 100_000_000_000_000  # for: Increase the maximum message response size in bytes
