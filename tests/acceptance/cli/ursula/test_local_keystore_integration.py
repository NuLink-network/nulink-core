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


import json
import secrets
from pathlib import Path

import pytest
from eth_account import Account
from web3 import Web3

from nulink.blockchain.eth.agents import PREApplicationAgent, ContractAgency
from nulink.blockchain.eth.signers import KeystoreSigner
from nulink.blockchain.eth.signers.software import Web3Signer
from nulink.cli.main import nulink_cli
from nulink.config.characters import UrsulaConfiguration
from nulink.config.constants import (
    NULINK_ENVVAR_KEYSTORE_PASSWORD,
    NULINK_ENVVAR_OPERATOR_ETH_PASSWORD,
    TEMPORARY_DOMAIN,
)
from nulink.crypto.powers import TransactingPower
from tests.constants import (
    MOCK_IP_ADDRESS,
    TEST_ETH_PROVIDER_URI, INSECURE_DEVELOPMENT_PASSWORD, TEST_HECO_PROVIDER_URI
)
from tests.utils.ursula import select_test_port


@pytest.fixture(scope='module')
def mock_funded_account_password_keystore(tmp_path_factory, testerchain, threshold_staking, application_economics, test_registry):
    """
    Generate a random keypair & password and create a local keystore. Then prepare a staking provider
    for ursula. Then check that the correct ursula ethereum key signs the commitment.
    """
    keystore = tmp_path_factory.mktemp('keystore', numbered=True)
    password = secrets.token_urlsafe(12)
    account = Account.create()
    path = keystore / f'{account.address}'
    json.dump(account.encrypt(password), open(path, 'x+t'))

    testerchain.wait_for_receipt(
        testerchain.client.w3.eth.sendTransaction({
            'to': account.address,
            'from': testerchain.etherbase_account,
            'value': Web3.toWei('1', 'ether')}))

    # initialize threshold stake
    provider_address = testerchain.unassigned_accounts[0]
    tx = threshold_staking.functions.setRoles(provider_address).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(provider_address, application_economics.min_authorization, 0, 0).transact()
    testerchain.wait_for_receipt(tx)

    provider_power = TransactingPower(account=provider_address, signer=Web3Signer(testerchain.client))
    provider_power.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)

    pre_application_agent = ContractAgency.get_agent(PREApplicationAgent, registry=test_registry)
    pre_application_agent.bond_operator(staking_provider=provider_address,
                                        operator=account.address,
                                        transacting_power=provider_power)

    return account, password, keystore


def test_ursula_and_local_keystore_signer_integration(click_runner,
                                                      tmp_path,
                                                      staking_providers,
                                                      application_economics,
                                                      mocker,
                                                      mock_funded_account_password_keystore,
                                                      testerchain):
    config_root_path = tmp_path
    ursula_config_path = config_root_path / UrsulaConfiguration.generate_filename()
    worker_account, password, mock_keystore_path = mock_funded_account_password_keystore

    #
    # Operator Steps
    #

    # Good signer...
    mock_signer_uri = f'keystore:{mock_keystore_path}'
    pre_config_signer = KeystoreSigner.from_signer_uri(uri=mock_signer_uri, testnet=True)
    assert worker_account.address in pre_config_signer.accounts

    deploy_port = select_test_port()

    init_args = ('ursula', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--payment-network', TEMPORARY_DOMAIN,
                 '--operator-address', worker_account.address,
                 '--config-root', str(config_root_path.absolute()),
                 '--eth-provider', TEST_ETH_PROVIDER_URI,
                 '--payment-provider', TEST_HECO_PROVIDER_URI,
                 '--rest-host', MOCK_IP_ADDRESS,
                 '--rest-port', deploy_port,

                 # The bit we are testing for here
                 '--signer', mock_signer_uri)

    cli_env = {
        NULINK_ENVVAR_KEYSTORE_PASSWORD: password,
        NULINK_ENVVAR_OPERATOR_ETH_PASSWORD: password,
    }
    result = click_runner.invoke(nulink_cli, init_args, catch_exceptions=False, env=cli_env)
    assert result.exit_code == 0, result.stdout

    # Inspect the configuration file for the signer URI
    with open(ursula_config_path, 'r') as config_file:
        raw_config_data = config_file.read()
        config_data = json.loads(raw_config_data)
        assert config_data['signer_uri'] == mock_signer_uri,\
            "Keystore URI was not correctly included in configuration file"

    # Recreate a configuration with the signer URI preserved
    ursula_config = UrsulaConfiguration.from_configuration_file(ursula_config_path)
    assert ursula_config.signer_uri == mock_signer_uri

    # Mock decryption of web3 client keystore
    mocker.patch.object(Account, 'decrypt', return_value=worker_account.key)
    ursula_config.keystore.unlock(password=password)

    # Produce an Ursula with a Keystore signer correctly derived from the signer URI, and don't do anything else!
    ursula = ursula_config.produce()
    ursula.signer.unlock_account(account=worker_account.address, password=password)

    try:
        # Verify the keystore path is still preserved
        assert isinstance(ursula.signer, KeystoreSigner)
        assert isinstance(ursula.signer.path, Path), "Use Path"
        assert ursula.signer.path.absolute() == mock_keystore_path.absolute()

        # Show that we can produce the exact same signer as pre-config...
        assert pre_config_signer.path == ursula.signer.path

        # ...and that transactions are signed by the keystore signer
        txhash = ursula.confirm_address()
        receipt = testerchain.wait_for_receipt(txhash)
        transaction_data = testerchain.client.w3.eth.getTransaction(receipt['transactionHash'])
        assert transaction_data['from'] == worker_account.address
    finally:
        ursula.stop()
