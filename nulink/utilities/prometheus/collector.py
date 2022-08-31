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


from nulink.blockchain.eth.events import ContractEventsThrottler

try:
    from prometheus_client import Gauge, Enum, Counter, Info, Histogram, Summary
    from prometheus_client.registry import CollectorRegistry
except ImportError:
    raise ImportError('"prometheus_client" must be installed - run "pip install nulink[ursula]" and try again.')

from abc import ABC, abstractmethod
from eth_typing.evm import ChecksumAddress

import nulink
from nulink.blockchain.eth.actors import NulinkTokenActor
from nulink.blockchain.eth.agents import ContractAgency, PREApplicationAgent, EthereumContractAgent
from nulink.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nulink.blockchain.eth.registry import BaseContractRegistry
from nulink.datastore.queries import get_reencryption_requests

from typing import Dict, Type


class MetricsCollector(ABC):
    """Metrics Collector Interface."""
    class CollectorError(Exception):
        pass

    class CollectorNotInitialized(Exception):
        """Raised when the Collector was not initialized before being used."""

    @abstractmethod
    def initialize(self, metrics_prefix: str, registry: CollectorRegistry) -> None:
        """Initialize metrics collector."""
        return NotImplemented

    @abstractmethod
    def collect(self) -> None:
        """Collect relevant metrics."""
        return NotImplemented


class BaseMetricsCollector(MetricsCollector):
    """
    Base metrics collector that checks whether collector was initialized before used.

    Subclasses should initialize the self.metrics member in their initialize() method since the
    self.metrics member is used to determine whether initialize was called, and if not an exception is raised.
    """
    def __init__(self):
        self.metrics: Dict = None

    def collect(self) -> None:
        if self.metrics is None:
            raise self.CollectorNotInitialized

        self._collect_internal()

    @abstractmethod
    def _collect_internal(self):
        """
        Called by collect() - subclasses should override this method instead of collect() to ensure that the
        initialization check is always performed.
        """
        # created so that the initialization check does not have to be specified by all subclasses of
        # BaseMetricsCollector; instead it is performed automatically by collect()
        return NotImplemented


class UrsulaInfoMetricsCollector(BaseMetricsCollector):
    """Collector for Ursula specific metrics."""
    def __init__(self, ursula: 'Ursula'):
        super().__init__()
        self.ursula = ursula

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry) -> None:
        self.metrics = {
            "host_info": Info(f'{metrics_prefix}_host_info', 'Description of info', registry=registry),
            "learning_status": Enum(f'{metrics_prefix}_node_discovery', 'Learning loop status',
                                    states=['starting', 'running', 'stopped'], registry=registry),
            "known_nodes_gauge": Gauge(f'{metrics_prefix}_known_nodes',
                                       'Number of currently known nodes',
                                       registry=registry),
            "work_orders_gauge": Gauge(f'{metrics_prefix}_work_orders',
                                       'Number of accepted work orders',
                                       registry=registry),
            "policies_held_gauge": Gauge(f'{metrics_prefix}_policies_held',
                                         'Policies held',
                                         registry=registry),
            "availability_score_gauge": Gauge(f'{metrics_prefix}_availability_score',
                                              'Availability score',
                                              registry=registry),
        }

    def _collect_internal(self) -> None:
        # info
        base_payload = {'app_version': nulink.__version__,
                        'host': str(self.ursula.rest_interface),
                        'domain': self.ursula.domain,
                        'nickname': str(self.ursula.nickname),
                        'nickname_icon': self.ursula.nickname.icon,
                        'fleet_state': str(self.ursula.known_nodes.checksum),
                        'known_nodes': str(len(self.ursula.known_nodes))
                        }

        self.metrics["learning_status"].state('running' if self.ursula._learning_task.running else 'stopped')
        self.metrics["known_nodes_gauge"].set(len(self.ursula.known_nodes))
        if self.ursula._availability_tracker and self.ursula._availability_tracker.running:
            self.metrics["availability_score_gauge"].set(self.ursula._availability_tracker.score)
        else:
            self.metrics["availability_score_gauge"].set(-1)

        # TODO (#2797): for now we leave a terminology discrepancy here, for backward compatibility reasons.
        # Update "work orders" to "reencryption requests" when possible.
        reencryption_requests = get_reencryption_requests(self.ursula.datastore)
        self.metrics["work_orders_gauge"].set(len(reencryption_requests))

        if not self.ursula.federated_only:
            application_agent = ContractAgency.get_agent(PREApplicationAgent, registry=self.ursula.registry)
            authorized = application_agent.get_authorized_stake(staking_provider=self.ursula.checksum_address)
            decentralized_payload = {'provider': str(self.ursula.eth_provider_uri),
                                     'active_stake': str(authorized)}
            base_payload.update(decentralized_payload)

            # TODO: Arrangements are deprecated and Policies are no longer trackable by arrangement storage.
            # policy_arrangements = get_policy_arrangements(self.ursula.datastore)
            # self.metrics["policies_held_gauge"].set(len(policy_arrangements))

        self.metrics["host_info"].info(base_payload)


