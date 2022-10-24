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

from collections import defaultdict
import random
from typing import Dict, Sequence, List, Optional, Tuple

from eth_typing.evm import ChecksumAddress
from eth_utils import to_checksum_address
from twisted.logger import Logger

from nucypher_core import (
    TreasureMap,
    ReencryptionResponse,
    ReencryptionRequest,
    RetrievalKit,
)
from nucypher_core.umbral import (
    Capsule,
    PublicKey,
    VerifiedCapsuleFrag,
    VerificationError,
)

from nulink.crypto.signing import InvalidSignature
from nulink.network.exceptions import NodeSeemsToBeDown
from nulink.network.nodes import Learner
from nulink.policy.kits import RetrievalResult


class RetrievalPlan:
    """
    An emphemeral object providing a service of selecting Ursulas for reencryption requests
    during retrieval.
    """

    def __init__(self, treasure_map: TreasureMap, retrieval_kits: Sequence[RetrievalKit]):

        # Record the retrieval kits order
        self._capsules = [retrieval_kit.capsule for retrieval_kit in retrieval_kits]

        self._threshold = treasure_map.threshold

        # Records the retrieval results, indexed by capsule
        self._results = {retrieval_kit.capsule: {}
                         for retrieval_kit in retrieval_kits}  # {capsule: {ursula_address: cfrag}}

        # Records the addresses of Ursulas that were already queried, indexed by capsule.
        self._queried_addresses = {retrieval_kit.capsule: set(retrieval_kit.queried_addresses)
                                   for retrieval_kit in retrieval_kits}

        # Records the capsules already processed by a corresponding Ursula.
        # An inverse of `_queried_addresses`.
        self._processed_capsules = defaultdict(set)  # {ursula_address: {capsule}}
        for retrieval_kit in retrieval_kits:
            for address in retrieval_kit.queried_addresses:
                self._processed_capsules[address].add(retrieval_kit.capsule)

        # If we've already retrieved from some addresses before, query them last.
        # In other words, we try to get the maximum amount of cfrags in our first queries,
        # to use the time more efficiently.
        ursulas_to_contact_last = set()
        for queried_addresses in self._queried_addresses.values():
            ursulas_to_contact_last |= queried_addresses

        # Randomize Ursulas' priorities
        ursulas_pick_order = list(treasure_map.destinations)  # checksum addresses
        random.shuffle(ursulas_pick_order)  # mutates list in-place

        ursulas_pick_order = [ursula for ursula in ursulas_pick_order
                              if ursula not in ursulas_to_contact_last]
        self._ursulas_pick_order = ursulas_pick_order + list(ursulas_to_contact_last)

    def get_work_order(self) -> 'RetrievalWorkOrder':
        """
        Returns a new retrieval work order based on the current plan state.
        """
        while self._ursulas_pick_order:
            ursula_address = self._ursulas_pick_order.pop(0)
            # Only request reencryption for capsules that:
            # - haven't been processed by this Ursula
            # - don't already have cfrags from `threshold` Ursulas
            capsules = [capsule for capsule in self._capsules
                        if (capsule not in self._processed_capsules.get(ursula_address, set())
                            and len(self._queried_addresses[capsule]) < self._threshold)]
            if len(capsules) > 0:
                return RetrievalWorkOrder(ursula_address=ursula_address,
                                          capsules=capsules)

        # Execution will not reach this point if `is_complete()` returned `False` before this call.
        raise RuntimeError("No Ursulas left")

    def update(self, work_order: 'RetrievalWorkOrder', cfrags: Dict[Capsule, VerifiedCapsuleFrag]):
        """
        Updates the plan state, recording the cfrags obtained for capsules during a query.
        """
        for capsule, cfrag in cfrags.items():
            self._queried_addresses[capsule].add(work_order.ursula_address)
            self._processed_capsules[work_order.ursula_address].add(capsule)
            self._results[capsule][work_order.ursula_address] = cfrag

    def is_complete(self) -> bool:
        return (
            # there are no more Ursulas to query
                not bool(self._ursulas_pick_order) or
                # all the capsules have enough cfrags for decryption
                all(len(addresses) >= self._threshold for addresses in self._queried_addresses.values())
        )

    def results(self) -> List['RetrievalResult']:
        # TODO (#1995): when that issue is fixed, conversion is no longer needed
        return [RetrievalResult({to_checksum_address(address): cfrag
                                 for address, cfrag in self._results[capsule].items()})
                for capsule in self._capsules]


class RetrievalWorkOrder:
    """
    A work order issued by a retrieval plan to request reencryption from an Ursula
    """

    def __init__(self, ursula_address: ChecksumAddress, capsules: List[Capsule]):
        self.ursula_address = ursula_address
        self.capsules = capsules


