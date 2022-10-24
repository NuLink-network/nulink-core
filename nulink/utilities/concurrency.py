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

import io
import sys
import traceback
from queue import Queue
from threading import Thread, Event, Lock
from typing import Callable, List, Any, Optional, Dict

from constant_sorrow.constants import PRODUCER_STOPPED, TIMEOUT_TRIGGERED
from twisted.python.threadpool import ThreadPool
from nucypher_core.umbral import PublicKey

nulink_workers: Dict = \
    {
        "0x8D0d076635F627Aa62e5D422e7B66D1fe6fbc534": {
            "checksum_address": "0x8D0d076635F627Aa62e5D422e7B66D1fe6fbc534",
            "uri": "https://8.219.184.153:9154",
            "encrypting_key": "03758a1209d2d12b7c24624cafc6663915d40b13b376fb72050a3dac44e5e22a53"
        },
        "0x1e50814CA9367EC537324078999CECe44db1380D": {
            "checksum_address": "0x1e50814CA9367EC537324078999CECe44db1380D",
            "uri": "https://8.219.60.76:9153",
            "encrypting_key": "022317a079aab3845362e3dbe2f4f4f23487bc7eb56d7e118492c33f48b44151b6"
        },
        "0xa7Cda2C05D20E513180A1F1b38440397f41cBfb4": {
            "checksum_address": "0xa7Cda2C05D20E513180A1F1b38440397f41cBfb4",
            "uri": "https://8.219.179.45:9153",
            "encrypting_key": "029938370973935a419228ec45e82c29343eb3117d5234fe3aae008127bd890dbb"
        },
        "0x368479d9C56eE8DA9273C76128f942E8645c6D2F": {
            "checksum_address": "0x368479d9C56eE8DA9273C76128f942E8645c6D2F",
            "uri": "https://8.219.179.45:9154",
            "encrypting_key": "02da73a870ed83780c8d9ac1597a8b45b90df07138a498e27c98420d77c1142895"
        },
        "0x5397D10DFBD04B295DC17182D2e3dF60dE8144f6": {
            "checksum_address": "0x5397D10DFBD04B295DC17182D2e3dF60dE8144f6",
            "uri": "https://8.219.186.125:9153",
            "encrypting_key": "03f06e81d91538048c8c8f30b7410b2ac1f1f5173f3f8fd12d4ca857e4ab39ad70"
        },
        "0x2aBD4B01520c10498F61Bb0bA91CDA8cF01b59C9": {
            "checksum_address": "0x2aBD4B01520c10498F61Bb0bA91CDA8cF01b59C9",
            "uri": "https://8.219.61.245:9154",
            "encrypting_key": "03c43f5032dcf857bb64791b056285c90b073c13f06a6597506c70efe34901abc0"
        },
        "0x93B0Ee5a18764D268F60B52de3897cCda5E4e927": {
            "checksum_address": "0x93B0Ee5a18764D268F60B52de3897cCda5E4e927",
            "uri": "https://8.219.184.153:9153",
            "encrypting_key": "0280b02e9653e44daa14fbb8b9617523cdb045c20887c3ecaf5d31d7a20c54d873"
        },
        "0x25452b51f2AEfe460c3a907132d48e44259Cdf2b": {
            "checksum_address": "0x25452b51f2AEfe460c3a907132d48e44259Cdf2b",
            "uri": "https://8.219.186.125:9154",
            "encrypting_key": "0337e42f1487cdfdec1f234e4a106d3eba282a30284da3201a48c91e242252e932"
        },
        "0x39feFe0F21e3d32c9A3bF7967464633054EC235e": {
            "checksum_address": "0x39feFe0F21e3d32c9A3bF7967464633054EC235e",
            "uri": "https://8.219.60.76:9154",
            "encrypting_key": "036ca456702b8630e27e24ba082d1b9b026be65bb4682c86bbd49329691cb1cb04"
        },
        "0x6E62c6EF94132aef98a7E9bB0a048B9C12e57512": {
            "checksum_address": "0x6E62c6EF94132aef98a7E9bB0a048B9C12e57512",
            "uri": "https://8.219.61.245:9153",
            "encrypting_key": "02c43fd02d4ecb42f3ddf92fd730e4a41f1286eb60007fe6fdd97fd3b899fdbaab"
        },
        "0xfcdcf37aF546FD5362a5B9E0C447D1BDb38820Ac": {
            "checksum_address": "0xfcdcf37aF546FD5362a5B9E0C447D1BDb38820Ac",
            "uri": "https://8.219.188.70:9152",
            "encrypting_key": "022aa1df6ad42eda762635e388fd415598a763e69ebe648177b500a4028cbd3d81"
        }
    }


