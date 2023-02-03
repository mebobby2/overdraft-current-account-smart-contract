import sys
sys.path.append("..")


import json  # this needs to be added
import vault_caller
from datetime import datetime, timezone
from decimal import Decimal
import os
import unittest
import products_test_utils

core_api_url = "https://core-api.public-sandbox.partner.tmachine.io"
auth_token = "A0003256414797670411991!FZ/D4LwwwqJMTyKW644WAqJkf/uXg7sC7LhWNtl7kL5dVCA7NDz6KQVLcMsei1O8eXBwxked7hNvZWQ9YXmrR8OPG+M="

CONTRACT_FILE = './advanced_tutorial_contract.py'


class TutorialTest(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        contract = os.path.join(os.path.dirname(__file__), CONTRACT_FILE)
        if not core_api_url or not auth_token:
            raise ValueError(
                "Please provide values for core_api_url and auth_token.")
        with open(contract) as smart_contract_file:
            self.smart_contract_contents = smart_contract_file.read()
        self.client = vault_caller.Client(
            core_api_url=core_api_url,
            auth_token=auth_token
        )

    def test_initial_fund_movement(self):
        start = datetime(year=2019, month=1, day=1, tzinfo=timezone.utc)
        end = datetime(year=2019, month=1, day=2, tzinfo=timezone.utc)
        template_params = {
            'denomination': 'GBP',
            'gross_interest_rate_tiers': json.dumps(
                {
                    'tier1': '0.135',
                    'tier2': '0.098',
                    'tier3': '0.045',
                    'tier4': '0.03',
                    'tier5': '0.035'
                }
            ),
            'tier_ranges': json.dumps(
                {
                    "tier1": {"min": 1000, "max": 2999},
                    "tier2": {"min": 3000, "max": 4999},
                    "tier3": {"min": 5000, "max": 7499},
                    "tier4": {"min": 7500, "max": 14999},
                    "tier5": {"min": 15000, "max": 20000}
                }
            ),
            'internal_account': '1',
        }
        instance_params = {
            'loan_amount': '10000',
            'deposit_account': '12345'
        }
        res = self.client.simulate_contracts(
            start_timestamp=start,
            end_timestamp=end,
            smart_contracts=[
                {
                    "smart_contract_version_id": "1",
                    "code": self.smart_contract_contents,
                    "smart_contract_param_vals": template_params,
                },
                {
                    "smart_contract_version_id": "2",
                    "code": "api = '3.6.0'",
                },
                {
                    "smart_contract_version_id": "3",
                    "code": "api = '3.6.0'",
                },
            ],
            instructions=[
                vault_caller.SimulationInstruction(start, {
                    "create_account": {
                        "id": "main_account",
                        "product_version_id": "1",
                        "instance_param_vals": instance_params,
                    }
                }),
                vault_caller.SimulationInstruction(start, {
                    "create_account": {
                        "id": "1",
                        "product_version_id": "2",
                    }
                }),
                vault_caller.SimulationInstruction(start, {
                    "create_account": {
                        "id": "12345",
                        "product_version_id": "3",
                    }
                })
            ],
        )
        final_account_balance = res[-1]["result"]["balances"]["main_account"]["balances"][0]
        self.assertEqual(float(final_account_balance["amount"]), 10000)

    def test_interest_accruals(self):
        # We want to test that at 12:00 AM interest is accrued
        start = datetime(year=2019, month=1, day=1,
                         hour=9, tzinfo=timezone.utc)
        end = datetime(year=2019, month=1, day=2, hour=9, tzinfo=timezone.utc)
        template_params = {
            'denomination': 'GBP',
            'gross_interest_rate_tiers': json.dumps(
                {
                    'tier1': '0.135',
                    'tier2': '0.098',
                    'tier3': '0.045',
                    'tier4': '0.03',
                    'tier5': '0.035'
                }
            ),
            'tier_ranges': json.dumps(
                {
                    "tier1": {"min": 1000, "max": 2999},
                    "tier2": {"min": 3000, "max": 4999},
                    "tier3": {"min": 5000, "max": 7499},
                    "tier4": {"min": 7500, "max": 14999},
                    "tier5": {"min": 15000, "max": 20000}
                }
            ),
            'internal_account': '1',
        }
        instance_params = {
            'loan_amount': '10000',
            'deposit_account': '12345'
        }
        res = self.client.simulate_contracts(
            start_timestamp=start,
            end_timestamp=end,
            smart_contracts=[
                {
                    "smart_contract_version_id": "1",
                    "code": self.smart_contract_contents,
                    "smart_contract_param_vals": template_params,
                },
                {
                    "smart_contract_version_id": "2",
                    "code": "api = '3.6.0'",
                },
                {
                    "smart_contract_version_id": "3",
                    "code": "api = '3.6.0'",
                },
            ],
            instructions=[
                vault_caller.SimulationInstruction(start, {
                    "create_account": {
                        "id": "main_account",
                        "product_version_id": "1",
                        "instance_param_vals": instance_params,
                    }
                }),
                # Our deposit account.
                vault_caller.SimulationInstruction(start, {
                    "create_account": {
                        "id": "1",
                        "product_version_id": "2",
                    }
                }),
                # Our internal account.
                vault_caller.SimulationInstruction(start, {
                    "create_account": {
                        "id": "12345",
                        "product_version_id": "3",
                    }
                })
            ],
        )
        final_account_balances = res[-1]["result"]["balances"]["main_account"]["balances"]
        interest_balance = next(
            balance
            for balance in final_account_balances
            if "ACCRUED_INTEREST" in balance["account_address"]
        )
        self.assertEqual(float(interest_balance["amount"]), 0.8219)
