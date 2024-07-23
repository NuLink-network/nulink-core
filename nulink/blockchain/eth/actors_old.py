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

import json
import time
from decimal import Decimal
from typing import Optional, Tuple
from typing import Union

import maya
import web3.exceptions
from constant_sorrow.constants import FULL
from eth_typing import ChecksumAddress
from hexbytes import HexBytes
from nulink.blockchain.eth.signers.base import Signer

from nulink.characters.banners import STAKEHOLDER_BANNER
from web3 import Web3
from web3.types import TxReceipt, Wei

from nulink.acumen.nicknames import Nickname
from nulink.blockchain.economics import Economics
from nulink.blockchain.eth.agents import (
    AdjudicatorAgent,
    ContractAgency,
    NulinkTokenAgent,
    PREApplicationAgent, StakingPoolAgent
)
from nulink.blockchain.eth.constants import NULL_ADDRESS
from nulink.blockchain.eth.decorators import save_receipt, validate_checksum_address, only_me
from nulink.blockchain.eth.deployers import (
    BaseContractDeployer,
    NuLinkTokenDeployer,
    PREApplicationDeployer,
    SubscriptionManagerDeployer, AdjudicatorDeployer
)
from nulink.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nulink.blockchain.eth.registry import BaseContractRegistry
from nulink.blockchain.eth.token import NLK, WorkTracker
from nulink.config.constants import DEFAULT_CONFIG_ROOT
from nulink.control.emitters import StdoutEmitter
from nulink.crypto.powers import TransactingPower
from nulink.types import NLKWei
from nulink.utilities.logging import Logger


class BaseActor:
    """
    Concrete base class for any actor that will interface with NuLink's ethereum smart contracts.
    """

    class ActorError(Exception):
        pass

    @validate_checksum_address
    def __init__(self,
                 domain: Optional[str],
                 registry: BaseContractRegistry,
                 transacting_power: Optional[TransactingPower] = None,
                 checksum_address: Optional[ChecksumAddress] = None,
                 economics: Optional[Economics] = None):

        if not (bool(checksum_address) ^ bool(transacting_power)):
            error = f'Pass transacting power or checksum address, got {checksum_address} and {transacting_power}.'
            raise ValueError(error)

        try:
            parent_address = self.checksum_address
            if checksum_address is not None:
                if parent_address != checksum_address:
                    raise ValueError(f"Can't have two different ethereum addresses. "
                                     f"Got {parent_address} and {checksum_address}.")
        except AttributeError:
            if transacting_power:
                self.checksum_address = transacting_power.account
            else:
                self.checksum_address = checksum_address

        self.economics = economics or Economics()
        self.transacting_power = transacting_power
        self.registry = registry
        self.network = domain
        self._saved_receipts = list()  # track receipts of transmitted transactions

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(address='{}')"
        r = r.format(class_name, self.checksum_address)
        return r

    def __eq__(self, other) -> bool:
        """Actors are equal if they have the same address."""
        try:
            return bool(self.checksum_address == other.checksum_address)
        except AttributeError:
            return False

    @property
    def eth_balance(self) -> Decimal:
        """Return this actor's current ETH balance"""
        blockchain = BlockchainInterfaceFactory.get_interface()  # TODO: EthAgent?  #1509
        balance = blockchain.client.get_balance(self.wallet_address)
        return Web3.fromWei(balance, 'ether')

    @property
    def wallet_address(self):
        return self.checksum_address


class NulinkTokenActor(BaseActor):
    """
    Actor to interface with the NuLinkToken contract
    """

    def __init__(self, registry: BaseContractRegistry, **kwargs):
        super().__init__(registry=registry, **kwargs)
        self.__token_agent = None

    @property
    def token_agent(self):
        if self.__token_agent:
            return self.__token_agent
        self.__token_agent = ContractAgency.get_agent(NulinkTokenAgent, registry=self.registry)
        return self.__token_agent

    @property
    def token_balance(self) -> NLK:
        """Return this actor's current token balance"""
        balance = int(self.token_agent.get_balance(address=self.checksum_address))
        nu_balance = NLK(balance, 'NLKWei')
        return nu_balance

    def get_allowance(self, spender: ChecksumAddress, owner: ChecksumAddress = None) -> NLKWei:
        return self.token_agent.get_allowance(owner or self.checksum_address, spender)

    @only_me
    @save_receipt
    def approve(self, amount: Wei, spender_address: ChecksumAddress) -> TxReceipt:
        receipt = self.token_agent.approve_transfer(NLKWei(amount), spender_address, transacting_power=self.transacting_power)
        return receipt


