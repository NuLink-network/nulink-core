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

from nulink.blockchain.eth.signers.base import Signer
from nulink.blockchain.eth.signers.software import ClefSigner, KeystoreSigner
from nulink.blockchain.eth.signers.hardware import TrezorSigner


Signer._SIGNERS = {
    ClefSigner.uri_scheme(): ClefSigner,
    KeystoreSigner.uri_scheme(): KeystoreSigner,
    TrezorSigner.uri_scheme(): TrezorSigner
}
