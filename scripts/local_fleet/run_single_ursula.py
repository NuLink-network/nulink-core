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


# WARNING This is not a mining script!
# you will not perform any re-encryptions, and you will not get paid.
# It might be (but might not be) useful for determining whether you have
# the proper dependencies and configuration to run an actual mining node.


from nuclick.testing import CliRunner

from nulink.cli.main import nulink_cli
from nulink.exceptions import DevelopmentInstallationRequired
from nulink.utilities.networking import LOOPBACK_ADDRESS

try:
    from tests.utils.ursula import select_test_port
except ImportError:
    raise DevelopmentInstallationRequired(importable_name='tests.utils.ursula.select_test_port')

click_runner = CliRunner()

DEMO_NODE_PORT = select_test_port()
DEMO_FLEET_STARTING_PORT = 11500

args = ['ursula', 'run',
        '--debug',
        '--federated-only',
        '--teacher', f'https://{LOOPBACK_ADDRESS}:{DEMO_FLEET_STARTING_PORT}',
        '--rest-port', DEMO_NODE_PORT,
        '--dev'
        ]

nulink_cli.main(args=args, prog_name="nulink-cli")
