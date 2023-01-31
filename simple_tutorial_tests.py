import vault_caller
from datetime import datetime, timezone
from decimal import Decimal
import os
import unittest

core_api_url = "https://core-api.public-sandbox.partner.tmachine.io"
auth_token = "A0003256414797670411991!FZ/D4LwwwqJMTyKW644WAqJkf/uXg7sC7LhWNtl7kL5dVCA7NDz6KQVLcMsei1O8eXBwxked7hNvZWQ9YXmrR8OPG+M="
CONTRACT_FILE = "./tutorial_contract.py"


class TutorialTest(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        contract = os.path.join(os.path.dirname(__file__), CONTRACT_FILE)
        if not core_api_url or not auth_token:
            raise ValueError(
                "Please provide values for core_api_url and auth_token, these should "
                "be provided by your system administrator."
            )
        with open(contract) as smart_contract_file:
            self.smart_contract_contents = smart_contract_file.read()
        self.client = vault_caller.Client(
            core_api_url=core_api_url, auth_token=auth_token)

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
                # Our internal account.
                vault_caller.SimulationInstruction(
                    start,
                    {
                        "create_account": {
                            "id": "1",
                            "product_version_id": "2",
                        }
                    },
                ),
            ]
            + instructions,
        )

    # Exercise 1.
    def test_unchallenged_deposit(self):
        start = datetime(year=2019, month=1, day=1, tzinfo=timezone.utc)
        end = datetime(year=2019, month=1, day=2, tzinfo=timezone.utc)
        template_params = {}
        instance_params = {}
        deposit_instruction = {
            "create_posting_instruction_batch": {
                "client_id": "Visa",
                "client_batch_id": "123",
                "posting_instructions": [
                    {
                        "inbound_hard_settlement": {
                            "amount": "1000",
                            "denomination": "EUR",
                            "target_account": {
                                "account_id": "main_account",
                            },
                            "internal_account_id": "1",
                        },
                        "client_transaction_id": "123456",
                        "pics": ["FEES"],
                        "instruction_details": {"description": "test1"},
                    }
                ],
                "batch_details": {"description": "test"},
                "value_timestamp": "2019-01-01T01:00:00+00:00",
            }
        }
        instructions = [vault_caller.SimulationInstruction(
            start, deposit_instruction)]
        res = self.make_simulate_contracts_call(
            start,
            end,
            template_params,
            instance_params,
            instructions,
        )
        self.assertEqual(
            len(res[-1]["result"]["posting_instruction_batches"]), 1)

    # Exercise 2.
    def test_wrong_denomination_deposit(self):
        start = datetime(year=2019, month=1, day=1, tzinfo=timezone.utc)
        end = datetime(year=2019, month=1, day=2, tzinfo=timezone.utc)
        template_params = {}
        instance_params = {}

        deposit_instruction = {
            "create_posting_instruction_batch": {
                "client_id": "Visa",
                "client_batch_id": "123",
                "posting_instructions": [
                    {
                        "inbound_hard_settlement": {
                            "amount": "1000",
                            "denomination": "EUR",
                            "target_account": {
                                "account_id": "main_account",
                            },
                            "internal_account_id": "1",
                        },
                        "client_transaction_id": "123456",
                        "instruction_details": {"description": "test2"},
                    }
                ],
                "batch_details": {"description": "test"},
                "value_timestamp": "2019-01-01T01:00:00+00:00",
            }
        }
        instructions = [vault_caller.SimulationInstruction(
            start, deposit_instruction)]
        res = self.make_simulate_contracts_call(
            start,
            end,
            template_params,
            instance_params,
            instructions,
        )

        # No valid postings were made.
        for result in res:
            self.assertEqual(
                0, len(result["result"]["posting_instruction_batches"]))
        # The last item in res contains the outcome for the created posting.
        # Its log contains the error we expect to be raised by an invalid currency.
        self.assertIn(
            "Cannot make transactions in given denomination; transactions must be in GBP",
            res[-1]["result"]["logs"][1],
        )

    # Exercise 3.
    def test_wrong_denomination_with_parameter_deposit(self):
        start = datetime(year=2019, month=1, day=1, tzinfo=timezone.utc)
        end = datetime(year=2019, month=1, day=2, tzinfo=timezone.utc)
        template_params = {"denomination": "GBP"}
        instance_params = {}
        deposit_instruction = {
            "create_posting_instruction_batch": {
                "client_id": "Visa",
                "client_batch_id": "123",
                "posting_instructions": [
                    {
                        "inbound_hard_settlement": {
                            "amount": "1000",
                            "denomination": "EUR",
                            "target_account": {
                                "account_id": "main_account",
                            },
                            "internal_account_id": "1",
                        },
                        "client_transaction_id": "123456",
                        "pics": ["FEES"],
                        "instruction_details": {"description": "test3"},
                    }
                ],
                "batch_details": {"description": "test"},
                "value_timestamp": "2019-01-01T01:00:00+00:00",
            }
        }
        instructions = [vault_caller.SimulationInstruction(
            start, deposit_instruction)]
        res = self.make_simulate_contracts_call(
            start,
            end,
            template_params,
            instance_params,
            instructions,
        )
        # No valid postings were made.
        for result in res:
            self.assertEqual(
                0, len(result["result"]["posting_instruction_batches"]))
        # The last item in res contains the outcome for the created posting.
        # Its log contains the error we expect to be raised by an invalid currency.
        self.assertIn(
            "Cannot make transactions in given denomination; transactions must be in GBP",
            res[-1]["result"]["logs"][1],
        )

    # Exercise 4.
    def test_fee_applied_after_withdrawal(self):
        start = datetime(year=2019, month=1, day=1, tzinfo=timezone.utc)
        end = datetime(year=2019, month=1, day=2, tzinfo=timezone.utc)
        template_params = {
            "denomination": "GBP",
            "overdraft_limit": "100",
            "overdraft_fee": "20",
        }
        instance_params = {}

        deposit_instruction = {
            "create_posting_instruction_batch": {
                "client_id": "Visa",
                "client_batch_id": "123",
                "posting_instructions": [
                    {
                        "outbound_hard_settlement": {
                            "amount": "110",
                            "denomination": "GBP",
                            "target_account": {
                                "account_id": "main_account",
                            },
                            "internal_account_id": "1",
                        },
                        "client_transaction_id": "123456",
                        "instruction_details": {"description": "test4"},
                    }
                ],
                "batch_details": {"description": "test"},
                "value_timestamp": "2019-01-01T01:00:00+00:00",
            }
        }
        instructions = [vault_caller.SimulationInstruction(
            start, deposit_instruction)]
        res = self.make_simulate_contracts_call(
            start,
            end,
            template_params,
            instance_params,
            instructions,
        )

        self.assertEqual(
            res[-2]["result"]["balances"]["main_account"]["balances"][0]["amount"], "-110"
        )

        # Latest balance will include the overdraft fee.
        self.assertEqual(
            res[-1]["result"]["balances"]["main_account"]["balances"][0]["amount"], "-130"
        )

    # Exercise 6.
    def test_execution_schedule(self):
        start = datetime(year=2019, month=1, day=1, tzinfo=timezone.utc)
        end = datetime(year=2019, month=1, day=2, tzinfo=timezone.utc)
        template_params = {
            "denomination": "GBP",
            "overdraft_limit": "100",
            "overdraft_fee": "20",
            "gross_interest_rate": "0.08",
        }
        instance_params = {}

        deposit_instruction = {
            "create_posting_instruction_batch": {
                "client_id": "Visa",
                "client_batch_id": "123",
                "posting_instructions": [
                    {
                        "inbound_hard_settlement": {
                            "amount": "1000",
                            "denomination": "GBP",
                            "target_account": {
                                "account_id": "main_account",
                            },
                            "internal_account_id": "1",
                        },
                        "client_transaction_id": "123456",
                        "instruction_details": {"description": "test6"},
                    }
                ],
                "batch_details": {"description": "test"},
                "value_timestamp": "2019-01-01T01:00:00+00:00",
            }
        }
        instructions = [vault_caller.SimulationInstruction(
            start, deposit_instruction)]
        res = self.make_simulate_contracts_call(
            start,
            end,
            template_params,
            instance_params,
            instructions,
        )
        balances = []
        for result in res:
            b = result["result"].get("balances")
            if len(b) > 0:
                balances.append(b)
        self.assertEqual(len(balances), 2)

        # There will be two balances because we now have an interest accrual.
        self.assertEqual(
            len(res[-1]["result"]["balances"]["main_account"]["balances"]),
            2,
        )
        interest_balance = next(
            balance["amount"]
            for balance in res[-1]["result"]["balances"]["main_account"]["balances"]
            if balance["account_address"] == "ACCRUED_INCOMING"
        )
        self.assertEqual(
            Decimal(interest_balance).quantize(Decimal(".00001")),
            Decimal("0.21918"),
        )

    # Exercise 7.
    def test_improved_execution_schedule(self):
        start = datetime(year=2019, month=1, day=1, tzinfo=timezone.utc)
        end = datetime(year=2019, month=1, day=5, hour=1, tzinfo=timezone.utc)
        template_params = {
            "denomination": "GBP",
            "overdraft_limit": "100",
            "overdraft_fee": "20",
            "gross_interest_rate": "0.08",
        }
        instance_params = {"interest_payment_day": "5"}

        deposit_instruction = {
            "create_posting_instruction_batch": {
                "client_id": "Visa",
                "client_batch_id": "123",
                "posting_instructions": [
                    {
                        "inbound_hard_settlement": {
                            "amount": "1000",
                            "denomination": "GBP",
                            "target_account": {
                                "account_id": "main_account",
                            },
                            "internal_account_id": "1",
                        },
                        "client_transaction_id": "123456",
                        "instruction_details": {"description": "test6"},
                    }
                ],
                "batch_details": {"description": "test"},
                "value_timestamp": "2019-01-01T01:00:00+00:00",
            }
        }
        instructions = [vault_caller.SimulationInstruction(
            start, deposit_instruction)]
        res = self.make_simulate_contracts_call(
            start,
            end,
            template_params,
            instance_params,
            instructions,
        )

        # The last result contains the interest payment.
        pi_batches = res[-1]["result"]["posting_instruction_batches"]
        self.assertEqual(len(pi_batches), 1)
        posting_instructions = pi_batches[0]["posting_instructions"]
        # One of the instructions will be for the client, the other for the customer. The order
        # of the two is not fixed but both will have the same amount. We can check for either of them.
        self.assertEqual(len(posting_instructions), 2)
        self.assertEqual(
            posting_instructions[0]["committed_postings"][0]["amount"], "0.88")


if __name__ == "__main__":
    unittest.main()

# flake8: noqa
