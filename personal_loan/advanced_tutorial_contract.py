api = '3.0.0'
tside = Tside.ASSET

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
