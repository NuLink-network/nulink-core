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
import uuid
import weakref
from http import HTTPStatus
from pathlib import Path
from typing import Tuple

from constant_sorrow import constants
from constant_sorrow.constants import RELAX
from eth.constants import ZERO_ADDRESS
from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address
from flask import Flask, Response, jsonify, request
from mako import exceptions as mako_exceptions
from mako.template import Template
from nucypher_core import (
    ReencryptionRequest,
    RevocationOrder,
    MetadataRequest,
    MetadataResponse,
    MetadataResponsePayload,
)
from nulink.blockchain.eth.constants import NULL_ADDRESS

from nulink.network.middleware import NulinkMiddlewareClient, RestMiddleware

from nulink import __version__
from nulink.config.constants import MAX_UPLOAD_CONTENT_LENGTH
from nulink.control.emitters import StdoutEmitter
from nulink.crypto.keypairs import DecryptingKeypair
from nulink.crypto.signing import InvalidSignature
from nulink.datastore.datastore import Datastore
from nulink.datastore.models import ReencryptionRequest as ReencryptionRequestModel
from nulink.network.exceptions import NodeSeemsToBeDown
from nulink.network.nodes import NodeSprout
from nulink.network.protocols import InterfaceInfo
from nulink.utilities.logging import Logger
from nulink.utilities.version import check_version_pickle_symbol, VersionMismatchError, check_version

HERE = BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = HERE / "templates"

status_template = Template(filename=str(TEMPLATES_DIR / "basic_status.mako")).get_def('main')


class ProxyRESTServer:
    log = Logger("network-server")

    def __init__(self,
                 rest_host: str,
                 rest_port: int,
                 hosting_power=None,
                 rest_app=None,
                 datastore=None,
                 ) -> None:

        self.rest_interface = InterfaceInfo(host=rest_host, port=rest_port)
        if rest_app:  # if is me
            self.rest_app = rest_app
            self.datastore = datastore
        else:
            self.rest_app = constants.PUBLIC_ONLY

        self.__hosting_power = hosting_power

    def rest_url(self):
        return "{}:{}".format(self.rest_interface.host, self.rest_interface.port)


def make_rest_app(
        db_filepath: Path,
        this_node,
        log: Logger = Logger("http-application-layer"),
        lmdb_map_size=None,
) -> Tuple[Flask, Datastore]:
    """
    Creates a REST application and an associated ``Datastore`` object.
    Note that the REST app **does not** hold a reference to the datastore;
    it is your responsibility to ensure it lives for as long as the app does.
    """

    # A trampoline function for the real REST app,
    # to ensure that a reference to the node and the datastore object is not held by the app closure.
    # One would think that it's enough to only remove a reference to the node,
    # but `rest_app` somehow holds a reference to itself, Uroboros-like,
    # and will hold the datastore reference if it is created there.

    log.info("Starting datastore {}".format(db_filepath))
    datastore = Datastore(db_filepath, map_size=lmdb_map_size)
    rest_app = _make_rest_app(weakref.proxy(datastore), weakref.proxy(this_node), log)

    return rest_app, datastore