class ContractAdministrator(BaseActor):
    """
    The administrator of network contracts.
    """

    # Note: Deployer classes are sorted by deployment dependency order.

    standard_deployer_classes = (
        NuLinkTokenDeployer,
        PREApplicationDeployer,
        SubscriptionManagerDeployer  # TODO: Move to dispatched/upgradeable section
    )

    dispatched_upgradeable_deployer_classes = (
        AdjudicatorDeployer,
    )

    upgradeable_deployer_classes = (
        *dispatched_upgradeable_deployer_classes,
    )

    aux_deployer_classes = (
        # Add more deployer classes here
    )

    # For ownership transfers.
    ownable_deployer_classes = (*dispatched_upgradeable_deployer_classes,)

    # Used in the automated deployment series.
    primary_deployer_classes = (*standard_deployer_classes,
                                *upgradeable_deployer_classes)

    # Comprehensive collection.
    all_deployer_classes = (*primary_deployer_classes,
                            *aux_deployer_classes,
                            *ownable_deployer_classes)

    class UnknownContract(ValueError):
        pass

    def __init__(self, *args, **kwargs):
        self.log = Logger("Deployment-Actor")
        self.deployers = {d.contract_name: d for d in self.all_deployer_classes}
        super().__init__(*args, **kwargs)

    def __repr__(self):
        r = '{name} - {deployer_address})'.format(name=self.__class__.__name__, deployer_address=self.checksum_address)
        return r

    def __get_deployer(self, contract_name: str):
        try:
            Deployer = self.deployers[contract_name]
        except KeyError:
            raise self.UnknownContract(contract_name)
        return Deployer

    def deploy_contract(self,
                        contract_name: str,
                        gas_limit: int = None,
                        deployment_mode=FULL,
                        ignore_deployed: bool = False,
                        progress=None,
                        confirmations: int = 0,
                        deployment_parameters: dict = None,
                        emitter=None,
                        *args, **kwargs,
                        ) -> Tuple[dict, BaseContractDeployer]:

        if not self.transacting_power:
            raise self.ActorError('No transacting power available for deployment.')

        deployment_parameters = deployment_parameters or {}

        Deployer = self.__get_deployer(contract_name=contract_name)
        deployer = Deployer(registry=self.registry, economics=self.economics, *args, **kwargs)

        if Deployer._upgradeable:
            receipts = deployer.deploy(transacting_power=self.transacting_power,
                                       gas_limit=gas_limit,
                                       progress=progress,
                                       ignore_deployed=ignore_deployed,
                                       confirmations=confirmations,
                                       deployment_mode=deployment_mode,
                                       emitter=emitter,
                                       **deployment_parameters)
        else:
            receipts = deployer.deploy(transacting_power=self.transacting_power,
                                       gas_limit=gas_limit,
                                       progress=progress,
                                       confirmations=confirmations,
                                       deployment_mode=deployment_mode,
                                       ignore_deployed=ignore_deployed,
                                       emitter=emitter,
                                       **deployment_parameters)
        return receipts, deployer

    def upgrade_contract(self,
                         contract_name: str,
                         confirmations: int,
                         ignore_deployed: bool = False,
                         ) -> dict:
        if not self.transacting_power:
            raise self.ActorError('No transacting power available for deployment.')
        Deployer = self.__get_deployer(contract_name=contract_name)
        deployer = Deployer(registry=self.registry)
        receipts = deployer.upgrade(transacting_power=self.transacting_power,
                                    ignore_deployed=ignore_deployed,
                                    confirmations=confirmations)
        return receipts

    def retarget_proxy(self,
                       confirmations: int,
                       contract_name: str,
                       target_address: str,
                       just_build_transaction: bool = False
                       ):
        if not self.transacting_power:
            raise self.ActorError('No transacting power available for deployment.')
        Deployer = self.__get_deployer(contract_name=contract_name)
        deployer = Deployer(registry=self.registry)
        result = deployer.retarget(transacting_power=self.transacting_power,
                                   target_address=target_address,
                                   just_build_transaction=just_build_transaction,
                                   confirmations=confirmations)
        return result

    def rollback_contract(self, contract_name: str):
        if not self.transacting_power:
            raise self.ActorError('No transacting power available for deployment.')
        Deployer = self.__get_deployer(contract_name=contract_name)
        deployer = Deployer(registry=self.registry)
        receipts = deployer.rollback(transacting_power=self.transacting_power)
        return receipts

    def save_deployment_receipts(self, receipts: dict, filename_prefix: str = 'deployment') -> str:
        config_root = DEFAULT_CONFIG_ROOT  # We force the use of the default here.
        filename = f'{filename_prefix}-receipts-{self.deployer_address[:6]}-{maya.now().epoch}.json'
        filepath = config_root / filename
        config_root.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w') as file:
            data = dict()
            for contract_name, contract_receipts in receipts.items():
                contract_records = dict()
                for tx_name, receipt in contract_receipts.items():
                    # Formatting
                    pretty_receipt = {item: str(result) for item, result in receipt.items()}
                    contract_records[tx_name] = pretty_receipt
                data[contract_name] = contract_records
            data = json.dumps(data, indent=4)
            file.write(data)
        return filepath


