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


class NetworksInventory:  # TODO: See #1564

    MAINNET = 'mainnet'
    IBEX = 'ibex'
    LYNX = 'lynx'
    ORYX = 'oryx'
    ETH = 'ethereum'

    # TODO: Use naming scheme to preserve multiple compatibility with multiple deployments to a single network?
    POLYGON = 'polygon'
    MUMBAI = 'mumbai'

    HECO = 'heco'
    HECO_TESTNET = 'heco_testnet'

    BSC = 'bsc'
    BSC_TESTNET = 'bsc_testnet'

    UNKNOWN = 'unknown'  # TODO: Is there a better way to signal an unknown network?
    DEFAULT = MAINNET

    __to_chain_id_eth = {
        MAINNET: 1,  # Ethereum Mainnet
        ORYX: 3,  # Ropsten
        IBEX: 4,  # Rinkeby
        LYNX: 5,  # Goerli
    }

    __to_chain_id_polygon = {
        # TODO: Use naming scheme?
        POLYGON: 137,  # Polygon Mainnet
        MUMBAI: 80001,  # Polygon Testnet (Mumbai)
    }

    __to_chain_id_heco = {
        HECO: 128,
        HECO_TESTNET: 256,
    }

    __to_chain_id_bsc = {
        BSC: 56,
        BSC_TESTNET: 97,
    }

    ETH_NETWORKS = tuple(__to_chain_id_eth.keys())
    POLY_NETWORKS = tuple(__to_chain_id_polygon.keys())
    HECO_NETWORKS = tuple(__to_chain_id_heco.keys())
    BSC_NETWORKS = tuple(__to_chain_id_bsc.keys())

    NETWORKS = ETH_NETWORKS + POLY_NETWORKS + HECO_NETWORKS + BSC_NETWORKS

    class UnrecognizedNetwork(RuntimeError):
        pass

    @classmethod
    def get_ethereum_chain_id(cls, network):  # TODO: Use this (where?) to make sure we're in the right chain
        try:
            return cls.__to_ethereum_chain_id[network]
        except KeyError:
            return 1337  # TODO: what about chain id when testing?

    @classmethod
    def validate_network_name(cls, network_name: str):
        if network_name not in cls.NETWORKS:
            raise cls.UnrecognizedNetwork(f"{network_name} is not a recognized network of NuLink")
