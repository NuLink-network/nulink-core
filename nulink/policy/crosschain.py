from nucypher_core import HRAC


class CrossChainHRAC:
    def __init__(self, hrac: HRAC, chain_id: int):
        self.hrac = hrac
        self.chain_id = chain_id

    @classmethod
    def from_bytes(cls, some_bytes: bytes):
        hrac_bytes, chain_bytes = some_bytes.rsplit(b"_:_")

        return cls(HRAC.from_bytes(hrac_bytes), chain_bytes.decode())

    def __bytes__(self) -> bytes:
        return HRAC.__bytes__(self.hrac) + b"_:_" + str(self.chain_id).encode()
