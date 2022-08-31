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

from nucypher_core.umbral import SecretKey

from nulink.cli.main import nulink_cli


def test_enrico_encrypt(click_runner):
    policy_encrypting_key = bytes(SecretKey.random().public_key()).hex()
    encrypt_args = ('enrico', 'encrypt',
                    '--message', 'to be or not to be',
                    '--policy-encrypting-key', policy_encrypting_key)
    result = click_runner.invoke(nulink_cli, encrypt_args, catch_exceptions=False)

    assert result.exit_code == 0
    assert policy_encrypting_key in result.output
    assert "message_kit" in result.output


def test_enrico_control_starts(click_runner):
    policy_encrypting_key = bytes(SecretKey.random().public_key()).hex()
    run_args = ('enrico', 'run',
                '--policy-encrypting-key', policy_encrypting_key,
                '--dry-run')

    result = click_runner.invoke(nulink_cli, run_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert policy_encrypting_key in result.output
