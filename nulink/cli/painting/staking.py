from nulink.blockchain.eth.constants import STAKING_POOL_CONTRACT_NAME
from nulink.cli.painting.transactions import paint_receipt_summary


def paint_staking_confirmation(emitter, staker, receipt):
    emitter.echo("\nStake initialization transaction was successful.", color='green')
    emitter.echo(f'\nTransaction details:')
    paint_receipt_summary(emitter=emitter, receipt=receipt, transaction_type="deposit stake")
    emitter.echo(f'\n{STAKING_POOL_CONTRACT_NAME} address: {staker.staking_agent.contract_address}', color='bright_yellow')


def paint_approve_confirmation(emitter, staker, receipt):
    emitter.echo("\nStake approve transaction was successful.", color='green')
    emitter.echo(f'\nTransaction details:')
    paint_receipt_summary(emitter=emitter, receipt=receipt, transaction_type="stake approve")
    emitter.echo(f'\n{STAKING_POOL_CONTRACT_NAME} address: {staker.staking_agent.contract_address}', color='blue')
