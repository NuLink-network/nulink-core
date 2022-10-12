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

from pathlib import Path

import pytest_twisted
import requests
from cryptography.hazmat.primitives import serialization
from twisted.internet import threads

from nulink.characters.lawful import Ursula
from nulink.utilities.version import check_version, check_version_pickle_symbol, VersionMismatchError
from nulink import __version__

@pytest_twisted.inlineCallbacks
def test_federated_nodes_connect_via_tls_and_verify(lonely_ursula_maker):
    node = lonely_ursula_maker(quantity=1).pop()
    node_deployer = node.get_deployer()

    node_deployer.addServices()
    node_deployer.catalogServers(node_deployer.hendrix)
    node_deployer.start()

    cert = node_deployer.cert.to_cryptography()
    cert_bytes = cert.public_bytes(serialization.Encoding.PEM)

    def check_node_with_cert(node, cert_file):
        response = requests.get("https://{}/public_information".format(node.rest_url()), verify=cert_file)
        response_data = response.content

        # check whether the version needs to be upgraded
        bytes_list = response_data.split(bytes(check_version_pickle_symbol, 'utf-8'))
        len_bytes_list = len(bytes_list)
        if len_bytes_list == 1:
            # old version
            raise VersionMismatchError(f"the teacher {node.rest_url()}'s version 0.1.0 is too low, you can't connect to it")
        else:
            # current len_bytes_list must be 2
            assert len_bytes_list == 2
            node_metadata_bytes, version_bytes = bytes_list
            version_str = version_bytes.decode('utf-8')

            if not check_version(version_str):
                # major version
                raise VersionMismatchError(
                    f"the teacher {node.rest_url()}'s version {version_str} do not match with the local node's version {__version__}, please upgrade the node or connect to the node of the latest version")


            ursula = Ursula.from_metadata_bytes(node_metadata_bytes)
            assert ursula == node

    try:
        with open("test-cert", "wb") as f:
            f.write(cert_bytes)
        yield threads.deferToThread(check_node_with_cert, node, "test-cert")
    finally:
        Path("test-cert").unlink()
