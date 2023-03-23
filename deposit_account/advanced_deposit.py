from decimal import Decimal
from typing import Union, Optional
from dateutil.relativedelta import relativedelta
from contracts_api import (
    BalanceCoordinate,
    BalanceDefaultDict,
    BalancesObservationFetcher,
    DefinedDateTime,
    DEFAULT_ADDRESS,
    DEFAULT_ASSET,
    fetch_account_data,
    ParameterLevel,
    Parameter,
    ParameterUpdatePermission,
    Phase,
    Posting,
    PostingInstructionsDirective,
    PostingInstructionType,
    PostingsIntervalFetcher,
    Rejection,
    RejectionReason,
    RelativeDateTime,
    requires,
    ScheduledEvent,
    ScheduleExpression,
    Shift,
    SmartContractEventType,
    TransactionCode,
    Tside,
    UpdateAccountEventTypeDirective,
    # hook arguments and results
    ActivationHookArguments,
    ActivationHookResult,
    DerivedParameterHookArguments,
    DerivedParameterHookResult,
    PrePostingHookArguments,
    PrePostingHookResult,
    ScheduledEventHookArguments,
    ScheduledEventHookResult,
    # shapes
    AccountIdShape,
    DenominationShape,
    NumberShape,
    # posting types
    AuthorisationAdjustment,
    CustomInstruction,
    InboundAuthorisation,
    InboundHardSettlement,
    OutboundAuthorisation,
    OutboundHardSettlement,
    Release,
    Settlement,
    Transfer,
)

api = "4.0.0"
version = "1.0.0"
tside = Tside.LIABILITY
supported_denominations = ["GBP"]

parameters = [
    Parameter(
        name="denomination",
        shape=DenominationShape(),
        level=ParameterLevel.TEMPLATE,
        display_name="Denomination",
        description="The default denomination of the account.",
        update_permission=ParameterUpdatePermission.USER_EDITABLE,
    ),
    Parameter(
        name="maximum_balance_limit",
        display_name="Maximum Deposit Limit",
        description="The maximum balance possible for this account.",
        level=ParameterLevel.TEMPLATE,
        shape=NumberShape(min_value=0, max_value=100000, step=Decimal("0.01")),
        default_value=Decimal("100000"),
    ),
    Parameter(
        name="deposit_bonus_payout_internal_account",
        display_name="Deposit Bonus Payout Internal Account",
        description="The internal account to debit bonus payments from.",
        level=ParameterLevel.TEMPLATE,
        shape=AccountIdShape(),
        default_value="DEPOSIT_BONUS_PAYOUT_INTERNAL_ACCOUNT",
    ),
    Parameter(
        name="interest_rate",
        display_name="Interest Rate (APR)",
        description="The interest rate of the account.",
        level=ParameterLevel.TEMPLATE,
        shape=NumberShape(min_value=0, max_value=1, step=Decimal("0.001")),
        default_value=Decimal("0.01"),
    ),
    Parameter(
        name="interest_paid_internal_account",
        display_name="Interest Paid Internal Account",
        description="The internal account to debit interest payments from.",
        level=ParameterLevel.TEMPLATE,
        shape=AccountIdShape(),
        default_value="INTEREST_PAID_INTERNAL_ACCOUNT",
    ),
    Parameter(
        name="monthly_fee",
        display_name="Monthly Fee",
        description="The monthly fee charged to the account depending on the number of deposits.",
        level=ParameterLevel.TEMPLATE,
        shape=NumberShape(min_value=0, max_value=20, step=Decimal("0.01")),
        default_value=Decimal("10"),
    ),
    Parameter(
        name="monthly_fee_income_internal_account",
        display_name="Monthly Fee Income Internal Account",
        description="The internal account to credit the monthly fee from.",
        level=ParameterLevel.TEMPLATE,
        shape=AccountIdShape(),
        default_value="MONTHLY_FEE_INCOME_INTERNAL_ACCOUNT",
    ),
    Parameter(
        name="opening_withdrawal_lockout_period",
        display_name="Opening Withdrawal Lockout Period",
        description="The number of days after account opening in which withdrawals are not allowed.",
        level=ParameterLevel.TEMPLATE,
        shape=NumberShape(min_value=0, max_value=10, step=1),
        default_value=Decimal("7"),
    ),
    # instance parameters
    Parameter(
        name="opening_bonus",
        display_name="Opening Bonus",
        description="The bonus amount to credit the account upon opening.",
        level=ParameterLevel.INSTANCE,
        shape=NumberShape(min_value=0, max_value=100, step=Decimal("0.01")),
        update_permission=ParameterUpdatePermission.OPS_EDITABLE,
        default_value=Decimal("100.00"),
    ),
    # derived parameters
    Parameter(
        name="available_deposit_limit",
        display_name="Available Deposit Limit",
        description="The available deposit limit remaining based on current account balance.",
        level=ParameterLevel.INSTANCE,
        shape=NumberShape(min_value=0, step=1),
        derived=True,
    ),
]

