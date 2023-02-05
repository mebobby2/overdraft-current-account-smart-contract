# Overdraft Current Account & Loan Smart Contract

For ThoughtMachines Vault tutorial: https://docs.thoughtmachine.net/vault-core/4-5/EN/tutorials/smart-contracts/#basic-contract

## Personal Loan Requirements
* Customers should be able to borrow between 1,000 and 20,000 GBP
* Customers can specify which account they want to have the funds moved to
* Duration of the loan must be between 1 and 5 years
* The loan should allow a variable interest rate based on the amount borrowed, which will then fall into one of 5 defined tiers as per table shown below:

| Tier      | Min Amount | Max Amount | Gross Rate
| ----------- | ----------- | ----------- | ----------- |
| tier1      | 1000       | 2,999 | 13.50%
| tier2      | 3000       | 4,999 | 9.80%
| tier3      | 5000       | 7,499 | 4.50%
| tier4      | 7,500       | 14,999 | 3.00%
| tier5      | 15,000       | 20, 000 | 3.50%

* If a customer has not repaid the expected monthly amount:
  * Apply a fee
  * Send a notification to customer for the missed repayment
* Repayments can be broken down into multiple transactions, but cannot be summed up higher than the total required repayment amount
* Interest on the outstanding loan amount should be accrued at the end of every day, with accrual precision of 4 decimal places
* Charging of the interest should happen once a month at the start of the day of expected repayment, with application precision of 2 decimal places

## Prerequisites
* Install pipenv
  * pip3 install --user pipenv
* Start a pipenv project
  * pipenv install

## Installing packages
* pipenv install package_name

## Development
* Activate Pipenvshell
  * pipenv shell
  * This will spawn a new shell subprocess, which can be deactivated by using exit
* Testing
  * python3 -m unittest simple_tutorial_tests.TutorialTest.test_unchallenged_deposit
  * run all tests: python3 -m unittest tests.py

## Upto
https://docs.thoughtmachine.net/vault-core/4-5/EN/tutorials/smart-contracts/#advanced-contract-repayment_logic

In this part of the tutorial, we are going to add the repayment logic to the loan contract.
