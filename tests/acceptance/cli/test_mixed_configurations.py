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

import os
import shutil
from pathlib import Path

import pytest

from nulink.blockchain.eth.actors import Operator
from nulink.cli.main import nulink_cli
from nulink.config.characters import AliceConfiguration, UrsulaConfiguration
from nulink.config.constants import (
    NULINK_ENVVAR_KEYSTORE_PASSWORD,
    TEMPORARY_DOMAIN,
    NULINK_ENVVAR_ALICE_ETH_PASSWORD,
    NULINK_ENVVAR_BOB_ETH_PASSWORD
)
from nulink.crypto.keystore import Keystore, InvalidPassword
from nulink.network.nodes import Teacher
from tests.constants import (
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_CUSTOM_INSTALLATION_PATH,
    MOCK_IP_ADDRESS,
    MOCK_IP_ADDRESS_2,
    TEST_ETH_PROVIDER_URI,
    TEST_HECO_PROVIDER_URI
)


@pytest.fixture(scope='function')
def custom_filepath():
    _path = MOCK_CUSTOM_INSTALLATION_PATH
    shutil.rmtree(_path, ignore_errors=True)
    assert not _path.exists()
    yield _path
    shutil.rmtree(_path, ignore_errors=True)


def test_destroy_with_no_configurations(click_runner, custom_filepath):
    """Provide useful error messages when attempting to destroy when there is nothing to destroy"""
    assert not custom_filepath.exists()
    ursula_file_location = custom_filepath / 'ursula.json'
    destruction_args = ('ursula', 'destroy', '--config-file', str(ursula_file_location.absolute()))
    result = click_runner.invoke(nulink_cli, destruction_args, catch_exceptions=False)
    assert result.exit_code == 2
    assert "Error: Invalid value for '--config-file':" in result.output
    assert str(ursula_file_location) in result.output
    assert not custom_filepath.exists()


