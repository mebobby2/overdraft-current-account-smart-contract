# Understand the cashflows (Postings and Balances)
![Alt Cashflows](personal_loan/cashflows.png "Cashflows")


## On account creation
```
"posting_instructions": [
    {
      "id": "8f00d483-ddef-416a-9853-69085a823b80",
      "client_transaction_id": "main_account_3__1546333200000000000_PRINCIPAL",
      "custom_instruction": {
        "postings": [
          {
            "credit": false,
            "amount": "10000",
            "denomination": "GBP",
            "account_id": "main_account",
            "account_address": "DEFAULT",
            "asset": "COMMERCIAL_BANK_MONEY",
            "phase": "POSTING_PHASE_COMMITTED"
          },
          {
            "credit": true,
            "amount": "10000",
            "denomination": "GBP",
            "account_id": "12345",
            "account_address": "DEFAULT",
            "asset": "COMMERCIAL_BANK_MONEY",
            "phase": "POSTING_PHASE_COMMITTED"
          }
        ]
      },

    ...
]
```
We move 10000 from the main_account (where the personal loan sits) to the borrower's account (12334)

The balances look like this:
```
"balances": {
    "12345": {
      "balances": [
        {
          "id": "",
          "account_id": "12345",
          "account_address": "DEFAULT",
          "phase": "POSTING_PHASE_COMMITTED",
          "asset": "COMMERCIAL_BANK_MONEY",
          "denomination": "GBP",
          "posting_instruction_batch_id": "",
          "update_posting_instruction_batch_id": "",
          "value_time": "2019-01-01T09:00:00Z",
          "amount": "10000",
          "total_debit": "0",
          "total_credit": "10000"
        }
      ]
    },
    "main_account": {
      "balances": [
        {
          "id": "",
          "account_id": "main_account",
          "account_address": "DEFAULT",
          "phase": "POSTING_PHASE_COMMITTED",
          "asset": "COMMERCIAL_BANK_MONEY",
          "denomination": "GBP",
          "posting_instruction_batch_id": "",
          "update_posting_instruction_batch_id": "",
          "value_time": "2019-01-01T09:00:00Z",
          "amount": "10000",
          "total_debit": "10000",
          "total_credit": "0"
        }
      ]
    }
  },
```

Notice the total_debit and total_credit fields. These are the fields that show you which way the cash is flowing. Debit = flowing out of the account, Credit = flowing into the account.

## On interest accural
```
"posting_instructions": [
  {
    "id": "ce707f03-d85b-402b-946c-9a1d04ff4675",
    "client_transaction_id": "main_account_5_ACCRUED_INTEREST_1546387200000000000_PRINCIPAL",
    "custom_instruction": {
      "postings": [
        {
          "credit": false,
          "amount": "0.8219",
          "denomination": "GBP",
          "account_id": "main_account",
          "account_address": "ACCRUED_INTEREST",
          "asset": "COMMERCIAL_BANK_MONEY",
          "phase": "POSTING_PHASE_COMMITTED"
        },
        {
          "credit": true,
          "amount": "0.8219",
          "denomination": "GBP",
          "account_id": "1",
          "account_address": "ACCRUED_INCOMING",
          "asset": "COMMERCIAL_BANK_MONEY",
          "phase": "POSTING_PHASE_COMMITTED"
        }
      ]
    },
```

We take 0.8219 (DAILY interest on the principal) from the ACCRUED_INTEREST and put it into the ACCRUED_INCOMING addresses of the two accounts. Interest rates are usually yearly, so, we have to divide it by 365 to get the daily.

It's important to note that the 0.8219 is DEBITED (credit=false) from the ACCRUED_INTEREST address (this becomes important later in 'On interest charged' section). This essentially means the ACCRUED_INTEREST account is negative for that month.

The balances for this batch of postings are
```
"balances": {
    "1": {
      "balances": [
        {
          "id": "",
          "account_id": "1",
          "account_address": "ACCRUED_INCOMING",
          "phase": "POSTING_PHASE_COMMITTED",
          "asset": "COMMERCIAL_BANK_MONEY",
          "denomination": "GBP",
          "posting_instruction_batch_id": "",
          "update_posting_instruction_batch_id": "",
          "value_time": "2019-01-02T00:00:00Z",
          "amount": "0.8219",
          "total_debit": "0",
          "total_credit": "0.8219"
        }
      ]
    },
    "main_account": {
      "balances": [
        {
          "id": "",
          "account_id": "main_account",
          "account_address": "ACCRUED_INTEREST",
          "phase": "POSTING_PHASE_COMMITTED",
          "asset": "COMMERCIAL_BANK_MONEY",
          "denomination": "GBP",
          "posting_instruction_batch_id": "",
          "update_posting_instruction_batch_id": "",
          "value_time": "2019-01-02T00:00:00Z",
          "amount": "0.8219",
          "total_debit": "0.8219",
          "total_credit": "0"
        },
        {
          "id": "",
          "account_id": "main_account",
          "account_address": "DEFAULT",
          "phase": "POSTING_PHASE_COMMITTED",
          "asset": "COMMERCIAL_BANK_MONEY",
          "denomination": "GBP",
          "posting_instruction_batch_id": "",
          "update_posting_instruction_batch_id": "",
          "value_time": "2019-01-01T09:00:00Z",
          "amount": "10000",
          "total_debit": "10000",
          "total_credit": "0"
        }
      ]
    }
  },
```

