# flake8: noqa
import json
from collections import defaultdict


def create_deposit_instruction(
    *,
    amount,
    timestamp,
    denomination="GBP",
    target_account_id="main_account",
    client_batch_id="123",
    client_transaction_id="123456",
    batch_description="",
    instruction_description="",
    internal_account_id="12345",
):
    deposit_instruction = {
        "create_posting_instruction_batch": {
            "client_id": "Visa",
            "client_batch_id": client_batch_id,
            "posting_instructions": [
                {
                    "inbound_hard_settlement": {
                        "amount": amount,
                        "denomination": denomination,
                        "target_account": {
                            "account_id": target_account_id,
                        },
                        "internal_account_id": internal_account_id,
                    },
                    "client_transaction_id": client_transaction_id,
                    "instruction_details": {"description": instruction_description},
                }
            ],
            "batch_details": {"description": batch_description},
            "value_timestamp": timestamp,
        }
    }
    return deposit_instruction


def create_withdrawal_instruction(
    *,
    amount,
    timestamp,
    denomination="GBP",
    target_account_id="main_account",
    client_batch_id="123",
    client_transaction_id="1234567",
    batch_description="",
    instruction_description="",
    internal_account_id="12345",
):
    withdrawal_instruction = {
        "create_posting_instruction_batch": {
            "client_id": "Visa",
            "client_batch_id": client_batch_id,
            "posting_instructions": [
                {
                    "outbound_hard_settlement": {
                        "amount": amount,
                        "denomination": denomination,
                        "target_account": {
                            "account_id": target_account_id,
                        },
                        "internal_account_id": internal_account_id,
                    },
                    "client_transaction_id": client_transaction_id,
                    "instruction_details": {"description": instruction_description},
                }
            ],
            "batch_details": {"description": batch_description},
            "value_timestamp": timestamp,
        }
    }
    return withdrawal_instruction


def get_final_balances(balances_timeseries):
    final_balances = defaultdict()
    for balance in balances_timeseries:
        final_balances[balance["account_address"]] = balance["amount"]
    return final_balances
