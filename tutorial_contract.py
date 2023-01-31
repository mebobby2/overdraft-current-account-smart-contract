display_name = 'Bobank Current Account'
api = '3.0.0'
version = '0.0.1'
summary = "A Current Account with an Overdraft facility"
tside = Tside.LIABILITY

parameters = [
    Parameter(
        name='denomination',
        shape=DenominationShape,
        level=Level.TEMPLATE,
        description='Default denomination',
        display_name='Default denomination for the contract',
    ),
    Parameter(
        name='overdraft_limit',
        shape=NumberShape(
            kind=NumberKind.MONEY,
            min_value=0,
            max_value=10000,
            step=0.01
        ),
        level=Level.TEMPLATE,
        description='Overdraft limit',
        display_name='Maximum overdraft permitted for this account',
    ),
    Parameter(
        name='overdraft_fee',
        shape=NumberShape(
            kind=NumberKind.MONEY,
            min_value=0,
            max_value=1,
            step=0.01
        ),
        level=Level.TEMPLATE,
        description='Overdraft fee',
        display_name='Fee charged on balances over overdraft limit',
    ),
]
internal_account = '1'


@requires(parameters=True)
def pre_posting_code(postings, effective_date):
    denomination = vault.get_parameter_timeseries(name='denomination').latest()

    if any(post.denomination != denomination for post in postings):
        raise Rejected(
            'Cannot make transactions in given denomination; '
            'transactions must be in {}'.format('GBP'),
            reason_code=RejectedReason.WRONG_DENOMINATION,
        )


@requires(parameters=True, balances='latest')
def post_posting_code(postings, effective_date):
    denomination = vault.get_parameter_timeseries(name='denomination').latest()
    overdraft_limit = vault.get_parameter_timeseries(
        name='overdraft_limit').latest()
    balances = vault.get_balance_timeseries().latest()
    committed_balance = balances[(
        DEFAULT_ADDRESS, DEFAULT_ASSET, denomination, Phase.COMMITTED)].net
    # We ignore authorised (PENDING_OUT) transactions and only look at settled ones (COMMITTED)
    if committed_balance <= -overdraft_limit:
        # Charge the fee
        _charge_overdraft_fee(vault, effective_date + timedelta(minutes=1))


def _charge_overdraft_fee(vault, effective_date):
    denomination = vault.get_parameter_timeseries(name='denomination').latest()
    overdraft_fee = vault.get_parameter_timeseries(name='overdraft_fee').latest()
    instructions = vault.make_internal_transfer_instructions(
      amount=overdraft_fee,
      denomination=denomination,
      from_account_id=vault.account_id,
      from_account_address=DEFAULT_ADDRESS,
      to_account_id=internal_account,
      to_account_address=DEFAULT_ADDRESS,
      asset=DEFAULT_ASSET,
      client_transaction_id='{}_OVERDRAFT_FEE'.format(
        vault.get_hook_execution_id()
      ),
      instruction_details={
        'description': 'Overdraft fee charged'
      },
      pics=[]
    )
    vault.instruct_posting_batch(
      posting_instructions=instructions,
      effective_date=effective_date,
      client_batch_id='BATCH_{}_OVERDRAFT_FEE'.format(
        vault.get_hook_execution_id()
      )
    )