data_fetchers = [
    BalancesObservationFetcher(
        fetcher_id="live_balances",
        at=DefinedDateTime.LIVE,
    ),
    PostingsIntervalFetcher(
        fetcher_id="1_month",
        start=RelativeDateTime(
            origin=DefinedDateTime.EFFECTIVE_DATETIME,
            shift=Shift(months=-1),
        ),
        end=DefinedDateTime.EFFECTIVE_DATETIME,
    ),
]

# event types
APPLY_INTEREST = "APPLY_INTEREST"
MONTHLY_FEE = "MONTHLY_FEE"

event_types = [
    SmartContractEventType(
        name=APPLY_INTEREST,
    ),
    SmartContractEventType(
        name=MONTHLY_FEE,
    ),
]


@requires(parameters=True)
@fetch_account_data(balances=["live_balances"])
def derived_parameter_hook(vault, hook_arguments: DerivedParameterHookArguments):
    denomination = vault.get_parameter_timeseries(name="denomination").latest()
    deposit_limit = Decimal(
        vault.get_parameter_timeseries(name="maximum_balance_limit").latest()
    )

    balances = vault.get_balances_observation(fetcher_id="live_balances").balances
    default_balance = balances[
        BalanceCoordinate(DEFAULT_ADDRESS, DEFAULT_ASSET, denomination, Phase.COMMITTED)
    ].net

    available_deposit_limit = deposit_limit - default_balance

    return DerivedParameterHookResult(
        parameters_return_value={"available_deposit_limit": available_deposit_limit}
    )


@requires(parameters=True)
@fetch_account_data(balances=["live_balances"])
def pre_posting_hook(vault, hook_arguments: PrePostingHookArguments):
    denomination = vault.get_parameter_timeseries(name="denomination").latest()

    # check denomination
    posting_instructions = hook_arguments.posting_instructions

    posting_denominations_used = set(post.denomination for post in posting_instructions)
    disallowed_denominations_used = posting_denominations_used.difference(
        [denomination]
    )
    if disallowed_denominations_used:
        return PrePostingHookResult(
            rejection=Rejection(
                message=f"Only postings in {denomination} are allowed.",
                reason_code=RejectionReason.WRONG_DENOMINATION,
            )
        )

    # check deposit limit
    deposit_limit = Decimal(
        vault.get_parameter_timeseries(name="maximum_balance_limit").latest()
    )
    # check existing account balance on the DEFAULT address using the fetcher
    balances = vault.get_balances_observation(fetcher_id="live_balances").balances
    default_balance = balances[
        BalanceCoordinate(DEFAULT_ADDRESS, DEFAULT_ASSET, denomination, Phase.COMMITTED)
    ].net

    # check expected total balance taking into account existing balance and incoming postings
    incoming_postings_amount = total_balances(hook_arguments.posting_instructions)[
        BalanceCoordinate(DEFAULT_ADDRESS, DEFAULT_ASSET, denomination, Phase.COMMITTED)
    ].net
    expected_balance_total = incoming_postings_amount + default_balance

    if expected_balance_total > deposit_limit:
        return PrePostingHookResult(
            rejection=Rejection(
                message=f"Incoming deposit breaches deposit limit of {deposit_limit}.",
                reason_code=RejectionReason.AGAINST_TNC,
            )
        )

    # check opening withdrawal lockout period
    account_creation_date = vault.get_account_creation_datetime()
    opening_withdrawal_lockout_period = int(
        vault.get_parameter_timeseries(
            name="opening_withdrawal_lockout_period"
        ).latest()
    )

    withdrawal_lockout_period_end = account_creation_date + relativedelta(
        days=opening_withdrawal_lockout_period
    )
    withdrawal_types = [
        PostingInstructionType.OUTBOUND_AUTHORISATION,
        PostingInstructionType.OUTBOUND_HARD_SETTLEMENT,
    ]
    for posting in hook_arguments.posting_instructions:
        if (
            posting.amount > 0
            and posting.type in withdrawal_types
            and hook_arguments.effective_datetime <= withdrawal_lockout_period_end
        ):
            return PrePostingHookResult(
                rejection=Rejection(
                    message="Withdrawals not allowed during withdrawal lockout period.",
                    reason_code=RejectionReason.AGAINST_TNC,
                )
            )


