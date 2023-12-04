"""
 This file is part of nulink.

 nulink is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nulink is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nulink.  If not, see <https://www.gnu.org/licenses/>.
"""
from decimal import Decimal
from pathlib import Path

import click
from web3 import Web3
from web3.datastructures import AttributeDict

from nulink.blockchain.eth.actors import StakeHolder
from nulink.blockchain.eth.constants import MAX_UINT16
from nulink.blockchain.eth.interfaces import BlockchainInterface, BlockchainInterfaceFactory
from nulink.blockchain.eth.signers import TrezorSigner
from nulink.blockchain.eth.signers.software import ClefSigner
from nulink.blockchain.eth.utils import datetime_at_period
from nulink.cli.actions.auth import get_client_password
from nulink.cli.actions.configure import get_or_update_configuration, handle_missing_configuration_file
from nulink.cli.actions.select import select_client_account_for_staking

from nulink.cli.config import group_general_config, GroupGeneralConfig
from nulink.cli.literature import (
    BONDING_DETAILS,
    BONDING_RELEASE_INFO,
    COLLECTING_ETH_FEE,
    COLLECTING_TOKEN_REWARD,
    DETACH_DETAILS,
    SUCCESSFUL_NEW_STAKEHOLDER_CONFIG,
    NO_TOKENS_TO_WITHDRAW,
    NO_FEE_TO_WITHDRAW, PROMPT_STAKE_CREATE_VALUE, INSUFFICIENT_BALANCE_TO_CREATE, STAKE_VALUE_GREATER_THAN_BALANCE_TO_CREATE,
)
from nulink.cli.options import (
    group_options,
    option_config_file,
    option_config_root,
    option_event_name,
    option_force,
    option_hw_wallet,
    option_light,
    option_network,
    option_poa,
    option_provider_uri,
    option_registry_filepath,
    option_signer_uri,
    option_staking_address,
    option_gas_price
)
from nulink.cli.painting.staking import paint_staking_confirmation, paint_approve_confirmation

from nulink.cli.painting.transactions import paint_receipt_summary
from nulink.cli.types import (
    DecimalRange,
    EIP55_CHECKSUM_ADDRESS,
    GWEI
)
from nulink.cli.utils import retrieve_events, setup_emitter
from nulink.config.characters import StakeHolderConfiguration
from nulink.config.constants import NULINK_ENVVAR_STAKING_PROVIDER_ETH_PASSWORD
from nulink.types import NLKWei
from nulink.utilities.gas_strategies import construct_fixed_price_gas_strategy

option_signer_uri = click.option('--signer', 'signer_uri', '-S', default=None, type=str)
option_value = click.option('--value', help="Token value of stake", type=DecimalRange(min=0))
option_worker_address = click.option('--worker-address', help="Address to bond as an Ursula-Worker", type=EIP55_CHECKSUM_ADDRESS)


class StakeHolderConfigOptions:
    __option_name__ = 'config_options'

    def __init__(self, provider_uri, poa, light, registry_filepath, network, signer_uri):
        self.provider_uri = provider_uri
        self.signer_uri = signer_uri
        self.poa = poa
        self.light = light
        self.registry_filepath = registry_filepath
        self.network = network

    def retrieve_config(self, emitter, config_file):
        try:
            return StakeHolderConfiguration.from_configuration_file(
                emitter=emitter,
                filepath=config_file,
                provider_uri=self.provider_uri,
                signer_uri=self.signer_uri,
                poa=self.poa,
                light=self.light,
                domain=self.network,
                registry_filepath=self.registry_filepath)

        except FileNotFoundError:
            return handle_missing_configuration_file(
                character_config_class=StakeHolderConfiguration,
                init_command_hint=f"{stake.name} {init_stakeholder.name}",
                config_file=config_file)

    def generate_config(self, config_root):

        if self.provider_uri is None:
            raise click.BadOptionUsage(
                option_name="--provider",
                message="--provider must be specified to create a new stakeholder")

        if self.network is None:
            raise click.BadOptionUsage(
                option_name="--network",
                message="--network must be specified to create a new stakeholder")

        return StakeHolderConfiguration.generate(
            config_root=config_root,
            provider_uri=self.provider_uri,
            signer_uri=self.signer_uri,
            poa=self.poa,
            light=self.light,
            registry_filepath=self.registry_filepath,
            domain=self.network
        )

    def get_updates(self) -> dict:
        payload = dict(provider_uri=self.provider_uri,
                       signer_uri=self.signer_uri,
                       poa=self.poa,
                       light=self.light,
                       registry_filepath=self.registry_filepath,
                       domain=self.network)
        # Depends on defaults being set on Configuration classes, filtrates None values
        updates = {k: v for k, v in payload.items() if v is not None}
        return updates


