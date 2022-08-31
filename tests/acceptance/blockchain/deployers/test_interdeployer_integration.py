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
from constant_sorrow import constants

from nulink.blockchain.eth.agents import (
    ContractAgency,
    NulinkTokenAgent,
)
from nulink.blockchain.eth.deployers import (
    BaseContractDeployer,
    NuLinkTokenDeployer,
)
from nulink.blockchain.eth.signers.software import Web3Signer
from nulink.crypto.powers import TransactingPower


@pytest.mark.skip()
def test_deploy_ethereum_contracts(testerchain,
                                   deployment_progress,
                                   test_registry):

    origin, *everybody_else = testerchain.client.accounts
    tpower = TransactingPower(account=origin,
                              signer=Web3Signer(testerchain.client))

    #
    # NuLink Token
    #
    token_deployer = NuLinkTokenDeployer(registry=test_registry)

    with pytest.raises(BaseContractDeployer.ContractDeploymentError):
        assert token_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not token_deployer.is_deployed()

    token_deployer.deploy(progress=deployment_progress, transacting_power=tpower)
    assert token_deployer.is_deployed()
    assert len(token_deployer.contract_address) == 42

    token_agent = NulinkTokenAgent(registry=test_registry)
    assert len(token_agent.contract_address) == 42
    assert token_agent.contract_address == token_deployer.contract_address

    another_token_agent = token_deployer.make_agent()
    assert len(another_token_agent.contract_address) == 42
    assert another_token_agent.contract_address == token_deployer.contract_address == token_agent.contract_address

    # overall deployment steps must match aggregated individual expected number of steps
    all_deployment_transactions = token_deployer.deployment_steps
    assert deployment_progress.num_steps == len(all_deployment_transactions)
