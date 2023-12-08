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
from http import HTTPStatus
from pathlib import Path
from typing import List, NamedTuple, Optional, Sequence, Dict, Set, Any, Tuple

from constant_sorrow.constants import NO_BLOCKCHAIN_CONNECTION, NO_CONTROL_PROTOCOL
from eth.constants import ZERO_ADDRESS
from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address
from flask import request, Response
from nucypher_core import TreasureMap, RetrievalKit
from nucypher_core.umbral import PublicKey
from nulink import __version__
from nulink.blockchain.eth.agents import ContractAgency, PREApplicationAgent
from nulink.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nulink.blockchain.eth.registry import BaseContractRegistry, InMemoryContractRegistry
from nulink.characters.lawful import Ursula
from nulink.cli.utils import random_dic
from nulink.control.controllers import JSONRPCController, WebController
from nulink.crypto.powers import DecryptingPower
from nulink.network.nodes import Learner
from nulink.network.retrieval import RetrievalClient
from nulink.policy.crosschain import CrossChainHRAC
from nulink.policy.kits import RetrievalResult
from nulink.policy.reservoir import (
    make_federated_staker_reservoir,
    make_decentralized_staking_provider_reservoir,
    PrefetchStrategy
)
from nulink.utilities.concurrency import WorkerPool
from nulink.utilities.logging import Logger
from nulink.utilities.porter.control.controllers import PorterCLIController
from nulink.utilities.porter.control.interfaces import PorterInterface
from nulink.utilities.version import VersionMismatchError

nulink_workers: Dict = \
    {
        # "0xc95C2BA4234b2a3E1aa91d167Ee1CB5f951A5945": {
        #     "checksum_address": "0xc95C2BA4234b2a3E1aa91d167Ee1CB5f951A5945",
        #     "uri": "https://8.222.155.168:9161",
        #     "encrypting_key": "032aa6db627b3a4b527d4bbe74b8b82801fa287dddc30665b6d8d45292c60640ee"
        # },
        # "0x4F09EA918210dC8422299BD0E94eEfE78C30eC18": {
        #     "checksum_address": "0x4F09EA918210dC8422299BD0E94eEfE78C30eC18",
        #     "uri": "https://8.222.131.226:9161",
        #     "encrypting_key": "0317ea59b97b7114a4954229a6798ac1565c64f19ac66364fbba205c8ba008e948"
        # },
        # "0x37e134573AE74C212Aa47941C95b58265D437998": {
        #     "checksum_address": "0x37e134573AE74C212Aa47941C95b58265D437998",
        #     "uri": "https://8.222.146.98:9161",
        #     "encrypting_key": "031addb934b01b8a373a8db2947156e664fe8ee2f6d723231cf972fa7cf6bb2059"
        # }
    }