## On interest charged
```
"posting_instructions": [
    {
      "id": "e07a98ca-d6c8-421b-b482-f2f9c7b5e7a0",
      "client_transaction_id": "APPLY_ACCRUED_INTEREST_main_account_5_APPLY_INTEREST_1548979201000000000_GBP_CUSTOMER",
      "custom_instruction": {
        "postings": [
          {
            "credit": false,
            "amount": "25.48",
            "denomination": "GBP",
            "account_id": "main_account",
            "account_address": "DEFAULT",
            "asset": "COMMERCIAL_BANK_MONEY",
            "phase": "POSTING_PHASE_COMMITTED"
          },
          {
            "credit": true,
            "amount": "25.48",
            "denomination": "GBP",
            "account_id": "main_account",
            "account_address": "ACCRUED_INTEREST",
            "asset": "COMMERCIAL_BANK_MONEY",
            "phase": "POSTING_PHASE_COMMITTED"
          }
        ]
      },
```

We debit 25.48 (the full interest for that month) from the DEFAULT address and credit it to the ACCRUED_INTEREST address. From the 'On interest accural' section we said that the ACCRUED_INTEREST is in negative...well, this step essentially makes it positive again since we are crediting into it.

We also then make additional postings to transfer the monthly interested in the ACCRUED_INCOMING address of the internal account to the DEFAULT address.

The balances:
```
"custom_instruction": {
    "postings": [
      {
        "credit": false,
        "amount": "25.48",
        "denomination": "GBP",
        "account_id": "1",
        "account_address": "ACCRUED_INCOMING",
        "asset": "COMMERCIAL_BANK_MONEY",
        "phase": "POSTING_PHASE_COMMITTED"
      },
      {
        "credit": true,
        "amount": "25.48",
        "denomination": "GBP",
        "account_id": "1",
        "account_address": "DEFAULT",
        "asset": "COMMERCIAL_BANK_MONEY",
        "phase": "POSTING_PHASE_COMMITTED"
      }
    ]
  },
```

This is self explanatory. During the month, the daily interest is accrued into the ACCRUED_INCOMING address. At the end of the pay (or pay day) we transfer it into the DEFAULT space.

And finally, the balances for all four postings above:
```
"balances": {
    "1": {
      "balances": [
        {
          "id": "",
          "account_id": "1",
          "account_address": "ACCRUED_INCOMING",
          "phase": "POSTING_PHASE_COMMITTED",
          "asset": "COMMERCIAL_BANK_MONEY",
          "denomination": "GBP",
          "posting_instruction_batch_id": "",
          "update_posting_instruction_batch_id": "",
          "value_time": "2019-02-01T00:00:01Z",
          "amount": "-0.0011",
          "total_debit": "25.48",
          "total_credit": "25.4789"
        },
        {
          "id": "",
          "account_id": "1",
          "account_address": "DEFAULT",
          "phase": "POSTING_PHASE_COMMITTED",
          "asset": "COMMERCIAL_BANK_MONEY",
          "denomination": "GBP",
          "posting_instruction_batch_id": "",
          "update_posting_instruction_batch_id": "",
          "value_time": "2019-02-01T00:00:01Z",
          "amount": "25.48",
          "total_debit": "0",
          "total_credit": "25.48"
        }
      ]
    },
    "main_account": {
      "balances": [
        {
          "id": "",
          "account_id": "main_account",
          "account_address": "DEFAULT",
          "phase": "POSTING_PHASE_COMMITTED",
          "asset": "COMMERCIAL_BANK_MONEY",
          "denomination": "GBP",
          "posting_instruction_batch_id": "",
          "update_posting_instruction_batch_id": "",
          "value_time": "2019-02-01T00:00:01Z",
          "amount": "10025.48",
          "total_debit": "10025.48",
          "total_credit": "0"
        },
        {
          "id": "",
          "account_id": "main_account",
          "account_address": "ACCRUED_INTEREST",
          "phase": "POSTING_PHASE_COMMITTED",
          "asset": "COMMERCIAL_BANK_MONEY",
          "denomination": "GBP",
          "posting_instruction_batch_id": "",
          "update_posting_instruction_batch_id": "",
          "value_time": "2019-02-01T00:00:01Z",
          "amount": "-0.0011",
          "total_debit": "25.4789",
          "total_credit": "25.48"
        }
      ]
    }
  },
```
