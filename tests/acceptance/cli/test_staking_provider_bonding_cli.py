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
from eth_typing import ChecksumAddress

from nulink.cli.commands.bond import bond, unbond
from nulink.config.constants import TEMPORARY_DOMAIN
from tests.constants import TEST_ETH_PROVIDER_URI, INSECURE_DEVELOPMENT_PASSWORD


@pytest.fixture(scope='module')
def operator_address(testerchain):
    return testerchain.unassigned_accounts.pop(1)


@pytest.fixture(scope='module')
@pytest.mark.usefixtures('test_registry_source_manager', 'agency')
def staking_provider_address(testerchain):
    return testerchain.unassigned_accounts.pop(1)


def test_nulink_bond_help(click_runner, testerchain):
    command = '--help'
    result = click_runner.invoke(bond, command, catch_exceptions=False)
    assert result.exit_code == 0


@pytest.fixture(scope='module')
def authorized_staking_provider(testerchain, threshold_staking, staking_provider_address, application_economics):
    # initialize threshold stake
    tx = threshold_staking.functions.setRoles(staking_provider_address).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(staking_provider_address, application_economics.min_authorization, 0, 0).transact()
    testerchain.wait_for_receipt(tx)
    return staking_provider_address


def exec_bond(click_runner, operator_address: ChecksumAddress, staking_provider_address: ChecksumAddress):
    command = ('--operator-address', operator_address,
               '--staking-provider', staking_provider_address,
               '--eth-provider', TEST_ETH_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--signer', TEST_ETH_PROVIDER_URI,
               '--force')
    result = click_runner.invoke(bond,
                                 command,
                                 catch_exceptions=False,
                                 env=dict(NULINK_STAKING_PROVIDER_ETH_PASSWORD=INSECURE_DEVELOPMENT_PASSWORD))
    return result


def exec_unbond(click_runner, staking_provider_address: ChecksumAddress):
    command = ('--staking-provider', staking_provider_address,
               '--eth-provider', TEST_ETH_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--signer', TEST_ETH_PROVIDER_URI,
               '--force')
    result = click_runner.invoke(unbond,
                                 command,
                                 catch_exceptions=False,
                                 env=dict(NULINK_STAKING_PROVIDER_ETH_PASSWORD=INSECURE_DEVELOPMENT_PASSWORD))
    return result


@pytest.mark.usefixtures('test_registry_source_manager', 'agency')
def test_nulink_bond_unauthorized(click_runner, testerchain, operator_address, staking_provider_address):
    result = exec_bond(
        click_runner=click_runner,
        operator_address=operator_address,
        staking_provider_address=staking_provider_address
    )
    assert result.exit_code == 1
    error_message = f'{staking_provider_address} is not authorized'
    assert error_message in result.output


@pytest.mark.usefixtures('test_registry_source_manager', 'agency', 'test_registry')
def test_nulink_bond(click_runner, testerchain, operator_address, authorized_staking_provider):
    result = exec_bond(
        click_runner=click_runner,
        operator_address=operator_address,
        staking_provider_address=authorized_staking_provider
    )
    assert result.exit_code == 0


@pytest.mark.usefixtures('test_registry_source_manager', 'agency')
def test_nulink_rebond_too_soon(click_runner, testerchain, operator_address, staking_provider_address):
    result = exec_bond(
        click_runner=click_runner,
        operator_address=operator_address,
        staking_provider_address=staking_provider_address
    )
    assert result.exit_code == 1
    error_message = 'Bonding/Unbonding not permitted until '
    assert error_message in result.output


@pytest.mark.usefixtures('test_registry_source_manager', 'agency')
def test_nulink_rebond_operator(click_runner,
                                  testerchain,
                                  operator_address,
                                  staking_provider_address,
                                  application_economics):
    testerchain.time_travel(seconds=application_economics.min_operator_seconds)
    result = exec_bond(
        click_runner=click_runner,
        operator_address=testerchain.unassigned_accounts[-1],
        staking_provider_address=staking_provider_address
    )
    assert result.exit_code == 0


@pytest.mark.usefixtures('test_registry_source_manager', 'agency')
def test_nulink_unbond_operator(click_runner,
                                  testerchain,
                                  staking_provider_address,
                                  application_economics):
    testerchain.time_travel(seconds=application_economics.min_operator_seconds)
    result = exec_unbond(click_runner=click_runner, staking_provider_address=staking_provider_address)
    assert result.exit_code == 0
