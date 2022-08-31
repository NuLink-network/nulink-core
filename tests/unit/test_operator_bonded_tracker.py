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
import pytest_twisted
from twisted.internet import threads

from nulink.blockchain.eth.agents import ContractAgency
from nulink.blockchain.eth.constants import NULL_ADDRESS
from nulink.network.trackers import OperatorBondedTracker


@pytest_twisted.inlineCallbacks
def test_operator_never_bonded(mocker, get_random_checksum_address):
    ursula = mocker.Mock()
    operator_address = get_random_checksum_address()
    ursula.operator_address = operator_address

    application_agent = mocker.Mock()
    application_agent.get_staking_provider_from_operator.return_value = NULL_ADDRESS

    mocker.patch.object(ContractAgency, 'get_agent', return_value=application_agent)

    tracker = OperatorBondedTracker(ursula=ursula)
    try:
        d = threads.deferToThread(tracker.start)
        yield d

        with pytest.raises(OperatorBondedTracker.OperatorNoLongerBonded):
            d = threads.deferToThread(tracker.run)
            yield d
    finally:
        application_agent.get_staking_provider_from_operator.assert_called_once()
        ursula.stop.assert_called_once_with(halt_reactor=True)  # stop entire reactor
        tracker.stop()


@pytest_twisted.inlineCallbacks
def test_operator_bonded_but_becomes_unbonded(mocker, get_random_checksum_address):
    ursula = mocker.Mock()
    operator_address = get_random_checksum_address()
    ursula.operator_address = operator_address

    application_agent = mocker.Mock()
    staking_provider = get_random_checksum_address()
    application_agent.get_staking_provider_from_operator.return_value = staking_provider

    mocker.patch.object(ContractAgency, 'get_agent', return_value=application_agent)

    tracker = OperatorBondedTracker(ursula=ursula)
    try:
        d = threads.deferToThread(tracker.start)
        yield d

        # bonded
        for i in range(1, 10):
            d = threads.deferToThread(tracker.run)
            yield d
            assert application_agent.get_staking_provider_from_operator.call_count == i, "check for operator bonded called"
            ursula.stop.assert_not_called()

        # becomes unbonded
        application_agent.get_staking_provider_from_operator.return_value = NULL_ADDRESS
        with pytest.raises(OperatorBondedTracker.OperatorNoLongerBonded):
            d = threads.deferToThread(tracker.run)
            yield d
    finally:
        ursula.stop.assert_called_once_with(halt_reactor=True)  # stop entire reactor
        tracker.stop()