def _make_rest_app(datastore: Datastore, this_node, log: Logger) -> Flask:
    # TODO: Avoid circular imports :-(
    from nulink.characters.lawful import Alice, Bob, Ursula

    _alice_class = Alice
    _bob_class = Bob
    _node_class = Ursula

    rest_app = Flask("ursula-service")
    rest_app.config[
        'MAX_CONTENT_LENGTH'] = MAX_UPLOAD_CONTENT_LENGTH  # handle http response: HTTP 413 Content Too Large

    @rest_app.route("/public_information")
    def public_information():
        """REST endpoint for public keys and address."""
        # add version info
        from nulink import __version__
        split_symbol = bytes(check_version_pickle_symbol, 'utf-8')

        response = Response(response=bytes(this_node.metadata()) + split_symbol + bytes(__version__, 'utf-8'),
                            mimetype='application/octet-stream')
        return response

    @rest_app.route('/node_metadata', methods=["GET"])
    def all_known_nodes():
        headers = {'Content-Type': 'application/octet-stream'}
        if this_node._learning_deferred is not RELAX and not this_node._learning_task.running:
            # Learn when learned about
            this_node.start_learning_loop()

        # notice: Since the peer requests this interface is the note_Metadata interface of the teacher node, the node must be a teacher
        # All known nodes + this node
        response_bytes = this_node.bytestring_of_known_nodes()

        split_symbol = bytes(check_version_pickle_symbol, 'utf-8')

        return Response(response_bytes + split_symbol + bytes(__version__, 'utf-8'), headers=headers)

    @rest_app.route('/node_metadata', methods=["POST"])
    def node_metadata_exchange():

        log.info(f"known_nodes {len(this_node.known_nodes)}")

        def bytestring_of_empty_known_nodes():
            headers = {'Content-Type': 'application/octet-stream'}
            response_payload = MetadataResponsePayload(timestamp_epoch=this_node.known_nodes.timestamp.epoch,
                                                       announce_nodes=[])
            response = MetadataResponse(this_node.stamp.as_umbral_signer(), response_payload)

            split_symbol = bytes(check_version_pickle_symbol, 'utf-8')
            return Response(bytes(response) + split_symbol + bytes(__version__, 'utf-8'), headers=headers)

        try:
            metadata_request = MetadataRequest.from_bytes(request.data)
        except Exception as e:
            # The code runs here, indicating that an older version of the node sent a node_metadata Post request, so return an empty node list, Indicates that we do not support the old version
            log.info(f"Post/node_metadata MetadataRequest.from_bytes failed: {str(e)}")

            split_symbol = bytes(check_version_pickle_symbol, 'utf-8')
            # bytes(request) + split_symbol + bytes(__version__, 'utf-8')

            bytes_list = request.data.split(split_symbol)
            len_bytes_list = len(bytes_list)
            if len_bytes_list == 1:
                # Note The version of the requesting end is relatively early, return an empty node list, Indicates that we do not support the old version
                return bytestring_of_empty_known_nodes()
            else:
                # current len_bytes_list must be 2
                assert len_bytes_list == 2
                node_metadata_bytes, version_bytes = bytes_list
                version_str = version_bytes.decode('utf-8')

                if not check_version(version_str):
                    # Note The version of the requesting end is different from the current node version, return an empty node list, Indicates that we do not support the old version
                    return bytestring_of_empty_known_nodes()

            metadata_request = MetadataRequest.from_bytes(node_metadata_bytes)

        # If these nodes already have the same fleet state, no exchange is necessary.

        learner_fleet_state = request.args.get('fleet')
        if metadata_request.fleet_state_checksum == this_node.known_nodes.checksum:
            # log.debug("Learner already knew fleet state {}; doing nothing.".format(learner_fleet_state))  # 1712
            return bytestring_of_empty_known_nodes()

        # announce_nodes is the Teacher Node
        if metadata_request.announce_nodes:
            for metadata in metadata_request.announce_nodes:
                try:
                    # # from nucypher_core import NodeMetadata
                    # return self.signature.verify(message=bytes(self._metadata_payload), verifying_pk=self.verifying_key)
                    metadata.verify()
                except Exception:
                    # inconsistent metadata
                    pass
                else:
                    this_node.remember_node(NodeSprout(metadata))

        # TODO: generate a new fleet state here?

        # TODO: What's the right status code here?  202?  Different if we already knew about the node(s)?
        return all_known_nodes()

    @rest_app.route('/reencrypt', methods=["POST"])
    def reencrypt():

        from nulink.characters.lawful import Bob

        # TODO: Cache & Optimize

        # reenc_request = ReencryptionRequest.from_bytes(request.data)

        from nulink.policy.crosschain import CrossChainReencryptionRequest
        try:
            cross_chain_reenc_request = CrossChainReencryptionRequest.from_bytes(request.data)
        except Exception as e:
            print(f"------------ request.data ----------------- ex: {e}")

        reenc_request = cross_chain_reenc_request.reencryption_request

        # hrac = reenc_request.hrac  # => treasure_map.hrac => HRAC
        cross_chain_hrac = cross_chain_reenc_request.hrac  # CrossChainHRAC
        hrac = cross_chain_hrac.hrac
        bob = Bob.from_public_keys(verifying_key=reenc_request.bob_verifying_key)
        log.info(f"Reencryption request from {bob} for policy {cross_chain_hrac}")

        # Right off the bat, if this HRAC is already known to be revoked, reject the order.
        if cross_chain_hrac in this_node.revoked_policies:
            return Response(response=f"Policy with {cross_chain_hrac} has been revoked.",
                            status=HTTPStatus.UNAUTHORIZED)

        publisher_verifying_key = reenc_request.publisher_verifying_key

        # Bob
        bob_ip_address = request.remote_addr
        bob_verifying_key = bob.stamp.as_umbral_pubkey()
        bob_identity_message = f"[{bob_ip_address}] Bob({bytes(bob.stamp).hex()})"

        # Verify & Decrypt KFrag Payload
        try:
            verified_kfrag = this_node._decrypt_kfrag(reenc_request.encrypted_kfrag, hrac, publisher_verifying_key)
        except DecryptingKeypair.DecryptionFailed:
            # TODO: don't we want to record suspicious activities here too?
            return Response(response="EncryptedKeyFrag decryption failed.", status=HTTPStatus.FORBIDDEN)
        except InvalidSignature as e:
            message = f'{bob_identity_message} Invalid signature for KeyFrag: {e}.'
            log.info(message)
            # TODO (#567): bucket the node as suspicious
            return Response(message, status=HTTPStatus.UNAUTHORIZED)  # 401 - Unauthorized
        except Exception as e:
            message = f'{bob_identity_message} Invalid EncryptedKeyFrag: {e}.'
            log.info(message)
            # TODO (#567): bucket the node as suspicious
            return Response(message, status=HTTPStatus.BAD_REQUEST)

        # Enforce Policy Payment
        # TODO: Accept multiple payment methods
        # TODO: Evaluate multiple reencryption prerequisites & enforce policy expiration
        # this_node.payment_method: SubscriptionManagerPayment
        paid = this_node.payment_method.verify(payee=this_node.checksum_address, request=cross_chain_reenc_request)
        if not paid:
            message = f"{bob_identity_message} Policy {bytes(cross_chain_hrac)} is unpaid."
            return Response(message, status=HTTPStatus.PAYMENT_REQUIRED)

        # Re-encrypt
        # TODO: return a sensible response if it fails (currently results in 500)
        response = this_node._reencrypt(kfrag=verified_kfrag, capsules=reenc_request.capsules)

        try:
            # Now, Ursula saves evidence of this workorder to her database...
            # Note: we give the work order a random ID to store it under.
            with datastore.describe(ReencryptionRequestModel, str(uuid.uuid4()), writeable=True) as new_request:
                new_request.bob_verifying_key = bob_verifying_key
        except BaseException as e:
            # process exception:
            #   with self.__db_env.begin(write=writeable) as datastore_tx => raise:
            #       lmdb.InvalidParameterError: mdb_txn_begin: Invalid argument
            # call params:
            #    => with datastore.describe(ReencryptionRequestModel, str(uuid.uuid4()), writeable=True) as new_request:
            import traceback
            print(traceback.format_exc())

        headers = {'Content-Type': 'application/octet-stream'}
        return Response(headers=headers, response=bytes(response))

    @rest_app.route('/revoke', methods=['POST'])
    def revoke():
        revocation = RevocationOrder.from_bytes(request.data)
        # TODO: Implement off-chain revocation.
        return Response(status=HTTPStatus.OK)

    @rest_app.route("/ping", methods=['GET'])
    def ping():
        """Asks this node: What is my IP address?"""
        requester_ip_address = request.remote_addr

        return Response(json.dumps({'requester_ip': requester_ip_address, 'version': __version__}),
                        content_type="application/json", status=HTTPStatus.OK)

    @rest_app.route("/check_availability", methods=['POST'])
    def check_availability():
        """Asks this node: Can you access my public information endpoint?"""

        split_symbol = bytes(check_version_pickle_symbol, 'utf-8')
        # bytes(request) + split_symbol + bytes(__version__, 'utf-8')

        bytes_list = request.data.split(split_symbol)
        len_bytes_list = len(bytes_list)
        if len_bytes_list == 1:
            # Note The version of the requesting end is relatively early, return an empty node list, Indicates that we do not support the old version
            return Response(json.dumps({'version': __version__,
                                        'error': f'Invalid Ursula: Version mismatch, please upgrade your node version to {__version__}'}),
                            content_type="application/json",
                            status=HTTPStatus.BAD_REQUEST)
        else:
            # current len_bytes_list must be 2
            assert len_bytes_list == 2
            ursula_metadata_bytes, version_bytes = bytes_list  # ursula_metadata_bytes is sender's metadata
            version_str = version_bytes.decode('utf-8')

            if not check_version(version_str):
                # Note The version of the requesting end is different from the current node version, return an empty node list, Indicates that we do not support the old version
                return Response(json.dumps({'version': __version__,
                                            'error': f'Invalid Ursula: Version {version_str} mismatch, please upgrade your node version to {__version__}'}),
                                content_type="application/json", status=HTTPStatus.BAD_REQUEST)

        try:
            requesting_ursula = Ursula.from_metadata_bytes(ursula_metadata_bytes)  # request.data)
            requesting_ursula.mature()
        except ValueError:
            return Response(json.dumps({'version': __version__, 'error': 'Invalid Ursula'}),
                            content_type="application/json", status=HTTPStatus.BAD_REQUEST)
        else:
            initiator_address, initiator_port = tuple(requesting_ursula.rest_interface)

        # Compare requester and posted Ursula information
        request_address = request.remote_addr
        if request_address != initiator_address:
            message = f'Origin address mismatch: Request origin is {request_address} but metadata claims {initiator_address}.'
            return Response(json.dumps({'version': __version__, 'error': message}), content_type="application/json",
                            status=HTTPStatus.BAD_REQUEST)

        # Make a Sandwich
        try:
            requesting_ursula_metadata = this_node.network_middleware.client.node_information(
                host=initiator_address,
                port=initiator_port,
            )
        except NodeSeemsToBeDown:
            return Response(json.dumps({'version': __version__, 'error': 'Unreachable node'}),
                            content_type="application/json", status=HTTPStatus.BAD_REQUEST)  # ... toasted

        # Compare the results of the outer POST with the inner GET... yum
        if requesting_ursula_metadata == ursula_metadata_bytes:  # request.data:
            return Response(json.dumps({'version': __version__}), content_type="application/json", status=HTTPStatus.OK)
        else:
            return Response(json.dumps({'version': __version__, 'error': 'Suspicious node'}),
                            content_type="application/json", status=HTTPStatus.BAD_REQUEST)

    @rest_app.route('/status/', methods=['GET'])
    def status():
        return_json = request.args.get('json') == 'true'
        omit_known_nodes = request.args.get('omit_known_nodes') == 'true'
        status_info = this_node.status_info(omit_known_nodes=omit_known_nodes)
        if return_json:
            return jsonify(status_info.to_json())
        headers = {"Content-Type": "text/html", "charset": "utf-8"}
        try:
            content = status_template.render(status_info)
        except Exception as e:
            text_error = mako_exceptions.text_error_template().render()
            html_error = mako_exceptions.html_error_template().render()
            log.debug("Template Rendering Exception:\n" + text_error)
            return Response(response=html_error, headers=headers, status=HTTPStatus.INTERNAL_SERVER_ERROR)
        return Response(response=content, headers=headers)

    @rest_app.route("/checkip", methods=['GET'])
    def checkip():
        """
        Add a checking mechanism: when the backend server ping the node, the node need to return a signature which is signed by the worker account, the message is the node uri.
        Then when server check the signature, it can check if this worker is running with specific URI.
        https://github.com/NuLink-network/nulink-core/issues/3

        The problem with this scheme is that if the user uses a domain name,
        we can't get it, and the front end can't use the domain name to verify the signature


        The original idea is to register with a domain name in the Ursula init, and then do not get an external IP address,
        take the user Ursula init IP or domain name as a signature, when the front end gets the signature,
        and use the same IP or domain name as the Ursula init to verify it. However, when I verified this scheme,
        I found that Ursula init cannot be registered with a domain name, only an IP. So it doesn't work.

        the current plan:

        """
        # "Asks this node: What is my IP address?"
        # requester_ip_address = request.remote_addr

        emitter = StdoutEmitter()

        from nulink.cli.actions.configure import get_external_ip

        # ip = get_external_ip(emitter, this_node)
        # emitter.message(f"external ip: {ip},  rest_interface.host: {this_node.rest_interface.host}")
        emitter.message(f"rest_interface.host: {this_node.rest_interface.host}")

        signed_message = this_node.signer.sign_message(this_node.wallet_address,
                                                       this_node.rest_interface.host.encode()).hex()
        emitter.message(f"signed_message: {signed_message}")
        return Response(json.dumps({'version': __version__, "worker_signed": signed_message}),
                        content_type="application/json", status=HTTPStatus.OK)

    @rest_app.route("/check-running", methods=['GET'])
    def check_current_ursula_started():
        """Porter or others Ursula check the status of the current ursula node (this_node ursula_object)"""
        # requester_ip_address = request.remote_addr

        emitter = StdoutEmitter()

        staker_address = request.args.get('staker_address')

        if not staker_address or staker_address == NULL_ADDRESS:
            return Response(json.dumps({'version': __version__, 'error': 'Parameter staker_address not be null'}),
                            content_type="application/json", status=HTTPStatus.BAD_REQUEST)

        staker_address = to_checksum_address(staker_address)
        ursula: Ursula = this_node
        # ursula.network_middleware: RestMiddleware
        # ursula.network_middleware.client: NulinkMiddlewareClient

        if not hasattr(ursula, "checksum_address") or ursula.checksum_address == NULL_ADDRESS:
            return Response(json.dumps(
                {'version': __version__,
                 'error': f'current node is not valid (checksum_address is {NULL_ADDRESS}). Please Make sure the worker is staked and bonded and the ursula node is started, then wait for node discovery'}),
                content_type="application/json", status=HTTPStatus.BAD_REQUEST)

        client: NulinkMiddlewareClient = ursula.network_middleware.client

        is_authorized: bool = ursula.application_agent.is_authorized(staker_address)
        if not is_authorized:
            return Response(
                json.dumps({'version': __version__,
                            'error': f'The amount staked of NLK must be greater than the minimum amount staked: {ursula.application_agent.get_min_authorization()}'}),
                content_type="application/json", status=HTTPStatus.PRECONDITION_REQUIRED)

        operator_address: ChecksumAddress = ursula.application_agent.get_operator_from_staking_provider(staker_address)
        if not operator_address or operator_address == f"0x{ZERO_ADDRESS.hex()}":
            return Response(json.dumps({'version': __version__, 'error': 'Please bond worker first'}),  # 'Please stake NLK and bond worker first'}),
                            content_type="application/json", status=HTTPStatus.PRECONDITION_REQUIRED)

        operator_confirmed: bool = ursula.application_agent.is_operator_confirmed(operator_address)
        if not operator_confirmed:
            return Response(json.dumps({'version': __version__,
                                        'error': 'Please bond worker and started the worker(ursula) node first and Keep an adequate balance in your account'}),
                            content_type="application/json",
                            status=HTTPStatus.PRECONDITION_REQUIRED)

        # Notes: ursula.known_nodes's keys are the staker_addresses, not the operator_addresses
        all_known_nodes = ursula.known_nodes.values()
        if not all_known_nodes or len(all_known_nodes) < 1:
            return Response(json.dumps({'version': __version__,
                                        'error': 'Please bond worker and start the worker(ursula) node first and wait for node discovery'}),
                            content_type="application/json",
                            status=HTTPStatus.PRECONDITION_REQUIRED)

        # Call the check_availability of the teacher node to check whether it is externally accessible =>
        # (Asks teacher node: Can you access my(this_node: current ursula node) public information endpoint?)
        last_error = ""
        teacher_unreachable = False

        node_to_remove = list(ursula.known_nodes._nodes_to_remove)

        filter_nodes = {node.checksum_address: node for node in ursula.known_nodes if
                        (node.checksum_address != NULL_ADDRESS and node.checksum_address not in node_to_remove)}

        date_len = len(filter_nodes)

        if date_len < 1:
            return Response(json.dumps({'version': __version__,
                                        'error': 'Make sure the worker is staked and bonded and the ursula node is started, then wait for node discovery'}),
                            content_type="application/json",
                            status=HTTPStatus.PRECONDITION_REQUIRED)

        for node in filter_nodes.values():
            split_symbol = bytes(check_version_pickle_symbol, 'utf-8')
            try:
                teacher_unreachable = False
                response = client.post(node_or_sprout=node,
                                       # andi comment
                                       # Note: When ursula's checksum_address is NULL_ADDRESS, self.metadata() throws a segment error exception that cannot be caught
                                       #  so let's get to the root of the problem. Ursula whose checksum_address is NULL_ADDRESS is not allowed
                                       data=bytes(ursula.metadata()) + split_symbol + bytes(__version__, 'utf-8'),
                                       path="check_availability",
                                       timeout=15,  # Two round trips are expected
                                       )

                if not str(response.status_code).startswith('2'):
                    try:
                        last_error = response.content.decode()
                    except:
                        last_error = response.content

                    continue

                return Response(json.dumps({'version': __version__, 'data': 'success'}),
                                content_type="application/json", status=HTTPStatus.OK)

            except BaseException as e:
                last_error = f"teacher(worker) node {node.rest_interface.host}:{node.rest_interface.port} unreachable details reason: {str(e)}"
                teacher_unreachable = True
                emitter.message(f"check_current_ursula_started exception: {last_error}")
                continue

        error_info = f'The ursula node cannot be accessed externally. Enable port {ursula.rest_interface.port} and set a static public ip address' if not teacher_unreachable else 'teacher(work) node is inaccessible, configure the accessible node as the worker\'s learning(teacher) node or resolve the problem that the teacher(work) node is inaccessible'
        return Response(json.dumps({'version': __version__, 'error': error_info, 'details': last_error}),
                        content_type="application/json", status=HTTPStatus.GATEWAY_TIMEOUT)

    return rest_app
