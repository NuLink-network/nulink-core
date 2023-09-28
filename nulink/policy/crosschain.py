from nucypher_core import HRAC, ReencryptionRequest


class CrossChainHRAC:
    def __init__(self, hrac: HRAC, chain_id: int):
        self.hrac = hrac
        self.chain_id = chain_id

    @classmethod
    def from_bytes(cls, some_bytes: bytes):
        hrac_bytes, chain_bytes = some_bytes.rsplit(bytes("CHAINID", 'utf-8'))
        return cls(HRAC.from_bytes(hrac_bytes), chain_bytes.decode('utf-8'))

    def __bytes__(self) -> bytes:
        return HRAC.__bytes__(self.hrac) + bytes("CHAINID", 'utf-8') + bytes(str(self.chain_id), 'utf-8')


class CrossChainReencryptionRequest:
    def __init__(self, reencryption_request: ReencryptionRequest, hrac: CrossChainHRAC):
        self.reencryption_request = reencryption_request
        self.hrac = hrac

    @classmethod
    def from_bytes(cls, some_bytes: bytes):
        reencryption_request_bytes, hrac_bytes = some_bytes.rsplit(bytes("CCHRAC", 'utf-8'))

        return cls(ReencryptionRequest.from_bytes(reencryption_request_bytes), CrossChainHRAC.from_bytes(hrac_bytes))

    def __bytes__(self) -> bytes:
        return ReencryptionRequest.__bytes__(self.reencryption_request) + bytes("CCHRAC", 'utf-8') + CrossChainHRAC.__bytes__(self.hrac)
