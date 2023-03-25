# Copyright @ 2022 Thought Machine Group Limited. All rights reserved.

api = "3.12.0"
version = "0.0.1"

supervised_smart_contracts = [
    SmartContractDescriptor(
        alias="deposit",
        smart_contract_version_id="1.0.1",
        supervised_hooks=SupervisedHooks(pre_posting_code=SupervisionExecutionMode.INVOKED),
        supervise_post_posting_hook=False,
   ),
]

data_fetchers = [
    BalancesObservationFetcher(
        fetcher_id="live_balances",
        at=DefinedDateTime.LIVE,
    )
]
event_types = [
    EventType(
        name="MONTHLY_FEE",
        overrides_event_types=[("deposit", "MONTHLY_FEE")],
    ),
]

@requires(data_scope="all", parameters=True)
def execution_schedules():
    start_date = vault.get_plan_creation_date()
    schedule_cron = _get_next_month_schedule(start_date, timedelta(months=1))
    return [
        ("MONTHLY_FEE", schedule_cron),
    ]

@requires(
    event_type="MONTHLY_FEE",
    data_scope="all",
    supervisee_hook_directives="all",
    parameters=True,
    postings="1 month",
)
def scheduled_code(event_type, effective_date):
    if event_type == "MONTHLY_FEE":
        deposit_acct_vaults = _get_supervisees_for_alias(vault, "deposit")
        ignored_types = [
            "APPLY_INTEREST",
            "MONTHLY_FEE",
            "OPENING_BONUS",
        ]
        deposits = 0
        for deposit_acct_vault in deposit_acct_vaults:
            postings = deposit_acct_vault.get_postings()
            for posting in postings:
                if posting.instruction_details.get("event_type") not in ignored_types:
                    deposits += 1
        if deposits < len(deposit_acct_vaults):
            for deposit_acct_vault in deposit_acct_vaults:
                deposit_hook_directives = deposit_acct_vault.get_hook_directives()
                deposit_pib_directives = deposit_hook_directives.posting_instruction_batch_directives
                if not deposit_pib_directives:
                    continue

                posting_ins = []
                for pib_directive in deposit_pib_directives:
                    pib = pib_directive.posting_instruction_batch
                    for posting in pib:
                        posting_ins.append(posting)

                if posting_ins:
                    deposit_acct_vault.instruct_posting_batch(
                        posting_instructions=posting_ins, effective_date=effective_date
                    )
        new_schedule = _get_next_month_schedule(
            effective_date,
            timedelta(months=1),
        )
        vault.update_event_type(
            event_type="MONTHLY_FEE",
            schedule=EventTypeSchedule(
                year=new_schedule["year"],
                month=new_schedule["month"],
                day=new_schedule["day"],
                hour=new_schedule["hour"],
                minute=new_schedule["minute"],
                second=new_schedule["second"],
            ),
        )

@requires(parameters=True, data_scope="all")
@fetch_account_data(
    balances={"deposit": ["live_balances"]},
)
def pre_posting_code(postings: PostingInstructionBatch, effective_date: datetime):
    # Check there are supervisees
    deposit_acct_vaults = _get_supervisees_for_alias(vault, "deposit")
    if not deposit_acct_vaults:
        raise Rejected(
            "Cannot process postings until a deposit account is associated to the plan",
            reason_code=RejectedReason.CLIENT_CUSTOM_REASON,
        )

    # For now assume all deposit accounts have the same denomination
    deposit_acct_vault = deposit_acct_vaults[0]
    denomination = deposit_acct_vault.get_parameter_timeseries(name="denomination").latest()

    if len(postings) > 1:
        raise Rejected(
            "Currently we do not support more than one posting instruction per batch"
        )
    if postings[0].credit:
        _validate_deposit_limits(deposit_acct_vaults, denomination, postings[0])


def _validate_deposit_limits(
    deposit_vaults: list, denomination: str, posting: PostingInstruction
) -> None:
    """
    Determine whether a deposit to one of the accounts should be accepted, raising
    Rejected exceptions otherwise

    :param deposit_vaults: deposit account vault objects.
    :param denomination: the denomination of the loc and loan accounts
    :param posting: the posting to process
    :raises: Rejected if the deposit should not be accepted
    :return: None
    """
    total_limit = 0
    total_balance = posting.amount
    for deposit_vault in deposit_vaults:
        # This is how the balance dictionary is fetched using the
        # live balances Fetcher ID
        balances = deposit_vault.get_balances_observation(
            fetcher_id="live_balances"
        ).balances
        total_balance += balances[(
            DEFAULT_ADDRESS,
            DEFAULT_ASSET,
            denomination,
            Phase.COMMITTED,
        )].net
        total_limit += Decimal(
            deposit_vault.get_parameter_timeseries(name="maximum_balance_limit").latest()
        )
    if total_balance > total_limit:
        raise Rejected(
            f"Total balance {total_balance} exceed total limit {total_limit} "
            "across all deposit accounts",
            reason_code=RejectedReason.AGAINST_TNC,
        )

def _get_supervisees_for_alias(vault, alias: str) -> list:
    """
    Returns a list of supervisee vault objects for the given alias, ordered by account creation date
    :param vault: vault, supervisor vault object
    :param alias: str, the supervisee alias to filter for
    :return: list, supervisee vault objects for given alias, ordered by account creation date
    """
    return _sort_supervisees(
        [
            supervisee
            for supervisee in vault.supervisees.values()
            if supervisee.get_alias() == alias
        ],
    )


def _sort_supervisees(supervisees: list) -> list:
    """
    Sorts supervisees first by creation date, and then alphabetically by id if
    numerous supervisees share the same creation date and creates a list of ordered
    vault objects.
    :param supervisees: list[Vault], list of supervisee vault objects
    :return sorted_supervisees: list[Vault], list of ordered vault objects
    """
    sorted_supervisees_by_id = sorted(supervisees, key=lambda vault: vault.account_id)
    sorted_supervisees_by_age_then_id = sorted(
        sorted_supervisees_by_id, key=lambda vault: vault.get_account_creation_date()
    )

    return sorted_supervisees_by_age_then_id

def _get_next_month_schedule(start_date, offset):
   next_schedule_date = start_date + offset

   return {
       "year": str(next_schedule_date.year),
       "month": str(next_schedule_date.month),
       "day": str(next_schedule_date.day),
       "hour": "0",
       "minute": "10",
       "second": "0",
   }
