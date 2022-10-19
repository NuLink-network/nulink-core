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

import random
from ipaddress import ip_address
from typing import Union, Optional

import requests
from requests.exceptions import RequestException, HTTPError, JSONDecodeError

from nulink.acumen.perception import FleetSensor
from nulink.blockchain.eth.registry import BaseContractRegistry
from nulink.config.storages import LocalFileBasedNodeStorage
from nulink.network.exceptions import NodeSeemsToBeDown
from nulink.network.middleware import RestMiddleware, NulinkMiddlewareClient
from nulink.utilities.logging import Logger
from nulink.utilities.version import check_version, VersionMismatchError
from nulink import __version__


class UnknownIPAddress(RuntimeError):
    pass


class InvalidOperatorIP(RuntimeError):
    """Raised when an Ursula is using an invalid IP address for it's server."""


CENTRALIZED_IP_ORACLE_URL = 'https://ifconfig.me/'

LOOPBACK_ADDRESS = '127.0.0.1'

RequestErrors = (
    # https://requests.readthedocs.io/en/latest/user/quickstart/#errors-and-exceptions
    ConnectionError,
    TimeoutError,
    RequestException,
    HTTPError
)

RESERVED_IP_ADDRESSES = (
    '0.0.0.0',
    LOOPBACK_ADDRESS,
    '1.2.3.4'
)

IP_DETECTION_LOGGER = Logger('external-ip-detection')


def validate_operator_ip(ip: str) -> None:
    if ip in RESERVED_IP_ADDRESSES:
        raise InvalidOperatorIP(f"{ip} is not a valid or permitted operator IP address. "
                                f"Verify the 'rest_host' configuration value is set to the "
                                f"external IPV4 address")


def _request(url: str, certificate=None) -> Union[str, None]:
    """
    Utility function to send a GET request to a URL returning it's
    text content or None, suppressing all errors. Certificate is
    needed if the remote URL source is self-signed.
    """
    try:
        # 'None' or 'True' will verify self-signed certificates
        response = requests.get(url, verify=certificate)
    except RequestErrors:
        return None
    if response.status_code == 200:
        return response.text


def _request_from_node(teacher,
                       client: Optional[NulinkMiddlewareClient] = None,
                       timeout: int = 8,
                       log: Logger = IP_DETECTION_LOGGER
                       ) -> Union[str, None]:
    if not client:
        client = NulinkMiddlewareClient()
    try:
        response = client.get(node_or_sprout=teacher, path=f"ping", timeout=timeout)  # TLS certificate logic within
    except RestMiddleware.UnexpectedResponse:
        # 404, 405, 500, All server response codes handled by will be caught here.
        return  # Default teacher does not support this request - just move on.
    except NodeSeemsToBeDown:
        # This node is unreachable.  Move on.
        return

    if response.status_code == 200:
        try:
            # "application/json" in response.headers['Content-Type'].lower()
            ping_response = response.json()
            ver = ping_response.get('version')
            if not check_version(ver):
                # major version
                raise VersionMismatchError(
                    f"the teacher {ping_response.get('requester_ip')}'s version {ver} do not match with the local node's version {__version__}, please upgrade the node or connect to the node of the latest version")

        except JSONDecodeError:
            # old version content-type is text/html
            raise VersionMismatchError(f"the teacher {teacher.rest_interface.uri}'s version 0.1.0 is too low, you can't connect to it")

        try:
            ip = str(ip_address(ping_response.get('requester_ip')))
        except ValueError:
            error = f"Teacher {teacher} returned an invalid IP response; Got {ping_response.get('requester_ip')}"
            raise UnknownIPAddress(error)
        log.info(f'Fetched external IP address ({ip}) from teacher ({teacher}).')
        return ip
    else:
        # Something strange happened... move on anyways.
        log.debug(f'Failed to get external IP from teacher node ({teacher} returned {response.status_code})')


def get_external_ip_from_default_teacher(network: str,
                                         federated_only: bool = False,
                                         registry: Optional[BaseContractRegistry] = None,
                                         log: Logger = IP_DETECTION_LOGGER
                                         ) -> Union[str, None]:
    # Prevents circular imports
    from nulink.characters.lawful import Ursula
    from nulink.network.nodes import TEACHER_NODES

    if federated_only and registry:
        raise ValueError('Federated mode must not be true if registry is provided.')

    base_error = 'Cannot determine IP using default teacher'

    if network not in TEACHER_NODES:
        log.debug(f'{base_error}: Unknown network "{network}".')
        return

    ####
    # TODO: Clean this mess #1481 (Federated Mode)
    node_storage = LocalFileBasedNodeStorage(federated_only=federated_only)
    Ursula.set_cert_storage_function(node_storage.store_node_certificate)
    Ursula.set_federated_mode(federated_only)
    #####

    external_ip = None
    for teacher_uri in TEACHER_NODES[network]:
        try:
            teacher = Ursula.from_teacher_uri(teacher_uri=teacher_uri,
                                              federated_only=federated_only,
                                              min_stake=0)  # TODO: Handle customized min stake here.
            # TODO: Pass registry here to verify stake (not essential here since it's a hardcoded node)
            external_ip = _request_from_node(teacher=teacher)
            # Found a reachable teacher, return from loop
            if external_ip:
                break
        except NodeSeemsToBeDown:
            # Teacher is unreachable, try next one
            continue

    if not external_ip:
        log.debug(f'{base_error}: No teacher available for network "{network}".')
        return

    return external_ip


def get_external_ip_from_known_nodes(known_nodes: FleetSensor,
                                     sample_size: int = 3,
                                     log: Logger = IP_DETECTION_LOGGER
                                     ) -> Union[str, None]:
    """
    Randomly select a sample of peers to determine the external IP address
    of this host. The first node to reply successfully will be used.
    # TODO: Parallelize the requests and compare results.
    """
    if len(known_nodes) < sample_size:
        return  # There are too few known nodes
    sample = random.sample(list(known_nodes), sample_size)
    client = NulinkMiddlewareClient()
    for node in sample:
        ip = _request_from_node(teacher=node, client=client)
        if ip:
            log.info(f'Fetched external IP address ({ip}) from randomly selected known nodes.')
            return ip


def get_external_ip_from_centralized_source(log: Logger = IP_DETECTION_LOGGER) -> Union[str, None]:
    """Use hardcoded URL to determine the external IP address of this host."""
    ip = _request(url=CENTRALIZED_IP_ORACLE_URL)
    if ip:
        log.info(f'Fetched external IP address ({ip}) from centralized source ({CENTRALIZED_IP_ORACLE_URL}).')
    return ip


def determine_external_ip_address(network: str, known_nodes: FleetSensor = None) -> str:
    """
    Attempts to automatically determine the external IP in the following priority:
    1. Randomly Selected Known Nodes
    2. The Default Teacher URI from RestMiddleware
    3. A centralized IP address service

    If the IP address cannot be determined for any reason UnknownIPAddress is raised.
    """
    rest_host = None

    # primary source
    if known_nodes:
        rest_host = get_external_ip_from_known_nodes(known_nodes=known_nodes)

    # fallback 1
    if not rest_host:
        rest_host = get_external_ip_from_default_teacher(network=network)

    # fallback 2
    if not rest_host:
        rest_host = get_external_ip_from_centralized_source()

    # complete failure!
    if not rest_host:
        raise UnknownIPAddress('External IP address detection failed')
    return rest_host
