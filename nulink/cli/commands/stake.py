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
from eth.constants import ZERO_ADDRESS
from eth_utils import to_checksum_address
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
    SUCCESSFUL_NEW_STAKEHOLDER_CONFIG,
    PROMPT_STAKE_CREATE_VALUE, INSUFFICIENT_BALANCE_TO_CREATE, STAKE_VALUE_GREATER_THAN_BALANCE_TO_CREATE, PROMPT_OPERATOR_ADDRESS,
    CONFIRM_PROVIDER_AND_OPERATOR_ADDRESSES_ARE_EQUAL, SUCCESSFUL_OPERATOR_BONDING, SUCCESSFUL_UNBOND_OPERATOR, INSUFFICIENT_BALANCE_TO_SEND_TRANSACTIONS,
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
from nulink.cli.painting.staking import paint_staking_confirmation, paint_approve_confirmation, paint_stakes, paint_unstaking_confirmation

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
    network=option_network(validate=True),
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
@option_config_file
@group_general_config
@group_config_options
def config(general_config, config_file, config_options):
    """View and optionally update existing StakeHolder's configuration."""
    emitter = setup_emitter(general_config)
    configuration_file_location = config_file or StakeHolderConfiguration.default_filepath()
    updates = config_options.get_updates()
    get_or_update_configuration(emitter=emitter,
                                config_class=StakeHolderConfiguration,
                                filepath=configuration_file_location,
                                updates=updates)


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
    receipt = STAKEHOLDER.staker.stake(staking_address, int(value), gas_price=int(transacting_staker_options.gas_price))
    paint_staking_confirmation(emitter=emitter, staker=STAKEHOLDER.staker, receipt=receipt)


@stake.command('unstake-all')
@group_transacting_staker_options
@option_config_file
@option_force
@group_general_config
def unstake_all(general_config: GroupGeneralConfig,
                transacting_staker_options: TransactingStakerOptions,
                config_file, force):
    """unstake all nlk for one address."""

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

    token_balance = STAKEHOLDER.staker.token_balance

    if token_balance <= 0:
        emitter.echo(INSUFFICIENT_BALANCE_TO_SEND_TRANSACTIONS, color='red')
        raise click.Abort

    #
    # Review and Publish
    #

    # Execute
    receipt = STAKEHOLDER.staker.unstake_all(gas_price=int(transacting_staker_options.gas_price))
    paint_unstaking_confirmation(emitter=emitter, staker=STAKEHOLDER.staker, receipt=receipt)


@stake.command('tokens')
@group_staker_options
@option_config_file
@group_general_config
def get_stake_tokens(general_config: GroupGeneralConfig,
                     staker_options: StakerOptions,
                     config_file):
    """unstake all nlk for one address."""

    # Setup
    emitter = setup_emitter(general_config)
    # stakholder is StakeHolder
    STAKEHOLDER = staker_options.create_character(emitter, config_file)

    client_account, staking_address = select_client_account_for_staking(
        emitter=emitter,
        stakeholder=STAKEHOLDER,
        staking_address=staker_options.staking_address)

    STAKEHOLDER.assimilate(checksum_address=client_account, password=None)
    #
    # get Stake tokens by address
    #

    token_stakes = STAKEHOLDER.staker.stakes()
    #
    # Review and Publish
    paint_stakes(emitter=emitter, staker=STAKEHOLDER.staker, token_stakes=token_stakes)


