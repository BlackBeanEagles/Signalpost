import unittest

from signalpost.budget import Budget, BudgetExceeded


class BudgetTests(unittest.TestCase):
    def test_request_limit(self):
        budget = Budget(max_requests=1)
        budget.reserve()
        with self.assertRaises(BudgetExceeded):
            budget.reserve()


if __name__ == "__main__":
    unittest.main()