@requires(parameters=True)
def activation_hook(
    vault, hook_arguments: ActivationHookArguments
) -> Optional[ActivationHookResult]:
    denomination = vault.get_parameter_timeseries(name="denomination").latest()
    opening_bonus = Decimal(
        vault.get_parameter_timeseries(name="opening_bonus").latest()
    )
    bonus_internal_account = vault.get_parameter_timeseries(
        name="deposit_bonus_payout_internal_account"
    ).latest()

    posting_instruction = _move_funds_between_vault_accounts(
        from_account_id=bonus_internal_account,
        from_account_address=DEFAULT_ADDRESS,
        to_account_id=vault.account_id,
        to_account_address=DEFAULT_ADDRESS,
        asset=DEFAULT_ASSET,
        denomination=denomination,
        amount=opening_bonus,
        instruction_details={
            # CLv4 has no client transaction ID - this is for compatibility with legacy integrations
            "ext_client_transaction_id": f"OPENING_BONUS_{vault.get_hook_execution_id()}",
            "description": f"Opening bonus of {opening_bonus} {denomination} paid.",
            "event_type": f"OPENING_BONUS",
        },
        override_all_restrictions=True,
    )

    account_creation_date = vault.get_account_creation_datetime()

    one_month_later_schedule_expression = _get_next_schedule_expression(
        account_creation_date, relativedelta(months=1)
    )
    return ActivationHookResult(
        posting_instructions_directives=[
            PostingInstructionsDirective(
                posting_instructions=posting_instruction,
                value_datetime=hook_arguments.effective_datetime,
            )
        ],
        scheduled_events_return_value={
            APPLY_INTEREST: ScheduledEvent(
                start_datetime=hook_arguments.effective_datetime,
                expression=one_month_later_schedule_expression,
            ),
            MONTHLY_FEE: ScheduledEvent(
                start_datetime=hook_arguments.effective_datetime,
                expression=one_month_later_schedule_expression,
            ),
        },
    )


@requires(event_type="APPLY_INTEREST", parameters=True)
@fetch_account_data(event_type="APPLY_INTEREST", balances=["live_balances"])
@requires(event_type="MONTHLY_FEE", parameters=True)
@fetch_account_data(event_type="MONTHLY_FEE", postings=["1_month"])
def scheduled_event_hook(vault, hook_arguments: ScheduledEventHookArguments):
    if hook_arguments.event_type == APPLY_INTEREST:
        scheduled_event_hook_result = _handle_apply_interest_schedule(
            vault, hook_arguments
        )
    if hook_arguments.event_type == MONTHLY_FEE:
        scheduled_event_hook_result = _handle_monthly_fee_schedule(
            vault, hook_arguments
        )
    return scheduled_event_hook_result


def _handle_apply_interest_schedule(vault, hook_arguments):
    denomination = vault.get_parameter_timeseries(name="denomination").latest()
    interest_rate = vault.get_parameter_timeseries(name="interest_rate").latest()
    interest_paid_internal_account = vault.get_parameter_timeseries(
        name="interest_paid_internal_account"
    ).latest()

    balances = vault.get_balances_observation(fetcher_id="live_balances").balances
    default_balance = balances[
        BalanceCoordinate(DEFAULT_ADDRESS, DEFAULT_ASSET, denomination, Phase.COMMITTED)
    ].net
    daily_interest_rate = interest_rate / 365
    interest_amount = default_balance * (daily_interest_rate * 30)
    interest_amount = Decimal(round(interest_amount))

    if interest_amount > 0:
        posting_instruction = _move_funds_between_vault_accounts(
            from_account_id=interest_paid_internal_account,
            from_account_address=DEFAULT_ADDRESS,
            to_account_id=vault.account_id,
            to_account_address=DEFAULT_ADDRESS,
            asset=DEFAULT_ASSET,
            denomination=denomination,
            amount=interest_amount,
            instruction_details={
                # CLv4 has no client transaction ID - this is for compatibility with legacy integrations
                "ext_client_transaction_id": f"APPLY_INTEREST_{vault.get_hook_execution_id()}",
                "description": (
                    f"Applying interest of {interest_amount} {denomination}"
                    " at daily rate of {daily_interest_rate}."
                ),
                "event_type": f"APPLY_INTEREST",
            },
        )
        posting_instructions_directives = [
            PostingInstructionsDirective(
                posting_instructions=posting_instruction,
                client_batch_id=f"{hook_arguments.event_type}_{vault.get_hook_execution_id()}",
                value_datetime=hook_arguments.effective_datetime,
            )
        ]
    else:
        posting_instructions_directives = []

    update_account_event_type_directives = [
        UpdateAccountEventTypeDirective(
            event_type=APPLY_INTEREST,
            expression=_get_next_schedule_expression(
                hook_arguments.effective_datetime, relativedelta(months=1)
            ),
        )
    ]
    return ScheduledEventHookResult(
        posting_instructions_directives=posting_instructions_directives,
        update_account_event_type_directives=update_account_event_type_directives,
    )


