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

import pytest
from decimal import Decimal, InvalidOperation

from nulink.blockchain.eth.token import NLK


def test_NLK(application_economics):

    # Starting Small
    min_allowed_locked = NLK(application_economics.min_authorization, 'NLKWei')
    assert application_economics.min_authorization == int(min_allowed_locked.to_units())

    min_NLK_locked = int(str(application_economics.min_authorization)[0:-18])
    expected = NLK(min_NLK_locked, 'NLK')
    assert min_allowed_locked == expected

    # Starting Big
    # min_allowed_locked = NLK(min_NLK_locked, 'NLK')
    # assert token_economics.min_authorization == int(min_allowed_locked)
    # assert token_economics.min_authorization == int(min_allowed_locked.to_units())
    # assert str(min_allowed_locked) == '40000 NLK'

    # Alternate construction
    assert NLK(1, 'NLK') == NLK('1.0', 'NLK') == NLK(1.0, 'NLK')

    # Arithmetic

    # NUs
    one_nu = NLK(1, 'NLK')
    zero_nu = NLK(0, 'NLK')
    one_hundred_nu = NLK(100, 'NLK')
    two_hundred_nu = NLK(200, 'NLK')
    three_hundred_nu = NLK(300, 'NLK')

    # Nits
    one_nu_wei = NLK(1, 'NLKWei')
    three_nu_wei = NLK(3, 'NLKWei')
    assert three_nu_wei.to_tokens() == Decimal('3E-18')
    assert one_nu_wei.to_tokens() == Decimal('1E-18')

    # Base Operations
    assert one_hundred_nu < two_hundred_nu < three_hundred_nu
    assert one_hundred_nu <= two_hundred_nu <= three_hundred_nu

    assert three_hundred_nu > two_hundred_nu > one_hundred_nu
    assert three_hundred_nu >= two_hundred_nu >= one_hundred_nu

    assert (one_hundred_nu + two_hundred_nu) == three_hundred_nu
    assert (three_hundred_nu - two_hundred_nu) == one_hundred_nu

    difference = one_nu - one_nu_wei
    assert not difference == zero_nu

    actual = float(difference.to_tokens())
    expected = 0.999999999999999999
    assert actual == expected

    # 3.14 NLK is 3_140_000_000_000_000_000 NLKWei
    pi_nuweis = NLK(3.14, 'NLK')
    assert NLK('3.14', 'NLK') == pi_nuweis.to_units() == NLK(3_140_000_000_000_000_000, 'NLKWei')

    # Mixed type operations
    difference = NLK('3.14159265', 'NLK') - NLK(1.1, 'NLK')
    assert difference == NLK('2.04159265', 'NLK')

    result = difference + one_nu_wei
    assert result == NLK(2041592650000000001, 'NLKWei')

    # Similar to stake read + metadata operations in Staker
    collection = [one_hundred_nu, two_hundred_nu, three_hundred_nu]
    assert sum(collection) == NLK('600', 'NLK') == NLK(600, 'NLK') == NLK(600.0, 'NLK') == NLK(600e+18, 'NLKWei')

    #
    # Fractional Inputs
    #

    # A decimal amount of NLK (i.e., a fraction of a NLK)
    pi_nuweis = NLK('3.14', 'NLKWei')
    assert pi_nuweis == three_nu_wei  # Floor

    # A decimal amount of NLK, which amounts to NLK with decimals
    pi_nus = NLK('3.14159265358979323846', 'NLK')
    assert pi_nus == NLK(3141592653589793238, 'NLKWei')  # Floor

    # Positive Infinity
    with pytest.raises(NLK.InvalidAmount):
        _inf = NLK(float('infinity'), 'NLK')

    # Negative Infinity
    with pytest.raises(NLK.InvalidAmount):
        _neg_inf = NLK(float('-infinity'), 'NLK')

    # Not a Number
    with pytest.raises(InvalidOperation):
        _nan = NLK(float('NaN'), 'NLK')

    # Rounding NUs
    assert round(pi_nus, 2) == NLK("3.14", "NLK")
    assert round(pi_nus, 1) == NLK("3.1", "NLK")
    assert round(pi_nus, 0) == round(pi_nus) == NLK("3", "NLK")
