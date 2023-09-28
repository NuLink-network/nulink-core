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
from typing import List, Optional

from eth_typing import ChecksumAddress

from nucypher_core import TreasureMap, RetrievalKit
from nucypher_core.umbral import PublicKey

from nulink.control.interfaces import ControlInterface, attach_schema
from nulink.policy.crosschain import CrossChainHRAC
from nulink.utilities.porter.control.specifications import porter_schema


class PorterInterface(ControlInterface):
    def __init__(self, porter: 'Porter' = None, *args, **kwargs):
        super().__init__(implementer=porter, *args, **kwargs)

    #
    # Alice Endpoints
    #
    @attach_schema(porter_schema.AliceGetUrsulas)
    def get_ursulas(self,
                    quantity: int,
                    exclude_ursulas: Optional[List[ChecksumAddress]] = None,
                    include_ursulas: Optional[List[ChecksumAddress]] = None) -> dict:
        ursulas_info = self.implementer.get_ursulas(quantity=quantity,
                                                    exclude_ursulas=exclude_ursulas,
                                                    include_ursulas=include_ursulas)

        response_data = {"ursulas": ursulas_info}
        return response_data

    @attach_schema(porter_schema.StakerGetUrsulasTotal)
    def get_ursulas_total(self, return_list: bool = False) -> dict:
        ret = self.implementer.get_ursulas_total(return_list)

        if return_list:
            response_data = {"total": ret[0], 'list': ret[1]}
        else:
            response_data = {"total": ret}

        return response_data

    @attach_schema(porter_schema.GetCurrentVersion)
    def get_current_version(self) -> dict:
        version = self.implementer.get_current_version()

        return {"version": version}

    @attach_schema(porter_schema.AliceRevoke)
    def revoke(self) -> dict:
        # Steps (analogous to nucypher.character.control.interfaces):
        # 1. creation of objects / setup
        # 2. call self.implementer.some_function() i.e. Porter learner has an associated function to call
        # 3. create response
        pass

    @attach_schema(porter_schema.BobRetrieveCFrags)
    def retrieve_cfrags(self,
                        treasure_map: TreasureMap,
                        retrieval_kits: List[RetrievalKit],
                        alice_verifying_key: PublicKey,
                        bob_encrypting_key: PublicKey,
                        bob_verifying_key: PublicKey,
                        cross_chain_hrac: CrossChainHRAC,
                        ) -> dict:
        retrieval_results = self.implementer.retrieve_cfrags(treasure_map=treasure_map,
                                                             retrieval_kits=retrieval_kits,
                                                             alice_verifying_key=alice_verifying_key,
                                                             bob_encrypting_key=bob_encrypting_key,
                                                             bob_verifying_key=bob_verifying_key,
                                                             cross_chain_hrac=cross_chain_hrac)
        results = retrieval_results  # list of RetrievalResult objects
        response_data = {'retrieval_results': results}
        return response_data