class BlockchainMetricsCollector(BaseMetricsCollector):
    """Collector for Blockchain specific metrics."""
    def __init__(self, eth_provider_uri: str):
        super().__init__()
        self.eth_provider_uri = eth_provider_uri

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry) -> None:
        self.metrics = {
            "current_eth_block_number": Gauge(f'{metrics_prefix}_current_eth_block_number',
                                              'Current Ethereum block',
                                              registry=registry),
        }

    def _collect_internal(self) -> None:
        blockchain = BlockchainInterfaceFactory.get_or_create_interface(eth_provider_uri=self.eth_provider_uri)
        self.metrics["current_eth_block_number"].set(blockchain.client.block_number)


class StakerMetricsCollector(BaseMetricsCollector):
    """Collector for Staker specific metrics."""
    def __init__(self, domain: str, staker_address: ChecksumAddress, contract_registry: BaseContractRegistry):
        super().__init__()
        self.domain = domain
        self.staker_address = staker_address
        self.contract_registry = contract_registry

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry) -> None:
        self.metrics = {
            "current_period_gauge": Gauge(f'{metrics_prefix}_current_period', 'Current period', registry=registry),
            "eth_balance_gauge": Gauge(f'{metrics_prefix}_staker_eth_balance', 'Ethereum balance', registry=registry),
            "token_balance_gauge": Gauge(f'{metrics_prefix}_staker_token_balance', 'NlkUNit balance', registry=registry),
            "substakes_count_gauge": Gauge(f'{metrics_prefix}_substakes_count', 'Substakes count', registry=registry),
            "active_stake_gauge": Gauge(f'{metrics_prefix}_active_stake', 'Active stake', registry=registry),
            "unlocked_tokens_gauge": Gauge(f'{metrics_prefix}_unlocked_tokens',
                                           'Amount of unlocked tokens',
                                           registry=registry),
            "owned_tokens_gauge": Gauge(f'{metrics_prefix}_owned_tokens',
                                        'All tokens that belong to the staker, including '
                                        'locked, unlocked and rewards',
                                        registry=registry),
        }

    def _collect_internal(self) -> None:
        staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=self.contract_registry)

        # current period
        self.metrics["current_period_gauge"].set(staking_agent.get_current_period())

        # balances
        nulink_token_actor = NulinkTokenActor(registry=self.contract_registry,
                                                  domain=self.domain,
                                                  checksum_address=self.staker_address)
        self.metrics["eth_balance_gauge"].set(nulink_token_actor.eth_balance)
        self.metrics["token_balance_gauge"].set(int(nulink_token_actor.token_balance))

        # stake information
        self.metrics["substakes_count_gauge"].set(
            staking_agent.contract.functions.getSubStakesLength(self.staker_address).call())

        locked = staking_agent.get_locked_tokens(staker_address=self.staker_address, periods=1)
        self.metrics["active_stake_gauge"].set(locked)

        owned_tokens = staking_agent.owned_tokens(self.staker_address)
        unlocked_tokens = owned_tokens - locked
        self.metrics["unlocked_tokens_gauge"].set(unlocked_tokens)
        self.metrics["owned_tokens_gauge"].set(owned_tokens)


class OperatorMetricsCollector(BaseMetricsCollector):
    """Collector for Operator specific metrics."""
    def __init__(self, domain: str, operator_address: ChecksumAddress, contract_registry: BaseContractRegistry):
        super().__init__()
        self.domain = domain
        self.operator_address = operator_address
        self.contract_registry = contract_registry

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry) -> None:
        self.metrics = {
            "worker_eth_balance_gauge": Gauge(f'{metrics_prefix}_worker_eth_balance',
                                              'Operator Ethereum balance',
                                              registry=registry),
            "worker_token_balance_gauge": Gauge(f'{metrics_prefix}_worker_token_balance',
                                                'Operator NlkUNit balance',
                                                registry=registry),
        }

    def _collect_internal(self) -> None:
        nulink_worker_token_actor = NulinkTokenActor(registry=self.contract_registry,
                                                         domain=self.domain,
                                                         checksum_address=self.operator_address)
        self.metrics["worker_eth_balance_gauge"].set(nulink_worker_token_actor.eth_balance)
        self.metrics["worker_token_balance_gauge"].set(int(nulink_worker_token_actor.token_balance))