class Porter(Learner):
    BANNER = r"""

 ______
(_____ \           _
 _____) )__   ____| |_  ____  ____
|  ____/ _ \ / ___)  _)/ _  )/ ___)
| |   | |_| | |   | |_( (/ /| |
|_|    \___/|_|    \___)____)_|

the Pipe for PRE Application network operations
"""

    APP_NAME = "Porter"

    _SHORT_LEARNING_DELAY = 2
    _LONG_LEARNING_DELAY = 30
    _ROUNDS_WITHOUT_NODES_AFTER_WHICH_TO_SLOW_DOWN = 25

    DEFAULT_EXECUTION_TIMEOUT = 15

    DEFAULT_PORT = 9155

    _interface_class = PorterInterface

    class UrsulaInfo(NamedTuple):
        """Simple object that stores relevant Ursula information resulting from sampling."""
        checksum_address: ChecksumAddress
        uri: str
        encrypting_key: PublicKey

    def __init__(self,
                 domain: str = None,
                 registry: BaseContractRegistry = None,
                 controller: bool = True,
                 federated_only: bool = False,
                 node_class: object = Ursula,
                 eth_provider_uri: str = None,
                 execution_timeout: int = DEFAULT_EXECUTION_TIMEOUT,
                 *args, **kwargs):
        self.federated_only = federated_only

        if not self.federated_only:
            if not eth_provider_uri:
                raise ValueError('ETH Provider URI is required for decentralized Porter.')

            if not BlockchainInterfaceFactory.is_interface_initialized(eth_provider_uri=eth_provider_uri):
                BlockchainInterfaceFactory.initialize_interface(eth_provider_uri=eth_provider_uri)

            self.registry = registry or InMemoryContractRegistry.from_latest_publication(network=domain)
            self.application_agent = ContractAgency.get_agent(PREApplicationAgent, registry=self.registry)
        else:
            self.registry = NO_BLOCKCHAIN_CONNECTION.bool_value(False)
            node_class.set_federated_mode(federated_only)

        super().__init__(save_metadata=True, domain=domain, node_class=node_class, *args, **kwargs)

        self.log = Logger(self.__class__.__name__)
        self.execution_timeout = execution_timeout

        # Controller Interface
        self.interface = self._interface_class(porter=self)
        self.controller = NO_CONTROL_PROTOCOL
        if controller:
            # TODO need to understand this better - only made it analogous to what was done for characters
            self.make_cli_controller()
        self.log.info(self.BANNER)

    @classmethod
    def get_nulink_workers(cls) -> Dict[ChecksumAddress, 'Porter.UrsulaInfo']:

        # Porter.UrsulaInfo(checksum_address=ursula_address,
        #                   uri=f"{ursula.rest_interface.formal_uri}",
        #                   encrypting_key=ursula.public_keys(DecryptingPower))

        porter_ursula_worker_dict: Dict[ChecksumAddress, Porter.UrsulaInfo] = {to_checksum_address(ursula_address): Porter.UrsulaInfo(checksum_address=to_checksum_address(ursula_address),
                                                                                                                                      uri=ursula_info["uri"],
                                                                                                                                      encrypting_key=PublicKey.from_bytes(
                                                                                                                                          bytes.fromhex(ursula_info["encrypting_key"])))
                                                                               for ursula_address, ursula_info in nulink_workers.items()}

        porter_ursula_worker_dict = random_dic(porter_ursula_worker_dict)

        return porter_ursula_worker_dict

    @classmethod
    def get_nulink_worker_addresses(cls) -> Set[ChecksumAddress]:

        return set([to_checksum_address(ursula_address) for ursula_address in nulink_workers.keys()])

    def get_enough_ursulas(self, worker_pool: WorkerPool) -> Dict[ChecksumAddress, 'Porter.UrsulaInfo']:

        success_workers: Dict[ChecksumAddress, Porter.UrsulaInfo] = worker_pool.get_successes()
        # need_to_add_worker_len = worker_pool.get_target_successes() - len(success_workers)

        enough_success_workers: Dict[ChecksumAddress, 'Porter.UrsulaInfo'] = success_workers

        _nulink_workers: Dict[ChecksumAddress, 'Porter.UrsulaInfo'] = Porter.get_nulink_workers()

        enough_success_workers.update(_nulink_workers)

        len_enough_success_workers = len(enough_success_workers)

        while len_enough_success_workers > worker_pool.get_target_successes():
            enough_success_workers.popitem()
            len_enough_success_workers -= 1

        return enough_success_workers

    def get_enough_ursulas_from_nulink_worker(self, quantity: int) -> Dict[ChecksumAddress, 'Porter.UrsulaInfo']:

        _nulink_workers: Dict[ChecksumAddress, 'Porter.UrsulaInfo'] = Porter.get_nulink_workers()

        len_enough_success_workers = len(_nulink_workers)

        if quantity > len_enough_success_workers:
            return {}

        while len_enough_success_workers > quantity:
            _nulink_workers.popitem()
            len_enough_success_workers -= 1

        return _nulink_workers

    def get_ursulas(self,
                    quantity: int,
                    exclude_ursulas: Optional[Sequence[ChecksumAddress]] = None,
                    include_ursulas: Optional[Sequence[ChecksumAddress]] = None) -> List[UrsulaInfo]:

        # workers = self.get_enough_ursulas_from_nulink_worker(quantity)
        # ursulas_info = workers.values()
        # return list(ursulas_info)

        reservoir = self._make_reservoir(quantity, exclude_ursulas, include_ursulas)
        value_factory = PrefetchStrategy(reservoir, quantity)

        def get_ursula_info(ursula_address) -> Porter.UrsulaInfo:
            if to_checksum_address(ursula_address) not in self.known_nodes:
                raise ValueError(f"{ursula_address} is not known")

            ursula_address = to_checksum_address(ursula_address)
            ursula = self.known_nodes[ursula_address]
            try:
                # ensure node is up and reachable
                self.network_middleware.ping(ursula)
                return Porter.UrsulaInfo(checksum_address=ursula_address,
                                         uri=f"{ursula.rest_interface.formal_uri}",
                                         encrypting_key=ursula.public_keys(DecryptingPower))
            except Exception as e:
                self.log.debug(f"Ursula ({ursula_address}) is unreachable: {str(e)}")
                raise

        self.block_until_number_of_known_nodes_is(quantity,
                                                  timeout=self.execution_timeout,
                                                  learn_on_this_thread=True,
                                                  eager=True)

        worker_pool = WorkerPool(worker=get_ursula_info,
                                 value_factory=value_factory,
                                 target_successes=quantity,
                                 timeout=self.execution_timeout,
                                 stagger_timeout=1)
        worker_pool.start()
        try:
            successes = worker_pool.block_until_target_successes()
        except (WorkerPool.TimedOut, WorkerPool.OutOfValues) as ex:
            workers = self.get_enough_ursulas(worker_pool)
            if len(workers) >= worker_pool.get_target_successes():
                successes = workers
            else:
                raise ex
        finally:
            worker_pool.cancel()
            # don't wait for it to stop by "joining" - too slow...

        ursulas_info = successes.values()

        return list(ursulas_info)

    def get_ursulas_total(self, return_list=False):

        if return_list:
            return len(self.known_nodes), [{'checksum_address': node.checksum_address, 'uri': node.rest_interface.formal_uri} for node in self.known_nodes]
        else:
            return len(self.known_nodes)

    def get_include_ursulas(self, include_ursulas=None):

        if include_ursulas is None:
            include_ursulas = []

        date_len = len(self.known_nodes)
        ret_list = []
        for ursula_address in include_ursulas:
            _ursula_address = to_checksum_address(ursula_address)
            if _ursula_address not in self.known_nodes:
                ret_list.append("")
            else:
                node = self.known_nodes[_ursula_address]
                ret_list.append(node.rest_interface.formal_uri)

        return date_len, ret_list

    def get_ursula_paging_data(self, start_index: int = 0, end_index: int = 0):

        if start_index > end_index:
            start_index, end_index = end_index, start_index

        date_len = len(self.known_nodes)
        if start_index > date_len - 1:
            return date_len, []
        # sorted(list(self.known_nodes.addresses()))
        node_list = [node for node in self.known_nodes]
        if end_index < 0 or end_index > date_len - 1:
            return date_len, [{'checksum_address': node.checksum_address, 'uri': node.rest_interface.formal_uri} for node in node_list[start_index:]]
        else:
            return date_len, [{'checksum_address': node.checksum_address, 'uri': node.rest_interface.formal_uri} for node in node_list[start_index: end_index]]

    def get_current_version(self):
        from nulink import __version__
        return str(__version__)

    def check_ursula_status(self, staker_address: ChecksumAddress) -> dict:

        if not staker_address or staker_address == f"0x{ZERO_ADDRESS.hex()}":
            return {  # 'version': __version__,
                "error": "staker_address must be passed and cannot be empty"}
            # status=HTTPStatus.BAD_REQUEST)

        date_len = len(self.known_nodes)
        if date_len <= 0:
            return {  # 'version': __version__,
                "error": "Porter has not learned the node. Please ask the administrator to check the porter network and startup status"}
            # status=HTTPStatus.INTERNAL_SERVER_ERROR)

        _ursula_staker_address = to_checksum_address(staker_address)

        if _ursula_staker_address not in self.known_nodes:
            return {  # 'version': __version__,
                "error": "porter has not found the current staker, please troubleshoot the problem in the following order:\n\t1. Check whether the staker address is correct\n\t2. Check whether the worker service corresponding to the operator address is started\n\t3. If the worker service has been started, wait until the worker node is discovered by the network"}
            # status=HTTPStatus.BAD_REQUEST)

        # Notes: ursula.known_nodes's keys are the staker_addresses, not the operator_addresses
        ursula = self.known_nodes[_ursula_staker_address]

        try:
            return self.network_middleware.check_ursula_status(ursula, _ursula_staker_address)
        except Exception as e:
            # if isinstance(e, VersionMismatchError):
            return {  # 'version': __version__,
                "error": str(e)}
            # status=HTTPStatus.BAD_REQUEST)

    def retrieve_cfrags(self,
                        treasure_map: TreasureMap,
                        retrieval_kits: Sequence[RetrievalKit],
                        alice_verifying_key: PublicKey,
                        bob_encrypting_key: PublicKey,
                        bob_verifying_key: PublicKey,
                        cross_chain_hrac: CrossChainHRAC,
                        ) -> List[RetrievalResult]:
        client = RetrievalClient(self)
        return client.retrieve_cfrags(treasure_map, retrieval_kits,
                                      alice_verifying_key, bob_encrypting_key, bob_verifying_key, cross_chain_hrac)

    def _make_reservoir(self,
                        quantity: int,
                        exclude_ursulas: Optional[Sequence[ChecksumAddress]] = None,
                        include_ursulas: Optional[Sequence[ChecksumAddress]] = None):
        if self.federated_only:
            sample_size = quantity - (len(include_ursulas) if include_ursulas else 0)
            if not self.block_until_number_of_known_nodes_is(sample_size,
                                                             timeout=self.execution_timeout,
                                                             learn_on_this_thread=True):
                raise ValueError("Unable to learn about sufficient Ursulas")
            return make_federated_staker_reservoir(known_nodes=self.known_nodes,
                                                   exclude_addresses=exclude_ursulas,
                                                   include_addresses=include_ursulas)
        else:
            return make_decentralized_staking_provider_reservoir(application_agent=self.application_agent,
                                                                 exclude_addresses=exclude_ursulas,
                                                                 include_addresses=include_ursulas)

    def make_cli_controller(self, crash_on_error: bool = False):
        controller = PorterCLIController(app_name=self.APP_NAME,
                                         crash_on_error=crash_on_error,
                                         interface=self.interface)
        self.controller = controller
        return controller

    def make_rpc_controller(self, crash_on_error: bool = False):
        controller = JSONRPCController(app_name=self.APP_NAME,
                                       crash_on_error=crash_on_error,
                                       interface=self.interface)

        self.controller = controller
        return controller

    def make_web_controller(self,
                            crash_on_error: bool = False,
                            htpasswd_filepath: Path = None,
                            cors_allow_origins_list: List[str] = None):
        controller = WebController(app_name=self.APP_NAME,
                                   crash_on_error=crash_on_error,
                                   interface=self._interface_class(porter=self))
        self.controller = controller

        # Register Flask Decorator
        porter_flask_control = controller.make_control_transport()

        # CORS origins
        if cors_allow_origins_list:
            try:
                from flask_cors import CORS
            except ImportError:
                raise ImportError('Porter installation is required for to specify CORS origins '
                                  '- run "pip install nulink[porter]" and try again.')
            _ = CORS(app=porter_flask_control, origins=cors_allow_origins_list)

        # Basic Auth
        if htpasswd_filepath:
            try:
                from flask_htpasswd import HtPasswdAuth
            except ImportError:
                raise ImportError('Porter installation is required for basic authentication '
                                  '- run "pip install nulink[porter]" and try again.')

            porter_flask_control.config['FLASK_HTPASSWD_PATH'] = str(htpasswd_filepath.absolute())
            # ensure basic auth required for all endpoints
            porter_flask_control.config['FLASK_AUTH_ALL'] = True
            _ = HtPasswdAuth(app=porter_flask_control)

        #
        # Porter Control HTTP Endpoints
        #
        @porter_flask_control.route('/get_ursulas', methods=['GET'])
        def get_ursulas() -> Response:
            """Porter control endpoint for sampling Ursulas on behalf of Alice."""
            response = controller(method_name='get_ursulas', control_request=request)
            return response

        @porter_flask_control.route('/ursulas/total', methods=['GET'])
        def get_ursulas_total() -> Response:
            """Porter control endpoint for get Ursulas total count."""
            response = controller(method_name='get_ursulas_total', control_request=request)
            return response

        @porter_flask_control.route('/ursulas/info', methods=['POST'])
        def get_ursula_paging_data() -> Response:
            """Porter control endpoint for get Ursulas total count."""
            response = controller(method_name='get_ursula_paging_data', control_request=request)
            return response

        @porter_flask_control.route('/include/ursulas', methods=['POST'])
        def get_include_ursulas() -> Response:
            """Porter control endpoint for get Ursulas total count."""
            response = controller(method_name='get_include_ursulas', control_request=request)
            return response

        @porter_flask_control.route("/revoke", methods=['POST'])
        def revoke():
            """Porter control endpoint for off-chain revocation of a policy on behalf of Alice."""
            response = controller(method_name='revoke', control_request=request)
            return response

        @porter_flask_control.route("/retrieve_cfrags", methods=['POST'])
        def retrieve_cfrags() -> Response:
            """Porter control endpoint for executing a PRE work order on behalf of Bob."""
            response = controller(method_name='retrieve_cfrags', control_request=request)
            return response

        @porter_flask_control.route('/version', methods=['GET'])
        def get_current_version() -> Response:
            """Porter control endpoint for get Current Version."""
            # response = controller(method_name='get_current_version', control_request=request)
            # return response
            from nulink import __version__
            return Response(json.dumps({'version': __version__}), content_type="application/json", status=HTTPStatus.OK)

        @porter_flask_control.route('/check/ursula', methods=['GET'])
        def check_ursula_status() -> Response:
            """Porter control endpoint for checking the status of the specified ursula node (."""

            response = controller(method_name='check_ursula_status', control_request=request)
            return response

        return controller