group_config_options = group_options(
    StakeHolderConfigOptions,
    provider_uri=option_provider_uri(),
    poa=option_poa,
    light=option_light,
    registry_filepath=option_registry_filepath,
    network=option_network(),
    signer_uri=option_signer_uri
)


class StakerOptions:
    __option_name__ = 'staker_options'

    def __init__(self, config_options: StakeHolderConfigOptions, staking_address: str):
        self.config_options = config_options
        self.staking_address = staking_address

    def create_character(self, emitter, config_file, initial_address=None, *args, **kwargs):
        stakeholder_config = self.config_options.retrieve_config(emitter, config_file)
        if initial_address is None:
            initial_address = self.staking_address
        stakeholder: StakeHolder = stakeholder_config.produce(initial_address=initial_address, *args, **kwargs)
        self.config_options.provider_uri = stakeholder_config.eth_provider_uri
        self.config_options.network = stakeholder_config.domain
        self.config_options.poa = stakeholder_config.poa
        self.config_options.light = stakeholder_config.is_light
        self.config_options.registry_filepath = stakeholder_config.registry_filepath
        self.config_options.signer_uri = stakeholder_config.signer_uri
        return stakeholder

    def get_blockchain(self):
        return BlockchainInterfaceFactory.get_interface(eth_provider_uri=self.config_options.provider_uri)  # Eager connection


group_staker_options = group_options(
    StakerOptions,
    config_options=group_config_options,
    staking_address=option_staking_address,
)


class TransactingStakerOptions:
    __option_name__ = 'transacting_staker_options'

    def __init__(self, staker_options: StakerOptions, hw_wallet, gas_price):
        self.staker_options = staker_options
        self.hw_wallet = hw_wallet
        self.gas_price = gas_price

    def create_character(self, emitter, config_file):
        opts = self.staker_options
        stakeholder_config = opts.config_options.retrieve_config(emitter, config_file)  # TODO
        return opts.create_character(emitter=emitter, config_file=config_file)

    def get_blockchain(self):
        # andi: blockchain is BlockchainInterface
        blockchain = self.staker_options.get_blockchain()
        if self.gas_price:  # TODO: Consider performing this step in the init of EthereumClient
            fixed_price_strategy = construct_fixed_price_gas_strategy(gas_price=self.gas_price, denomination="gwei")
            blockchain.configure_gas_strategy(fixed_price_strategy)
        return blockchain


group_transacting_staker_options = group_options(
    TransactingStakerOptions,
    staker_options=group_staker_options,
    hw_wallet=option_hw_wallet,
    gas_price=option_gas_price,
)


def get_password(stakeholder: StakeHolder,
                 blockchain: BlockchainInterface,
                 client_account: str,
                 hw_wallet: bool = False):
    signer_handles_passwords = isinstance(stakeholder.signer, (ClefSigner, TrezorSigner))
    eth_password_needed = not hw_wallet and not blockchain.client.is_local and not signer_handles_passwords
    password = None
    if eth_password_needed:
        password = get_client_password(checksum_address=client_account, envvar=NULINK_ENVVAR_STAKING_PROVIDER_ETH_PASSWORD)
    return password


