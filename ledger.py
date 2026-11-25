"""Small SQLite CLI; inventory rules live in sql/schema.sql."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True, help='SQLite file')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('init'); commands.add_parser('seed'); commands.add_parser('report')
    receipt = commands.add_parser('receive')
    for field in ['reference', 'sku', 'location']: receipt.add_argument(field)
    receipt.add_argument('units', type=int)
    transfer = commands.add_parser('transfer')
    for field in ['reference', 'sku', 'source', 'destination']: transfer.add_argument(field)
    transfer.add_argument('units', type=int)
    args = parser.parse_args(argv)
    try:
        path = Path(args.db).resolve()
        if args.command == 'init':
            if path.exists(): raise ValueError('init requires a new database path')
            connection = sqlite3.connect(path)
        else:
            if not path.is_file(): raise ValueError('database does not exist; run init first')
            connection = sqlite3.connect(path.as_uri() + ('?mode=ro' if args.command == 'report' else '?mode=rw'), uri=True)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute('PRAGMA foreign_keys = ON')
            with connection:
                if args.command == 'init': connection.executescript((ROOT/'sql/schema.sql').read_text())
                elif args.command == 'seed': connection.executescript((ROOT/'sql/fixture.sql').read_text())
                elif args.command == 'receive': connection.execute('INSERT INTO movement(reference, sku, location, delta, kind) VALUES (?, ?, ?, ?, \'receipt\')', (args.reference, args.sku, args.location, args.units))
                elif args.command == 'transfer': connection.execute('INSERT INTO transfer VALUES (?, ?, ?, ?, ?)', (args.reference, args.sku, args.source, args.destination, args.units))
                else:
                    report = {'balances': [dict(row) for row in connection.execute('SELECT * FROM reconciliation ORDER BY sku, location')], 'transfers': [dict(row) for row in connection.execute('SELECT * FROM transfer_reconciliation ORDER BY reference')]}
                    print(json.dumps(report, indent=2))
                    return 1 if any(row['difference'] for row in report['balances']) or any(not row['reconciled'] for row in report['transfers']) else 0
            print(json.dumps({'command': args.command, 'status': 'committed'}))
        finally:
            connection.close()
    except (sqlite3.Error, OSError, ValueError, OverflowError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__': raise SystemExit(main())