@stake.command('bond-worker')
@group_transacting_staker_options
@option_config_file
@option_force
@group_general_config
@option_worker_address
def bond_worker(general_config: GroupGeneralConfig,
                transacting_staker_options: TransactingStakerOptions,
                config_file, force, worker_address):
    """Bond a worker to a staker."""

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

    token_balance = STAKEHOLDER.staker.token_balance

    if token_balance <= 0:
        emitter.echo(INSUFFICIENT_BALANCE_TO_SEND_TRANSACTIONS, color='red')
        raise click.Abort

    if not worker_address:
        worker_address = click.prompt(PROMPT_OPERATOR_ADDRESS, type=EIP55_CHECKSUM_ADDRESS)

    if (worker_address == staking_address) and not force:
        click.confirm(CONFIRM_PROVIDER_AND_OPERATOR_ADDRESSES_ARE_EQUAL.format(address=worker_address), abort=True)

    if not force:
        click.confirm(f"Commit to bonding "
                      f"operator {worker_address} to staker {staking_address} ?", abort=True)

    #
    # Review and Publish
    #

    # Execute
    receipt = STAKEHOLDER.staker.bond_worker(worker_address=worker_address, gas_price=int(transacting_staker_options.gas_price))

    # Report Success
    message = SUCCESSFUL_OPERATOR_BONDING.format(worker_address=worker_address, staking_address=staking_address)
    emitter.echo(message, color='green')
    paint_receipt_summary(emitter=emitter,
                          receipt=receipt,
                          chain_name=blockchain.client.chain_name,
                          transaction_type='bond_worker')


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

    token_balance = STAKEHOLDER.staker.token_balance

    if token_balance <= 0:
        emitter.echo(INSUFFICIENT_BALANCE_TO_SEND_TRANSACTIONS, color='red')
        raise click.Abort

    worker_address = STAKEHOLDER.staker.get_operator_from_staking_provider(staking_address)

    if to_checksum_address(worker_address) == f"0x{ZERO_ADDRESS.hex()}":
        emitter.echo("\nStake unbound was successful.", color='green')
        emitter.echo(f"operator address is zero address, no need unbound", color='green')
        return
    if not force:
        click.confirm("Are you sure you want to unbond your worker?", abort=True)

    #
    # Review and Publish
    #

    # Execute
    receipt = STAKEHOLDER.staker.unbond_worker(gas_price=int(transacting_staker_options.gas_price))

    # Report Success
    message = SUCCESSFUL_OPERATOR_BONDING.format(worker_address=worker_address, staking_address=staking_address)
    emitter.echo(message, color='green')
    message = SUCCESSFUL_UNBOND_OPERATOR.format(worker_address=worker_address, staking_address=staking_address)

    emitter.echo(message, color='green')
    paint_receipt_summary(emitter=emitter,
                          receipt=receipt,
                          chain_name=blockchain.client.chain_name,
                          transaction_type='unbond_worker')


@stake.group()
def rewards():
    """Manage staking rewards."""


@rewards.command('claim')
@group_transacting_staker_options
@option_config_file
@option_force
@group_general_config
def claim(general_config: GroupGeneralConfig,
          transacting_staker_options: TransactingStakerOptions,
          config_file, force):
    """
    claim unstaked tokens
    """
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

    token_balance = STAKEHOLDER.staker.token_balance

    if token_balance <= 0:
        emitter.echo(INSUFFICIENT_BALANCE_TO_SEND_TRANSACTIONS, color='red')
        raise click.Abort

    if not force:
        click.confirm("Are you sure you want to claim unstaked tokens?", abort=True)
    #
    # Review and Publish
    #

    # Execute
    receipt = STAKEHOLDER.staker.claim_unstaked_tokens(gas_price=int(transacting_staker_options.gas_price))

    # Report Success
    paint_receipt_summary(emitter=emitter,
                          receipt=receipt,
                          chain_name=blockchain.client.chain_name,
                          transaction_type='claim unstaked tokens')


@rewards.command('claim-rewards')
@group_transacting_staker_options
@option_config_file
@option_force
@group_general_config
def claim_rewards(general_config: GroupGeneralConfig,
                  transacting_staker_options: TransactingStakerOptions,
                  config_file, force):
    """
    claim rewards
    """
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

    token_balance = STAKEHOLDER.staker.token_balance

    if token_balance <= 0:
        emitter.echo(INSUFFICIENT_BALANCE_TO_SEND_TRANSACTIONS, color='red')
        raise click.Abort

    if not force:
        click.confirm("Are you sure you want to claim rewards?", abort=True)
    #
    # Review and Publish
    #

    # Execute
    receipt = STAKEHOLDER.staker.claim_rewards(gas_price=int(transacting_staker_options.gas_price))

    # Report Success
    paint_receipt_summary(emitter=emitter,
                          receipt=receipt,
                          chain_name=blockchain.client.chain_name,
                          transaction_type='claim rewards')