@click.group()
def stake():
    """Manage stakes operations."""


@stake.command(name='init')
@option_config_root
@option_force
@group_config_options
@group_general_config
def init_stakeholder(general_config, config_root, force, config_options):
    """Create a new stakeholder configuration."""
    emitter = setup_emitter(general_config)

    new_stakeholder: StakeHolderConfiguration = config_options.generate_config(config_root)
    filepath = new_stakeholder.to_configuration_file(override=force)
    emitter.echo(SUCCESSFUL_NEW_STAKEHOLDER_CONFIG.format(filepath=filepath), color='green')


@stake.command()
@group_transacting_staker_options
@option_config_file
@option_force
@option_value
@group_general_config
def create(general_config: GroupGeneralConfig,
           transacting_staker_options: TransactingStakerOptions,
           config_file, force, value):
    """Initialize a new stake."""

    # Setup
    emitter = setup_emitter(general_config)
    # stakholder is StakeHolder
    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()

    client_account, staking_address = select_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address)

    # Authenticate
    password = get_password(stakeholder=STAKEHOLDER,
                            blockchain=blockchain,
                            client_account=client_account,
                            hw_wallet=transacting_staker_options.hw_wallet)
    STAKEHOLDER.assimilate(checksum_address=staking_address, password=password)

    #
    # Stage Stake
    #

    min_stake_amount = STAKEHOLDER.staker.get_min_stake_amount()
    max_stake_amount = STAKEHOLDER.staker.get_min_stake_amount()
    token_balance = STAKEHOLDER.staker.token_balance

    stake_value_range = DecimalRange(min=min_stake_amount, max=max_stake_amount, clamp=False)

    if not value or not (value >= min_stake_amount and value <= max_stake_amount):
        value = click.prompt(PROMPT_STAKE_CREATE_VALUE.format(lower_limit=min_stake_amount, upper_limit=max_stake_amount),
                             type=stake_value_range,
                             default=max_stake_amount)

    if token_balance < min_stake_amount:
        emitter.echo(INSUFFICIENT_BALANCE_TO_CREATE, color='red')
        raise click.Abort

    if value > token_balance:
        emitter.echo(STAKE_VALUE_GREATER_THAN_BALANCE_TO_CREATE.format(value=value, balance=token_balance), color='red')
        raise click.Abort

    #
    # Review and Publish
    #
    value = int(value)

    approve_threshold = 100000000000000000000000000  # don't use the float value: 1e28: Value comparison error

    approve_value = int(value if value > approve_threshold else approve_threshold)

    receipt_approve = STAKEHOLDER.staker.approve_if_need(amount=int(approve_value))

    if isinstance(receipt_approve, (dict, AttributeDict)):  # (dict, TxReceipt) TypeError: TypedDict does not support instance and class checks
        paint_approve_confirmation(emitter=emitter, staker=STAKEHOLDER.staker, receipt=receipt_approve)

    # Execute
    receipt = STAKEHOLDER.staker.stake(staking_address, int(value), int(transacting_staker_options.gas_price))
    paint_staking_confirmation(emitter=emitter, staker=STAKEHOLDER.staker, receipt=receipt)


