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

import random
from typing import Union

import maya
from twisted.internet import reactor
from twisted.internet.task import LoopingCall
from twisted.python.failure import Failure

from nulink.blockchain.eth.agents import ContractAgency, PREApplicationAgent
from nulink.blockchain.eth.constants import NULL_ADDRESS
from nulink.control.emitters import StdoutEmitter
from nulink.network.exceptions import NodeSeemsToBeDown
from nulink.network.middleware import RestMiddleware
from nulink.network.nodes import NodeSprout
from nulink.utilities.logging import Logger
from nulink.utilities.task import SimpleTask


# OperatorBondedTracker 判断质押者的地址是否为NULL
class OperatorBondedTracker(SimpleTask):
    INTERVAL = 60 * 60  # 1 hour

    class OperatorNoLongerBonded(RuntimeError):
        """Raised when a running node is no longer associated with a staking provider."""

    def __init__(self, ursula):
        self._ursula = ursula
        super().__init__()

    def run(self) -> None:
        application_agent = ContractAgency.get_agent(PREApplicationAgent,
                                                     registry=self._ursula.registry,
                                                     eth_provider_uri=self._ursula.eth_provider_uri)
        staking_provider_address = application_agent.get_staking_provider_from_operator(
            operator_address=self._ursula.operator_address)
        if staking_provider_address == NULL_ADDRESS:
            # forcibly shut down ursula
            self._shutdown_ursula(halt_reactor=True)

    def _shutdown_ursula(self, halt_reactor=False):
        emitter = StdoutEmitter()
        emitter.message(f'x [Operator {self._ursula.operator_address} is no longer bonded to any '
                        f'staking provider] - Commencing auto-shutdown sequence...', color="red")
        try:
            raise self.OperatorNoLongerBonded()
        finally:
            self._ursula.stop(halt_reactor=halt_reactor)

    def handle_errors(self, failure: Failure) -> None:
        cleaned_traceback = self.clean_traceback(failure)
        self.log.warn(f"Unhandled error during operator bonded check: {cleaned_traceback}")
        if failure.check([self.OperatorNoLongerBonded]):
            # this type of exception we want to propagate because we will shut down
            failure.raiseException()


