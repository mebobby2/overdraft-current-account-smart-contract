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
    description='Default denomination.',
    display_name='Default denomination for the contract.',
  ),
]

@requires(parameters=True)
def pre_posting_code(postings, effective_date):
    denomination = vault.get_parameter_timeseries(name='denomination').latest()

    if any(post.denomination != denomination for post in postings):
        raise Rejected(
            'Cannot make transactions in given denomination; '
            'transactions must be in {}'.format('GBP'),
            reason_code=RejectedReason.WRONG_DENOMINATION,
        )
