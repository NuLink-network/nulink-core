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

from abc import ABC, abstractmethod
from typing import Sequence, Optional, Iterable, List, Dict, Set

import maya
from eth_typing.evm import ChecksumAddress
from nucypher_core import HRAC, TreasureMap
from nucypher_core.umbral import PublicKey, VerifiedKeyFrag

from nulink.blockchain.eth.utils import calculate_period_duration
from nulink.crypto.powers import DecryptingPower
from nulink.network.middleware import RestMiddleware
from nulink.policy.reservoir import (
    make_federated_staker_reservoir,
    MergedReservoir,
    PrefetchStrategy,
    make_decentralized_staking_provider_reservoir
)
from nulink.policy.revocation import RevocationKit
from nulink.utilities.concurrency import WorkerPool
from nulink.utilities.logging import Logger


class Policy(ABC):
    """
    An edict by Alice, arranged with n Ursulas, to perform re-encryption for a specific Bob.
    """

    log = Logger("Policy")

    class PolicyException(Exception):
        """Base exception for policy exceptions"""

    class NotEnoughUrsulas(PolicyException):
        """
        Raised when a Policy cannot be generated due an insufficient
        number of available qualified network nodes.
        """

    def __init__(self,
                 publisher: 'Alice',
                 label: bytes,
                 bob: 'Bob',
                 kfrags: Sequence[VerifiedKeyFrag],
                 public_key: PublicKey,
                 threshold: int,
                 expiration: maya.MayaDT,
                 commencement: maya.MayaDT,
                 value: int,
                 rate: int,
                 duration: int,
                 payment_method: 'PaymentMethod'
                 ):

        self.threshold = threshold
        self.shares = len(kfrags)
        self.label = label
        self.bob = bob
        self.kfrags = kfrags
        self.public_key = public_key
        self.commencement = commencement
        self.expiration = expiration
        self.duration = duration
        self.value = value
        self.rate = rate
        self.nodes = None  # set by publication

        self.publisher = publisher
        self.hrac = HRAC(publisher_verifying_key=self.publisher.stamp.as_umbral_pubkey(),
                         bob_verifying_key=self.bob.stamp.as_umbral_pubkey(),
                         label=self.label)
        self.payment_method = payment_method
        self.payment_method.validate_price(shares=self.shares, value=value, duration=duration)

    def __repr__(self):
        return f"{self.__class__.__name__}:{bytes(self.hrac).hex()[:6]}"

    @abstractmethod
    def _make_reservoir(self, handpicked_addresses: Sequence[ChecksumAddress]) -> MergedReservoir:
        """Builds a `MergedReservoir` to use for drawing addresses to send proposals to."""
        raise NotImplementedError

    def _publish(self, ursulas: List['Ursula']) -> Dict:
        self.nodes = [ursula.checksum_address for ursula in ursulas]
        receipt = self.payment_method.pay(policy=self)
        return receipt

    def _ping_node(self, address: ChecksumAddress, network_middleware: RestMiddleware) -> 'Ursula':
        # Handles edge case when provided address is not a known peer.
        if address not in self.publisher.known_nodes:
            raise RuntimeError(f"{address} is not a known peer")

        ursula = self.publisher.known_nodes[address]
        response = network_middleware.ping(node=ursula)
        status_code = response.status_code

        if status_code == 200:
            return ursula
        else:
            raise RuntimeError(f"{ursula} is not available for selection ({status_code}).")

    def get_enough_ursulas(self, worker_pool: WorkerPool) -> Dict[ChecksumAddress, 'Ursula']:
        from nulink.utilities.porter.porter import Porter

        success_workers: Dict[ChecksumAddress, 'Ursula'] = worker_pool.get_successes()

        _nulink_workers: Set[ChecksumAddress] = Porter.get_nulink_worker_addresses()

        need_to_successes = worker_pool.get_target_successes() - len(success_workers)

        enough_success_ursulas: Dict[ChecksumAddress, 'Ursula'] = success_workers

        for checksum_address in _nulink_workers:
            if need_to_successes <= 0:
                return enough_success_ursulas

            if checksum_address in success_workers:
                continue
            if checksum_address not in self.publisher.known_nodes:
                continue

            ursula = self.publisher.known_nodes[checksum_address]

            enough_success_ursulas[checksum_address] = ursula
            need_to_successes = need_to_successes - 1

        return enough_success_ursulas

    def _sample(self,
                network_middleware: RestMiddleware,
                ursulas: Optional[Iterable['Ursula']] = None,
                timeout: int = 15,
                ) -> List['Ursula']:
        """Send concurrent requests to the /ping HTTP endpoint of nodes drawn from the reservoir."""

        ursulas = ursulas or []
        handpicked_addresses = [ChecksumAddress(ursula.checksum_address) for ursula in ursulas]

        self.publisher.block_until_number_of_known_nodes_is(self.shares, learn_on_this_thread=True, eager=True)
        # 获取 active stakers
        reservoir = self._make_reservoir(handpicked_addresses)
        value_factory = PrefetchStrategy(reservoir, self.shares)

        def worker(address) -> 'Ursula':
            return self._ping_node(address, network_middleware)

        worker_pool = WorkerPool(
            worker=worker,
            value_factory=value_factory,
            target_successes=self.shares,
            timeout=timeout,
            stagger_timeout=1
        )
        worker_pool.start()
        try:
            successes = worker_pool.block_until_target_successes()
        except (WorkerPool.OutOfValues, WorkerPool.TimedOut):
            # It's possible to raise some other exceptions here but we will use the logic below.
            successes = self.get_enough_ursulas(worker_pool)
        finally:
            worker_pool.cancel()
            worker_pool.join()
        failures = worker_pool.get_failures()

        accepted_addresses = ", ".join(ursula.checksum_address for ursula in successes.values())
        if len(successes) < self.shares:
            rejections = "\n".join(f"{address}: {value}" for address, (type_, value, traceback) in failures.items())
            message = "Failed to contact enough sampled nodes.\n" \
                      f"Selected:\n{accepted_addresses}\n" \
                      f"Unavailable:\n{rejections}"
            self.log.debug(message)
            raise self.NotEnoughUrsulas(message)

        self.log.debug(f"Selected nodes for policy: {accepted_addresses}")
        ursulas = list(successes.values())
        return ursulas

    def enact(self, network_middleware: RestMiddleware, ursulas: Optional[Iterable['Ursula']] = None) -> 'EnactedPolicy':
        """Attempts to enact the policy, returns an `EnactedPolicy` object on success."""

        ursulas = self._sample(network_middleware=network_middleware, ursulas=ursulas)
        self._publish(ursulas=ursulas)

        assigned_kfrags = {
            ursula.canonical_address: (ursula.public_keys(DecryptingPower), vkfrag)
            for ursula, vkfrag in zip(ursulas, self.kfrags)
        }

        treasure_map = TreasureMap(signer=self.publisher.stamp.as_umbral_signer(),
                                   hrac=self.hrac,
                                   policy_encrypting_key=self.public_key,
                                   assigned_kfrags=assigned_kfrags,
                                   threshold=self.threshold)

        enc_treasure_map = treasure_map.encrypt(signer=self.publisher.stamp.as_umbral_signer(),
                                                recipient_key=self.bob.public_keys(DecryptingPower))

        # TODO: Signal revocation without using encrypted kfrag
        revocation_kit = RevocationKit(treasure_map=treasure_map, signer=self.publisher.stamp)

        enacted_policy = EnactedPolicy(self.hrac,
                                       self.label,
                                       self.public_key,
                                       treasure_map.threshold,
                                       enc_treasure_map,
                                       revocation_kit,
                                       self.publisher.stamp.as_umbral_pubkey())

        return enacted_policy