@stake.command('bond-worker')
@group_transacting_staker_options
@option_config_file
@option_force
@group_general_config
# @option_worker_address
def bond_worker(general_config: GroupGeneralConfig,
                transacting_staker_options: TransactingStakerOptions,
                config_file, force, worker_address):
    """Bond a worker to a staker."""

    emitter = setup_emitter(general_config)
    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()

    client_account, staking_address = select_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address)

    password = get_password(stakeholder=STAKEHOLDER,
                            blockchain=blockchain,
                            client_account=client_account,
                            hw_wallet=transacting_staker_options.hw_wallet)
    STAKEHOLDER.assimilate(checksum_address=client_account, password=password)
    economics = STAKEHOLDER.staker.economics

    if not worker_address:
        worker_address = click.prompt(PROMPT_WORKER_ADDRESS, type=EIP55_CHECKSUM_ADDRESS)

    if (worker_address == staking_address) and not force:
        click.confirm(CONFIRM_WORKER_AND_STAKER_ADDRESSES_ARE_EQUAL.format(address=worker_address), abort=True)

    # TODO: Check preconditions (e.g., minWorkerPeriods, already in use, etc)

    # TODO: Double-check dates
    # Calculate release datetime
    current_period = STAKEHOLDER.staker.staking_agent.get_current_period()
    bonded_date = datetime_at_period(period=current_period, seconds_per_period=economics.seconds_per_period)
    min_worker_periods = STAKEHOLDER.staker.economics.minimum_worker_periods

    release_period = current_period + min_worker_periods
    release_date = datetime_at_period(period=release_period,
                                      seconds_per_period=economics.seconds_per_period,
                                      start_of_period=True)

    if not force:
        click.confirm(f"Commit to bonding "
                      f"worker {worker_address} to staker {staking_address} "
                      f"for a minimum of {STAKEHOLDER.staker.economics.minimum_worker_periods} periods?", abort=True)

    receipt = STAKEHOLDER.staker.bond_worker(worker_address=worker_address)

    # Report Success
    message = SUCCESSFUL_WORKER_BONDING.format(worker_address=worker_address, staking_address=staking_address)
    emitter.echo(message, color='green')
    paint_receipt_summary(emitter=emitter,
                          receipt=receipt,
                          chain_name=blockchain.client.chain_name,
                          transaction_type='bond_worker')
    emitter.echo(BONDING_DETAILS.format(current_period=current_period, bonded_date=bonded_date), color='green')
    emitter.echo(BONDING_RELEASE_INFO.format(release_period=release_period, release_date=release_date), color='green')


@stake.command('unbond-worker')
@group_transacting_staker_options
@option_config_file
@option_force
@group_general_config
def unbond_worker(general_config: GroupGeneralConfig,
                  transacting_staker_options: TransactingStakerOptions,
                  config_file, force):
    """
    Unbond worker currently bonded to a staker.
    """
    emitter = setup_emitter(general_config)

    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()

    client_account, staking_address = select_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address)

    # TODO: Check preconditions (e.g., minWorkerPeriods)
    worker_address = STAKEHOLDER.staker.staking_agent.get_worker_from_staker(staking_address)

    password = get_password(stakeholder=STAKEHOLDER,
                            blockchain=blockchain,
                            client_account=client_account,
                            hw_wallet=transacting_staker_options.hw_wallet)

    if not force:
        click.confirm("Are you sure you want to unbond your worker?", abort=True)

    STAKEHOLDER.assimilate(checksum_address=client_account, password=password)
    economics = STAKEHOLDER.staker.economics
    receipt = STAKEHOLDER.staker.unbond_worker()

    # TODO: Double-check dates
    current_period = STAKEHOLDER.staker.staking_agent.get_current_period()
    bonded_date = datetime_at_period(period=current_period, seconds_per_period=economics.seconds_per_period)

    message = SUCCESSFUL_DETACH_WORKER.format(worker_address=worker_address, staking_address=staking_address)
    emitter.echo(message, color='green')
    paint_receipt_summary(emitter=emitter,
                          receipt=receipt,
                          chain_name=blockchain.client.chain_name,
                          transaction_type='unbond_worker')
    emitter.echo(DETACH_DETAILS.format(current_period=current_period, bonded_date=bonded_date), color='green')


@stake.group()
def rewards():
    """Manage staking rewards."""