class Operator(BaseActor):
    READY_TIMEOUT = None  # (None or 0) == indefinite
    READY_POLL_RATE = 10

    class OperatorError(BaseActor.ActorError):
        pass

    def __init__(self,
                 is_me: bool,
                 work_tracker: WorkTracker = None,
                 operator_address: ChecksumAddress = None,
                 *args, **kwargs):

        super().__init__(*args, **kwargs)
        self.log = Logger("worker")
        self.is_me = is_me
        self.__operator_address = operator_address
        self.__staking_provider_address = None  # set by block_until_ready
        if is_me:
            self.token_agent = ContractAgency.get_agent(NulinkTokenAgent, registry=self.registry)
            self.application_agent = ContractAgency.get_agent(PREApplicationAgent, registry=self.registry)
            self.work_tracker = work_tracker or WorkTracker(worker=self)

    def _local_operator_address(self):
        return self.__operator_address

    @property
    def wallet_address(self):
        return self.operator_address

    @property
    def staking_provider_address(self):
        if not self.__staking_provider_address or self.__staking_provider_address == NULL_ADDRESS:
            self.__staking_provider_address = self.get_staking_provider_address()
        return self.__staking_provider_address

    def get_staking_provider_address(self):
        self.__staking_provider_address = self.application_agent.get_staking_provider_from_operator(self.operator_address)
        self.checksum_address = self.__staking_provider_address
        self.nickname = Nickname.from_seed(self.checksum_address)
        return self.__staking_provider_address

    @property
    def is_confirmed(self):
        return self.application_agent.is_operator_confirmed(self.operator_address)

    def confirm_address(self, fire_and_forget: bool = True) -> Union[TxReceipt, HexBytes]:
        # self.token_agent.get_balance(self.operator_address)
        txhash_or_receipt = self.application_agent.confirm_operator_address(self.transacting_power, fire_and_forget=fire_and_forget)
        return txhash_or_receipt

    def block_until_ready(self, poll_rate: int = None, timeout: int = None):
        emitter = StdoutEmitter()
        client = self.application_agent.blockchain.client
        poll_rate = poll_rate or self.READY_POLL_RATE
        timeout = timeout or self.READY_TIMEOUT
        start, funded, bonded = maya.now(), False, False
        while not (funded and bonded):

            if timeout and ((maya.now() - start).total_seconds() > timeout):
                message = f"x Operator was not qualified after {timeout} seconds"
                emitter.message(message, color='red')
                raise self.ActorError(message)

            if not funded:
                # check for funds
                ether_balance = client.get_balance(self.operator_address)
                if ether_balance:
                    # funds found
                    funded, balance = True, Web3.fromWei(ether_balance, 'ether')
                    emitter.message(f"✓ Operator {self.operator_address} is funded with {balance} ETH", color='green')
                else:
                    emitter.message(f"! Operator {self.operator_address} is not funded with ETH", color="yellow")

            if (not bonded) and (self.get_staking_provider_address() != NULL_ADDRESS):
                bonded = True
                emitter.message(f"✓ Operator {self.operator_address} is bonded to staking provider {self.staking_provider_address}", color='green')
            else:
                emitter.message(f"! Operator {self.operator_address} is not bonded to a staking provider", color='yellow')

            time.sleep(poll_rate)

    def get_work_is_needed_check(self):
        def func(self):
            # we have not confirmed yet
            return not self.is_confirmed

        return func