def test_coexisting_configurations(click_runner,
                                   custom_filepath,
                                   testerchain,
                                   agency_local_registry,
                                   mocker):
    #
    # Setup
    #

    if custom_filepath.exists():
        shutil.rmtree(str(custom_filepath), ignore_errors=True)
    assert not custom_filepath.exists()

    # Parse node addresses
    # TODO: Is testerchain & Full contract deployment needed here (causes massive slowdown)?
    alice, ursula, another_ursula, staking_provider, *all_yall = testerchain.unassigned_accounts

    envvars = {NULINK_ENVVAR_KEYSTORE_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD,
               NULINK_ENVVAR_ALICE_ETH_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD,
               NULINK_ENVVAR_BOB_ETH_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD}

    # Future configuration filepaths for assertions...
    public_keys_dir = custom_filepath / 'keystore' / 'public'
    known_nodes_dir = custom_filepath / 'known_nodes'

    # ... Ensure they do not exist to begin with.

    # No keys have been generated...
    assert not public_keys_dir.exists()

    # No known nodes exist...
    assert not known_nodes_dir.exists()

    # Not the configuration root...
    assert not custom_filepath.is_dir()

    # ... nothing
    None

    #
    # Create
    #

    # Expected config files
    alice_file_location = custom_filepath / AliceConfiguration.generate_filename()
    ursula_file_location = custom_filepath / UrsulaConfiguration.generate_filename()

    # Use a custom local filepath to init a persistent Alice
    alice_init_args = ('alice', 'init',
                       '--network', TEMPORARY_DOMAIN,
                       '--payment-network', TEMPORARY_DOMAIN,
                       '--eth-provider', TEST_ETH_PROVIDER_URI,
                       '--pay-with', alice,
                       '--registry-filepath', str(agency_local_registry.filepath.absolute()),
                       '--config-root', str(custom_filepath.absolute()))

    result = click_runner.invoke(nulink_cli, alice_init_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0

    # All configuration files still exist.
    assert alice_file_location.is_file()

    # Use the same local filepath to init a persistent Ursula
    init_args = ('ursula', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--payment-network', TEMPORARY_DOMAIN,
                 '--eth-provider', TEST_ETH_PROVIDER_URI,
                 '--payment-provider', TEST_HECO_PROVIDER_URI,
                 '--operator-address', ursula,
                 '--rest-host', MOCK_IP_ADDRESS,
                 '--registry-filepath', str(agency_local_registry.filepath.absolute()),
                 '--config-root', str(custom_filepath.absolute()))

    result = click_runner.invoke(nulink_cli, init_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0, result.output

    # All configuration files still exist.
    assert alice_file_location.is_file()
    assert ursula_file_location.is_file()

    key_spy = mocker.spy(Keystore, 'generate')

    # keystore signing key
    # Use the same local filepath to init another persistent Ursula
    init_args = ('ursula', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--payment-network', TEMPORARY_DOMAIN,
                 '--operator-address', another_ursula,
                 '--rest-host', MOCK_IP_ADDRESS_2,
                 '--registry-filepath', str(agency_local_registry.filepath.absolute()),
                 '--eth-provider', TEST_ETH_PROVIDER_URI,
                 '--payment-provider', TEST_HECO_PROVIDER_URI,
                 '--config-root', str(custom_filepath.absolute()))

    result = click_runner.invoke(nulink_cli, init_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0

    # All configuration files still exist.
    assert alice_file_location.is_file()

    kid = key_spy.spy_return.id[:8]
    another_ursula_configuration_file_location = custom_filepath / UrsulaConfiguration.generate_filename(modifier=kid)
    assert another_ursula_configuration_file_location.is_file()

    assert ursula_file_location.is_file()

    #
    # Run
    #

    # Run an Ursula amidst the other configuration files
    run_args = ('ursula', 'run',
                '--dry-run',
                '--no-ip-checkup',
                '--config-file', str(another_ursula_configuration_file_location.absolute()))

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}\n' * 2

    Operator.READY_POLL_RATE = 1
    Operator.READY_TIMEOUT = 1
    with pytest.raises(Operator.ActorError):
        # Operator init success, but not bonded.
        result = click_runner.invoke(nulink_cli, run_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    Operator.READY_TIMEOUT = None

    # All configuration files still exist.
    assert alice_file_location.is_file()
    assert another_ursula_configuration_file_location.is_file()
    assert ursula_file_location.is_file()

    # Check that the proper Ursula console is attached
    assert another_ursula in result.output

    #
    # Destroy
    #

    another_ursula_destruction_args = ('ursula', 'destroy',
                                       '--force',
                                       '--config-file', str(another_ursula_configuration_file_location.absolute()))
    result = click_runner.invoke(nulink_cli, another_ursula_destruction_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0
    assert not another_ursula_configuration_file_location.is_file()

    ursula_destruction_args = ('ursula', 'destroy', '--config-file', str(ursula_file_location.absolute()))
    result = click_runner.invoke(nulink_cli, ursula_destruction_args, input='Y', catch_exceptions=False, env=envvars)
    assert result.exit_code == 0
    assert 'y/N' in result.output
    assert not ursula_file_location.is_file()

    alice_destruction_args = ('alice', 'destroy', '--force', '--config-file', str(alice_file_location.absolute()))
    result = click_runner.invoke(nulink_cli, alice_destruction_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0
    assert not alice_file_location.is_file()


def test_corrupted_configuration(click_runner,
                                 custom_filepath,
                                 testerchain,
                                 agency_local_registry):

    #
    # Setup
    #

    # Please tell me why
    if custom_filepath.exists():
        shutil.rmtree(custom_filepath, ignore_errors=True)
    assert not custom_filepath.exists()
    
    alice, ursula, another_ursula, staking_provider, *all_yall = testerchain.unassigned_accounts

    #
    # Chaos
    #

    init_args = ('ursula', 'init',
                 '--eth-provider', TEST_ETH_PROVIDER_URI,
                '--payment-provider', TEST_HECO_PROVIDER_URI,
                 '--operator-address', another_ursula,
                 '--network', TEMPORARY_DOMAIN,
                 '--payment-network', TEMPORARY_DOMAIN,
                 '--rest-host', MOCK_IP_ADDRESS,
                 '--config-root', str(custom_filepath.absolute()),
                 )

    # Fails because password is too short and the command uses incomplete args (needs either -F or blockchain details)
    envvars = {NULINK_ENVVAR_KEYSTORE_PASSWORD: ''}

    with pytest.raises(InvalidPassword):
        result = click_runner.invoke(nulink_cli, init_args, catch_exceptions=False, env=envvars)
        assert result.exit_code != 0

    # Ensure there is no unintentional file creation (keys, config, etc.)
    top_level_config_root = [f.name for f in custom_filepath.iterdir()]
    assert 'ursula.config' not in top_level_config_root                         # no config file was created

    assert Path(custom_filepath).exists()
    keystore = custom_filepath / 'keystore'
    assert not keystore.exists()

    known_nodes = 'known_nodes'
    path = custom_filepath / known_nodes
    assert not path.exists()

    # Attempt installation again, with full args
    init_args = ('ursula', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--payment-network', TEMPORARY_DOMAIN,
                 '--eth-provider', TEST_ETH_PROVIDER_URI,
                 '--payment-provider', TEST_HECO_PROVIDER_URI,
                 '--operator-address', another_ursula,
                 '--rest-host', MOCK_IP_ADDRESS,
                 '--registry-filepath', str(agency_local_registry.filepath.absolute()),
                 '--config-root', str(custom_filepath.absolute()))

    envvars = {NULINK_ENVVAR_KEYSTORE_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD}
    result = click_runner.invoke(nulink_cli, init_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0

    default_filename = UrsulaConfiguration.generate_filename()

    # Ensure configuration creation
    top_level_config_root = [f.name for f in custom_filepath.iterdir()]
    assert default_filename in top_level_config_root, "JSON configuration file was not created"

    expected_fields = [
        # TODO: Only using in-memory node storage for now
        # 'known_nodes',
        'keystore',
        default_filename
    ]
    for field in expected_fields:
        assert field in top_level_config_root

    # "Corrupt" the configuration by removing the contract registry
    agency_local_registry.filepath.unlink()

    # Attempt destruction with invalid configuration (missing registry)
    ursula_file_location = custom_filepath / default_filename
    destruction_args = ('ursula', 'destroy', '--debug', '--config-file', str(ursula_file_location.absolute()))
    result = click_runner.invoke(nulink_cli, destruction_args, input='Y\n', catch_exceptions=False, env=envvars)
    assert result.exit_code == 0

    # Ensure character destruction
    top_level_config_root = [f.name for f in custom_filepath.iterdir()]
    assert default_filename not in top_level_config_root  # config file was destroyed
