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
from typing import List

from nulink.blockchain.eth.registry import BaseContractRegistry
from nulink.characters.lawful import Ursula
from nulink.config.characters import AliceConfiguration, BobConfiguration, UrsulaConfiguration
from nulink.config.constants import TEMPORARY_DOMAIN
from tests.utils.middleware import MockRestMiddleware
from tests.utils.ursula import MOCK_URSULA_STARTING_PORT

TEST_CHARACTER_CONFIG_BASE_PARAMS = dict(
    dev_mode=True,
    domain=TEMPORARY_DOMAIN,
    start_learning_now=False,
    abort_on_learning_error=True,
    save_metadata=False,
    reload_metadata=False
)


def assemble(federated: bool,
             checksum_address: str = None,
             eth_provider_uri: str = None,
             test_registry: BaseContractRegistry = None,
             known_nodes: List[Ursula] = None) -> dict:

    """Assemble a dictionary of keyword arguments to use when constructing a test configuration."""

    # Validate input
    blockchain_params = all((eth_provider_uri, test_registry))
    if not federated and not blockchain_params:
        dev_help = "Cannot make test configuration: Provider URI and test registry must be passed in decentralized mode."
        raise ValueError(dev_help)
    elif federated and blockchain_params:
        dev_help = "Cannot make test configuration: Provider URI or test registry cannot be passed in FEDERATED mode."
        raise ValueError(dev_help)

    # Generate runtime config params
    runtime_params = dict(federated_only=federated,
                          eth_provider_uri=eth_provider_uri if not federated else None,
                          registry=test_registry if not federated else None,
                          network_middleware=MockRestMiddleware(),
                          known_nodes=known_nodes,
                          checksum_address=checksum_address)

    # Combine and return
    base_test_params = dict(**TEST_CHARACTER_CONFIG_BASE_PARAMS, **runtime_params)
    return base_test_params


def make_ursula_test_configuration(rest_port: int = MOCK_URSULA_STARTING_PORT,
                                   payment_provider: str = None,
                                   **assemble_kwargs
                                   ) -> UrsulaConfiguration:
    test_params = assemble(**assemble_kwargs)
    federated = test_params['federated_only']
    payment_provider = payment_provider if not federated else None
    payment_network = TEMPORARY_DOMAIN if not federated else None
    ursula_config = UrsulaConfiguration(**test_params,
                                        rest_port=rest_port,
                                        payment_provider=payment_provider,
                                        payment_network=payment_network,
                                        policy_registry=test_params['registry'])
    return ursula_config


def make_alice_test_configuration(payment_provider: str = None,
                                  **assemble_kwargs) -> AliceConfiguration:
    test_params = assemble(**assemble_kwargs)
    federated = test_params['federated_only']
    payment_provider = payment_provider if not federated else None
    payment_network = TEMPORARY_DOMAIN if not federated else None
    config = AliceConfiguration(**test_params,
                                payment_provider=payment_provider,
                                payment_network=payment_network,
                                policy_registry=test_params['registry'])
    return config


def make_bob_test_configuration(**assemble_kwargs) -> BobConfiguration:
    test_params = assemble(**assemble_kwargs)
    config = BobConfiguration(**test_params)
    return config
