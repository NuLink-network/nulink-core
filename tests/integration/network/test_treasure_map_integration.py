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


import pytest

from nucypher_core import HRAC

from nulink.characters.lawful import Ursula
from nulink.crypto.utils import keccak_digest


def test_alice_creates_policy_with_correct_hrac(federated_alice, federated_bob, idle_federated_policy):
    """
    Alice creates a Policy.  It has the proper HRAC, unique per her, Bob, and the label
    """
    from nulink.blockchain.eth.networks import NetworksInventory
    chain_id = NetworksInventory.get_ethereum_chain_id(federated_alice.domain)

    # TODO: what are we actually testing here?
    from nulink.policy.crosschain import CrossChainHRAC
    assert idle_federated_policy.hrac == CrossChainHRAC(HRAC(federated_alice.stamp.as_umbral_pubkey(),
                                                             federated_bob.stamp.as_umbral_pubkey(),
                                                             idle_federated_policy.label), chain_id=chain_id)


def test_alice_does_not_update_with_old_ursula_info(federated_alice, federated_ursulas):
    ursula = list(federated_ursulas)[0]
    old_metadata = bytes(ursula.metadata())

    # Alice has remembered Ursula.
    assert federated_alice.known_nodes[ursula.checksum_address] == ursula

    # But now, Ursula wants to sign and date her metadata again.  This causes a new timestamp.
    ursula._metadata = None
    ursula.metadata()

    # Indeed, her metadata is not the same now.
    assert bytes(ursula.metadata()) != old_metadata

    old_ursula = Ursula.from_metadata_bytes(old_metadata)

    # Once Alice learns about Ursula's updated info...
    federated_alice.remember_node(ursula)

    # ...she can't learn about old ursula anymore.
    federated_alice.remember_node(old_ursula)

    new_metadata = bytes(federated_alice.known_nodes[ursula.checksum_address].metadata())
    assert new_metadata != old_metadata
