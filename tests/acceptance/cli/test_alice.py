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

from unittest import mock
from unittest.mock import PropertyMock

from nulink.cli.commands.alice import AliceConfigOptions
from nulink.cli.literature import COLLECT_NULINK_PASSWORD, SUCCESSFUL_DESTRUCTION
from nulink.cli.main import nulink_cli
from nulink.config.base import CharacterConfiguration
from nulink.config.characters import AliceConfiguration
from nulink.config.constants import NULINK_ENVVAR_KEYSTORE_PASSWORD, TEMPORARY_DOMAIN
from nulink.config.storages import LocalFileBasedNodeStorage
from nulink.crypto.keystore import Keystore
from nulink.policy.identity import Card
from tests.constants import (
    FAKE_PASSWORD_CONFIRMED,
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_CUSTOM_INSTALLATION_PATH
)


@mock.patch('nulink.config.characters.AliceConfiguration.default_filepath', return_value='/non/existent/file')
def test_missing_configuration_file(default_filepath_mock, click_runner, test_registry_source_manager):
    cmd_args = ('alice', 'run', '--network', TEMPORARY_DOMAIN)
    env = {NULINK_ENVVAR_KEYSTORE_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD}
    result = click_runner.invoke(nulink_cli, cmd_args, catch_exceptions=False, env=env)
    assert result.exit_code != 0
    assert default_filepath_mock.called
    assert "nulink alice init" in result.output


def test_initialize_alice_defaults(click_runner, mocker, custom_filepath, monkeypatch, blockchain_ursulas, tmpdir):
    monkeypatch.delenv(NULINK_ENVVAR_KEYSTORE_PASSWORD, raising=False)

    # Mock out filesystem writes
    mocker.patch.object(AliceConfiguration, 'initialize', autospec=True)
    mocker.patch.object(AliceConfiguration, 'to_configuration_file', autospec=True)
    mocker.patch.object(LocalFileBasedNodeStorage, 'all', return_value=blockchain_ursulas)

    # Mock Keystore init
    keystore = Keystore.generate(keystore_dir=tmpdir, password=INSECURE_DEVELOPMENT_PASSWORD)
    mocker.patch.object(CharacterConfiguration, 'keystore', return_value=keystore, new_callable=PropertyMock)

    # Use default alice init args
    init_args = ('alice', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--config-root', str(custom_filepath.absolute()),
                 '--federated-only')
    result = click_runner.invoke(nulink_cli, init_args, input=FAKE_PASSWORD_CONFIRMED, catch_exceptions=False)
    assert result.exit_code == 0

    # REST Host
    assert "nulink alice run" in result.output

    # Auth
    assert COLLECT_NULINK_PASSWORD in result.output, 'WARNING: User was not prompted for password'
    assert 'Repeat for confirmation:' in result.output, 'User was not prompted to confirm password'


def test_alice_control_starts_with_mocked_keystore(click_runner, mocker, monkeypatch, custom_filepath):
    monkeypatch.delenv(NULINK_ENVVAR_KEYSTORE_PASSWORD, raising=False)

    class MockKeystore:
        is_unlocked = False
        keystore_dir = custom_filepath / 'keystore'
        keystore_path = custom_filepath / 'keystore' / 'path.json'

        def derive_crypto_power(self, power_class, *args, **kwargs):
            return power_class()

        @classmethod
        def unlock(cls, password, *args, **kwargs):
            assert password == INSECURE_DEVELOPMENT_PASSWORD
            cls.is_unlocked = True

    good_enough_config = AliceConfiguration(dev_mode=True, federated_only=True, keystore=MockKeystore())
    mocker.patch.object(AliceConfigOptions, "create_config", return_value=good_enough_config)
    init_args = ('alice', 'run', '-x', '--lonely', '--network', TEMPORARY_DOMAIN)
    result = click_runner.invoke(nulink_cli, init_args, input=FAKE_PASSWORD_CONFIRMED)
    assert result.exit_code == 0, result.output