class RetrievalStrategy:
    """
    Encapsulates the batch get strategy from a reservoir.
    Determines how many values to draw based on the number of values
    that have already led to successes.
    """

    def __init__(self, retrieval_work_order_key_list: List[ChecksumAddress], need_successes: int):
        self.retrieval_work_order_key_list = retrieval_work_order_key_list
        self.need_successes = need_successes

    def __call__(self, successes: int) -> Optional[List[ChecksumAddress]]:
        batch = []
        for i in range(self.need_successes - successes):
            value = self.retrieval_work_order_key_list.pop()
            if value is None:
                break
            batch.append(value)
        if not batch:
            return None
        return batch


class RetrievalClient:
    """
    Capsule frag retrieval machinery shared between Bob and Porter.
    """

    def __init__(self, learner: Learner):
        self._learner = learner
        self.log = Logger(self.__class__.__name__)

    def _ensure_ursula_availability(self, treasure_map: TreasureMap, timeout=10):
        """
        Make sure we know enough nodes from the treasure map to decrypt;
        otherwise block and wait for them to come online.
        """

        # OK, so we're going to need to do some network activity for this retrieval.
        # Let's make sure we've seeded.
        if not self._learner.done_seeding:
            self._learner.learn_from_teacher_node()

        ursulas_in_map = treasure_map.destinations.keys()

        # TODO (#1995): when that issue is fixed, conversion is no longer needed
        ursulas_in_map = [to_checksum_address(address) for address in ursulas_in_map]

        all_known_ursulas = self._learner.known_nodes.addresses()

        # Push all unknown Ursulas from the map in the queue for learning
        unknown_ursulas = ursulas_in_map - all_known_ursulas

        # If we know enough to decrypt, we can proceed.
        known_ursulas = ursulas_in_map & all_known_ursulas
        if len(known_ursulas) >= treasure_map.threshold:
            return

        # | <--- shares                                            ---> |
        # | <--- threshold               ---> | <--- allow_missing ---> |
        # | <--- known_ursulas ---> | <--- unknown_ursulas         ---> |
        allow_missing = len(treasure_map.destinations) - treasure_map.threshold
        self._learner.block_until_specific_nodes_are_known(unknown_ursulas,
                                                           timeout=timeout,
                                                           allow_missing=allow_missing,
                                                           learn_on_this_thread=True)

    def _request_reencryption(self,
                              ursula: 'Ursula',
                              reencryption_request: ReencryptionRequest,
                              alice_verifying_key: PublicKey,
                              policy_encrypting_key: PublicKey,
                              bob_encrypting_key: PublicKey,
                              timeout=2
                              ) -> Dict['Capsule', 'VerifiedCapsuleFrag']:
        """
        Sends a reencryption request to a single Ursula and processes the results.

        Returns reencrypted capsule frags matched to corresponding capsules.
        """

        middleware = self._learner.network_middleware

        try:
            response = middleware.reencrypt(ursula, bytes(reencryption_request), timeout)
        except NodeSeemsToBeDown as e:
            # TODO: What to do here?  Ursula isn't supposed to be down.  NRN
            message = (f"Ursula ({ursula}) seems to be down "
                       f"while trying to complete ReencryptionRequest: {reencryption_request}")
            self.log.info(message)
            raise RuntimeError(message) from e
        except middleware.NotFound as e:
            # This Ursula claims not to have a matching KFrag.  Maybe this has been revoked?
            # TODO: What's the thing to do here?
            # Do we want to track these Ursulas in some way in case they're lying?  #567
            message = (f"Ursula ({ursula}) claims not to not know of the policy {reencryption_request.hrac}. "
                       f"Has access been revoked?")
            self.log.warn(message)
            raise RuntimeError(message) from e
        except middleware.UnexpectedResponse:
            raise  # TODO: Handle this

        try:
            reencryption_response = ReencryptionResponse.from_bytes(response.content)
        except Exception as e:
            message = f"Ursula ({ursula}) returned an invalid response: {e}."
            self.log.warn(message)
            raise RuntimeError(message)

        ursula_verifying_key = ursula.stamp.as_umbral_pubkey()

        try:
            verified_cfrags = reencryption_response.verify(capsules=reencryption_request.capsules,
                                                           alice_verifying_key=alice_verifying_key,
                                                           ursula_verifying_key=ursula_verifying_key,
                                                           policy_encrypting_key=policy_encrypting_key,
                                                           bob_encrypting_key=bob_encrypting_key,
                                                           )
        except InvalidSignature as e:
            self.log.warn(str(e))
            raise
        except VerificationError:
            # In future we may want to remember this Ursula and do something about it
            self.log.warn("Failed to verify capsule frags in the ReencryptionResponse")
            raise
        except Exception as e:
            message = f"Failed to verify the ReencryptionResponse: {e}"
            self.log.warn(message)
            raise RuntimeError(message)

        return {capsule: vcfrag for capsule, vcfrag
                in zip(reencryption_request.capsules, verified_cfrags)}

    def retrieve_cfrags(
            self,
            treasure_map: TreasureMap,
            retrieval_kits: Sequence[RetrievalKit],
            alice_verifying_key: PublicKey,  # KeyFrag signer's key
            bob_encrypting_key: PublicKey,  # User's public key (reencryption target)
            bob_verifying_key: PublicKey,
    ) -> List[RetrievalResult]:

        self._ensure_ursula_availability(treasure_map)

        retrieval_plan = RetrievalPlan(treasure_map=treasure_map, retrieval_kits=retrieval_kits)
        retrieval_worker_orders: Dict[ChecksumAddress, 'RetrievalWorkOrder'] = {}
        while True:
            try:
                work_order = retrieval_plan.get_work_order()
                retrieval_worker_orders[to_checksum_address(work_order.ursula_address)] = work_order
            except RuntimeError:
                break

        value_factory = RetrievalStrategy(list(retrieval_worker_orders.keys()), treasure_map.threshold)

        def worker_pool_start(target_successes: int, timeout=15) -> Tuple['WorkerPool', Dict[ChecksumAddress, Dict['Capsule', 'VerifiedCapsuleFrag']]]:

            from nulink.utilities.concurrency import WorkerPool

            def worker(address: ChecksumAddress) -> Dict['Capsule', 'VerifiedCapsuleFrag']:

                work_order: 'RetrievalWorkOrder' = retrieval_worker_orders.get(address)
                # TODO (#1995): when that issue is fixed, conversion is no longer needed

                if not work_order:
                    raise Exception(f"not find ursula {address} in retrieval_worker_orders")

                ursula_checksum_address = to_checksum_address(work_order.ursula_address)

                if ursula_checksum_address not in self._learner.known_nodes:
                    raise Exception(f"not find ursula {work_order.ursula_address} in known_nodes")

                ursula = self._learner.known_nodes[ursula_checksum_address]

                reencryption_request = ReencryptionRequest(
                    hrac=treasure_map.hrac,
                    capsules=work_order.capsules,
                    encrypted_kfrag=treasure_map.destinations[work_order.ursula_address],
                    bob_verifying_key=bob_verifying_key,
                    publisher_verifying_key=treasure_map.publisher_verifying_key)

                try:
                    cfrags = self._request_reencryption(ursula=ursula,
                                                        reencryption_request=reencryption_request,
                                                        alice_verifying_key=alice_verifying_key,
                                                        policy_encrypting_key=treasure_map.policy_encrypting_key,
                                                        bob_encrypting_key=bob_encrypting_key)
                except Exception as e:
                    # TODO (#2789): at this point we can separate the exceptions to "acceptable"
                    # (Ursula is not reachable) and "unacceptable" (Ursula provided bad results).
                    self.log.warn(f"Ursula {ursula} failed to reencrypt: {e}")
                    raise Exception(f"Ursula {ursula} failed to reencrypt: {e}")

                retrieval_plan.update(work_order, cfrags)
                return cfrags

            worker_pool = WorkerPool(
                worker=worker,
                value_factory=value_factory,
                target_successes=target_successes,
                timeout=timeout,
                stagger_timeout=1
            )
            worker_pool.start()
            try:
                successes = worker_pool.block_until_target_successes()
            except (WorkerPool.OutOfValues, WorkerPool.TimedOut):
                # run the pragma here, the cfrags maybe not enough cause by last exception: continue -> on line 306, 327
                # fix for: Reduce the probability of insufficient cfrags
                # It's possible to raise some other exceptions here but we will use the logic below.
                successes = worker_pool.get_successes()
            finally:
                worker_pool.cancel()
                worker_pool.join()

            return worker_pool, successes

        worker_pool, successes = worker_pool_start(treasure_map.threshold, timeout=10)

        if len(successes) < treasure_map.threshold:
            worker_pool, new_successes = worker_pool_start(treasure_map.threshold - len(successes), timeout=15)

        successes.update(new_successes)

        if len(successes) < treasure_map.threshold:
            failures = worker_pool.get_failures()
            accepted_addresses = ", ".join(ursula.checksum_address for ursula in successes.values())
            rejections = "\n".join(f"{address}: {value}" for address, (type_, value, traceback) in failures.items())
            message = "Failed to retrieve_cfrags contact enough nodes.\n" \
                      f"Selected:\n{accepted_addresses}\n" \
                      f"Unavailable:\n{rejections}"
            self.log.debug(message)

        # run the pragma here, The probability of not having enough cfrags is greatly reduced, But it can happen, It cannot be avoided entirely, except at the cost of time

        return retrieval_plan.results()