class AvailabilityTracker:
    """
        andi comment:
        从Ursulas样本或从已知节点自动测量自可用性。
        处理示例中不可到达或无效远程节点的可能性。
    """


    FAST_INTERVAL = 15    # Seconds
    SLOW_INTERVAL = 60 * 2
    SEEDING_DURATION = 60
    MAXIMUM_ALONE_TIME = 120

    MAXIMUM_SCORE = 10.0  # Score
    SAMPLE_SIZE = 1       # Ursulas
    SENSITIVITY = 0.5     # Threshold
    CHARGE_RATE = 0.9     # Measurement Multiplier

    class Unreachable(RuntimeError):
        pass

    class Solitary(Unreachable):
        message = "Cannot connect to any teacher nodes."

    class Lonely(Unreachable):
        message = "Cannot connect to enough teacher nodes."

    def __init__(self, ursula, enforce_loneliness: bool = True):

        self.log = Logger(self.__class__.__name__)
        self._ursula = ursula
        self.enforce_loneliness = enforce_loneliness

        self.__excuses = dict()  # List of failure reasons
        self.__score = 10
        # 10 == Perfect Score
        self.warnings = {
            9: self.mild_warning,
            7: self.medium_warning,
            2: self.severe_warning,
            1: self.shutdown_everything  # 0 is unobtainable
        }

        self._start_time = None
        self.__active_measurement = False
        self.__task = LoopingCall(self.maintain)
        self.responders = set()

    @property
    def excuses(self):
        return self.__excuses

    def mild_warning(self) -> None:
        self.log.info(f'[UNREACHABLE NOTICE (SCORE {self.score})] This node was recently reported as unreachable.')

    def medium_warning(self) -> None:
        self.log.warn(f'[UNREACHABLE CAUTION (SCORE {self.score})] This node is reporting as unreachable.'
                      f'Please check your network and firewall configuration.')

    def severe_warning(self) -> None:
        self.log.warn(f'[UNREACHABLE WARNING (SCORE {self.score})] '
                      f'Please check your network and firewall configuration.'
                      f'Auto-shutdown will commence soon if the services do not become available.')

    def shutdown_everything(self, reason=None, halt_reactor=False):
        self.log.warn(f'[NODE IS UNREACHABLE (SCORE {self.score})] Commencing auto-shutdown sequence...')
        self._ursula.stop(halt_reactor=False)
        try:
            if reason:
                raise reason(reason.message)
            raise self.Unreachable(f'{self._ursula} is unreachable (scored {self.score}).')
        finally:
            if halt_reactor:
                self._halt_reactor()

    @staticmethod
    def _halt_reactor() -> None:
        if reactor.running:
            reactor.stop()

    def handle_measurement_errors(self, crash_on_error: bool = False, *args, **kwargs) -> None:

        if args:
            failure = args[0]
            cleaned_traceback = failure.getTraceback().replace('{', '').replace('}', '')  # FIXME: Amazing.
            self.log.warn("Unhandled error during availability check: {}".format(cleaned_traceback))
            if crash_on_error:
                failure.raiseException()
        else:
            # Restart on failure
            if not self.running:
                self.log.debug(f"Availability check crashed, restarting...")
                self.start(now=True)

    def status(self) -> bool:
        """Returns current indication of availability"""
        result = self.score > (self.SENSITIVITY * self.MAXIMUM_SCORE)
        if not result:
            for time, reason in self.__excuses.items():
                self.log.info(f'[{time}] - {reason["error"]}')
        return result

    @property
    def running(self) -> bool:
        return self.__task.running

    def start(self, now: bool = False):
        if not self.running:
            self._start_time = maya.now()
            d = self.__task.start(interval=self.FAST_INTERVAL, now=now)
            d.addErrback(self.handle_measurement_errors)

    def stop(self) -> None:
        if self.running:
            self.__task.stop()

    def maintain(self) -> None:
        known_nodes_is_smaller_than_sample_size = len(self._ursula.known_nodes) < self.SAMPLE_SIZE

        # If there are no known nodes or too few known nodes, skip this round...
        # ... but not for longer than the maximum allotted alone time
        if known_nodes_is_smaller_than_sample_size:
            if not self._ursula.lonely and self.enforce_loneliness:
                now = maya.now().epoch
                delta = now - self._start_time.epoch
                if delta >= self.MAXIMUM_ALONE_TIME:
                    self.severe_warning()
                    reason = self.Solitary if not self._ursula.known_nodes else self.Lonely
                    self.shutdown_everything(reason=reason)
            return

        if self.__task.interval == self.FAST_INTERVAL:
            now = maya.now().epoch
            delta = now - self._start_time.epoch
            if delta >= self.SEEDING_DURATION:
                # Slow down
                self.__task.interval = self.SLOW_INTERVAL
                return

        if self.__active_measurement:
            self.log.debug(f"Availability check already in progress - skipping this round (Score: {self.score}). ")
            return  # Abort
        else:
            self.log.debug(f"Continuing to measure availability (Score: {self.score}).")
            self.__active_measurement = True

        try:
            self.measure_sample()
        finally:
            self.__active_measurement = False

        delta = maya.now() - self._start_time
        self.log.info(f"Current availability score is {self.score} measured since {delta}")
        self.issue_warnings()

    def issue_warnings(self, cascade: bool = True) -> None:
        warnings = sorted(self.warnings.items(), key=lambda t: t[0])
        for threshold, action in warnings:
            if self.score <= threshold:
                action()
                if not cascade:
                    # Exit after the first active warning is issued
                    return

    def sample(self, quantity: int) -> list:
        population = tuple(self._ursula.known_nodes.values())
        ursulas = random.sample(population=population, k=quantity)
        return ursulas

    @property
    def score(self) -> float:
        return self.__score

    def record(self, result: bool = None, reason: dict = None) -> None:
        """Score the result and cache it."""
        if (not result) and reason:
            self.__excuses[maya.now().epoch] = reason
        if result is None:
            return  # Actually nevermind, dont score this one...
        score = int(result) + self.CHARGE_RATE * self.__score
        if score >= self.MAXIMUM_SCORE:
            self.__score = self.MAXIMUM_SCORE
        else:
            self.__score = score
        self.log.debug(f"Recorded new uptime score ({self.score})")

    def measure_sample(self, ursulas: list = None) -> None:
        """
        Measure self-availability from a sample of Ursulas or automatically from known nodes.
        Handle the possibility of unreachable or invalid remote nodes in the sample.
        """

        # TODO: Relocate?
        Unreachable = (*NodeSeemsToBeDown,
                       self._ursula.NotStaking,
                       self._ursula.network_middleware.UnexpectedResponse)

        if not ursulas:
            ursulas = self.sample(quantity=self.SAMPLE_SIZE)

        for ursula_or_sprout in ursulas:
            try:
                self.measure(ursula_or_sprout=ursula_or_sprout)
            except self._ursula.network_middleware.NotFound:
                # Ignore this measurement and move on because the remote node is not compatible.
                self.record(None, reason={"error": "Remote node did not support 'ping' endpoint."})
            except Unreachable as e:
                # This node is either not an Ursula, not available, does not support uptime checks, or is not staking...
                # ...do nothing and move on without changing the score.
                self.log.debug(f'{ursula_or_sprout} responded to uptime check with {e.__class__.__name__}')
                continue

    def measure(self, ursula_or_sprout: Union['Ursula', NodeSprout]) -> None:
        """Measure self-availability from a single remote node that participates uptime checks."""
        try:
            response = self._ursula.network_middleware.check_availability(initiator=self._ursula, responder=ursula_or_sprout)
        except RestMiddleware.BadRequest as e:
            self.responders.add(ursula_or_sprout.checksum_address)
            self.record(False, reason=e.reason)
        else:
            # Record response
            self.responders.add(ursula_or_sprout.checksum_address)
            if response.status_code == 200:
                self.record(True)
            elif response.status_code == 400:
                self.record(False, reason={'failed': f"{ursula_or_sprout.checksum_address} reported unavailability."})
            else:
                self.record(None, reason={"error": f"{ursula_or_sprout.checksum_address} returned {response.status_code} from 'ping' endpoint."})
