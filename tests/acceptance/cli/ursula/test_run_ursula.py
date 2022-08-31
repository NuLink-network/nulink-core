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
import time
from unittest import mock

import pytest
import pytest_twisted as pt
from twisted.internet import threads

from nulink.blockchain.eth.actors import Operator
from nulink.characters.base import Learner
from nulink.cli.literature import NO_CONFIGURATIONS_ON_DISK
from nulink.cli.main import nulink_cli
from nulink.config.characters import UrsulaConfiguration
from nulink.config.constants import (
    NULINK_ENVVAR_KEYSTORE_PASSWORD,
    TEMPORARY_DOMAIN,
)
from nulink.network.nodes import Teacher
from nulink.utilities.networking import LOOPBACK_ADDRESS, UnknownIPAddress
from tests.constants import (
    FAKE_PASSWORD_CONFIRMED,
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_IP_ADDRESS,
    TEST_ETH_PROVIDER_URI,
    TEST_HECO_PROVIDER_URI,
    YES_ENTER
)
from tests.utils.ursula import select_test_port, start_pytest_ursula_services


@mock.patch('glob.glob', return_value=list())
def test_missing_configuration_file(_default_filepath_mock, click_runner):
    cmd_args = ('ursula', 'run', '--network', TEMPORARY_DOMAIN)
    result = click_runner.invoke(nulink_cli, cmd_args, catch_exceptions=False)
    assert result.exit_code != 0
    configuration_type = UrsulaConfiguration.NAME
    assert NO_CONFIGURATIONS_ON_DISK.format(name=configuration_type.capitalize(),
                                            command=configuration_type) in result.output


def test_ursula_startup_ip_checkup(click_runner, mocker):
    target = 'nulink.cli.actions.configure.determine_external_ip_address'

    # Patch the get_external_ip call
    mocker.patch(target, return_value=MOCK_IP_ADDRESS)
    mocker.patch.object(UrsulaConfiguration, 'to_configuration_file', return_value=None)

    args = ('ursula', 'init', '--federated-only', '--network', TEMPORARY_DOMAIN)
    user_input = YES_ENTER + FAKE_PASSWORD_CONFIRMED
    result = click_runner.invoke(nulink_cli, args, catch_exceptions=False, input=user_input)
    assert result.exit_code == 0
    assert MOCK_IP_ADDRESS in result.output

    args = ('ursula', 'init', '--federated-only', '--network', TEMPORARY_DOMAIN, '--force')
    result = click_runner.invoke(nulink_cli, args, catch_exceptions=False, input=FAKE_PASSWORD_CONFIRMED)
    assert result.exit_code == 0

    # Patch get_external_ip call to error output
    mocker.patch(target, side_effect=UnknownIPAddress)
    args = ('ursula', 'init', '--federated-only', '--network', TEMPORARY_DOMAIN, '--force')
    result = click_runner.invoke(nulink_cli, args, catch_exceptions=True, input=FAKE_PASSWORD_CONFIRMED)
    assert result.exit_code == 1, result.output
    assert isinstance(result.exception, UnknownIPAddress)


@pt.inlineCallbacks
def test_ursula_run_with_prometheus_but_no_metrics_port(click_runner):
    args = ('ursula', 'run',  # Stat Ursula Command
            '--debug',  # Display log output; Do not attach console
            '--federated-only',  # Operating Mode
            '--dev',  # Run in development mode (local ephemeral node)
            '--dry-run',  # Disable twisted reactor in subprocess
            '--lonely',  # Do not load seednodes
            '--prometheus'  # Specify collection of prometheus metrics
            )

    result = yield threads.deferToThread(click_runner.invoke,
                                         nulink_cli, args,
                                         catch_exceptions=False)

    assert result.exit_code != 0
    # TODO prometheus not currently supported - follow-up in #2928
    expected_error = f"prometheus is not currently supported"
    # expected_error = f"Error: --metrics-port is required when using --prometheus"
    assert expected_error in result.output


@pt.inlineCallbacks
def test_run_lone_federated_default_development_ursula(click_runner):
    deploy_port = select_test_port()
    args = ('ursula', 'run',  # Stat Ursula Command
            '--debug',  # Display log output; Do not attach console
            '--federated-only',  # Operating Mode
            '--rest-port', deploy_port,  # Network Port
            '--dev',  # Run in development mode (ephemeral node)
            '--dry-run',  # Disable twisted reactor in subprocess
            '--lonely'  # Do not load seednodes
            )

    result = yield threads.deferToThread(click_runner.invoke,
                                         nulink_cli, args,
                                         catch_exceptions=False,
                                         input=INSECURE_DEVELOPMENT_PASSWORD + '\n')

    time.sleep(Learner._SHORT_LEARNING_DELAY)
    assert result.exit_code == 0, result.output
    assert "Running" in result.output
    assert f"{LOOPBACK_ADDRESS}:{deploy_port}" in result.output

    reserved_ports = (UrsulaConfiguration.DEFAULT_REST_PORT, UrsulaConfiguration.DEFAULT_DEVELOPMENT_REST_PORT)
    assert deploy_port not in reserved_ports


