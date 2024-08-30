from typing import Dict

from nulink.blockchain.eth.networks import NetworksInventory

nulink_workers: Dict = \
    {
        NetworksInventory.BSC_DEV_TESTNET:
            {
                # "0xc95C2BA4234b2a3E1aa91d167Ee1CB5f951A5945": {
                #     "checksum_address": "0xc95C2BA4234b2a3E1aa91d167Ee1CB5f951A5945",
                #     "uri": "https://8.222.155.168:9161",
                #     "encrypting_key": "032aa6db627b3a4b527d4bbe74b8b82801fa287dddc30665b6d8d45292c60640ee"
                # },
                # "0x4F09EA918210dC8422299BD0E94eEfE78C30eC18": {
                #     "checksum_address": "0x4F09EA918210dC8422299BD0E94eEfE78C30eC18",
                #     "uri": "https://8.222.131.226:9161",
                #     "encrypting_key": "0317ea59b97b7114a4954229a6798ac1565c64f19ac66364fbba205c8ba008e948"
                # },
                # "0x37e134573AE74C212Aa47941C95b58265D437998": {
                #     "checksum_address": "0x37e134573AE74C212Aa47941C95b58265D437998",
                #     "uri": "https://8.222.146.98:9161",
                #     "encrypting_key": "031addb934b01b8a373a8db2947156e664fe8ee2f6d723231cf972fa7cf6bb2059"
                # }
            },
        NetworksInventory.BSC_TESTNET: {

        },

        NetworksInventory.HORUS: {

        },
    }
