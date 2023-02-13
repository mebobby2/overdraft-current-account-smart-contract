api = '3.0.0'

# https://docs.thoughtmachine.net/vault-core/4-5/EN/reference/balances/overview/#accounting_model-debits_credits_and_tside
# A contract template may optionally specify a variable named tside. This becomes a product level attribute with one of the values "ASSET"
# or "LIABILITY". Default value is "LIABILITY". The effect of this field is simply the sign of every balance. Every posting is either counted
# as a credit or a debit. If tside of a product is "LIABILITY", every account instance will calculate net balance as net = total credit - total debit.
# For an "ASSET" type account, net balances are defined as net = total debit - total credit.
tside = Tside.ASSET

# specifying custom balance address for accruals
ACCRUED_INTEREST = 'ACCRUED_INTEREST'
DUE = 'DUE'

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
        description='The internal account that collects charged interest.',
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
    Parameter(
        name='payment_day',
        level=Level.INSTANCE,
        description="On which day of the month would you like to pay?",
        display_name="The day of the month that you would like to pay. "
                     "This day must be between the 1st and 28th day of the month",
        shape=OptionalShape(NumberShape(
            kind=NumberKind.PLAIN,
            min_value=1,
            max_value=28,
            step=1,
        )),
        update_permission=UpdatePermission.USER_EDITABLE,
    ),
    Parameter(
        name='loan_term',
        shape=NumberShape(
            min_value=Decimal(1),
            max_value=Decimal(5),
            step=Decimal(1)
        ),
        level=Level.INSTANCE,
        description='The term of the loan in years',
        display_name='How long do you want to borrow the money for?',
        default_value=Decimal(5),
        update_permissions=UpdatePermission.FIXED
    ),
    Parameter(
        name='loan_end_date',
        shape=OptionalShape(DateShape),
        level=Level.INSTANCE,
        description='The date by which the loan must be fully paid off',
        display_name='The date by which the loan must be fully paid off',
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


@requires(parameters=True, balances='latest', postings='1 month')
def pre_posting_code(postings, effective_date):
    denomination = vault.get_parameter_timeseries(name='denomination').latest()
    payment_day_param = vault.get_parameter_timeseries(
        name='payment_day').latest()
    payment_day, _ = _get_payment_day(vault, payment_day_param, effective_date)
    next_payment_date = _calculate_next_payment_date(
        payment_day, effective_date)

    if any(post.denomination != denomination for post in postings):
        raise Rejected(
            'Cannot make transactions in given denomination; '
            f'transactions must be in {denomination}',
            reason_code=RejectedReason.WRONG_DENOMINATION,
        )

    if any(not post.credit for post in postings):
        raise Rejected(
            'Cannot withdraw from this account',
            reason_code=RejectedReason.AGAINST_TNC,
        )

    balances = vault.get_balance_timeseries().latest()
    recent_postings = vault.get_postings(include_proposed=False)

    total_due = sum(
        balance.net for ((address, asset, denomination, phase), balance) in balances.items() if
        address in [DUE]
    )

    amount_paid_off_this_month = sum(
        posting.amount for posting in recent_postings if
        posting.credit and posting.type != PostingInstructionType.CUSTOM_INSTRUCTION
        and posting.value_timestamp > next_payment_date - timedelta(months=1)
    )
    proposed_amount = sum(
        post.amount for post in postings if post.account_address == DEFAULT_ADDRESS
        and post.asset == DEFAULT_ASSET
    )
    if effective_date < vault.get_account_creation_date() + timedelta(days=28):
        raise Rejected(
            f'Repayments do not start until {next_payment_date.date()}',
            reason_code=RejectedReason.AGAINST_TNC,
        )
    if amount_paid_off_this_month + proposed_amount > total_due:
        raise Rejected(
            f'Cannot overpay with this account, you can currently pay up to {total_due} '
            f'(attempting to pay {amount_paid_off_this_month} + {proposed_amount})',
            reason_code=RejectedReason.AGAINST_TNC,
        )


@requires(parameters=True, balances='latest')
def post_posting_code(postings, effective_date):
    denomination = vault.get_parameter_timeseries(name='denomination').latest()
    balances = vault.get_balance_timeseries().latest()
    hook_execution_id = vault.get_hook_execution_id()
    for i, posting in enumerate(postings):
        client_transaction_id = (
            f'{posting.client_transaction_id}_{hook_execution_id}_{i}'
        )
        _process_payment(
            vault, effective_date, posting, client_transaction_id, denomination, balances
        )


def _process_payment(vault, effective_date, posting, client_transaction_id, denomination, balances):
    repayment_instructions = []
    current_address_balance = balances[
        (DUE, DEFAULT_ASSET, denomination, Phase.COMMITTED)
    ].net
    posting_amount = abs(
        posting.balances()[(DEFAULT_ADDRESS, DEFAULT_ASSET,
                            denomination, Phase.COMMITTED)].net
    )
    if posting_amount == Decimal('0'):
        return
    if current_address_balance and posting_amount > 0:
        repayment_instructions.extend(
            vault.make_internal_transfer_instructions(
                amount=posting.amount,
                denomination=denomination,
                client_transaction_id=f'REPAY_{DUE}_{client_transaction_id}',
                from_account_id=vault.account_id,
                from_account_address=DEFAULT_ADDRESS,
                to_account_id=vault.account_id,
                to_account_address=DUE,
                instruction_details={
                    'description': f'Paying off {posting_amount} from {DUE}, '
                                   f'which was at {current_address_balance} - {effective_date}'
                },
                asset=DEFAULT_ASSET
            )
        )
    if repayment_instructions:
        vault.instruct_posting_batch(
            posting_instructions=repayment_instructions,
            effective_date=effective_date
        )


@requires(parameters=True)
def execution_schedules():
    payment_day_param = vault.get_parameter_timeseries(
        name='payment_day').latest()
    creation_date = vault.get_account_creation_date()
    payment_day, roll_over_to_next_month = _get_payment_day(
        vault,
        payment_day_param,
        creation_date
    )
    first_payment_date = _calculate_first_payment_day(
        payment_day, roll_over_to_next_month, creation_date
    )

    # All scheduled events are defined in UTC timezone
    return [
        (
            'ACCRUED_INTEREST',
            {
                'hour': '0',
                'minute': '0',
                'second': '0'
            }
        ),
        (
            'APPLY_INTEREST',
            {
                'day': str(payment_day),
                'hour': '0',
                'minute': '0',
                'second': '1',
                'start_date': str(first_payment_date.date())
            }
        ),
        (
            'TRANSFER_DUE_AMOUNT',
            {
                'day': str(payment_day),
                'hour': '0',
                'minute': '0',
                'second': '1',
                'start_date': str(first_payment_date.date())
            }
        ),
    ]


def _get_payment_day(vault, payment_day_param, effective_date):
    roll_over_to_next_month = False
    if payment_day_param.is_set():
        payment_day = payment_day_param.value
    else:
        payment_day = 28
    if payment_day > 28:
        payment_day = 1
    if payment_day < effective_date.day:
        roll_over_to_next_month = True
    return payment_day, roll_over_to_next_month


def _calculate_first_payment_day(payment_day, roll_over_to_next_month, creation_date):
    first_payment_date = creation_date.replace(day=payment_day)
    if roll_over_to_next_month:
        first_payment_date += timedelta(months=1)
    date_delta = first_payment_date - creation_date
    # We wish to add a month to the first payment date
    # So that the customer doesnt pay in their first month
    if date_delta.days < 28:
        first_payment_date += timedelta(months=1)
    return first_payment_date


@requires(event_type='ACCRUED_INTEREST', parameters=True, balances='1 day')
@requires(event_type='APPLY_INTEREST', parameters=True, balances='1 day', last_execution_time=['APPLY_INTEREST'])
@requires(event_type='TRANSFER_DUE_AMOUNT', parameters=True, balances='1 day', last_execution_time=['TRANSFER_DUE_AMOUNT'])
def scheduled_code(event_type, effective_date):
    internal_account = vault.get_parameter_timeseries(
        name='internal_account').latest()
    denomination = vault.get_parameter_timeseries(name='denomination').latest()
    end_date = vault.get_parameter_timeseries(name='loan_end_date').latest()
    loan_amount = vault.get_parameter_timeseries(name='loan_amount').latest()
    loan_term = vault.get_parameter_timeseries(name='loan_term').latest()

    tier_ranges = json_loads(
        vault.get_parameter_timeseries(name='tier_ranges').latest())
    interest_rate_tiers = json_loads(
        vault.get_parameter_timeseries(
            name='gross_interest_rate_tiers').latest()
    )

    creation_date = vault.get_account_creation_date()
    payment_day, roll_over_to_next_month = _get_payment_day(
        vault,
        vault.get_parameter_timeseries(name='payment_day').latest(),
        creation_date
    )

    if event_type == 'ACCRUED_INTEREST':
        balances = vault.get_balance_timeseries().before(timestamp=effective_date)
        _accure_interest(
            vault, denomination, internal_account, effective_date, loan_amount,
            interest_rate_tiers, tier_ranges, balances
        )
    elif event_type == 'APPLY_INTEREST':
        balances = vault.get_balance_timeseries().latest()
        _apply_accrued_interest(
            vault, effective_date, internal_account, denomination, balances)
    elif event_type == 'TRANSFER_DUE_AMOUNT':
        balances = vault.get_balance_timeseries().latest()
        previous_payment_checked = vault.get_last_execution_time(
            event_type='TRANSFER_DUE_AMOUNT')
        _transfer_due_amount(
            vault, effective_date, previous_payment_checked, denomination, end_date, loan_term,
            loan_amount, interest_rate_tiers, tier_ranges, payment_day, roll_over_to_next_month,
            creation_date, balances
        )


def _transfer_due_amount(vault, effective_date, previous_payment_checked, denomination, end_date,
                         loan_term, loan_amount, interest_rate_tiers, tier_ranges, payment_day,
                         roll_over_to_next_month, creation_date, balances):
    additional_interest = _calculate_additional_interest(
        previous_payment_checked, loan_amount, interest_rate_tiers, tier_ranges,
        payment_day, roll_over_to_next_month, creation_date
    )
    monthly_repayment = _calculate_monthly_payment(
        effective_date, end_date, loan_term, loan_amount, interest_rate_tiers, tier_ranges, creation_date, balances
    )
    posting_ins = vault.make_internal_transfer_instructions(
        amount=monthly_repayment + additional_interest,
        denomination=denomination,
        client_transaction_id=vault.get_hook_execution_id() + "_DUE",
        from_account_id=vault.account_id,
        from_account_address=DUE,
        to_account_id=vault.account_id,
        to_account_address=DEFAULT_ADDRESS,
        instruction_details={
            'description': f'Monthly balance added to due address: {monthly_repayment}'
        },
        asset=DEFAULT_ASSET
    )
    vault.instruct_posting_batch(
        posting_instructions=posting_ins, effective_date=effective_date
    )

# In the last month of the loan, the repayment will be calculated as the sum of all the
# remaining balances, rather than the amortised monthly repayment amount, to ensure that
# the entire debt is repaid before the loan is closed.


def _calculate_monthly_payment(effective_date, end_date, loan_term, loan_amount, interest_rate_tiers, tier_ranges, creation_date, balances):
    natural_end_date = creation_date + timedelta(years=loan_term)
    if end_date.is_set() or natural_end_date < effective_date + timedelta(days=28):
        return sum(
            balance.net for ((address, asset, denomination, phase), balance) in balances.items()
        )
    no_of_periods = 12 * loan_term
    interest_rate = _calculate_tier_values(
        loan_amount, interest_rate_tiers, tier_ranges)
    if interest_rate == 0:
        return _precision_fulfillment(loan_amount / no_of_periods)
    monthly_rate = interest_rate / 12
    top_calc = monthly_rate * ((1 + monthly_rate) ** no_of_periods)
    bottom_calc = ((1 + monthly_rate) ** no_of_periods) - 1
    amortisation = _precision_fulfillment(
        loan_amount * (top_calc / bottom_calc))
    return amortisation


def _calculate_additional_interest(previous_payment_checked, loan_amount, interest_rate_tiers,
                                   tier_ranges, payment_day, roll_over_to_next_month,
                                   creation_date):
    if previous_payment_checked:
        return 0
    first_payment_date = _calculate_first_payment_day(
        payment_day, roll_over_to_next_month, creation_date)
    days_in_creation_month = calendar.monthrange(
        creation_date.year, creation_date.month)[1]
    additional_days = (first_payment_date -
                       creation_date).days - days_in_creation_month
    if not additional_days:
        return 0

    daily_rate = _calculate_daily_interest_rates(
        loan_amount, interest_rate_tiers, tier_ranges)
    return _precision_fulfillment(loan_amount * daily_rate * additional_days)


def _apply_accrued_interest(vault, end_of_day_datetime, internal_account, denomination, balances):
    outgoing_accrued = balances[
        (ACCRUED_INTEREST, DEFAULT_ASSET, denomination, Phase.COMMITTED)
    ].net
    amount_to_be_paid = _precision_fulfillment(outgoing_accrued)
    hook_execution_id = vault.get_hook_execution_id()

    if amount_to_be_paid > 0:
        posting_ins = vault.make_internal_transfer_instructions(
            amount=amount_to_be_paid,
            denomination=denomination,
            from_account_id=vault.account_id,
            from_account_address=DEFAULT_ADDRESS,
            to_account_id=vault.account_id,
            to_account_address=ACCRUED_INTEREST,
            asset=DEFAULT_ASSET,
            client_transaction_id=f'APPLY_ACCRUED_INTEREST_{hook_execution_id}_{denomination}'
            '_CUSTOMER',
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
                from_account_address='ACCRUED_INCOMING',
                to_account_id=internal_account,
                to_account_address=DEFAULT_ADDRESS,
                asset=DEFAULT_ASSET,
                client_transaction_id='APPLY_ACCRUED_INTEREST_{hook_execution_id}_{denomination}'
                '_INTERNAL',
                instruction_details={
                    'description': 'Interest Applied',
                    'event': 'APPLY_ACCRUED_INTEREST'
                }
            )
        )
        vault.instruct_posting_batch(
            posting_instructions=posting_ins,
            effective_date=end_of_day_datetime,
            client_batch_id=f'APPLY_ACCRUED_INTEREST_{hook_execution_id}_{denomination}'
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


def _calculate_next_payment_date(payment_day, effective_date):
    next_payment_date = effective_date.replace(day=payment_day)
    if next_payment_date < effective_date + timedelta(months=28):
        next_payment_date = next_payment_date + timedelta(months=1)
    return next_payment_date


def _yearly_to_daily_rate(yearly_rate):
    days_in_year = 365  # this is could be checking if the current year is leap and then use 366
    return yearly_rate / days_in_year


def _precision_accrual(amount):
    return amount.copy_abs().quantize(Decimal('.0001'), rounding=ROUND_HALF_UP)


def _precision_fulfillment(amount):
    return amount.copy_abs().quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