@pt.inlineCallbacks
def test_federated_ursula_learns_via_cli(click_runner, federated_ursulas):
    # Establish a running Teacher Ursula

    teacher = list(federated_ursulas)[0]
    teacher_uri = teacher.seed_node_metadata(as_teacher_uri=True)

    deploy_port = select_test_port()

    def run_ursula():
        i = start_pytest_ursula_services(ursula=teacher)
        args = ('ursula', 'run',
                '--debug',  # Display log output; Do not attach console
                '--federated-only',  # Operating Mode
                '--rest-port', deploy_port,  # Network Port
                '--teacher', teacher_uri,
                '--dev',  # Run in development mode (ephemeral node)
                '--dry-run'  # Disable twisted reactor
                )

        return threads.deferToThread(click_runner.invoke,
                                     nulink_cli, args,
                                     catch_exceptions=False,
                                     input=INSECURE_DEVELOPMENT_PASSWORD + '\n')

    # Run the Callbacks
    d = run_ursula()
    yield d

    result = d.result

    assert result.exit_code == 0
    assert "Starting services" in result.output
    assert f"{LOOPBACK_ADDRESS}:{deploy_port}" in result.output

    reserved_ports = (UrsulaConfiguration.DEFAULT_REST_PORT, UrsulaConfiguration.DEFAULT_DEVELOPMENT_REST_PORT)
    assert deploy_port not in reserved_ports

    # Check that CLI Ursula reports that it remembers the teacher and saves the TLS certificate
    assert f"Saved TLS certificate for {LOOPBACK_ADDRESS}" in result.output

    federated_ursulas.clear()


@pt.inlineCallbacks
def test_persistent_node_storage_integration(click_runner,
                                             custom_filepath,
                                             testerchain,
                                             blockchain_ursulas,
                                             agency_local_registry):

    alice, ursula, another_ursula, staking_provider, *all_yall = testerchain.unassigned_accounts
    filename = UrsulaConfiguration.generate_filename()
    another_ursula_configuration_file_location = custom_filepath / filename

    init_args = ('ursula', 'init',
                 '--eth-provider', TEST_ETH_PROVIDER_URI,
                 '--payment-provider', TEST_HECO_PROVIDER_URI,
                 '--operator-address', another_ursula,
                 '--network', TEMPORARY_DOMAIN,
                 '--payment-network', TEMPORARY_DOMAIN,
                 '--rest-host', MOCK_IP_ADDRESS,
                 '--config-root', str(custom_filepath.absolute()),
                 '--registry-filepath', str(agency_local_registry.filepath.absolute()),
                 )

    envvars = {NULINK_ENVVAR_KEYSTORE_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD}
    result = click_runner.invoke(nulink_cli, init_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0

    teacher = blockchain_ursulas.pop()
    teacher_uri = teacher.rest_information()[0].uri

    start_pytest_ursula_services(ursula=teacher)

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}\n'

    run_args = ('ursula', 'run',
                '--dry-run',
                '--debug',
                '--interactive',
                '--config-file', str(another_ursula_configuration_file_location.absolute()),
                '--teacher', teacher_uri)

    Operator.READY_TIMEOUT = 1
    with pytest.raises(Operator.ActorError):
        # Operator init success, but not bonded.
        result = yield threads.deferToThread(click_runner.invoke,
                                             nulink_cli, run_args,
                                             catch_exceptions=False,
                                             input=user_input,
                                             env=envvars)
    assert result.exit_code == 0

    # Run an Ursula amidst the other configuration files
    run_args = ('ursula', 'run',
                '--dry-run',
                '--debug',
                '--interactive',
                '--config-file',  str(another_ursula_configuration_file_location.absolute()))

    with pytest.raises(Operator.ActorError):
        # Operator init success, but not bonded.
        result = yield threads.deferToThread(click_runner.invoke,
                                             nulink_cli, run_args,
                                             catch_exceptions=False,
                                             input=user_input,
                                             env=envvars)
    assert result.exit_code == 0


def test_ursula_run_ip_checkup(testerchain, custom_filepath, click_runner, mocker, blockchain_ursulas, monkeypatch):

    # Mock IP determination
    target = 'nulink.cli.actions.configure.determine_external_ip_address'
    mocker.patch(target, return_value=MOCK_IP_ADDRESS)

    # Mock Teacher Resolution
    from nulink.characters.lawful import Ursula
    teacher = blockchain_ursulas.pop()
    mocker.patch.object(Ursula, 'from_teacher_uri', return_value=teacher)

    # Mock worker qualification
    staking_provider = blockchain_ursulas.pop()

    def set_staking_provider_address(operator, *args, **kwargs):
        operator.checksum_address = staking_provider.checksum_address
        return True
    monkeypatch.setattr(Operator, 'block_until_ready', set_staking_provider_address)

    # Setup
    teacher = blockchain_ursulas.pop()
    filename = UrsulaConfiguration.generate_filename()
    another_ursula_configuration_file_location = custom_filepath / filename

    # manual teacher
    run_args = ('ursula', 'run',
                '--dry-run',
                '--debug',
                '--config-file', str(another_ursula_configuration_file_location.absolute()),
                '--teacher', teacher.rest_url())
    result = click_runner.invoke(nulink_cli, run_args, catch_exceptions=False, input=FAKE_PASSWORD_CONFIRMED)
    assert result.exit_code == 0, result.output

    # default teacher
    run_args = ('ursula', 'run',
                '--dry-run',
                '--debug',
                '--config-file', str(another_ursula_configuration_file_location.absolute()))
    result = click_runner.invoke(nulink_cli, run_args, catch_exceptions=False, input=FAKE_PASSWORD_CONFIRMED)
    assert result.exit_code == 0, result.output

    blockchain_ursulas.clear()