@rewards.command('show')
@group_staker_options
@option_config_file
@group_general_config
@click.option('--periods', help="Number of past periods for which to calculate rewards", type=click.INT)
def show_rewards(general_config, staker_options, config_file, periods):
    """Show staking rewards."""

    if periods and periods < 0:
        raise click.BadOptionUsage(option_name='--periods', message='--periods must positive')

    emitter = setup_emitter(general_config)
    stakeholder = staker_options.create_character(emitter, config_file)
    _client_account, staking_address = select_client_account_for_staking(emitter=emitter,
                                                                         stakeholder=stakeholder,
                                                                         staking_address=staker_options.staking_address)
    blockchain = staker_options.get_blockchain()
    staking_agent = stakeholder.staker.staking_agent

    paint_staking_rewards(stakeholder, blockchain, emitter, periods, staking_address, staking_agent)


@rewards.command('withdraw')
@group_transacting_staker_options
@option_config_file
@click.option('--replace', help="Replace any existing pending transaction", is_flag=True)
@click.option('--tokens/--no-tokens', help="Enable/disable tokens withdrawal. Defaults to `--no-tokens`", is_flag=True,
              default=False)
@click.option('--fees/--no-fees', help="Enable/disable fees withdrawal. Defaults to `--no-fees`", is_flag=True,
              default=False)
@click.option('--withdraw-address', help="Send fee collection to an alternate address", type=EIP55_CHECKSUM_ADDRESS)
@option_force
@group_general_config
def withdraw_rewards(general_config: GroupGeneralConfig,
                     transacting_staker_options: TransactingStakerOptions,
                     config_file,
                     tokens,
                     fees,
                     withdraw_address,
                     replace,
                     force):
    """Withdraw staking rewards."""

    # Setup
    emitter = setup_emitter(general_config)
    STAKEHOLDER = transacting_staker_options.create_character(emitter, config_file)
    blockchain = transacting_staker_options.get_blockchain()

    if not tokens and not fees:
        raise click.BadArgumentUsage(f"Either --tokens or --fees must be True to collect rewards.")

    client_account, staking_address = select_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=transacting_staker_options.staker_options.staking_address)

    password = None

    if tokens:
        # Note: Sending staking / inflation rewards to another account is not allowed.
        reward_amount = STAKEHOLDER.staker.calculate_staking_reward()
        if reward_amount == 0:
            emitter.echo(NO_TOKENS_TO_WITHDRAW, color='red')
            raise click.Abort

        emitter.echo(message=COLLECTING_TOKEN_REWARD.format(reward_amount=reward_amount))

        withdrawing_last_portion = STAKEHOLDER.staker.non_withdrawable_stake() == 0
        if not force and withdrawing_last_portion and STAKEHOLDER.staker.mintable_periods() > 0:
            click.confirm(CONFIRM_COLLECTING_WITHOUT_MINTING, abort=True)

        # Authenticate and Execute
        password = get_password(stakeholder=STAKEHOLDER,
                                blockchain=blockchain,
                                client_account=client_account,
                                hw_wallet=transacting_staker_options.hw_wallet)
        STAKEHOLDER.assimilate(checksum_address=client_account, password=password)

        staking_receipt = STAKEHOLDER.staker.collect_staking_reward(replace=replace)
        paint_receipt_summary(receipt=staking_receipt,
                              chain_name=blockchain.client.chain_name,
                              emitter=emitter)

    if fees:
        fee_amount = Web3.fromWei(STAKEHOLDER.staker.calculate_policy_fee(), 'ether')
        if fee_amount == 0:
            emitter.echo(NO_FEE_TO_WITHDRAW, color='red')
            raise click.Abort

        emitter.echo(message=COLLECTING_ETH_FEE.format(fee_amount=fee_amount))

        if password is None:
            # Authenticate and Execute
            password = get_password(stakeholder=STAKEHOLDER,
                                    blockchain=blockchain,
                                    client_account=client_account,
                                    hw_wallet=transacting_staker_options.hw_wallet)
            STAKEHOLDER.assimilate(checksum_address=client_account, password=password)

        policy_receipt = STAKEHOLDER.staker.collect_policy_fee(collector_address=withdraw_address)
        paint_receipt_summary(receipt=policy_receipt,
                              chain_name=blockchain.client.chain_name,
                              emitter=emitter)


