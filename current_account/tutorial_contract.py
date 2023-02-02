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
    Parameter(
        name='gross_interest_rate',
        shape=NumberShape(
            kind=NumberKind.PERCENTAGE, min_value=0, max_value=1, step=0.01),
        level=Level.TEMPLATE,
        description='Gross Interest Rate',
        display_name='Rate paid on positive balances',
    ),
    Parameter(
        name='interest_payment_day',
        level=Level.INSTANCE,
        description="Which day of the month would you like to receive interest?",
        display_name='Elected day of month to apply interest',
        shape=OptionalShape(NumberShape(
            min_value=1,
            max_value=28,
            step=1
        )),
        update_permission=UpdatePermission.USER_EDITABLE,
    )
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


@requires(parameters=True)
def execution_schedules():
    selected_day = vault.get_parameter_timeseries(
        name='interest_payment_day').latest()
    interest_payday = selected_day.value if selected_day.is_set() else min(
        vault.get_account_creation_date().day, 28
    )

    return [
        (
            'APPLY_ACCRUED_INTEREST', {
                'day': str(interest_payday),
                'hour': '0',
                'minute': '1'
            }
        ),
        (
            'ACCRUE_INTEREST', {
                'hour': '00',
                'minute': '00',
                'second': '00'
            }
        ),
    ]

# https://docs.thoughtmachine.net/vault-core/4-5/EN/reference/balances/overview/#accounting_model


@requires(event_type='ACCRUE_INTEREST', parameters=True, balances='1 day')
@requires(event_type='APPLY_ACCRUED_INTEREST', parameters=True, balances='1 day')
def scheduled_code(event_type, effective_date):
    if event_type == 'ACCRUE_INTEREST':
        _accrue_interest(vault, effective_date)
    elif event_type == 'APPLY_ACCRUED_INTEREST':
        _apply_accrued_interest(vault, effective_date)


def _apply_accrued_interest(vault, end_of_day_datetime):
    denomination = vault.get_parameter_timeseries(name='denomination').latest()
    latest_bal_by_addr = vault.get_balance_timeseries().at(
        timestamp=end_of_day_datetime)

    incoming_accrued = latest_bal_by_addr[
        ('ACCRUED_INCOMING', DEFAULT_ASSET, denomination, Phase.COMMITTED)
    ].net

    amount_to_be_paid = _precision_fulfillment(incoming_accrued)

    # Fulfil any incoming interest into the account
    if amount_to_be_paid > 0:
        posting_ins = vault.make_internal_transfer_instructions(
            amount=amount_to_be_paid,
            denomination=denomination,
            from_account_id=vault.account_id,
            from_account_address='ACCRUED_INCOMING',
            to_account_id=vault.account_id,
            to_account_address=DEFAULT_ADDRESS,
            asset=DEFAULT_ASSET,
            client_transaction_id='APPLY_ACCRUED_INTEREST_{}_{}_CUSTOMER'.format(
                vault.get_hook_execution_id(), denomination
            ),
            instruction_details={
                'description': 'Interest Applied',
                'event': 'APPLY_ACCRUED_INTEREST'
            }
        )
        posting_ins.extend(
            vault.make_internal_transfer_instructions(
                amount=amount_to_be_paid,
                denomination=denomination,
                from_account_id=internal_account,
                from_account_address=DEFAULT_ADDRESS,
                to_account_id=internal_account,
                to_account_address='ACCRUED_OUTGOING',
                asset=DEFAULT_ASSET,
                client_transaction_id='APPLY_ACCRUED_INTEREST_{}_{}_INTERNAL'.format(
                    vault.get_hook_execution_id(), denomination
                ),
                instruction_details={
                    'description': 'Interest Applied',
                    'event': 'APPLY_ACCRUED_INTEREST'
                }
            )
        )

        # only zero out accrued interest if the remainder is positive (i.e. we rounded interest down)
        remainder = incoming_accrued - amount_to_be_paid
        if remainder > 0:
            posting_ins.extend(
                vault.make_internal_transfer_instructions(
                    amount=abs(remainder), denomination=denomination,
                    from_account_id=vault.account_id, from_account_address='ACCRUED_INCOMING',
                    to_account_id=internal_account, to_account_address='ACCRUED_OUTGOING',
                    asset=DEFAULT_ASSET,
                    client_transaction_id='REVERSE_ACCRUE_INTEREST_{}_{}'.format(
                        vault.get_hook_execution_id(), denomination
                    ),
                    instruction_details={
                        'description': 'Reversing negative accrued interest after payment.',
                        'event': 'APPLY_ACCRUED_INTEREST'
                    }
                )
            )

        # instructions to apply interest and optional reversal of remainder must be executed
        # in a batch to ensure the overall transaction is atomic
        vault.instruct_posting_batch(
            posting_instructions=posting_ins,
            effective_date=end_of_day_datetime,
            client_batch_id='APPLY_ACCRUED_INTEREST_{}_{}'.format(
                vault.get_hook_execution_id(), denomination
            )
        )


def _accrue_interest(vault, end_of_day_datetime):
    denomination = vault.get_parameter_timeseries(name='denomination').latest()
    balances = vault.get_balance_timeseries().at(timestamp=end_of_day_datetime)
    effective_balance = balances[(
        DEFAULT_ADDRESS, DEFAULT_ASSET, denomination, Phase.COMMITTED)].net

    gross_interest_rate = vault.get_parameter_timeseries(
        name='gross_interest_rate'
    ).before(timestamp=end_of_day_datetime)

    daily_rate = gross_interest_rate / 365
    daily_rate_percent = daily_rate * 100
    amount_to_accrue = _precision_accural(effective_balance * daily_rate)

    if amount_to_accrue > 0:
        posting_ins = vault.make_internal_transfer_instructions(
            amount=amount_to_accrue,
            denomination=denomination,
            client_transaction_id=vault.get_hook_execution_id(),
            from_account_id=internal_account,
            from_account_address='ACCRUED_OUTGOING',
            to_account_id=vault.account_id,
            to_account_address='ACCRUED_INCOMING',
            instruction_details={
                'description': 'Daily interest accrued at %0.5f%% on balance of %0.2f' %
                               (daily_rate_percent, effective_balance)
            },
            asset=DEFAULT_ASSET
        )
        vault.instruct_posting_batch(
            posting_instructions=posting_ins,
            effective_date=end_of_day_datetime
        )


def _precision_accural(amount):
    return amount.copy_abs().quantize(Decimal('.00001'), rounding=ROUND_HALF_UP)


def _precision_fulfillment(amount):
    return amount.copy_abs().quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def _charge_overdraft_fee(vault, effective_date):
    denomination = vault.get_parameter_timeseries(name='denomination').latest()
    overdraft_fee = vault.get_parameter_timeseries(
        name='overdraft_fee').latest()
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