class Staker(NulinkTokenActor):
    """
    Baseclass for staking-related operations on the blockchain.
    """

    class StakerError(NulinkTokenActor.ActorError):
        pass

    class InsufficientTokens(StakerError):
        pass

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.log = Logger("staker")
        self.is_me = bool(self.transacting_power)
        self._worker_address = None

        # Blockchain
        self.staking_agent = ContractAgency.get_agent(StakingPoolAgent, registry=self.registry)
        self.application_agent = ContractAgency.get_agent(PREApplicationAgent, registry=self.registry)

    def to_dict(self) -> dict:
        worker_address = self.worker_address or NULL_ADDRESS
        staker_funds = {'ETH': int(self.eth_balance), 'NLK': int(self.token_balance)}
        staker_payload = {'staker': self.checksum_address,
                          'balances': staker_funds,
                          'worker': worker_address,
                          }
        return staker_payload

    @only_me
    @save_receipt
    def approve_if_need(self, amount: NLKWei, owner: ChecksumAddress = None) -> TxReceipt or bool:
        spender: ChecksumAddress = self.staking_agent.contract_address
        allowance: NLKWei = self.get_allowance(spender, owner or self.checksum_address)

        if allowance >= amount:
            return True

        receipt: TxReceipt = self.approve(amount, spender)
        return receipt

    @only_me
    @save_receipt
    def stake(self, stake_address: ChecksumAddress, value: Wei, gas_price: Wei = None) -> TxReceipt:
        receipt = self.staking_agent.stake(stake_address, value=value, transacting_power=self.transacting_power, gas_price=gas_price)
        return receipt

    @only_me
    @save_receipt
    def unstake_all(self, stake_address: ChecksumAddress = None, gas_price: Wei = None) -> TxReceipt:
        receipt = self.staking_agent.unstake_all(stake_address or self.checksum_address, transacting_power=self.transacting_power, gas_price=gas_price)
        return receipt

    def stakes(self, stake_address: ChecksumAddress = None) -> int:
        return self.staking_agent.stakes(stake_address or self.checksum_address)

    def get_min_stake_amount(self) -> Wei:
        return self.staking_agent.min_stake_amount()

    def get_max_stake_amount(self) -> Wei:
        return self.staking_agent.max_stake_amount()

    #
    # Bonding with Worker
    #
    @only_me
    @save_receipt
    @validate_checksum_address
    def bond_worker(self, worker_address: ChecksumAddress, stake_address: ChecksumAddress = None, gas_price: Wei = None) -> TxReceipt:
        receipt = self.application_agent.bond_operator(stake_address or self.checksum_address, worker_address, transacting_power=self.transacting_power, gas_price=gas_price)
        self._worker_address = worker_address
        return receipt

    @only_me
    @save_receipt
    def unbond_worker(self, stake_address: ChecksumAddress = None, gas_price: Wei = None) -> TxReceipt:
        receipt = self.application_agent.unbond_operator(stake_address or self.checksum_address, transacting_power=self.transacting_power, gas_price=gas_price)
        self._worker_address = NULL_ADDRESS
        return receipt

    @property
    def worker_address(self) -> str:
        if not self._worker_address:
            # TODO: This is broken for StakeHolder with different stakers - See #1358
            worker_address = self.application_agent.get_operator_from_staking_provider(staker_address=self.checksum_address)
            self._worker_address = worker_address

        return self._worker_address

    def get_operator_from_staking_provider(self, stake_address: ChecksumAddress = None) -> ChecksumAddress:
        return self.application_agent.get_operator_from_staking_provider(stake_address or self.checksum_address)

    def get_staking_provider_from_operator(self, operator_address: ChecksumAddress) -> ChecksumAddress:
        return self.application_agent.get_staking_provider_from_operator(operator_address)

    @only_me
    @save_receipt
    def claim_unstaked_tokens(self, stake_address: ChecksumAddress = None, gas_price: Wei = None) -> TxReceipt:
        receipt = self.staking_agent.claim(stake_address or self.checksum_address, transacting_power=self.transacting_power, gas_price=gas_price)
        return receipt

    @only_me
    @save_receipt
    def claim_rewards(self, stake_address: ChecksumAddress = None, gas_price: Wei = None) -> TxReceipt:
        receipt = self.staking_agent.claim_reward(stake_address or self.checksum_address, transacting_power=self.transacting_power, gas_price=gas_price)
        return receipt

