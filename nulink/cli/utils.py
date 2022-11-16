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
from distutils.util import strtobool
from pathlib import Path
from typing import Dict, Optional, Tuple
from functools import wraps
import copy

import nuclick as click
from constant_sorrow.constants import NO_CONTROL_PROTOCOL
from web3.types import BlockIdentifier

from nulink.blockchain.eth.agents import EthereumContractAgent
from nulink.blockchain.eth.events import EventRecord
from nulink.blockchain.eth.interfaces import (
    BlockchainDeployerInterface,
    BlockchainInterface,
    BlockchainInterfaceFactory
)
from nulink.blockchain.eth.registry import (
    BaseContractRegistry,
    InMemoryContractRegistry,
    LocalContractRegistry
)
from nulink.characters.base import Character
from nulink.control.emitters import StdoutEmitter
from nulink.cli.actions.auth import (
    get_nulink_password,
    unlock_nulink_keystore,
    unlock_signer_account
)
from nulink.cli.literature import (
    CONNECTING_TO_BLOCKCHAIN,
    ETHERSCAN_FLAG_DISABLED_WARNING,
    ETHERSCAN_FLAG_ENABLED_WARNING,
    FEDERATED_WARNING,
    LOCAL_REGISTRY_ADVISORY,
    NO_HARDWARE_WALLET_WARNING,
    PRODUCTION_REGISTRY_ADVISORY,
    CONFIRM_OVERWRITE_EVENTS_CSV_FILE
)
from nulink.config.constants import DEFAULT_CONFIG_ROOT
from nulink.utilities.events import write_events_to_csv_file
import random


def setup_emitter(general_config, banner: str = None) -> StdoutEmitter:
    emitter = general_config.emitter
    if banner:
        emitter.banner(banner)
    return emitter


def make_cli_character(character_config,
                       emitter,
                       unlock_keystore: bool = True,
                       unlock_signer: bool = True,
                       teacher_uri: str = None,
                       min_stake: int = 0,
                       json_ipc: bool = False,
                       **config_args
                       ) -> Character:
    #
    # Pre-Init
    #

    # Handle KEYSTORE
    if unlock_keystore:
        unlock_nulink_keystore(emitter,
                               character_configuration=character_config,
                               password=get_nulink_password(emitter=emitter, confirm=False))

    # Handle Signer/Wallet
    if unlock_signer:
        unlock_signer_account(config=character_config, json_ipc=json_ipc)

    # Handle Teachers
    # TODO: Is this still relevant?  Is it better to DRY this up by doing it later?
    sage_nodes = list()

    #
    # Character Init
    #

    # Produce Character
    if teacher_uri:
        maybe_sage_node = character_config.known_node_class.from_teacher_uri(
            teacher_uri=teacher_uri,
            min_stake=min_stake,
            federated_only=character_config.federated_only,
            network_middleware=character_config.network_middleware,
            registry=character_config.registry
        )
        sage_nodes.append(maybe_sage_node)

    CHARACTER = character_config(known_nodes=sage_nodes,
                                 network_middleware=character_config.network_middleware,
                                 **config_args)

    #
    # Post-Init
    #

    if CHARACTER.controller is not NO_CONTROL_PROTOCOL:
        CHARACTER.controller.emitter = emitter

    # Federated
    if character_config.federated_only:
        emitter.message(FEDERATED_WARNING, color='yellow')

    emitter.message(f"Loaded {CHARACTER.__class__.__name__} ({CHARACTER.domain})", color='green')
    return CHARACTER


def establish_deployer_registry(emitter,
                                network: str = None,
                                registry_infile: Optional[Path] = None,
                                registry_outfile: Optional[Path] = None,
                                use_existing_registry: bool = False,
                                download_registry: bool = False,
                                dev: bool = False
                                ) -> BaseContractRegistry:
    if download_registry:
        registry = InMemoryContractRegistry.from_latest_publication(network=network)
        emitter.message(PRODUCTION_REGISTRY_ADVISORY.format(source=registry.source))
        return registry

    # Establish a contract registry from disk if specified
    filepath = registry_infile
    default_registry_filepath = DEFAULT_CONFIG_ROOT / BaseContractRegistry.REGISTRY_NAME
    if registry_outfile:
        # mutative usage of existing registry
        registry_infile = registry_infile or default_registry_filepath
        if use_existing_registry:
            try:
                _result = shutil.copyfile(registry_infile, registry_outfile)
            except shutil.SameFileError:
                raise click.BadArgumentUsage(f"--registry-infile and --registry-outfile must not be the same path '{registry_infile}'.")
        filepath = registry_outfile

    if dev:
        # TODO: Need a way to detect a geth --dev registry filepath here. (then deprecate the --dev flag)
        filepath = DEFAULT_CONFIG_ROOT / BaseContractRegistry.DEVELOPMENT_REGISTRY_NAME

    registry_filepath = filepath or default_registry_filepath

    # All Done.
    registry = LocalContractRegistry(filepath=registry_filepath)
    emitter.message(LOCAL_REGISTRY_ADVISORY.format(registry_filepath=registry_filepath))
    return registry


def get_registry(network: str, registry_filepath: Optional[Path] = None) -> BaseContractRegistry:
    if registry_filepath:
        registry = LocalContractRegistry(filepath=registry_filepath)
    else:
        registry = InMemoryContractRegistry.from_latest_publication(network=network)
    return registry


