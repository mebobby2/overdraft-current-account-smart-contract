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

default_template_params = {
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

default_instance_params = {
    'loan_term': '2',
    'loan_amount': '3000',
    'payment_day': '6',
    'deposit_account': '12345'
}


class TutorialTest(unittest.TestCase):
    def make_simulate_contracts_call(
        self,
        start,
        end,
        template_params,
        instance_params,
        instructions=[],
    ):
        return self.client.simulate_contracts(
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
                vault_caller.SimulationInstruction(
                    start,
                    {
                        "create_account": {
                            "id": "main_account",
                            "product_version_id": "1",
                            "instance_param_vals": instance_params,
                        }
                    },
                ),
                # Our deposit account.
                vault_caller.SimulationInstruction(
                    start,
                    {
                        "create_account": {
                            "id": "1",
                            "product_version_id": "2",
                        }
                    },
                ),
                # Our internal account.
                vault_caller.SimulationInstruction(
                    start,
                    {
                        "create_account": {
                            "id": "12345",
                            "product_version_id": "3",
                        }
                    },
                ),
            ]
            + instructions,
        )

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

        res = self.make_simulate_contracts_call(
            start, end, default_template_params, default_instance_params)

        final_account_balance = res[-1]["result"]["balances"]["main_account"]["balances"][0]
        self.assertEqual(float(final_account_balance["amount"]), 3000)

    def test_interest_accruals(self):
        # We want to test that at 12:00 AM interest is accrued
        start = datetime(year=2019, month=1, day=1,
                         hour=9, tzinfo=timezone.utc)
        end = datetime(year=2019, month=1, day=2, hour=9, tzinfo=timezone.utc)

        res = self.make_simulate_contracts_call(
            start, end, default_template_params, default_instance_params)

        # print(json.dumps(res, indent=2))

        final_account_balances = res[-1]["result"]["balances"]["main_account"]["balances"]
        interest_balance = next(
            balance
            for balance in final_account_balances
            if "ACCRUED_INTEREST" in balance["account_address"]
        )
        self.assertEqual(float(interest_balance["amount"]), 0.8055)

    def test_interest_charges(self):
        # We want to test that at 12:00:01 AM interest is charged
        start = datetime(year=2019, month=1, day=1,
                         hour=9, tzinfo=timezone.utc)
        end = datetime(year=2019, month=2, day=1, hour=9, tzinfo=timezone.utc)
        res = self.make_simulate_contracts_call(
            start, end, default_template_params, default_instance_params)

        # print(json.dumps(res[-1]["result"], indent=2))

        final_account_balances = res[-1]["result"]["balances"]["main_account"]["balances"]
        accrual_balances = next(
            balance
            for balance in final_account_balances
            if "DEFAULT" in balance["account_address"]
        )
        self.assertEqual(float(accrual_balances.get('amount')), 3000.0)
        self.assertEqual(accrual_balances.get(
            'value_time'), '2019-01-01T09:00:00Z')

    def test_payment_too_soon(self):
        start = datetime(year=2019, month=1, day=1, tzinfo=timezone.utc)
        instruction1 = datetime(year=2019, month=1, day=5, tzinfo=timezone.utc)
        end = datetime(year=2019, month=1, day=6, tzinfo=timezone.utc)
        template_params = {
            "denomination": "GBP",
            "gross_interest_rate_tiers": '{"tier1": "0"}',
            "tier_ranges": '{"tier1": {"min": 1000, "max": 25000}}',
            "internal_account": "1",
        }
        instance_params = {
            "loan_term": "1",
            "loan_amount": "6500",
            "payment_day": "5",
            "deposit_account": "12345",
        }

        deposit_instruction = products_test_utils.create_deposit_instruction(
            amount="283.5", timestamp=instruction1.isoformat()
        )
        instructions = [vault_caller.SimulationInstruction(
            instruction1, deposit_instruction)]
        res = self.make_simulate_contracts_call(
            start,
            end,
            template_params,
            instance_params,
            instructions,
        )

        log_entry = next(
            result
            for result in res
            if result["result"]["timestamp"] == "2019-01-05T00:00:00Z"
            and "rejected" in result["result"]["logs"][0]
        )
        self.assertIn("Repayments do not start until 2019-02-05",
                      log_entry["result"]["logs"][1])

    def test_payment(self):
        start = datetime(year=2019, month=1, day=1, tzinfo=timezone.utc)
        instruction1 = datetime(year=2019, month=2, day=5,
                                hour=9, tzinfo=timezone.utc)
        end = datetime(year=2019, month=2, day=6, tzinfo=timezone.utc)
        template_params = {
            "denomination": "GBP",
            "gross_interest_rate_tiers": '{"tier1": "0"}',
            "tier_ranges": '{"tier1": {"min": 1000, "max": 25000}}',
            "internal_account": "1",
        }
        instance_params = {
            "loan_term": "1",
            "loan_amount": "6500",
            "payment_day": "5",
            "deposit_account": "12345",
        }

        deposit_instruction = products_test_utils.create_deposit_instruction(
            amount="541.67", timestamp=instruction1.isoformat()
        )
        instructions = [vault_caller.SimulationInstruction(
            instruction1, deposit_instruction)]
        res = self.make_simulate_contracts_call(
            start,
            end,
            template_params,
            instance_params,
            instructions,
        )

        postings = []
        for result in res:
            pib = result["result"].get("posting_instruction_batches")
            if len(pib) > 0:
                postings.append(pib)
        # Postings:
        # 1. Initial transfer of loan amount
        # 2. Setting the monthly repayment in its own address
        # 3. The above deposit
        # 4. The deposit being moved to the DUE address
        self.assertEqual(len(postings), 4)

    def test_partial_payment(self):
        start = datetime(year=2019, month=1, day=1, tzinfo=timezone.utc)
        instruction1 = datetime(year=2019, month=2, day=5, hour=9, tzinfo=timezone.utc)
        end = datetime(year=2019, month=2, day=5, hour=23, tzinfo=timezone.utc)
        template_params = {
            "denomination": "GBP",
            "gross_interest_rate_tiers": '{"tier1": "0"}',
            "tier_ranges": '{"tier1": {"min": 1000, "max": 25000}}',
            "internal_account": "1",
        }
        instance_params = {
            "loan_term": "1",
            "loan_amount": "6500",
            "payment_day": "5",
            "deposit_account": "12345",
        }

        deposit_instruction = products_test_utils.create_deposit_instruction(
            amount="100", timestamp=instruction1.isoformat()
        )
        instructions = [vault_caller.SimulationInstruction(instruction1, deposit_instruction)]
        res = self.make_simulate_contracts_call(
            start,
            end,
            template_params,
            instance_params,
            instructions,
        )

        final_balances = products_test_utils.get_final_balances(
            res[-1]["result"]["balances"]["main_account"]["balances"]
        )
        self.assertEqual(final_balances["DEFAULT"], "5958.33")
        self.assertEqual(final_balances["DUE"], "441.67")

    def test_multiple_partial_payments(self):
        start = datetime(year=2019, month=1, day=1, tzinfo=timezone.utc)
        instruction1 = datetime(year=2019, month=2, day=5, hour=5, tzinfo=timezone.utc)
        instruction2 = datetime(year=2019, month=2, day=5, hour=7, tzinfo=timezone.utc)
        end = datetime(year=2019, month=2, day=5, hour=23, tzinfo=timezone.utc)
        template_params = {
            "denomination": "GBP",
            "gross_interest_rate_tiers": '{"tier1": "0"}',
            "tier_ranges": '{"tier1": {"min": 1000, "max": 25000}}',
            "internal_account": "1",
        }
        instance_params = {
            "loan_term": "1",
            "loan_amount": "6500",
            "payment_day": "5",
            "deposit_account": "12345",
        }

        deposit_instruction = products_test_utils.create_deposit_instruction(
            amount="100", timestamp=instruction1.isoformat()
        )
        deposit_instruction2 = products_test_utils.create_deposit_instruction(
            amount="100", timestamp=instruction2.isoformat(), client_transaction_id="128435984378"
        )
        instructions = [
            vault_caller.SimulationInstruction(instruction1, deposit_instruction),
            vault_caller.SimulationInstruction(instruction2, deposit_instruction2),
        ]
        res = self.make_simulate_contracts_call(
            start,
            end,
            template_params,
            instance_params,
            instructions,
        )

        postings = []
        for result in res:
            pib = result["result"].get("posting_instruction_batches")
            if len(pib) > 0:
                postings.append(pib)
        self.assertEqual(len(postings), 6)

        final_balances = products_test_utils.get_final_balances(
            res[-1]["result"]["balances"]["main_account"]["balances"]
        )
        self.assertEqual(final_balances["DEFAULT"], "5958.33")
        self.assertEqual(final_balances["DUE"], "341.67")

    def test_multiple_partial_payments_too_much(self):
        start = datetime(year=2019, month=1, day=1, tzinfo=timezone.utc)
        instruction1 = datetime(year=2019, month=2, day=5, hour=5, tzinfo=timezone.utc)
        instruction2 = datetime(year=2019, month=2, day=5, hour=7, tzinfo=timezone.utc)
        end = datetime(year=2019, month=2, day=5, hour=23, tzinfo=timezone.utc)
        template_params = {
            "denomination": "GBP",
            "gross_interest_rate_tiers": '{"tier1": "0"}',
            "tier_ranges": '{"tier1": {"min": 1000, "max": 25000}}',
            "internal_account": "1",
        }
        instance_params = {
            "loan_term": "1",
            "loan_amount": "6500",
            "payment_day": "5",
            "deposit_account": "12345",
        }

        deposit_instruction = products_test_utils.create_deposit_instruction(
            amount="100", timestamp=instruction1.isoformat()
        )
        deposit_instruction2 = products_test_utils.create_deposit_instruction(
            amount="500", timestamp=instruction2.isoformat(), client_transaction_id="24367567843"
        )
        instructions = [
            vault_caller.SimulationInstruction(instruction1, deposit_instruction),
            vault_caller.SimulationInstruction(instruction2, deposit_instruction2),
        ]
        res = self.make_simulate_contracts_call(
            start,
            end,
            template_params,
            instance_params,
            instructions,
        )

        postings = []
        for result in res:
            pib = result["result"].get("posting_instruction_batches")
            if len(pib) > 0:
                postings.append(pib)
        self.assertEqual(len(postings), 4)

        self.assertIn(
            "Cannot overpay with this account, you can currently pay up to 441.67",
            res[-1]["result"]["logs"][1],
        )

        # The final balances will be in the second to last streamed result.
        final_balances = products_test_utils.get_final_balances(
            res[-2]["result"]["balances"]["main_account"]["balances"]
        )
        self.assertEqual(final_balances["DEFAULT"], "5958.33")
        self.assertEqual(final_balances["DUE"], "441.67")

    def test_attempted_overpayment(self):
        start = datetime(year=2019, month=1, day=1, tzinfo=timezone.utc)
        instruction1 = datetime(year=2019, month=2, day=5, hour=9, tzinfo=timezone.utc)
        end = datetime(year=2019, month=2, day=5, hour=12, tzinfo=timezone.utc)
        template_params = {
            "denomination": "GBP",
            "gross_interest_rate_tiers": '{"tier1": "0"}',
            "tier_ranges": '{"tier1": {"min": 1000, "max": 25000}}',
            "internal_account": "1",
        }
        instance_params = {
            "loan_term": "1",
            "loan_amount": "6500",
            "payment_day": "5",
            "deposit_account": "12345",
        }

        deposit_instruction = products_test_utils.create_deposit_instruction(
            amount="1000", timestamp=instruction1.isoformat()
        )
        instructions = [vault_caller.SimulationInstruction(instruction1, deposit_instruction)]
        res = self.make_simulate_contracts_call(
            start,
            end,
            template_params,
            instance_params,
            instructions,
        )

        self.assertIn(
            "Cannot overpay with this account, you can currently pay up to 541.67",
            res[-1]["result"]["logs"][1],
        )

    def test_attempt_excessive_borrow(self):
        start = datetime(year=2019, month=1, day=1, tzinfo=timezone.utc)
        instruction1 = datetime(year=2019, month=1, day=5, tzinfo=timezone.utc)
        end = datetime(year=2019, month=1, day=6, tzinfo=timezone.utc)
        template_params = {
            "denomination": "GBP",
            "gross_interest_rate_tiers": '{"tier1": "0"}',
            "tier_ranges": '{"tier1": {"min": 1000, "max": 25000}}',
            "internal_account": "1",
        }
        instance_params = {
            "loan_term": "1",
            "loan_amount": "35000",
            "payment_day": "5",
            "deposit_account": "12345",
        }

        deposit_instruction = products_test_utils.create_deposit_instruction(
            amount="1000", timestamp=instruction1.isoformat()
        )
        instructions = [vault_caller.SimulationInstruction(instruction1, deposit_instruction)]

        with self.assertRaises(ValueError):
            self.make_simulate_contracts_call(
                start,
                end,
                template_params,
                instance_params,
                instructions,
            )

    def test_attempted_withdrawal(self):
        start = datetime(year=2019, month=1, day=1, tzinfo=timezone.utc)
        instruction1 = datetime(year=2019, month=1, day=5, tzinfo=timezone.utc)
        end = datetime(year=2019, month=1, day=5, hour=2, tzinfo=timezone.utc)
        template_params = {
            "denomination": "GBP",
            "gross_interest_rate_tiers": '{"tier1": "0"}',
            "tier_ranges": '{"tier1": {"min": 1000, "max": 25000}}',
            "internal_account": "1",
        }
        instance_params = {
            "loan_term": "1",
            "loan_amount": "10000",
            "payment_day": "5",
            "deposit_account": "12345",
        }

        withdrawal_instruction = products_test_utils.create_withdrawal_instruction(
            amount="283.45", timestamp=instruction1.isoformat()
        )
        instructions = [vault_caller.SimulationInstruction(instruction1, withdrawal_instruction)]
        res = self.make_simulate_contracts_call(
            start,
            end,
            template_params,
            instance_params,
            instructions,
        )

        self.assertIn(
            "Cannot withdraw from this account",
            res[-1]["result"]["logs"][1],
        )

    def test_interest_accrual(self):
        start = datetime(year=2019, month=1, day=1, tzinfo=timezone.utc)
        end = datetime(year=2019, month=1, day=2, tzinfo=timezone.utc)
        template_params = {
            "denomination": "GBP",
            "gross_interest_rate_tiers": '{"tier1": "0.0296"}',
            "tier_ranges": '{"tier1": {"min": 1000, "max": 25000}}',
            "internal_account": "1",
        }
        instance_params = {
            "loan_term": "1",
            "loan_amount": "10000",
            "payment_day": "5",
            "deposit_account": "12345",
        }

        res = self.make_simulate_contracts_call(
            start,
            end,
            template_params,
            instance_params,
        )

        final_balances = products_test_utils.get_final_balances(
            res[-1]["result"]["balances"]["main_account"]["balances"]
        )
        self.assertEqual(final_balances["ACCRUED_INTEREST"], "0.811")

    def test_interest_application(self):
        start = datetime(year=2019, month=1, day=1, tzinfo=timezone.utc)
        end = datetime(year=2019, month=2, day=6, tzinfo=timezone.utc)
        template_params = {
            "denomination": "GBP",
            "gross_interest_rate_tiers": '{"tier1": 0.0296}',
            "tier_ranges": '{"tier1": {"min": 1000, "max": 20000}}',
            "internal_account": "1",
        }
        instance_params = {
            "loan_term": "1",
            "loan_amount": "10000",
            "payment_day": "5",
            "deposit_account": "12345",
        }

        res = self.make_simulate_contracts_call(
            start,
            end,
            template_params,
            instance_params,
        )

        final_balances = products_test_utils.get_final_balances(
            res[-1]["result"]["balances"]["main_account"]["balances"]
        )
        self.assertEqual(final_balances["ACCRUED_INTEREST"], "0.7393")
        self.assertEqual(final_balances["DEFAULT"], "9178.4")
        self.assertEqual(final_balances["DUE"], "849.99")

    def test_full_ideal_loan(self):
        start = datetime(year=2019, month=1, day=4, tzinfo=timezone.utc)
        instruction1 = datetime(year=2019, month=2, day=5, hour=9, tzinfo=timezone.utc)
        instruction2 = datetime(year=2019, month=3, day=5, hour=9, tzinfo=timezone.utc)
        instruction3 = datetime(year=2019, month=4, day=5, hour=9, tzinfo=timezone.utc)
        instruction4 = datetime(year=2019, month=5, day=5, hour=9, tzinfo=timezone.utc)
        instruction5 = datetime(year=2019, month=6, day=5, hour=9, tzinfo=timezone.utc)
        instruction6 = datetime(year=2019, month=7, day=5, hour=9, tzinfo=timezone.utc)
        instruction7 = datetime(year=2019, month=8, day=5, hour=9, tzinfo=timezone.utc)
        instruction8 = datetime(year=2019, month=9, day=5, hour=9, tzinfo=timezone.utc)
        instruction9 = datetime(year=2019, month=10, day=5, hour=9, tzinfo=timezone.utc)
        instruction10 = datetime(year=2019, month=11, day=5, hour=9, tzinfo=timezone.utc)
        instruction11 = datetime(year=2019, month=12, day=5, hour=9, tzinfo=timezone.utc)
        instruction12 = datetime(year=2020, month=1, day=5, hour=9, tzinfo=timezone.utc)
        end = datetime(year=2020, month=1, day=5, hour=23, tzinfo=timezone.utc)
        template_params = default_template_params
        instance_params = {
            "loan_term": "1",
            "loan_amount": "6500",
            "payment_day": "5",
            "deposit_account": "12345",
        }
        instructions = []
        # First payment includes any additional interest calculated from difference between payment
        # date and account creation date
        deposit_instruction = products_test_utils.create_deposit_instruction(
            amount="555.76", timestamp=instruction1.isoformat(), client_transaction_id="1"
        )
        instructions.append(vault_caller.SimulationInstruction(instruction1, deposit_instruction))
        deposit_instruction = products_test_utils.create_deposit_instruction(
            amount="554.96", timestamp=instruction2.isoformat(), client_transaction_id="2"
        )
        instructions.append(vault_caller.SimulationInstruction(instruction2, deposit_instruction))
        deposit_instruction = products_test_utils.create_deposit_instruction(
            amount="554.96", timestamp=instruction3.isoformat(), client_transaction_id="3"
        )
        instructions.append(vault_caller.SimulationInstruction(instruction3, deposit_instruction))
        deposit_instruction = products_test_utils.create_deposit_instruction(
            amount="554.96", timestamp=instruction4.isoformat(), client_transaction_id="4"
        )
        instructions.append(vault_caller.SimulationInstruction(instruction4, deposit_instruction))
        deposit_instruction = products_test_utils.create_deposit_instruction(
            amount="554.96", timestamp=instruction5.isoformat(), client_transaction_id="5"
        )
        instructions.append(vault_caller.SimulationInstruction(instruction5, deposit_instruction))
        deposit_instruction = products_test_utils.create_deposit_instruction(
            amount="554.96", timestamp=instruction6.isoformat(), client_transaction_id="6"
        )
        instructions.append(vault_caller.SimulationInstruction(instruction6, deposit_instruction))
        deposit_instruction = products_test_utils.create_deposit_instruction(
            amount="554.96", timestamp=instruction7.isoformat(), client_transaction_id="7"
        )
        instructions.append(vault_caller.SimulationInstruction(instruction7, deposit_instruction))
        deposit_instruction = products_test_utils.create_deposit_instruction(
            amount="554.96", timestamp=instruction8.isoformat(), client_transaction_id="8"
        )
        instructions.append(vault_caller.SimulationInstruction(instruction8, deposit_instruction))
        deposit_instruction = products_test_utils.create_deposit_instruction(
            amount="554.96", timestamp=instruction9.isoformat(), client_transaction_id="9"
        )
        instructions.append(vault_caller.SimulationInstruction(instruction9, deposit_instruction))
        deposit_instruction = products_test_utils.create_deposit_instruction(
            amount="554.96", timestamp=instruction10.isoformat(), client_transaction_id="10"
        )
        instructions.append(vault_caller.SimulationInstruction(instruction10, deposit_instruction))
        deposit_instruction = products_test_utils.create_deposit_instruction(
            amount="554.96", timestamp=instruction11.isoformat(), client_transaction_id="11"
        )
        instructions.append(vault_caller.SimulationInstruction(instruction11, deposit_instruction))
        # Final payment just covers the leftover balance
        deposit_instruction = products_test_utils.create_deposit_instruction(
            amount="554.30", timestamp=instruction12.isoformat(), client_transaction_id="12"
        )
        instructions.append(vault_caller.SimulationInstruction(instruction12, deposit_instruction))

        res = self.make_simulate_contracts_call(
            start,
            end,
            template_params,
            instance_params,
            instructions,
        )

        final_balances = products_test_utils.get_final_balances(
            res[-1]["result"]["balances"]["main_account"]["balances"]
        )
        self.assertEqual(final_balances["DUE"], "0.005")
        self.assertEqual(final_balances["DEFAULT"], "0.005")
