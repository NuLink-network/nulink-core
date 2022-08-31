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


import glob
import json
from json.decoder import JSONDecodeError
from pathlib import Path
from typing import Optional, Type, List

import click

from nulink.characters.lawful import Ursula
from nulink.cli.actions.confirm import confirm_destroy_configuration
from nulink.cli.literature import (
    CONFIRM_FORGET_NODES,
    INVALID_CONFIGURATION_FILE_WARNING,
    INVALID_JSON_IN_CONFIGURATION_WARNING,
    MISSING_CONFIGURATION_FILE,
    SUCCESSFUL_DESTRUCTION,
    SUCCESSFUL_FORGET_NODES,
    SUCCESSFUL_UPDATE_CONFIGURATION_VALUES,
    COLLECT_URSULA_IPV4_ADDRESS,
    CONFIRM_URSULA_IPV4_ADDRESS
)
from nulink.cli.types import OPERATOR_IP
from nulink.config.base import CharacterConfiguration
from nulink.config.constants import DEFAULT_CONFIG_ROOT
from nulink.control.emitters import StdoutEmitter
from nulink.utilities.networking import InvalidOperatorIP, validate_operator_ip
from nulink.utilities.networking import determine_external_ip_address, UnknownIPAddress


def forget(emitter: StdoutEmitter, configuration: CharacterConfiguration) -> None:
    """Forget all known nodes via storage"""
    click.confirm(CONFIRM_FORGET_NODES, abort=True)
    configuration.forget_nodes()
    emitter.message(SUCCESSFUL_FORGET_NODES, color='red')


def get_config_filepaths(config_class: Type[CharacterConfiguration], config_root: Optional[Path] = None) -> List:
    #
    # Scrape disk for configuration files
    #
    config_root = config_root or DEFAULT_CONFIG_ROOT
    default_config_file = glob.glob(str(config_class.default_filepath(config_root=config_root)))

    # updated glob pattern for secondary configuration files accommodates for:
    # 1. configuration files with "0x..." checksum address as suffix - including older ursula config files
    # 2. newer (ursula) configuration files which use signing_pub_key[:8] as hex as the suffix
    glob_pattern = f'{config_root.absolute()}/{config_class.NAME}-[0-9a-fA-F]*.{config_class._CONFIG_FILE_EXTENSION}'

    secondary_config_files = sorted(glob.glob(glob_pattern))  # sort list to make order deterministic
    config_files = [*default_config_file, *secondary_config_files]
    config_files = [Path(f) for f in config_files]
    return config_files


def get_or_update_configuration(emitter: StdoutEmitter,
                                filepath: Path,
                                config_class: Type[CharacterConfiguration],
                                updates: Optional[dict] = None) -> None:
    """
    Utility for writing updates to an existing configuration file then displaying the result.
    If the config file is invalid, try very hard to display the problem.  If there are no updates,
    the config file will be displayed without changes.
    """
    try:
        config = config_class.from_configuration_file(filepath=filepath)
    except FileNotFoundError:
        return handle_missing_configuration_file(character_config_class=config_class, config_file=filepath)
    except config_class.ConfigurationError:
        return handle_invalid_configuration_file(emitter=emitter, config_class=config_class, filepath=filepath)

    emitter.echo(f"{config_class.NAME.capitalize()} Configuration {filepath} \n {'='*55}")
    if updates:
        pretty_fields = ', '.join(updates)
        emitter.message(SUCCESSFUL_UPDATE_CONFIGURATION_VALUES.format(fields=pretty_fields), color='yellow')
        config.update(**updates)
    emitter.echo(config.serialize())


def destroy_configuration(emitter: StdoutEmitter,
                          character_config: CharacterConfiguration,
                          force: bool = False) -> None:
    """Destroy a character configuration and report rhe result with an emitter."""
    if not force:
        confirm_destroy_configuration(config=character_config)
    character_config.destroy()
    emitter.message(SUCCESSFUL_DESTRUCTION, color='green')
    character_config.log.debug(SUCCESSFUL_DESTRUCTION)


