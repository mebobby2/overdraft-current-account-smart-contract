api = '3.0.0'
tside = Tside.ASSET

# specifying custom balance address for accruals
ACCRUED_INTEREST = 'ACCRUED_INTEREST'

parameters = [
    Parameter(
        name='denomination',
        shape=DenominationShape,
        level=Level.TEMPLATE,
        description='Default denomination.',
        display_name='Default denomination for the contract.',
        update_permission=UpdatePermission.FIXED,
    ),
    Parameter(
        name='loan_amount',
        shape=NumberShape(
            min_value=Decimal(1000),
            max_value=Decimal(20000),
            step=Decimal(500),
            kind=NumberKind.MONEY
        ),
        level=Level.INSTANCE,
        description='The amount you wish to borrow',
        display_name='How much would you like to borrow?',
        default_value=Decimal(1000),
        update_permissions=UpdatePermission.FIXED
    ),
    Parameter(
        name='deposit_account',
        level=Level.INSTANCE,
        description='Which account would you like to receive the money in?',
        display_name='Deposit Account',
        shape=AccountIdShape,
        update_permission=UpdatePermission.FIXED,
        default_value='1',
    ),
    Parameter(
        name='internal_account',
        shape=AccountIdShape,
        level=Level.TEMPLATE,
        description='Internal account ID.',
        display_name='Internal account ID',
    ),
    Parameter(
        name='gross_interest_rate_tiers',
        shape=StringShape,
        level=Level.TEMPLATE,
        description='The rate  of interest for this loan',
        display_name='How much interest will you pay?',
    ),
    Parameter(
        name='tier_ranges',
        shape=StringShape,
        level=Level.TEMPLATE,
        description='The available loan tiers',
        display_name='The available loan tiers',
    ),
]


@requires(parameters=True)
def post_activate_code():
    start_date = vault.get_account_creation_date()
    loan_amount = vault.get_parameter_timeseries(name='loan_amount').latest()
    deposit_account_id = vault.get_parameter_timeseries(
        name='deposit_account').latest()
    denomination = vault.get_parameter_timeseries(
        name='denomination').latest()

    posting_ins = vault.make_internal_transfer_instructions(
        amount=loan_amount,
        denomination=denomination,
        client_transaction_id=vault.get_hook_execution_id() + '_PRINCIPAL',
        from_account_id=vault.account_id,
        from_account_address=DEFAULT_ADDRESS,
        to_account_id=deposit_account_id,
        to_account_address=DEFAULT_ADDRESS,
        pics=[],
        instruction_details={'description': 'Payment of loan principal'},
        asset=DEFAULT_ASSET,
    )
    vault.instruct_posting_batch(
        posting_instructions=posting_ins, effective_date=start_date)


def execution_schedules():
    # All scheduled events are defined in UTC timezone
    return [
        (
            'ACCRUED_INTEREST',
            {
                'hour': '0',
                'minute': '0',
                'second': '0'
            }
        )
    ]


@requires(event_type='ACCRUED_INTEREST', parameters=True, balances='1 day')
def scheduled_code(event_type, effective_date):
    internal_account = vault.get_parameter_timeseries(
        name='internal_account').latest()
    denomination = vault.get_parameter_timeseries(name='denomination').latest()
    loan_amount = vault.get_parameter_timeseries(name='loan_amount').latest()

    tier_ranges = json_loads(
        vault.get_parameter_timeseries(name='tier_ranges').latest())
    interest_rate_tiers = json_loads(
        vault.get_parameter_timeseries(
            name='gross_interest_rate_tiers').latest()
    )

    if event_type == 'ACCRUED_INTEREST':
        balances = vault.get_balance_timeseries().before(timestamp=effective_date)
        _accure_interest(
            vault, denomination, internal_account, effective_date, loan_amount,
            interest_rate_tiers, tier_ranges, balances
        )


def _accure_interest(vault, denomination, internal_account, effective_date, loan_amount,
                     interest_rate_tiers, tier_ranges, balances):
    effective_balance = balances[
        (DEFAULT_ADDRESS, DEFAULT_ASSET, denomination, Phase.COMMITTED)
    ].net
    hook_execution_id = vault.get_hook_execution_id()
    daily_rate = _calculate_daily_interest_rates(
        loan_amount, interest_rate_tiers, tier_ranges)
    interest = effective_balance * daily_rate
    amount_to_accrue = _precision_accrual(interest)
    if amount_to_accrue > 0:
        posting_ins = vault.make_internal_transfer_instructions(
            amount=amount_to_accrue,
            denomination=denomination,
            client_transaction_id=hook_execution_id + '_PRINCIPAL',
            from_account_id=vault.account_id,
            from_account_address=ACCRUED_INTEREST,
            to_account_id=internal_account,
            to_account_address='ACCRUED_INCOMING',
            instruction_details={
                'description': f'Daily interest accrued at {daily_rate} on balance '
                               f'of {effective_balance}'
            },
            asset=DEFAULT_ASSET
        )
        vault.instruct_posting_batch(
            posting_instructions=posting_ins, effective_date=effective_date
        )


def _calculate_daily_interest_rates(loan_amount, interest_rate_tiers, tier_ranges):
    interest_rate = _calculate_tier_values(
        loan_amount, interest_rate_tiers, tier_ranges)
    daily_rate = _yearly_to_daily_rate(interest_rate)
    return daily_rate


def _calculate_tier_values(loan_amount, interest_rate_tiers, tier_ranges):
    tier = None
    for tier_range in tier_ranges:
        bounds = tier_ranges[tier_range]
        if bounds['min'] <= loan_amount <= bounds['max']:
            tier = tier_range
    if not tier:
        raise InvalidContractParameter(
            'Requested loan amount does not fit into any tier.'
        )
    interest_rate = Decimal(interest_rate_tiers[tier])
    return interest_rate


def _yearly_to_daily_rate(yearly_rate):
    days_in_year = 365  # this is could be checking if the current year is leap and then use 366
    return yearly_rate / days_in_year


def _precision_accrual(amount):
    return amount.copy_abs().quantize(Decimal('.0001'), rounding=ROUND_HALF_UP)