# add by andi for debug
if __name__ == '__main__':
    # # If the local connection is not connected to the extranet's chain, you need to set the proxy PyCHARM in your code to set the function
    # # https://blog.csdn.net/whatday/article/details/112169945
    # import os
    # os.environ["http_proxy"] = "http://127.0.0.1:7890"
    # os.environ["https_proxy"] = "http://127.0.0.1:7890"

    # Only Windows supports paths. All other systems must start with the network path /, which together is keystore:///
    #
    # init_stakeholder([
    #     #  '--config-root', 'D:\\nulink_data\\',
    #     '--force',
    #     '--debug',
    #     '--signer', 'keystore://D:\\wangyi\\code\\code\\nulink\\dev_docs\\keystore-0xf9ab0b2632783816312a12615cc3e68dda171e28-worker',
    #     # '--signer', 'keystore:///Users/t/data/nulink/keystore' ,
    #     '--provider', 'https://bsc-testnet.blockpi.network/v1/rpc/public',
    #     '--network', 'horus',
    #     # '--registry-filepath', 'D:\\wangyi\\code\\code\\nulink\\nulink-core\\nulink\\blockchain\\eth\\contract_registry\\bsc_testnet\\contract_registry.json',
    # ])

    import os

    os.environ['NULINK_STAKING_PROVIDER_ETH_PASSWORD'] = "qazwsxedc"

    create([
        #  '--config-root', 'D:\\nulink_data\\',
        '--gas-price', '1000000000',
        '--force',
        '--debug',
        '--value', '1000000000000000000',
        # '--registry-filepath', 'D:\\wangyi\\code\\code\\nulink\\nulink-core\\nulink\\blockchain\\eth\\contract_registry\\bsc_testnet\\contract_registry.json',
    ])

    # import os

    #
    # os.environ['NULINK_OPERATOR_ETH_PASSWORD'] = "c2d3f8bdf4"
    # os.environ['NULINK_KEYSTORE_PASSWORD'] = "12345678"  # "NuLink@tH9iym"
    # run([
    #     '--registry-filepath', 'D:\\wangyi\\code\\code\\nulink\\nulink-core\\nulink\\blockchain\\eth\\contract_registry\\bsc_testnet\\contract_registry.json',
    #     '--policy-registry-filepath', 'D:\\wangyi\\code\\code\\nulink\\nulink-core\\nulink\\blockchain\\eth\\contract_registry\\bsc_testnet\\contract_registry.json',
    #     # '--rest-host', '192.168.3.25',
    #     '--rest-port', '9151',
    #     # '--teacher', 'https://8.219.188.70:9151',
    #     '--config-file', 'D:\\nulink_data\\ursula-02fa5003.json',
    #     # '--config-file', "D:\\nulink_data\\ursula-02983e2b.json",
    #     '--db-filepath', 'D:\\nulink_data',
    #     '--debug',
    #     # '--force',
    #     '--no-ip-checkup',
    #     '--no-block-until-ready',
    #     '--console-logs',
    #     '--file-logs',
    # ])
    #
    # """
    # nulink ursula run --teacher 192.168.3.20:9152 --config-file D:\\nulink_data\\ursula-2.json --db-filepath D:\\nulink_data --no-ip-checkup --no-block-until-ready --console-logs --file-logs
    # """

"""
    # While creating a new staker
    $ nucypher stake init --network ibex --provider <RINKEBY PROVIDER URI>

    # Update an existing staker
    $ nucypher stake config --network ibex --provider <RINKEBY PROVIDER URI>
    
"""
