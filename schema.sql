CREATE TABLE IF NOT EXISTS accounts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    code        TEXT    NOT NULL UNIQUE,
    element     TEXT    NOT NULL CHECK(element IN ('assets','liabilities','equity','revenues','expenses')),
    sort_order  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS journal (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id  TEXT    NOT NULL,
    entry_date      TEXT    NOT NULL,
    account_id      INTEGER NOT NULL REFERENCES accounts(id),
    debit_credit    TEXT    NOT NULL CHECK(debit_credit IN ('debit','credit')),
    amount          INTEGER NOT NULL CHECK(amount > 0),
    note            TEXT,
    created_at      TEXT    DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_journal_entry_date ON journal(entry_date);
CREATE INDEX IF NOT EXISTS idx_journal_transaction_id ON journal(transaction_id);
CREATE INDEX IF NOT EXISTS idx_journal_account_id ON journal(account_id);

CREATE TABLE IF NOT EXISTS closings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    closing_date  TEXT    NOT NULL UNIQUE,
    account_id    INTEGER NOT NULL REFERENCES accounts(id),
    note          TEXT,
    created_at    TEXT    DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_closings_closing_date ON closings(closing_date);