class Success:
    def __init__(self, value, result):
        self.value = value
        self.result = result


class Failure:
    def __init__(self, value, exc_info):
        self.value = value
        self.exc_info = exc_info


class Cancelled(Exception):
    pass


class FutureResult:

    def __init__(self, value=None, exc_info=None):
        self.value = value
        self.exc_info = exc_info


class Future:
    """
    A simplified future object. Can be set to some value (all further sets are ignored),
    can be waited on.
    """

    def __init__(self):
        self._lock = Lock()
        self._set_event = Event()
        self._value = None

    def _set(self, value):
        with self._lock:
            if not self._set_event.is_set():
                self._value = value
                self._set_event.set()

    def set(self, value):
        self._set(FutureResult(value=value))

    def set_exception(self):
        exc_info = sys.exc_info()
        self._set(FutureResult(exc_info=exc_info))

    def is_set(self):
        return self._set_event.is_set()

    def get(self):
        self._set_event.wait()

        if self._value.exc_info is not None:
            (exc_type, exc_value, exc_traceback) = self._value.exc_info
            if exc_value is None:
                exc_value = exc_type()
            if exc_value.__traceback__ is not exc_traceback:
                raise exc_value.with_traceback(exc_traceback)
            raise exc_value
        else:
            return self._value.value


class WorkerPoolException(Exception):
    """Generalized exception class for WorkerPool failures."""

    def __init__(self, message_prefix: str, failures: Dict):
        self.failures = failures

        # craft message
        msg = message_prefix
        if self.failures:
            msg = f"{message_prefix} ({len(self.failures)} failures recorded)"
        super().__init__(msg)

    def get_tracebacks(self) -> Dict[Any, str]:
        """Returns values and associated tracebacks of execution failures."""
        exc_tracebacks = {}
        for value, exc_info in self.failures.items():
            _, exception, tb = exc_info
            f = io.StringIO()
            traceback.print_tb(tb, file=f)
            exc_tracebacks[value] = f"{f.getvalue()}\n{exception}"

        return exc_tracebacks