def test_initialize_alice_with_custom_configuration_root(custom_filepath, click_runner, monkeypatch):
    monkeypatch.delenv(NULINK_ENVVAR_KEYSTORE_PASSWORD, raising=False)

    # Use a custom local filepath for configuration
    init_args = ('alice', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--federated-only',
                 '--config-root', str(custom_filepath.absolute()))

    result = click_runner.invoke(nulink_cli, init_args, input=FAKE_PASSWORD_CONFIRMED, catch_exceptions=False)
    assert result.exit_code == 0

    # CLI Output
    assert str(MOCK_CUSTOM_INSTALLATION_PATH) in result.output, "Configuration not in system temporary directory"
    assert "nulink alice run" in result.output, 'Help message is missing suggested command'
    assert 'IPv4' not in result.output

    # Files and Directories
    assert custom_filepath.is_dir(), 'Configuration file does not exist'
    assert (custom_filepath / 'keystore').is_dir(), 'Keystore does not exist'

    # TODO: Only using in-memory node storage for now
    # assert (custom_filepath / 'known_nodes').is_dir(), 'known_nodes directory does not exist'
    assert not (custom_filepath / 'known_nodes').is_dir(), 'known_nodes directory does not exist'

    custom_config_filepath = custom_filepath / AliceConfiguration.generate_filename()
    assert custom_config_filepath.is_file(), 'Configuration file does not exist'

    # Auth
    assert COLLECT_NULINK_PASSWORD in result.output, 'WARNING: User was not prompted for password'
    assert 'Repeat for confirmation:' in result.output, 'User was not prompted to confirm password'


def test_alice_control_starts_with_preexisting_configuration(click_runner, custom_filepath):
    custom_config_filepath = custom_filepath / AliceConfiguration.generate_filename()
    run_args = ('alice', 'run', '--dry-run', '--lonely', '--config-file', str(custom_config_filepath.absolute()))
    result = click_runner.invoke(nulink_cli, run_args, input=FAKE_PASSWORD_CONFIRMED)
    assert result.exit_code == 0, result.exception


def test_alice_make_card(click_runner, custom_filepath, mocker):
    mock_save_card = mocker.patch.object(Card, 'save')
    custom_config_filepath = custom_filepath / AliceConfiguration.generate_filename()
    command = ('alice', 'make-card', '--nickname', 'flora', '--config-file', str(custom_config_filepath.absolute()))
    result = click_runner.invoke(nulink_cli, command, input=FAKE_PASSWORD_CONFIRMED, catch_exceptions=False)
    assert result.exit_code == 0
    mock_save_card.assert_called_once()
    assert "Saved new character card " in result.output


def test_alice_cannot_init_with_dev_flag(click_runner):
    init_args = ('alice', 'init', '--network', TEMPORARY_DOMAIN, '--federated-only', '--dev')
    result = click_runner.invoke(nulink_cli, init_args, catch_exceptions=False)
    assert result.exit_code == 2
    assert 'Cannot create a persistent development character' in result.output, \
           'Missing or invalid error message was produced.'


def test_alice_derive_policy_pubkey(click_runner):
    label = 'random_label'
    derive_key_args = ('alice', 'derive-policy-pubkey', '--label', label, '--dev')
    result = click_runner.invoke(nulink_cli, derive_key_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert "policy_encrypting_key" in result.output
    assert "label" in result.output
    assert label in result.output


def test_alice_public_keys(click_runner):
    derive_key_args = ('alice', 'public-keys', '--dev')
    result = click_runner.invoke(nulink_cli, derive_key_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert "alice_verifying_key" in result.output


def test_alice_view_preexisting_configuration(click_runner, custom_filepath):
    custom_config_filepath = custom_filepath / AliceConfiguration.generate_filename()
    view_args = ('alice', 'config', '--config-file', str(custom_config_filepath.absolute()))
    result = click_runner.invoke(nulink_cli, view_args, input=FAKE_PASSWORD_CONFIRMED)
    assert result.exit_code == 0
    assert "checksum_address" in result.output
    assert "domain" in result.output
    assert TEMPORARY_DOMAIN in result.output
    assert str(custom_filepath) in result.output


def test_alice_destroy(click_runner, custom_filepath):
    """Should be the last test since it deletes the configuration file"""
    custom_config_filepath = custom_filepath / AliceConfiguration.generate_filename()
    destroy_args = ('alice', 'destroy', '--config-file', str(custom_config_filepath.absolute()), '--force')
    result = click_runner.invoke(nulink_cli, destroy_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert SUCCESSFUL_DESTRUCTION in result.output
    assert not custom_config_filepath.exists(), "Alice config file was deleted"