def _handle_monthly_fee_schedule(vault, hook_arguments):
    posting_instructions_directives = []
    update_account_event_type_directives = []
    denomination = vault.get_parameter_timeseries(name="denomination").latest()
    monthly_fee = vault.get_parameter_timeseries(name="monthly_fee").latest()
    monthly_fee_income_internal_account = vault.get_parameter_timeseries(
        name="monthly_fee_income_internal_account"
    ).latest()

    deposits = 0

    posting_instructions = vault.get_posting_instructions(fetcher_id="1_month")
    for posting_instruction in posting_instructions:
        if posting_instruction.type == PostingInstructionType.CUSTOM_INSTRUCTION:
            # custom instructions do not have an "amount" attribute but its postings do
            if (
                posting_instruction.instruction_details.get("event_type")
                != "APPLY_INTEREST"
            ):
                for posting in posting_instruction.postings:
                    if posting.amount > 0:
                        deposits += 1
        else:
            if (
                posting_instruction.amount > 0
                and posting_instruction.instruction_details.get("event_type")
                != "APPLY_INTEREST"
            ):
                deposits += 1

    if not deposits:
        posting_instruction = _move_funds_between_vault_accounts(
            from_account_id=vault.account_id,
            from_account_address=DEFAULT_ADDRESS,
            to_account_id=monthly_fee_income_internal_account,
            to_account_address=DEFAULT_ADDRESS,
            asset=DEFAULT_ASSET,
            denomination=denomination,
            amount=monthly_fee,
            instruction_details={
                "ext_client_transaction_id": f"MONTHLY_FEE_{vault.get_hook_execution_id()}",
                "description": f"Applying monthly fee of {monthly_fee} {denomination}.",
                "event_type": f"MONTHLY_FEE",
            },
        )

        posting_instructions_directives.extend(
            [
                PostingInstructionsDirective(
                    posting_instructions=posting_instruction,
                    value_datetime=hook_arguments.effective_datetime,
                )
            ]
        )
    update_account_event_type_directives.extend(
        [
            UpdateAccountEventTypeDirective(
                event_type=MONTHLY_FEE,
                expression=_get_next_schedule_expression(
                    hook_arguments.effective_datetime, relativedelta(months=1)
                ),
            )
        ]
    )
    return ScheduledEventHookResult(
        posting_instructions_directives=posting_instructions_directives,
        update_account_event_type_directives=update_account_event_type_directives,
    )


def _get_next_schedule_expression(start_date, offset):
    next_schedule_date = start_date + offset
    return ScheduleExpression(
        year=str(next_schedule_date.year),
        month=str(next_schedule_date.month),
        day=str(next_schedule_date.day),
        hour="0",
        minute="10",
        second="0",
    )


def total_balances(
    input_posting_instructions: list[
        Union[
            AuthorisationAdjustment,
            CustomInstruction,
            InboundAuthorisation,
            InboundHardSettlement,
            OutboundAuthorisation,
            OutboundHardSettlement,
            Release,
            Settlement,
            Transfer,
        ]
    ]
) -> BalanceDefaultDict:
    total_balances = BalanceDefaultDict()
    for posting_instruction in input_posting_instructions:
        total_balances += posting_instruction.balances()
    return total_balances


def _move_funds_between_vault_accounts(
    amount: Decimal,
    denomination: str,
    from_account_id: str,
    from_account_address: str,
    to_account_id: str,
    to_account_address: str,
    instruction_details: dict[str, str],
    asset: str = DEFAULT_ASSET,
    transaction_code: Optional[TransactionCode] = None,
    override_all_restrictions: Optional[bool] = None,
) -> list[CustomInstruction]:
    postings = [
        Posting(
            credit=True,
            amount=amount,
            denomination=denomination,
            account_id=to_account_id,
            account_address=to_account_address,
            asset=asset,
            phase=Phase.COMMITTED,
        ),
        Posting(
            credit=False,
            amount=amount,
            denomination=denomination,
            account_id=from_account_id,
            account_address=from_account_address,
            asset=asset,
            phase=Phase.COMMITTED,
        ),
    ]
    custom_instruction = CustomInstruction(
        postings=postings,
        instruction_details=instruction_details,
        transaction_code=transaction_code,
        override_all_restrictions=override_all_restrictions,
    )

    return [custom_instruction]