# for debug
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
    #     # '--signer', 'keystore://D:\\wangyi\\code\\code\\nulink\\dev_docs\\keystore-0xf9ab0b2632783816312a12615cc3e68dda171e28-worker',
    #     '--signer', 'keystore://D:\\wangyi\\code\\code\\nulink\\dev_docs\\keystore-8ef191d2b8aef4c6c66e7700708885cf30bef6eb-worker',
    #     # '--signer', 'keystore:///Users/t/data/nulink/keystore' ,
    #     '--provider', 'https://data-seed-prebsc-1-s1.bnbchain.org:8545',
    #     '--network', 'horus',
    #     # '--registry-filepath', 'D:\\wangyi\\code\\code\\nulink\\nulink-core\\nulink\\blockchain\\eth\\contract_registry\\bsc_testnet\\contract_registry.json',
    # ])

    # config([
    #     #  '--config-file', 'D:\\nulink_data\\stakeholder.json',
    #     '--debug',
    #     # '--signer', 'keystore://D:\\wangyi\\code\\code\\nulink\\dev_docs\\keystore-0xd9eca420ea4384ec4831cb4f785b1da08d5890af-worker',
    #     '--signer', 'keystore://D:\\wangyi\\code\\code\\nulink\\dev_docs\\keystore-8ef191d2b8aef4c6c66e7700708885cf30bef6eb-worker',
    #     # '--signer', 'keystore:///Users/t/data/nulink/keystore' ,
    #     '--provider', 'https://data-seed-prebsc-1-s1.bnbchain.org:8545',
    #     '--network', 'horus',
    #     # '--registry-filepath', 'D:\\wangyi\\code\\code\\nulink\\nulink-core\\nulink\\blockchain\\eth\\contract_registry\\bsc_testnet\\contract_registry.json',
    # ])

    import os

    os.environ['NULINK_STAKING_PROVIDER_ETH_PASSWORD'] = "qazwsxedc"

    # create([
    #     #  '--config-root', 'D:\\nulink_data\\',
    #     '--gas-price', '1000000000',
    #     '--force',
    #     '--debug',
    #     '--value', '1000000000000000000',
    #     # '--registry-filepath', 'D:\\wangyi\\code\\code\\nulink\\nulink-core\\nulink\\blockchain\\eth\\contract_registry\\bsc_testnet\\contract_registry.json',
    # ])

    # get_stake_tokens()

    # unstake_all([
    #     #  '--config-file', 'D:\\nulink_data\\stakeholder-d9eca420ea4384ec4831cb4f785b1da08d5890af.json',
    #     '--gas-price', '1000000000',
    #     '--force',
    #     '--debug',
    #     # '--registry-filepath', 'D:\\wangyi\\code\\code\\nulink\\nulink-core\\nulink\\blockchain\\eth\\contract_registry\\bsc_testnet\\contract_registry.json',
    # ])

    bond_worker([
        #  '--config-file', 'D:\\nulink_data\\stakeholder-d9eca420ea4384ec4831cb4f785b1da08d5890af.json',
        '--gas-price', '1000000000',
        '--force',
        '--debug',
        # '--worker-address', '0x7afb812531f1c7a5c52c8a9720f34f4b65706b21',  # '0xf9ab0B2632783816312a12615Cc3e68dda171e28',
        '--worker-address', '0x1EDfC8629d723956c4c4147b61859FD5db3C98b1',
        # '--registry-filepath', 'D:\\wangyi\\code\\code\\nulink\\nulink-core\\nulink\\blockchain\\eth\\contract_registry\\bsc_testnet\\contract_registry.json',
    ])

    # unbond_worker([
    #     #  '--config-file', 'D:\\nulink_data\\stakeholder.json',
    #     '--gas-price', '1000000000',
    #     '--force',
    #     '--debug'
    # ])

    # claim([
    #     #  '--config-file', 'D:\\nulink_data\\stakeholder.json',
    #     '--gas-price', '1000000000',
    #     '--force',
    #     '--debug'
    # ])

    # claim_rewards([
    #     #  '--config-file', 'D:\\nulink_data\\stakeholder.json',
    #     '--gas-price', '1000000000',
    #     '--force',
    #     '--debug'
    # ])

"""
    # While creating a new staker
    $ nucypher stake init --network ibex --provider <RINKEBY PROVIDER URI>

    # Update an existing staker
    $ nucypher stake config --network ibex --provider <RINKEBY PROVIDER URI>
    
"""
