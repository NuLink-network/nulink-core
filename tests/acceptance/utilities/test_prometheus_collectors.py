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
from typing import List
from unittest.mock import patch

import pytest

from nulink.blockchain.eth.signers.software import Web3Signer
from nulink.crypto.powers import TransactingPower
from tests.constants import TEST_ETH_PROVIDER_URI
from tests.utils.blockchain import TesterBlockchain

try:
    # all prometheus related imports
    from prometheus_client import CollectorRegistry

    # include dependencies that have sub-dependencies on prometheus
    from nulink.utilities.prometheus.collector import (
        UrsulaInfoMetricsCollector,
        BlockchainMetricsCollector,
        StakerMetricsCollector,
        OperatorMetricsCollector,
        MetricsCollector
    )
    from nulink.utilities.prometheus.metrics import create_staking_events_metric_collectors, create_metrics_collectors

    # flag to skip tests
    PROMETHEUS_INSTALLED = True
except ImportError:
    PROMETHEUS_INSTALLED = False


@pytest.mark.skipif(condition=(not PROMETHEUS_INSTALLED), reason="prometheus_client is required for test")
def test_ursula_info_metrics_collector(test_registry,
                                       blockchain_ursulas,
                                       agency):
    ursula = random.choice(blockchain_ursulas)
    collector = UrsulaInfoMetricsCollector(ursula=ursula)

    collector_registry = CollectorRegistry()
    prefix = 'test_ursula_info_metrics_collector'
    collector.initialize(metrics_prefix=prefix, registry=collector_registry)
    collector.collect()

    known_nodes = collector_registry.get_sample_value('test_ursula_info_metrics_collector_known_nodes')
    assert known_nodes == len(ursula.known_nodes)

    availability_score = collector_registry.get_sample_value('test_ursula_info_metrics_collector_availability_score')
    assert availability_score == (ursula._availability_tracker.score
                                  if (ursula._availability_tracker and ursula._availability_tracker.running) else -1)

    policies_held = collector_registry.get_sample_value('test_ursula_info_metrics_collector_policies_held')
    assert policies_held == 0

    work_orders = collector_registry.get_sample_value('test_ursula_info_metrics_collector_work_orders')
    assert work_orders == 0

    mode = 'running' if ursula._learning_task.running else 'stopped'
    learning_mode = collector_registry.get_sample_value('test_ursula_info_metrics_collector_node_discovery',
                                                        labels={'test_ursula_info_metrics_collector_node_discovery': f'{mode}'})
    assert learning_mode == 1


@pytest.mark.skipif(condition=(not PROMETHEUS_INSTALLED), reason="prometheus_client is required for test")
def test_blockchain_metrics_collector(testerchain):
    collector = BlockchainMetricsCollector(eth_provider_uri=TEST_ETH_PROVIDER_URI)

    collector_registry = CollectorRegistry()
    prefix = 'test_blockchain_metrics_collector'
    collector.initialize(metrics_prefix=prefix, registry=collector_registry)
    collector.collect()

    metric_name = f"{prefix}_current_eth_block_number"
    assert metric_name in collector_registry._names_to_collectors.keys()

    block_number = collector_registry.get_sample_value(metric_name)
    assert block_number == testerchain.get_block_number()


@pytest.mark.skip()
@pytest.mark.skipif(condition=(not PROMETHEUS_INSTALLED), reason="prometheus_client is required for test")
def test_staker_metrics_collector(test_registry, staking_providers):
    staker = random.choice(staking_providers)
    collector = StakerMetricsCollector(domain=staker.network,
                                       staker_address=staker.checksum_address,
                                       contract_registry=test_registry)
    collector_registry = CollectorRegistry()
    prefix = 'test_staker_metrics_collector'
    collector.initialize(metrics_prefix=prefix, registry=collector_registry)
    collector.collect()

    current_period = collector_registry.get_sample_value(f'{prefix}_current_period')
    assert current_period == staker.application_agent.get_current_period()

    # only floats can be stored
    eth_balance = collector_registry.get_sample_value(f'{prefix}_staker_eth_balance')
    assert eth_balance == float(staker.eth_balance)

    nu_balance = collector_registry.get_sample_value(f'{prefix}_staker_token_balance')
    assert nu_balance == float(int(staker.token_balance))

    sub_stakes_count = collector_registry.get_sample_value(f'{prefix}_substakes_count')
    assert sub_stakes_count == \
           staker.application_agent.contract.functions.getSubStakesLength(staker.checksum_address).call()

    locked_tokens = collector_registry.get_sample_value(f'{prefix}_active_stake')
    assert locked_tokens == float(staker.locked_tokens().to_units())

    owned_tokens = collector_registry.get_sample_value(f'{prefix}_owned_tokens')
    assert owned_tokens == float(staker.owned_tokens().to_units())

    unlocked_tokens = collector_registry.get_sample_value(f'{prefix}_unlocked_tokens')
    assert unlocked_tokens == (owned_tokens - locked_tokens)

    missing_commitments = collector_registry.get_sample_value(f'{prefix}_missing_commitments')
    assert missing_commitments == staker.missing_commitments