def handle_missing_configuration_file(character_config_class: Type[CharacterConfiguration],
                                      init_command_hint: str = None,
                                      config_file: Optional[Path] = None) -> None:
    """Display a message explaining there is no configuration file to use and abort the current operation."""
    config_file_location = config_file or character_config_class.default_filepath()
    init_command = init_command_hint or f"{character_config_class.NAME} init"
    name = character_config_class.NAME.capitalize()
    message = MISSING_CONFIGURATION_FILE.format(name=name, init_command=init_command)
    raise click.FileError(filename=str(config_file_location.absolute()), hint=message)


def handle_invalid_configuration_file(emitter: StdoutEmitter,
                                      config_class: Type[CharacterConfiguration],
                                      filepath: Path) -> None:
    """
    Attempt to deserialize a config file that is not a valid nulink character configuration
    as a means of user-friendly debugging. :-)  I hope this helps!
    """
    # Issue warning for invalid configuration...
    emitter.message(INVALID_CONFIGURATION_FILE_WARNING.format(filepath=filepath))
    try:
        # ... but try to display it anyways
        response = config_class._read_configuration_file(filepath=filepath)
        emitter.echo(json.dumps(response, indent=4))
        raise config_class.ConfigurationError
    except (TypeError, JSONDecodeError):
        emitter.message(INVALID_JSON_IN_CONFIGURATION_WARNING.format(filepath=filepath))
        # ... sorry.. we tried as hard as we could
        raise  # crash :-(


def collect_operator_ip_address(emitter: StdoutEmitter, network: str, force: bool = False) -> str:

    # From node swarm
    try:
        message = f'Detecting external IP address automatically'
        emitter.message(message, verbosity=2)
        ip = determine_external_ip_address(network=network)
    except UnknownIPAddress:
        if force:
            raise
        emitter.message('Cannot automatically determine external IP address - input required')
        ip = click.prompt(COLLECT_URSULA_IPV4_ADDRESS, type=OPERATOR_IP)

    # Confirmation
    if not force:
        if not click.confirm(CONFIRM_URSULA_IPV4_ADDRESS.format(rest_host=ip)):
            ip = click.prompt(COLLECT_URSULA_IPV4_ADDRESS, type=OPERATOR_IP)

    validate_operator_ip(ip=ip)
    return ip


def perform_startup_ip_check(emitter: StdoutEmitter, ursula: Ursula, force: bool = False) -> None:
    """
    Used on ursula startup to determine if the external
    IP address is consistent with the configuration's values.
    """
    try:
        external_ip = determine_external_ip_address(network=ursula.domain, known_nodes=ursula.known_nodes)
    except UnknownIPAddress:
        message = 'Cannot automatically determine external IP address'
        emitter.message(message)
        return  # TODO: crash, or not to crash... that is the question
    rest_host = ursula.rest_interface.host
    try:
        validate_operator_ip(ip=rest_host)
    except InvalidOperatorIP:
        message = f'{rest_host} is not a valid or permitted operator IP address.  Set the correct external IP then try again\n' \
                  f'automatic configuration -> nulink ursula config ip-address\n' \
                  f'manual configuration    -> nulink ursula config --rest-host <IP ADDRESS>'
        emitter.message(message)
        return

    ip_mismatch = external_ip != rest_host
    if ip_mismatch and not force:
        error = f'\nx External IP address ({external_ip}) does not match configuration ({ursula.rest_interface.host}).\n'
        hint = f"Run 'nulink ursula config ip-address' to reconfigure the IP address then try " \
               f"again or use --no-ip-checkup to bypass this check (not recommended).\n"
        emitter.message(error, color='red')
        emitter.message(hint, color='yellow')
        raise click.Abort()
    else:
        emitter.message('✓ External IP matches configuration', 'green')