class FederatedPolicy(Policy):

    def _make_reservoir(self, handpicked_addresses: List[ChecksumAddress]):
        """Returns a federated node reservoir for creating a federated policy."""
        return make_federated_staker_reservoir(known_nodes=self.publisher.known_nodes,
                                               include_addresses=handpicked_addresses)


class BlockchainPolicy(Policy):

    # reservoir n. 水库；蓄水池
    def _make_reservoir(self, handpicked_addresses: List[ChecksumAddress]):
        """Returns a reservoir of staking nodes to create a decentralized policy."""
        # 获取 active stakers
        reservoir = make_decentralized_staking_provider_reservoir(application_agent=self.publisher.application_agent,  # BlockchainPolicyAuthor 代理 PREApplicationAgent
                                                                  include_addresses=handpicked_addresses)
        return reservoir


class EnactedPolicy:

    def __init__(self,
                 hrac: HRAC,
                 label: bytes,
                 public_key: PublicKey,
                 threshold: int,
                 treasure_map: 'EncryptedTreasureMap',
                 revocation_kit: RevocationKit,
                 publisher_verifying_key: PublicKey):
        self.hrac = hrac
        self.label = label
        self.public_key = public_key
        self.treasure_map = treasure_map
        self.revocation_kit = revocation_kit
        self.threshold = threshold
        self.shares = len(self.revocation_kit)
        self.publisher_verifying_key = publisher_verifying_key