@pytest.mark.skip()
@pytest.mark.skipif(condition=(not PROMETHEUS_INSTALLED), reason="prometheus_client is required for test")
def test_worker_metrics_collector(test_registry, blockchain_ursulas):
    ursula = random.choice(blockchain_ursulas)
    collector = OperatorMetricsCollector(domain=ursula.domain,
                                       operator_address=ursula.operator_address,
                                       contract_registry=test_registry)
    collector_registry = CollectorRegistry()
    prefix = 'test_worker_metrics_collector'
    collector.initialize(metrics_prefix=prefix, registry=collector_registry)
    collector.collect()

    worker_eth = collector_registry.get_sample_value(f'{prefix}_worker_eth_balance')
    assert worker_eth == float(ursula.eth_balance)

    worker_nlkunits = collector_registry.get_sample_value(f'{prefix}_worker_token_balance')
    assert worker_nlkunits == float(int(ursula.token_balance))


@pytest.mark.skip()
@pytest.mark.skipif(condition=(not PROMETHEUS_INSTALLED), reason="prometheus_client is required for test")
def test_staking_events_metric_collectors(testerchain, blockchain_ursulas):
    ursula = random.choice(blockchain_ursulas)

    collector_registry = CollectorRegistry()
    prefix = 'test_staking_events_metric_collectors'

    event_collectors = create_staking_events_metric_collectors(ursula=ursula, metrics_prefix=prefix)
    initialize_collectors(metrics_collectors=event_collectors,
                          testerchain=testerchain,
                          collector_registry=collector_registry,
                          prefix=prefix)

    # Since collectors only initialized, check base state i.e. current values
    # Restake
    restake_set = collector_registry.get_sample_value(f'{prefix}_restaking')
    assert restake_set == ursula.application_agent.is_restaking(ursula.checksum_address)

    # WindDown
    windown_set = collector_registry.get_sample_value(f'{prefix}_wind_down')
    assert windown_set == ursula.application_agent.is_winding_down(ursula.checksum_address)

    # Operator
    current_worker_is_me = collector_registry.get_sample_value(f'{prefix}_current_worker_is_me')
    assert current_worker_is_me == \
           (ursula.application_agent.get_worker_from_staker(ursula.checksum_address) == ursula.operator_address)

    staker_power = TransactingPower(account=ursula.checksum_address, signer=Web3Signer(testerchain.client))

    #
    # Update some values
    #

    # Change Restake
    ursula.application_agent.set_restaking(staker_power, not bool(restake_set))

    # Change WindingDown
    ursula.application_agent.set_winding_down(staker_power, not bool(windown_set))

    # Subsequent commit to next period
    testerchain.time_travel(periods=1)
    worker_power = TransactingPower(account=ursula.operator_address, signer=Web3Signer(testerchain.client))
    ursula.application_agent.commit_to_next_period(transacting_power=worker_power)
    period_committed_to = ursula.application_agent.get_current_period() + 1

    # Mint
    testerchain.time_travel(periods=2)
    _receipt = ursula.application_agent.mint(transacting_power=staker_power)
    minted_block_number = testerchain.get_block_number()
    minted_period = ursula.application_agent.get_current_period() - 1  # mint is for the previous period

    testerchain.time_travel(periods=1)

    # Force update of metrics collection
    for collector in event_collectors:
        collector.collect()

    #
    # Check updated values
    #

    updated_restake_set = collector_registry.get_sample_value(f'{prefix}_restaking')
    assert updated_restake_set == ursula.application_agent.is_restaking(ursula.checksum_address)
    assert updated_restake_set != restake_set

    updated_windown_set = collector_registry.get_sample_value(f'{prefix}_wind_down')
    assert updated_windown_set == ursula.application_agent.is_winding_down(ursula.checksum_address)
    assert updated_windown_set != windown_set

    committed_event_period = collector_registry.get_sample_value(f'{prefix}_activity_confirmed_period')
    assert committed_event_period == period_committed_to

    minted_event_period = collector_registry.get_sample_value(f'{prefix}_mined_period')
    minted_event_block_number = collector_registry.get_sample_value(f'{prefix}_mined_block_number')
    assert minted_event_period == minted_period
    assert minted_event_block_number == minted_block_number


@pytest.mark.skip()
@pytest.mark.skipif(condition=(not PROMETHEUS_INSTALLED), reason="prometheus_client is required for test")
def test_all_metrics_collectors_sanity_collect(testerchain, blockchain_ursulas):
    ursula = random.choice(blockchain_ursulas)

    collector_registry = CollectorRegistry()
    prefix = 'test_all_metrics_collectors'

    metrics_collectors = create_metrics_collectors(ursula=ursula, metrics_prefix=prefix)
    initialize_collectors(metrics_collectors=metrics_collectors,
                          testerchain=testerchain,
                          collector_registry=collector_registry,
                          prefix=prefix)

    for collector in metrics_collectors:
        collector.collect()


def initialize_collectors(metrics_collectors: List['MetricsCollector'],
                          testerchain: TesterBlockchain,
                          collector_registry: 'CollectorRegistry',
                          prefix: str) -> None:
    with patch('nulink.utilities.prometheus.collector.estimate_block_number_for_period',
               autospec=True,
               return_value=testerchain.get_block_number()):
        # patch for initial block number used by CommitmentMadeEventMetricsCollector
        for collector in metrics_collectors:
            collector.initialize(metrics_prefix=prefix, registry=collector_registry)
