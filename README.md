# SQL Inventory Ledger

A SQLite schema that records inventory movements, updates stock balances through triggers, and posts both sides of a transfer atomically. SQL views reconcile cached balances to the append-only movement ledger and transfers to their paired movements.

```sh
python ledger.py --help
python ledger.py --db demo.sqlite init
python ledger.py --db demo.sqlite seed
python ledger.py --db demo.sqlite transfer transfer-002 BOLT-M8 CALGARY EDMONTON 5
python ledger.py --db demo.sqlite report
python -m unittest discover -s tests -v
```

Python is a thin CLI and test harness; the business rules live in [sql/schema.sql](sql/schema.sql). Requires SQLite 3.37+ for STRICT tables (Python 3.11+ normally includes a suitable version; check `sqlite3.sqlite_version`). No third-party packages. The authored fixture receives 100 bolts in Calgary and transfers 25 to Edmonton, leaving balances of 75 and 25.

Foreign keys, integer quantity limits, unique references and nonnegative stock are enforced in SQL. A transfer trigger inserts its negative source movement and positive destination movement. If either insert fails, the entire transfer statement rolls back, including the first movement and its stock update. Direct ledger updates/deletes fail. Corrections require a new compensating movement, preserving the original record.

Movement references are unique. Repeating a reference is an error rather than a second posting. A transfer reference reserves its `:out` and `:in` movement references; conflicting references abort the transfer. The CLI uses bound parameters. `report` opens the database read-only and exits 1 if reconciliation finds drift; malformed input or database errors exit 2, and successful commands exit 0. `seed` is intended once on a newly initialized database.

This is an inventory-unit ledger, not double-entry financial accounting. It has no costs, currencies, purchase orders, user authorization or multi-host concurrency layer. SQLite serializes writers; a busy database can require retry by the caller. Each connection must enable `PRAGMA foreign_keys = ON`. An administrator with raw database access can modify cached stock, drop triggers or bypass application controls; reconciliation exposes balance drift but is not tamper-proof evidence. Inventory limits are explicit: each movement is at most one billion units and each stored balance at most 2,147,483,647.
