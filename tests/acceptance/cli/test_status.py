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


import csv
import re

import pytest

from nulink.blockchain.eth.agents import (
    AdjudicatorAgent,
    ContractAgency,
    NulinkTokenAgent,
)
from nulink.blockchain.eth.signers.software import Web3Signer
from nulink.cli.commands.status import status
from nulink.config.constants import TEMPORARY_DOMAIN
from nulink.crypto.powers import TransactingPower


@pytest.mark.skip()
def test_nulink_status_network(click_runner, testerchain, agency_local_registry):

    network_command = ('network',
                       '--registry-filepath', str(agency_local_registry.filepath.absolute()),
                       '--eth-provider', TEST_ETH_PROVIDER_URI,
                       '--network', TEMPORARY_DOMAIN)

    result = click_runner.invoke(status, network_command, catch_exceptions=False)
    assert result.exit_code == 0

    token_agent = ContractAgency.get_agent(NulinkTokenAgent, registry=agency_local_registry)
    adjudicator_agent = ContractAgency.get_agent(AdjudicatorAgent, registry=agency_local_registry)

    agents = (token_agent, adjudicator_agent)
    for agent in agents:
        contract_regex = f"^{agent.contract_name} \\.+ {agent.contract_address}"
        assert re.search(contract_regex, result.output, re.MULTILINE)

    assert re.search(f"^Provider URI \\.+ {TEST_ETH_PROVIDER_URI}", result.output, re.MULTILINE)