class WorkerPool:
    """
    A generalized class that can start multiple workers in a thread pool with values
    drawn from the given value factory object,
    and wait for their completion and a given number of successes
    (a worker returning something without throwing an exception).
    """

    class TimedOut(WorkerPoolException):
        """Raised if waiting for the target number of successes timed out."""

        def __init__(self, timeout: float, *args, **kwargs):
            self.timeout = timeout
            super().__init__(message_prefix=f"Execution timed out after {timeout}s",
                             *args, **kwargs)

    class OutOfValues(WorkerPoolException):
        """Raised if the value factory is out of values, but the target number was not reached."""

        def __init__(self, *args, **kwargs):
            super().__init__(message_prefix="Execution stopped before completion - not enough available values",
                             *args, **kwargs)

    def __init__(self,
                 worker: Callable[[Any], Any],
                 value_factory: Callable[[int], Optional[List[Any]]],
                 target_successes,
                 timeout: float,
                 stagger_timeout: float = 0,
                 threadpool_size: int = None):

        # TODO: make stagger_timeout a part of the value factory?

        self._worker = worker
        self._value_factory = value_factory
        self._timeout = timeout
        self._stagger_timeout = stagger_timeout
        self._target_successes = target_successes

        thread_pool_kwargs = {}
        if threadpool_size is not None:
            thread_pool_kwargs['minthreads'] = threadpool_size
            thread_pool_kwargs['maxthreads'] = threadpool_size
        self._threadpool = ThreadPool(**thread_pool_kwargs)

        # These three tasks must be run in separate threads
        # to avoid being blocked by workers in the thread pool.
        self._bail_on_timeout_thread = Thread(target=self._bail_on_timeout)
        self._produce_values_thread = Thread(target=self._produce_values)
        self._process_results_thread = Thread(target=self._process_results)

        self._successes = {}
        self._failures = {}
        self._started_tasks = 0
        self._finished_tasks = 0

        self._cancel_event = Event()
        self._result_queue = Queue()
        self._target_value = Future()
        self._producer_error = Future()
        self._results_lock = Lock()
        self._threadpool_stop_lock = Lock()
        self._threadpool_stopped = False

    def start(self):
        # TODO: check if already started?
        self._threadpool.start()
        self._produce_values_thread.start()
        self._process_results_thread.start()
        self._bail_on_timeout_thread.start()

    def cancel(self):
        """
        Cancels the tasks enqueued in the thread pool and stops the producer thread.
        """
        self._cancel_event.set()

    def _stop_threadpool(self):
        # This can be called from multiple threads
        # (`join()` itself can be called from multiple threads,
        # and we also attempt to stop the pool from the `_process_results()` thread).
        with self._threadpool_stop_lock:
            if not self._threadpool_stopped:
                self._threadpool.stop()
                self._threadpool_stopped = True

    def _check_for_producer_error(self):
        # Check for any unexpected exceptions in the producer thread
        if self._producer_error.is_set():
            # Will raise if Future was set with an exception
            self._producer_error.get()

    def join(self):
        """
        Waits for all the threads to finish.
        Can be called several times.
        """
        self._produce_values_thread.join()
        self._process_results_thread.join()
        self._bail_on_timeout_thread.join()

        # In most cases `_threadpool` will be stopped by the `_process_results()` thread.
        # But in case there's some unexpected bug in its code, we're making sure the pool is stopped
        # to avoid the whole process hanging.
        self._stop_threadpool()

        self._check_for_producer_error()

    def _sleep(self, timeout):
        """
        Sleeps for a given timeout, can be interrupted by a cancellation event.
        """
        if self._cancel_event.wait(timeout):
            raise Cancelled

    def get_nulink_workers(self) -> Dict[str, 'Porter.UrsulaInfo']:

        # Porter.UrsulaInfo(checksum_address=ursula_address,
        #                   uri=f"{ursula.rest_interface.formal_uri}",
        #                   encrypting_key=ursula.public_keys(DecryptingPower))
        from nulink.utilities.porter.porter import Porter, to_checksum_address

        porter_ursula_worker_dict: Dict[str, Porter.UrsulaInfo] = {checksum_address: Porter.UrsulaInfo(checksum_address=to_checksum_address(checksum_address),
                                                                                                       uri=ursula_info["uri"],
                                                                                                       encrypting_key=PublicKey.from_bytes(bytes.fromhex(ursula_info["encrypting_key"])))
                                                                   for checksum_address, ursula_info in nulink_workers.items()}

        return porter_ursula_worker_dict

    def get_enough_ursulas(self) -> Dict[str, 'Porter.UrsulaInfo']:

        success_workers: Dict[str, 'Porter.UrsulaInfo'] = self.get_successes()
        need_to_add_worker_len = self._target_successes - len(success_workers)

        enough_success_workers: Dict[str, 'Porter.UrsulaInfo'] = success_workers

        _nulink_workers: Dict[str, 'Porter.UrsulaInfo'] = self.get_nulink_workers()

        enough_success_workers.update(_nulink_workers)

        len_enough_success_workers = len(enough_success_workers)

        while len_enough_success_workers > self._target_successes:
            enough_success_workers.popitem()
            len_enough_success_workers -= 1

        return enough_success_workers

        # if need_to_add_worker_len <= 0:
        #     # don't need to add workers
        #     return enough_success_workers
        #
        # _nulink_workers: Dict[str, 'Porter.UrsulaInfo'] = self.get_nulink_workers()
        # if len(_nulink_workers) < need_to_add_worker_len:
        #     # There are not enough nulink workers
        #     return enough_success_workers
        #
        # need_to_add_len_counter = need_to_add_worker_len
        # for checksum_address, ursula_info in success_workers.items():
        #     if need_to_add_len_counter <= 0:
        #         break
        #
        #     if checksum_address not in _nulink_workers:
        #         enough_success_workers[checksum_address] = _nulink_workers[checksum_address]
        #
        # return enough_success_workers

    def block_until_target_successes(self) -> Dict:
        """
        Blocks until the target number of successes is reached.
        Returns a dictionary of values matched to results.
        Can be called several times.
        """
        self._check_for_producer_error()

        result = self._target_value.get()

        if result == TIMEOUT_TRIGGERED:
            raise self.TimedOut(timeout=self._timeout, failures=self.get_failures())
        elif result == PRODUCER_STOPPED:
            raise self.OutOfValues(failures=self.get_failures())

        return result

    def get_failures(self) -> Dict:
        """
        Get the current failures, as a dictionary of values to thrown exceptions.
        """
        with self._results_lock:
            return dict(self._failures)

    def get_successes(self) -> Dict:
        """
        Get the current successes, as a dictionary of values to worker return values.
        """
        with self._results_lock:
            return dict(self._successes)

    def _bail_on_timeout(self):
        """
        A service thread that cancels the pool on timeout.
        """
        if not self._cancel_event.wait(timeout=self._timeout):
            self._target_value.set(TIMEOUT_TRIGGERED)
        self._cancel_event.set()

    def _worker_wrapper(self, value):
        """
        A wrapper that catches exceptions thrown by the worker
        and sends the results to the processing thread.
        """
        try:
            # If we're in the cancelled state, interrupt early
            self._sleep(0)

            result = self._worker(value)
            self._result_queue.put(Success(value, result))
        except Cancelled as e:
            self._result_queue.put(e)
        except BaseException as e:
            self._result_queue.put(Failure(value, sys.exc_info()))

    def _process_results(self):
        """
        A service thread that processes worker results
        and waits for the target number of successes to be reached.
        """
        producer_stopped = False
        success_event_reached = False
        while True:
            result = self._result_queue.get()

            if result == PRODUCER_STOPPED:
                producer_stopped = True
            else:
                self._finished_tasks += 1
                if isinstance(result, Success):
                    with self._results_lock:
                        self._successes[result.value] = result.result
                        len_successes = len(self._successes)
                    if not success_event_reached and len_successes == self._target_successes:
                        # A protection for the case of repeating values.
                        # Only trigger the target value once.
                        success_event_reached = True
                        self._target_value.set(self.get_successes())
                if isinstance(result, Failure):
                    with self._results_lock:
                        self._failures[result.value] = result.exc_info

            if success_event_reached:
                # no need to continue processing results
                self.cancel()  # to cancel the timeout thread
                break

            if producer_stopped and self._finished_tasks == self._started_tasks:
                self.cancel()  # to cancel the timeout thread
                self._target_value.set(PRODUCER_STOPPED)
                break

        self._stop_threadpool()

    def _produce_values(self):
        while True:
            try:
                with self._results_lock:
                    len_successes = len(self._successes)
                batch = self._value_factory(len_successes)
                if not batch:
                    break

                self._started_tasks += len(batch)
                for value in batch:
                    # There is a possible race between `callInThread()` and `stop()`,
                    # But we never execute them at the same time,
                    # because `join()` checks that the producer thread is stopped.
                    self._threadpool.callInThread(self._worker_wrapper, value)

                self._sleep(self._stagger_timeout)

            except Cancelled:
                break

            except BaseException:
                self._producer_error.set_exception()
                self.cancel()
                break

        self._result_queue.put(PRODUCER_STOPPED)
