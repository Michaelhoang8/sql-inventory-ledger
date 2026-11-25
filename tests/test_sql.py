from pathlib import Path
import sqlite3
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.executescript((ROOT/'sql/schema.sql').read_text())
        self.db.executescript((ROOT/'sql/fixture.sql').read_text())

    def tearDown(self): self.db.close()

    def receipt(self, ref='new', amount=10, sku='BOLT-M8', location='CALGARY'):
        self.db.execute("INSERT INTO movement(reference,sku,location,delta,kind) VALUES(?,?,?,?,'receipt')",(ref,sku,location,amount))

    def test_fixture_balances_and_transfer_reconcile(self):
        self.assertEqual(self.db.execute("SELECT units FROM stock WHERE sku='BOLT-M8' ORDER BY location").fetchall(),[(75,),(25,)])
        self.assertEqual(self.db.execute('SELECT count(*) FROM reconciliation WHERE difference <> 0').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT net_delta,reconciled FROM transfer_reconciliation').fetchall(),[(0,1)])

    def test_insufficient_stock_rejects_transfer_and_both_movements(self):
        with self.assertRaisesRegex(sqlite3.IntegrityError,'insufficient'):
            self.db.execute("INSERT INTO transfer VALUES ('too-much','BOLT-M8','CALGARY','EDMONTON',1000)")
        self.assertEqual(self.db.execute("SELECT count(*) FROM movement WHERE reference LIKE 'too-much%'").fetchone()[0],0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM transfer WHERE reference='too-much'").fetchone()[0],0)

    def test_second_transfer_leg_failure_rolls_back_first_leg(self):
        self.receipt('conflict:in',1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO transfer VALUES ('conflict','BOLT-M8','CALGARY','EDMONTON',10)")
        self.assertEqual(self.db.execute("SELECT units FROM stock WHERE sku='BOLT-M8' AND location='CALGARY'").fetchone()[0],76)
        self.assertEqual(self.db.execute("SELECT count(*) FROM movement WHERE reference='conflict:out'").fetchone()[0],0)

    def test_duplicate_reference_does_not_add_stock_twice(self):
        with self.assertRaises(sqlite3.IntegrityError): self.receipt('receipt-001')
        self.assertEqual(self.db.execute("SELECT units FROM stock WHERE sku='BOLT-M8' AND location='CALGARY'").fetchone()[0],75)

    def test_replace_cannot_bypass_append_only_identity(self):
        for sql in ["INSERT OR REPLACE INTO movement(reference,sku,location,delta,kind) VALUES('receipt-001','BOLT-M8','CALGARY',5,'receipt')", "INSERT OR REPLACE INTO transfer VALUES('transfer-001','BOLT-M8','CALGARY','EDMONTON',1)"]:
            with self.assertRaisesRegex(sqlite3.IntegrityError,'already exists'): self.db.execute(sql)
        self.assertEqual(self.db.execute('SELECT count(*) FROM movement').fetchone()[0],4)

    def test_append_only_rules_apply_to_both_ledgers(self):
        for sql in ['DELETE FROM movement','UPDATE movement SET delta=1','DELETE FROM transfer','UPDATE transfer SET units=1']:
            with self.subTest(sql=sql), self.assertRaisesRegex(sqlite3.IntegrityError,'append-only'): self.db.execute(sql)

    def test_unknown_location_and_item_are_rejected(self):
        for sku, location in [('UNKNOWN','CALGARY'),('BOLT-M8','UNKNOWN')]:
            with self.assertRaises(sqlite3.IntegrityError): self.receipt(sku=sku,location=location)

    def test_quantities_reject_fraction_zero_negative_and_overflow(self):
        for amount in [1.5,0,-1,1000000001]:
            with self.subTest(amount=amount), self.assertRaises(sqlite3.IntegrityError): self.receipt(amount=amount)

    def test_same_location_transfer_is_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError): self.db.execute("INSERT INTO transfer VALUES ('same','BOLT-M8','CALGARY','CALGARY',1)")

    def test_reconciliation_detects_manual_balance_drift(self):
        self.db.execute("UPDATE stock SET units=units+7 WHERE sku='BOLT-M8' AND location='CALGARY'")
        self.assertEqual(self.db.execute('SELECT difference FROM reconciliation WHERE difference<>0').fetchall(),[(7,)])

    def test_outer_transaction_rolls_back_prior_statement(self):
        with self.assertRaises(sqlite3.IntegrityError), self.db:
            self.receipt('transaction-first',10)
            self.receipt('receipt-001',10)
        self.assertEqual(self.db.execute("SELECT count(*) FROM movement WHERE reference='transaction-first'").fetchone()[0],0)


if __name__ == '__main__': unittest.main()
