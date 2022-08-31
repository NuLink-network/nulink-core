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

# Get an interactive Python session with all the NuLink agents loaded by running:
#    python -i scripts/hooks/nulink_agents.py <NETWORK> <ETH_PROVIDER_URI>

import os
import sys

from constant_sorrow.constants import NO_BLOCKCHAIN_CONNECTION

from nulink.blockchain.eth.agents import ContractAgency, NulinkTokenAgent
from nulink.blockchain.eth.agents import (
    PREApplicationAgent,
    SubscriptionManagerAgent
)
from nulink.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nulink.blockchain.eth.registry import InMemoryContractRegistry
from nulink.config.constants import NULINK_ENVVAR_ETH_PROVIDER_URI
from nulink.control.emitters import StdoutEmitter
from nulink.utilities.logging import GlobalLoggerSettings

NO_BLOCKCHAIN_CONNECTION.bool_value(False)  # FIXME

GlobalLoggerSettings.start_console_logging()

emitter = StdoutEmitter(verbosity=2)

try:
    eth_provider_uri = sys.argv[2]
except IndexError:
    eth_provider_uri = os.getenv(NULINK_ENVVAR_ETH_PROVIDER_URI)
    if not eth_provider_uri:
        emitter.message("You have to pass a provider URI", color='red')
        sys.exit(-1)

try:
    network = sys.argv[1]
except IndexError:
    network = "heco_testnet"

BlockchainInterfaceFactory.initialize_interface(eth_provider_uri=eth_provider_uri, light=False, emitter=emitter)
blockchain = BlockchainInterfaceFactory.get_interface(eth_provider_uri=eth_provider_uri)

emitter.echo(message="Reading Latest Chaindata...")
blockchain.connect()

registry = InMemoryContractRegistry.from_latest_publication(network=network)
emitter.echo(f"NOTICE: Connecting to {network} network", color='yellow')

token_agent = ContractAgency.get_agent(agent_class=NulinkTokenAgent, registry=registry)  # type: NulinkTokenAgent
application_agent = ContractAgency.get_agent(agent_class=PREApplicationAgent, registry=registry)  # type: PREApplicationAgent
subscription_agent = ContractAgency.get_agent(agent_class=SubscriptionManagerAgent, registry=registry)  # type: SubscriptionManagerAgent

message = f"NuLink agents pre-loaded in variables 'token_agent', 'subscription_agent' and 'application_agent'"
emitter.echo(message=message, color='green')