def connect_to_blockchain(emitter: StdoutEmitter,
                          eth_provider_uri: str,
                          debug: bool = False,
                          light: bool = False
                          ) -> BlockchainInterface:
    try:
        # Note: Conditional for test compatibility.
        if not BlockchainInterfaceFactory.is_interface_initialized(eth_provider_uri=eth_provider_uri):
            BlockchainInterfaceFactory.initialize_interface(eth_provider_uri=eth_provider_uri,
                                                            light=light,
                                                            emitter=emitter)
        emitter.echo(message=CONNECTING_TO_BLOCKCHAIN)
        blockchain = BlockchainInterfaceFactory.get_interface(eth_provider_uri=eth_provider_uri)
        return blockchain
    except Exception as e:
        if debug:
            raise
        emitter.echo(str(e), bold=True, color='red')
        raise click.Abort


def initialize_deployer_interface(emitter: StdoutEmitter,
                                  poa: bool,
                                  eth_provider_uri,
                                  ignore_solidity_check: bool,
                                  gas_strategy: str = None,
                                  max_gas_price: int = None
                                  ) -> BlockchainDeployerInterface:
    if not BlockchainInterfaceFactory.is_interface_initialized(eth_provider_uri=eth_provider_uri):
        deployer_interface = BlockchainDeployerInterface(eth_provider_uri=eth_provider_uri,
                                                         poa=poa,
                                                         gas_strategy=gas_strategy,
                                                         max_gas_price=max_gas_price)
        BlockchainInterfaceFactory.register_interface(interface=deployer_interface, emitter=emitter)
    else:
        deployer_interface = BlockchainInterfaceFactory.get_interface(eth_provider_uri=eth_provider_uri)
    deployer_interface.connect(ignore_solidity_check=ignore_solidity_check)
    return deployer_interface


def get_env_bool(var_name: str, default: bool) -> bool:
    if var_name in os.environ:
        # TODO: which is better: to fail on an incorrect envvar, or to use the default?
        # Currently doing the former.
        return strtobool(os.environ[var_name])
    else:
        return default


def ensure_config_root(config_root: Path) -> None:
    """Ensure config root exists, because we need a default place to put output files."""
    config_root = config_root or DEFAULT_CONFIG_ROOT
    if not config_root.exists():
        config_root.mkdir(parents=True)


def deployer_pre_launch_warnings(emitter: StdoutEmitter, etherscan: bool, hw_wallet: bool) -> None:
    if not hw_wallet:
        emitter.echo(NO_HARDWARE_WALLET_WARNING, color='yellow')
    if etherscan:
        emitter.echo(ETHERSCAN_FLAG_ENABLED_WARNING, color='yellow')
    else:
        emitter.echo(ETHERSCAN_FLAG_DISABLED_WARNING, color='yellow')


def parse_event_filters_into_argument_filters(event_filters: Tuple[str]) -> Dict:
    """
    Converts tuple of entries of the form <filter_name>=<filter_value> into a dict
    of filter_name (key) -> filter_value (value) entries. Filter values can only be strings, but if the filter
    value can be converted to an int, then it is converted, otherwise it remains a string.
    """
    argument_filters = dict()
    for event_filter in event_filters:
        event_filter_split = event_filter.split('=')
        if len(event_filter_split) != 2:
            raise ValueError(f"Invalid filter format: {event_filter}")
        key = event_filter_split[0]
        value = event_filter_split[1]
        # events are only indexed by string or int values
        if value.isnumeric():
            value = int(value)
        argument_filters[key] = value
    return argument_filters


def retrieve_events(emitter: StdoutEmitter,
                    agent: EthereumContractAgent,
                    event_name: str,
                    from_block: BlockIdentifier,
                    to_block: BlockIdentifier,
                    argument_filters: Dict,
                    csv_output_file: Optional[Path] = None) -> None:
    if csv_output_file:
        if csv_output_file.exists():
            click.confirm(CONFIRM_OVERWRITE_EVENTS_CSV_FILE.format(csv_file=csv_output_file), abort=True)
        available_events = write_events_to_csv_file(csv_file=csv_output_file,
                                                    agent=agent,
                                                    event_name=event_name,
                                                    from_block=from_block,
                                                    to_block=to_block,
                                                    argument_filters=argument_filters)
        if available_events:
            emitter.echo(f"{agent.contract_name}::{event_name} events written to {csv_output_file}",
                         bold=True,
                         color='green')
        else:
            emitter.echo(f'No {agent.contract_name}::{event_name} events found', color='yellow')
    else:
        event = agent.contract.events[event_name]
        emitter.echo(f"{event_name}:", bold=True, color='yellow')
        entries = event.getLogs(fromBlock=from_block, toBlock=to_block, argument_filters=argument_filters)
        for event_record in entries:
            emitter.echo(f"  - {EventRecord(event_record)}")


def ursula_run_origin_params_save(func):
    """Attaches an option to the command.  All positional arguments are
    passed as parameter declarations to :class:`Option`; all keyword
    arguments are forwarded unchanged (except ``cls``).
    This is equivalent to creating an :class:`Option` instance manually
    and attaching it to the :attr:`Command.params` list.

    :param cls: the option class to instantiate.  This defaults to
                :class:`Option`.
    """

    @wraps(func)
    def decorator(*args, **kwargs):
        wrapper_args = list(args)
        wrapper_args[0].extend(['--origin-args', args])

        return func(*wrapper_args, **kwargs)

    return decorator


def random_dic(dicts):
    dict_key_ls = list(dicts.keys())
    random.shuffle(dict_key_ls)
    new_dic = {}
    for key in dict_key_ls:
        new_dic[key] = dicts.get(key)
    return new_dic

