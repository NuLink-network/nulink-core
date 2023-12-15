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

import nuclick as click

from nulink.blockchain.eth.networks import NetworksInventory
from nulink.characters.lawful import Ursula
from nulink.cli.config import group_general_config
from nulink.cli.literature import (
    PORTER_BASIC_AUTH_ENABLED,
    PORTER_BASIC_AUTH_REQUIRES_HTTPS,
    PORTER_BOTH_TLS_KEY_AND_CERTIFICATION_MUST_BE_PROVIDED,
    PORTER_CORS_ALLOWED_ORIGINS,
    PORTER_RUN_MESSAGE,
)
from nulink.cli.options import (
    option_network,
    option_eth_provider_uri,
    option_federated_only,
    option_teacher_uri,
    option_registry_filepath,
    option_min_stake
)
from nulink.cli.types import NETWORK_PORT
from nulink.cli.utils import setup_emitter, get_registry
from nulink.config.constants import TEMPORARY_DOMAIN
from nulink.utilities.porter.porter import Porter


@click.group()
def porter():
    """
    Porter management commands. Porter is a web-service that is the conduit between applications and the
    nucypher network, that performs actions on behalf of Alice and Bob.
    """


@porter.command()
@group_general_config
@option_network(default=NetworksInventory.DEFAULT, validate=True, required=False)
@option_eth_provider_uri(required=False)
@option_federated_only
@option_teacher_uri
@option_registry_filepath
@option_min_stake
@click.option('--http-port', help="Porter HTTP/HTTPS port for JSON endpoint", type=NETWORK_PORT, default=Porter.DEFAULT_PORT)
@click.option('--tls-certificate-filepath', help="Pre-signed TLS certificate filepath", type=click.Path(dir_okay=False, exists=True, path_type=Path))
@click.option('--tls-key-filepath', help="TLS private key filepath", type=click.Path(dir_okay=False, exists=True, path_type=Path))
@click.option('--basic-auth-filepath', help="htpasswd filepath for basic authentication", type=click.Path(dir_okay=False, exists=True, resolve_path=True, path_type=Path))
@click.option('--allow-origins', help="The CORS origin(s) comma-delimited list of strings/regexes for origins to allow - no origins allowed by default", type=click.STRING)
@click.option('--dry-run', '-x', help="Execute normally without actually starting Porter", is_flag=True)
@click.option('--eager', help="Start learning and scraping the network before starting up other services", is_flag=True, default=True)
def run(general_config,
        network,
        eth_provider_uri,
        federated_only,
        teacher_uri,
        registry_filepath,
        min_stake,
        http_port,
        tls_certificate_filepath,
        tls_key_filepath,
        basic_auth_filepath,
        allow_origins,
        dry_run,
        eager):
    """Start Porter's Web controller."""
    emitter = setup_emitter(general_config, banner=Porter.BANNER)

    # HTTP/HTTPS
    if bool(tls_key_filepath) ^ bool(tls_certificate_filepath):
        raise click.BadOptionUsage(option_name='--tls-key-filepath, --tls-certificate-filepath',
                                   message=click.style(PORTER_BOTH_TLS_KEY_AND_CERTIFICATION_MUST_BE_PROVIDED, fg="red"))

    is_https = (tls_key_filepath and tls_certificate_filepath)

    # check authentication
    if basic_auth_filepath and not is_https:
        raise click.BadOptionUsage(option_name='--basic-auth-filepath',
                                   message=click.style(PORTER_BASIC_AUTH_REQUIRES_HTTPS, fg="red"))

    if federated_only:
        if not teacher_uri:
            raise click.BadOptionUsage(option_name='--teacher',
                                       message=click.style("--teacher is required for federated porter.", fg="red"))

        teacher = Ursula.from_teacher_uri(teacher_uri=teacher_uri,
                                          federated_only=True,
                                          min_stake=min_stake)  # min stake is irrelevant for federated
        PORTER = Porter(domain=TEMPORARY_DOMAIN,
                        start_learning_now=eager,
                        known_nodes={teacher},
                        verify_node_bonding=False,
                        federated_only=True)
    else:
        # decentralized/blockchain
        if not eth_provider_uri:
            raise click.BadOptionUsage(option_name='--eth-provider',
                                       message=click.style("--eth-provider is required for decentralized porter.", fg="red"))
        if not network:
            # should never happen - network defaults to 'mainnet' if not specified
            raise click.BadOptionUsage(option_name='--network',
                                       message=click.style("--network is required for decentralized porter.", "red"))

        registry = get_registry(network=network, registry_filepath=registry_filepath)
        teacher = None
        if teacher_uri:
            teacher = Ursula.from_teacher_uri(teacher_uri=teacher_uri,
                                              federated_only=False,  # always False
                                              min_stake=min_stake,
                                              registry=registry)

        PORTER = Porter(domain=network,
                        known_nodes={teacher} if teacher else None,
                        registry=registry,
                        start_learning_now=eager,
                        eth_provider_uri=eth_provider_uri)

    # RPC
    if general_config.json_ipc:
        rpc_controller = PORTER.make_rpc_controller()
        _transport = rpc_controller.make_control_transport()
        rpc_controller.start()
        return

    emitter.message(f"Network: {PORTER.domain.capitalize()}", color='green')
    if not federated_only:
        emitter.message(f"ETH Provider URI: {eth_provider_uri}", color='green')

    # firm up falsy status (i.e. change specified empty string to None)
    allow_origins = allow_origins if allow_origins else None
    # covert to list of strings/regexes
    allow_origins_list = None
    if allow_origins:
        allow_origins_list = allow_origins.split(",")  # split into list of origins to allow
        emitter.message(PORTER_CORS_ALLOWED_ORIGINS.format(allow_origins=allow_origins_list), color='green')

    if basic_auth_filepath:
        emitter.message(PORTER_BASIC_AUTH_ENABLED, color='green')

    controller = PORTER.make_web_controller(crash_on_error=False,
                                            htpasswd_filepath=basic_auth_filepath,
                                            cors_allow_origins_list=allow_origins_list)
    http_scheme = "https" if is_https else "http"
    message = PORTER_RUN_MESSAGE.format(http_scheme=http_scheme, http_port=http_port)
    emitter.message(message, color='green', bold=True)
    return controller.start(port=http_port,
                            tls_key_filepath=tls_key_filepath,
                            tls_certificate_filepath=tls_certificate_filepath,
                            dry_run=dry_run)


# add by andi for debug
if __name__ == '__main__':
    # # If the local connection is not connected to the extranet's chain, you need to set the proxy PyCHARM in your code to set the function
    # # https://blog.csdn.net/whatday/article/details/112169945
    # import os
    #
    # os.environ["http_proxy"] = "http://127.0.0.1:7890"
    # os.environ["https_proxy"] = "http://127.0.0.1:7890"

    run([
        '--http-port', '9155',
        # '--teacher', '54.241.67.36:9151',
        # '--teacher', '192.168.3.20:9151',
        '--teacher', '8.222.155.168:9161',  # '127.0.0.1:9151',  # '192.168.3.25:9151',  # '127.0.0.1:9151',
        '--network', 'horus',
        '--eth-provider', 'https://data-seed-prebsc-1-s1.bnbchain.org:8545',
        '--allow-origins', "*",
        '--debug',
        '--console-logs',
        # '--file-logs',
    ])

    """
        demo:
        
        nulink porter run --http-port 80 --teacher 127.0.0.1:9151 --network mumbai --eth-provider https://polygon-mumbai.g.alchemy.com/v2/JylWDpuNyfSUjWH2exn4VTTmoSTcBo8Z

    """