class BlockchainPolicyAuthor(NulinkTokenActor):
    """Alice base class for blockchain operations, mocking up new policies!"""

    def __init__(self, eth_provider_uri: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.application_agent = ContractAgency.get_agent(
            PREApplicationAgent,
            registry=self.registry,
            eth_provider_uri=eth_provider_uri
        )

    def create_policy(self, *args, **kwargs):
        """Hence the name, a BlockchainPolicyAuthor can create a BlockchainPolicy with themself as the author."""
        from nulink.policy.policies import BlockchainPolicy
        blockchain_policy = BlockchainPolicy(publisher=self, *args, **kwargs)
        return blockchain_policy


class Investigator(NulinkTokenActor):
    """
    Actor that reports incorrect CFrags to the Adjudicator contract.
    In most cases, Bob will act as investigator, but the actor is generic enough than
    anyone can report CFrags.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.adjudicator_agent = ContractAgency.get_agent(AdjudicatorAgent, registry=self.registry)

    @save_receipt
    def request_evaluation(self, evidence) -> dict:
        receipt = self.adjudicator_agent.evaluate_cfrag(evidence=evidence, transacting_power=self.transacting_power)
        return receipt

    def was_this_evidence_evaluated(self, evidence) -> bool:
        result = self.adjudicator_agent.was_this_evidence_evaluated(evidence=evidence)
        return result


class StakeHolder:
    banner = STAKEHOLDER_BANNER

    class UnknownAccount(KeyError):
        pass

    def __init__(self,
                 signer: Signer,
                 registry: BaseContractRegistry,
                 domain: str,
                 initial_address: str = None,
                 worker_data: dict = None):

        self.worker_data = worker_data
        self.log = Logger(f"stakeholder")
        self.checksum_address = initial_address
        self.registry = registry
        self.domain = domain
        self.staker = None
        self.signer = signer

        if initial_address:
            # If an initial address was passed,
            # it is safe to understand that it has already been used at a higher level.
            if initial_address not in self.signer.accounts:
                message = f"Account {initial_address} is not known by this Ethereum client. Is it a HW account? " \
                          f"If so, make sure that your device is plugged in and you use the --hw-wallet flag."
                raise self.UnknownAccount(message)
            self.assimilate(checksum_address=initial_address)

    @validate_checksum_address
    def assimilate(self, checksum_address: ChecksumAddress, password: str = None) -> None:
        original_form = self.checksum_address
        staking_address = checksum_address
        self.checksum_address = staking_address
        self.staker = self.get_staker(checksum_address=staking_address)

        if password:
            self.signer.unlock_account(account=checksum_address, password=password)
        new_form = self.checksum_address
        self.log.info(f"Setting Staker from {original_form} to {new_form}.")

    @validate_checksum_address
    def get_staker(self, checksum_address: ChecksumAddress = None):
        checksum_address = self.checksum_address if not checksum_address else checksum_address
        if checksum_address not in self.signer.accounts:
            raise ValueError(f"{checksum_address} is not a known client account.")
        transacting_power = TransactingPower(account=checksum_address, signer=self.signer)
        staker = Staker(transacting_power=transacting_power,
                        domain=self.domain,
                        registry=self.registry)

        return staker