class EventMetricsCollector(BaseMetricsCollector):
    """General collector for emitted events."""
    def __init__(self,
                 event_name: str,
                 event_args_config: Dict[str, tuple],
                 argument_filters: Dict[str, str],
                 contract_agent_class: Type[EthereumContractAgent],
                 contract_registry: BaseContractRegistry):
        super().__init__()
        self.event_name = event_name
        self.contract_agent_class = contract_agent_class
        self.contract_registry = contract_registry

        contract_agent = ContractAgency.get_agent(self.contract_agent_class, registry=self.contract_registry)
        # this way we don't have to deal with 'latest' at all
        self.filter_current_from_block = contract_agent.blockchain.client.block_number
        self.filter_arguments = argument_filters
        self.event_args_config = event_args_config

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry) -> None:
        self.metrics = dict()
        for arg_name in self.event_args_config:
            metric_class, metric_name, metric_doc = self.event_args_config[arg_name]
            metric_key = self._get_arg_metric_key(arg_name)
            self.metrics[metric_key] = metric_class(metric_name, metric_doc, registry=registry)

    def _collect_internal(self) -> None:
        contract_agent = ContractAgency.get_agent(self.contract_agent_class, registry=self.contract_registry)
        from_block = self.filter_current_from_block
        to_block = contract_agent.blockchain.client.block_number
        if from_block >= to_block:
            # we've already checked the latest block and waiting for a new block
            # nothing to see here
            return

        # update last block checked for the next round - from/to block range is inclusive
        # increment before potentially long running execution to improve concurrency handling
        self.filter_current_from_block = to_block + 1

        events_throttler = ContractEventsThrottler(agent=contract_agent,
                                                   event_name=self.event_name,
                                                   from_block=from_block,
                                                   to_block=to_block,
                                                   **self.filter_arguments)
        for event_record in events_throttler:
            self._event_occurred(event_record.raw_event)

    def _event_occurred(self, event) -> None:
        for arg_name in self.event_args_config:
            metric_key = self._get_arg_metric_key(arg_name)
            if arg_name == "block_number":
                self.metrics[metric_key].set(event["blockNumber"])
                continue
            self.metrics[metric_key].set(event['args'][arg_name])

    def _get_arg_metric_key(self, arg_name: str):
        return f'{self.event_name}_{arg_name}'


class CommitmentMadeEventMetricsCollector(EventMetricsCollector):
    """Collector for CommitmentMade event."""
    def __init__(self, staker_address: ChecksumAddress, event_name: str = 'CommitmentMade', *args, **kwargs):
        super().__init__(event_name=event_name, argument_filters={'staker': staker_address}, *args, **kwargs)
        self.staker_address = staker_address

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry) -> None:
        super().initialize(metrics_prefix=metrics_prefix, registry=registry)


class ReStakeEventMetricsCollector(EventMetricsCollector):
    """Collector for RestakeSet event."""
    def __init__(self, staker_address: ChecksumAddress, event_name: str = 'ReStakeSet', *args, **kwargs):
        super().__init__(event_name=event_name, argument_filters={'staker': staker_address}, *args, **kwargs)
        self.staker_address = staker_address

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry) -> None:
        super().initialize(metrics_prefix=metrics_prefix, registry=registry)
        contract_agent = ContractAgency.get_agent(self.contract_agent_class, registry=self.contract_registry)
        metric_key = self._get_arg_metric_key("reStake")
        self.metrics[metric_key].set(contract_agent.is_restaking(self.staker_address))


class WindDownEventMetricsCollector(EventMetricsCollector):
    """Collector for WindDownSet event."""
    def __init__(self, staker_address: ChecksumAddress, event_name: str = 'WindDownSet', *args, **kwargs):
        super().__init__(event_name=event_name, argument_filters={'staker': staker_address}, *args, **kwargs)
        self.staker_address = staker_address

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry) -> None:
        super().initialize(metrics_prefix=metrics_prefix, registry=registry)
        contract_agent = ContractAgency.get_agent(self.contract_agent_class, registry=self.contract_registry)
        metric_key = self._get_arg_metric_key("windDown")
        self.metrics[metric_key].set(contract_agent.is_winding_down(self.staker_address))


class OperatorBondedEventMetricsCollector(EventMetricsCollector):
    """Collector for OperatorBonded event."""
    def __init__(self,
                 staker_address: ChecksumAddress,
                 operator_address: ChecksumAddress,
                 event_name: str = 'OperatorBonded',
                 *args,
                 **kwargs):
        super().__init__(event_name=event_name, argument_filters={'staker': staker_address}, *args, **kwargs)
        self.staker_address = staker_address
        self.operator_address = operator_address

    def initialize(self, metrics_prefix: str, registry: CollectorRegistry) -> None:
        super().initialize(metrics_prefix=metrics_prefix, registry=registry)
        contract_agent = ContractAgency.get_agent(self.contract_agent_class, registry=self.contract_registry)
        self.metrics["current_worker_is_me_gauge"] = Gauge(f'{metrics_prefix}_current_worker_is_me',
                                                           'Current worker is me',
                                                           registry=registry)

        # set initial value
        self.metrics["current_worker_is_me_gauge"].set(
            contract_agent.get_worker_from_staker(self.staker_address) == self.operator_address)

    def _event_occurred(self, event) -> None:
        super()._event_occurred(event)
        contract_agent = ContractAgency.get_agent(self.contract_agent_class, registry=self.contract_registry)
        self.metrics["current_worker_is_me_gauge"].set(
            contract_agent.get_worker_from_staker(self.staker_address) == self.operator_address)
