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


import pytest_twisted as pt

from nulink.config.storages import LocalFileBasedNodeStorage
from tests.acceptance.cli.lifecycle import run_entire_cli_lifecycle


@pt.inlineCallbacks
def test_decentralized_cli_lifecycle(click_runner,
                                     testerchain,
                                     random_policy_label,
                                     blockchain_ursulas,
                                     custom_filepath,
                                     custom_filepath_2,
                                     agency_local_registry,
                                     mocker):

    # For the purposes of this test, assume that all peers are already known and stored.
    mocker.patch.object(LocalFileBasedNodeStorage, 'all', return_value=blockchain_ursulas)

    yield run_entire_cli_lifecycle(click_runner,
                                   random_policy_label,
                                   blockchain_ursulas,
                                   custom_filepath,
                                   custom_filepath_2,
                                   agency_local_registry.filepath,
                                   testerchain=testerchain)
