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


import base64
import datetime

import maya
import pytest

from nucypher_core import (
    MessageKit,
    EncryptedTreasureMap as EncryptedTreasureMapClass,
    TreasureMap as TreasureMapClass,
    )
from nucypher_core.umbral import PublicKey

from nulink.characters.control.specifications import fields
from nulink.characters.control.specifications.alice import GrantPolicy
from nulink.characters.control.specifications.fields.treasuremap import EncryptedTreasureMap, TreasureMap
from nulink.control.specifications.base import BaseSchema
from nulink.control.specifications.exceptions import SpecificationError, InvalidInputData, InvalidArgumentCombo
from nulink.crypto.powers import DecryptingPower


def make_header(brand: bytes, major: int, minor: int) -> bytes:
    # Hardcoding this since it's too much trouble to expose it all the way from Rust
    assert len(brand) == 4
    major_bytes = major.to_bytes(2, 'big')
    minor_bytes = minor.to_bytes(2, 'big')
    header = brand + major_bytes + minor_bytes
    return header


def test_various_field_validations_by_way_of_alice_grant(federated_bob):
    """ test some semi-complex validation situations """

    with pytest.raises(InvalidInputData):
        GrantPolicy().load(dict())

    bob_encrypting_key = federated_bob.public_keys(DecryptingPower)

    data = {
        'bob_encrypting_key': bytes(bob_encrypting_key).hex(),
        'bob_verifying_key': bytes(federated_bob.stamp).hex(),
        'threshold': 5,
        'shares': 6,
        'expiration': (maya.now() + datetime.timedelta(days=3)).iso8601(),
        'label': 'cats the animal',
        'rate': 1000,
        'value': 3000,
    }

    # validate data with both rate and value fails validation
    with pytest.raises(InvalidArgumentCombo):
        GrantPolicy().load(data)

    # remove value and now it works
    del data['value']
    result = GrantPolicy().load(data)
    assert result['label'] == b'cats the animal'

    # validate that negative "m" value fails
    data['threshold'] = -5
    with pytest.raises(SpecificationError):
        GrantPolicy().load(data)

    # validate that m > n fails validation
    data['threshold'] = data['shares'] + 19
    with pytest.raises(SpecificationError):
        GrantPolicy().load(data)


def test_treasure_map_validation(enacted_federated_policy,
                                 federated_bob):
    """Tell people exactly what's wrong with their treasuremaps"""
    #
    # encrypted treasure map
    #
    class EncryptedTreasureMapsOnly(BaseSchema):
        tmap = EncryptedTreasureMap()

    # this will raise a base64 error
    with pytest.raises(SpecificationError) as e:
        EncryptedTreasureMapsOnly().load({'tmap': "your face looks like a treasure map"})

    # assert that field name is in the error message
    assert "Could not parse tmap" in str(e)
    assert "Invalid base64-encoded string" in str(e)

    # valid base64 but invalid treasuremap
    bad_map = make_header(b'EMap', 1, 0) + b"your face looks like a treasure map"
    bad_map_b64 = base64.b64encode(bad_map).decode()

    with pytest.raises(InvalidInputData) as e:
        EncryptedTreasureMapsOnly().load({'tmap': bad_map_b64})

    assert "Could not convert input for tmap to an EncryptedTreasureMap" in str(e)
    assert "Failed to deserialize" in str(e)

    # a valid treasuremap for once...
    tmap_bytes = bytes(enacted_federated_policy.treasure_map)
    tmap_b64 = base64.b64encode(tmap_bytes)
    result = EncryptedTreasureMapsOnly().load({'tmap': tmap_b64.decode()})
    assert isinstance(result['tmap'], EncryptedTreasureMapClass)

    #
    # unencrypted treasure map
    #
    class UnenncryptedTreasureMapsOnly(BaseSchema):
        tmap = TreasureMap()

    # this will raise a base64 error
    with pytest.raises(SpecificationError) as e:
        UnenncryptedTreasureMapsOnly().load({'tmap': "your face looks like a treasure map"})

    # assert that field name is in the error message
    assert "Could not parse tmap" in str(e)
    assert "Invalid base64-encoded string" in str(e)

    # valid base64 but invalid treasuremap
    bad_map = make_header(b'TMap', 1, 0) + b"your face looks like a treasure map"
    bad_map_b64 = base64.b64encode(bad_map).decode()

    with pytest.raises(InvalidInputData) as e:
        UnenncryptedTreasureMapsOnly().load({'tmap': bad_map_b64})

    assert "Could not convert input for tmap to a TreasureMap" in str(e)
    assert "Failed to deserialize" in str(e)

    # a valid treasuremap
    decrypted_treasure_map = federated_bob._decrypt_treasure_map(enacted_federated_policy.treasure_map,
                                                                 enacted_federated_policy.publisher_verifying_key)
    tmap_bytes = bytes(decrypted_treasure_map)
    tmap_b64 = base64.b64encode(tmap_bytes).decode()
    result = UnenncryptedTreasureMapsOnly().load({'tmap': tmap_b64})
    assert isinstance(result['tmap'], TreasureMapClass)


def test_messagekit_validation(capsule_side_channel):
    """Ensure that our users know exactly what's wrong with their message kit input"""

    class MessageKitsOnly(BaseSchema):

        mkit = fields.MessageKit()

    # this will raise a base64 error
    with pytest.raises(SpecificationError) as e:
        MessageKitsOnly().load({'mkit': "I got a message for you"})

    # assert that field name is in the error message
    assert "Could not parse mkit" in str(e)
    assert "Incorrect padding" in str(e)

    # valid base64 but invalid messagekit
    bad_kit = make_header(b'MKit', 1, 0) + b"I got a message for you"
    bad_kit_b64 = base64.b64encode(bad_kit).decode()

    with pytest.raises(SpecificationError) as e:
        MessageKitsOnly().load({'mkit': bad_kit_b64})

    assert "Could not parse mkit" in str(e)
    assert "Failed to deserialize" in str(e)

    # test a valid messagekit
    valid_kit = capsule_side_channel.messages[0][0]
    kit_bytes = bytes(valid_kit)
    kit_b64 = base64.b64encode(kit_bytes)
    result = MessageKitsOnly().load({'mkit': kit_b64.decode()})
    assert isinstance(result['mkit'], MessageKit)


def test_key_validation(federated_bob):

    class BobKeyInputRequirer(BaseSchema):
        bobkey = fields.Key()

    with pytest.raises(InvalidInputData) as e:
        BobKeyInputRequirer().load({'bobkey': "I am the key to nothing"})
    assert "non-hexadecimal number found in fromhex()" in str(e)
    assert "bobkey" in str(e)

    with pytest.raises(InvalidInputData) as e:
        BobKeyInputRequirer().load({'bobkey': "I am the key to nothing"})
    assert "non-hexadecimal number found in fromhex()" in str(e)
    assert "bobkey" in str(e)

    with pytest.raises(InvalidInputData) as e:
        # lets just take a couple bytes off
        BobKeyInputRequirer().load({'bobkey': "02f0cb3f3a33f16255d9b2586e6c56570aa07bbeb1157e169f1fb114ffb40037"})
    assert "Could not convert input for bobkey to an Umbral Key" in str(e)
    assert "xpected 33 bytes, got 32" in str(e)

    result = BobKeyInputRequirer().load(dict(bobkey=bytes(federated_bob.public_keys(DecryptingPower)).hex()))
    assert isinstance(result['bobkey'], PublicKey)
