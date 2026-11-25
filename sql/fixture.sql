BEGIN;
INSERT INTO item VALUES ('BOLT-M8', 'M8 bolt'), ('WASHER-M8', 'M8 washer');
INSERT INTO location VALUES ('CALGARY'), ('EDMONTON');
INSERT INTO movement (reference, sku, location, delta, kind)
VALUES ('receipt-001', 'BOLT-M8', 'CALGARY', 100, 'receipt'),
       ('receipt-002', 'WASHER-M8', 'CALGARY', 200, 'receipt');
INSERT INTO transfer VALUES ('transfer-001', 'BOLT-M8', 'CALGARY', 'EDMONTON', 25);
COMMIT;
