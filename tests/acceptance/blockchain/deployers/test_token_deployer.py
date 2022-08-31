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

from nulink.blockchain.eth.signers.software import Web3Signer
from nulink.crypto.powers import TransactingPower
from nulink.blockchain.eth.agents import NulinkTokenAgent
from nulink.blockchain.eth.deployers import NuLinkTokenDeployer
from nulink.blockchain.eth.interfaces import BaseContractRegistry


@pytest.mark.skip('remove me')
def test_token_deployer_and_agent(testerchain, deployment_progress, test_registry):

    origin = testerchain.etherbase_account
    tpower = TransactingPower(account=origin, signer=Web3Signer(testerchain.client))

    # Trying to get token from blockchain before it's been published should fail
    with pytest.raises(BaseContractRegistry.UnknownContract):
        NulinkTokenAgent(registry=test_registry)

    # The big day...
    deployer = NuLinkTokenDeployer(registry=test_registry)

    deployment_receipts = deployer.deploy(progress=deployment_progress, transacting_power=tpower)

    for title, receipt in deployment_receipts.items():
        assert receipt['status'] == 1

    # deployment steps must match expected number of steps
    assert deployment_progress.num_steps == len(deployer.deployment_steps) == 1

    # Create a token instance
    token_agent = deployer.make_agent()
    token_contract = token_agent.contract

    expected_token_supply = token_contract.functions.totalSupply().call()
    assert expected_token_supply == token_agent.contract.functions.totalSupply().call()

    # Retrieve the token from the blockchain
    same_token_agent = NulinkTokenAgent(registry=test_registry)

    # Compare the contract address for equality
    assert token_agent.contract_address == same_token_agent.contract_address
    assert token_agent == same_token_agent  # __eq__
