PRAGMA foreign_keys = ON;

CREATE TABLE item (
    sku TEXT PRIMARY KEY CHECK (length(trim(sku)) BETWEEN 1 AND 100),
    description TEXT NOT NULL
) STRICT;
CREATE TABLE location (
    code TEXT PRIMARY KEY CHECK (length(trim(code)) BETWEEN 1 AND 100)
) STRICT;
CREATE TABLE stock (
    sku TEXT NOT NULL REFERENCES item(sku),
    location TEXT NOT NULL REFERENCES location(code),
    units INTEGER NOT NULL CHECK (units BETWEEN 0 AND 2147483647),
    PRIMARY KEY (sku, location)
) STRICT;
CREATE TABLE movement (
    movement_id INTEGER PRIMARY KEY,
    reference TEXT NOT NULL UNIQUE CHECK (length(trim(reference)) BETWEEN 1 AND 200),
    sku TEXT NOT NULL REFERENCES item(sku),
    location TEXT NOT NULL REFERENCES location(code),
    delta INTEGER NOT NULL CHECK (delta BETWEEN -1000000000 AND 1000000000 AND delta <> 0),
    kind TEXT NOT NULL CHECK (kind IN ('receipt', 'issue', 'transfer_in', 'transfer_out')),
    CHECK ((kind IN ('receipt', 'transfer_in') AND delta > 0)
        OR (kind IN ('issue', 'transfer_out') AND delta < 0))
) STRICT;
CREATE TABLE transfer (
    reference TEXT PRIMARY KEY CHECK (length(trim(reference)) BETWEEN 1 AND 190),
    sku TEXT NOT NULL REFERENCES item(sku),
    source TEXT NOT NULL REFERENCES location(code),
    destination TEXT NOT NULL REFERENCES location(code),
    units INTEGER NOT NULL CHECK (units BETWEEN 1 AND 1000000000),
    CHECK (source <> destination)
) STRICT;

CREATE TRIGGER movement_prevent_negative BEFORE INSERT ON movement BEGIN
    SELECT CASE WHEN EXISTS (SELECT 1 FROM movement WHERE reference = NEW.reference OR movement_id = NEW.movement_id)
        THEN RAISE(ABORT, 'movement identity already exists') END;
    SELECT CASE WHEN coalesce((SELECT units FROM stock WHERE sku = NEW.sku AND location = NEW.location), 0) + NEW.delta < 0
        THEN RAISE(ABORT, 'insufficient stock') END;
END;
CREATE TRIGGER transfer_unique BEFORE INSERT ON transfer BEGIN
    SELECT CASE WHEN EXISTS (SELECT 1 FROM transfer WHERE reference = NEW.reference)
        THEN RAISE(ABORT, 'transfer identity already exists') END;
END;
CREATE TRIGGER movement_apply AFTER INSERT ON movement BEGIN
    INSERT INTO stock (sku, location, units) VALUES (NEW.sku, NEW.location, 0)
    ON CONFLICT (sku, location) DO NOTHING;
    UPDATE stock SET units = units + NEW.delta
    WHERE sku = NEW.sku AND location = NEW.location;
END;
CREATE TRIGGER transfer_apply AFTER INSERT ON transfer BEGIN
    INSERT INTO movement (reference, sku, location, delta, kind)
    VALUES (NEW.reference || ':out', NEW.sku, NEW.source, -NEW.units, 'transfer_out');
    INSERT INTO movement (reference, sku, location, delta, kind)
    VALUES (NEW.reference || ':in', NEW.sku, NEW.destination, NEW.units, 'transfer_in');
END;
CREATE TRIGGER movement_no_update BEFORE UPDATE ON movement BEGIN
    SELECT RAISE(ABORT, 'movement ledger is append-only');
END;
CREATE TRIGGER movement_no_delete BEFORE DELETE ON movement BEGIN
    SELECT RAISE(ABORT, 'movement ledger is append-only');
END;
CREATE TRIGGER transfer_no_update BEFORE UPDATE ON transfer BEGIN
    SELECT RAISE(ABORT, 'transfer ledger is append-only');
END;
CREATE TRIGGER transfer_no_delete BEFORE DELETE ON transfer BEGIN
    SELECT RAISE(ABORT, 'transfer ledger is append-only');
END;

CREATE VIEW ledger_balance AS
SELECT sku, location, sum(delta) AS ledger_units, count(*) AS movements
FROM movement GROUP BY sku, location;

CREATE VIEW reconciliation AS
WITH keys AS (SELECT sku, location FROM stock UNION SELECT sku, location FROM ledger_balance)
SELECT keys.sku, keys.location,
       coalesce(stock.units, 0) AS stored_units,
       coalesce(ledger_balance.ledger_units, 0) AS ledger_units,
       coalesce(stock.units, 0) - coalesce(ledger_balance.ledger_units, 0) AS difference,
       coalesce(ledger_balance.movements, 0) AS movements
FROM keys LEFT JOIN stock USING (sku, location)
LEFT JOIN ledger_balance USING (sku, location);

CREATE VIEW transfer_reconciliation AS
SELECT transfer.reference, transfer.units,
       coalesce(outgoing.delta, 0) + coalesce(incoming.delta, 0) AS net_delta,
       CASE WHEN outgoing.delta = -transfer.units AND incoming.delta = transfer.units
            AND outgoing.sku = transfer.sku AND incoming.sku = transfer.sku
            AND outgoing.location = transfer.source AND incoming.location = transfer.destination
            AND outgoing.kind = 'transfer_out' AND incoming.kind = 'transfer_in'
            THEN 1 ELSE 0 END AS reconciled
FROM transfer
LEFT JOIN movement outgoing ON outgoing.reference = transfer.reference || ':out'
LEFT JOIN movement incoming ON incoming.reference = transfer.reference || ':in';
