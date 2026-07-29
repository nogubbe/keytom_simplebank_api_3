# Accounts, transactions and transfers — design

## Goal

Implement the remaining SimpleBank requirements from `SimpleBank (API-only) 3.pdf`:

- Auto-create a bank account (unique 10-digit account number, €10,000 welcome
  bonus) on user registration.
- Get current balance.
- List the authenticated user's transactions, with optional `from`/`to`
  date-range filtering.
- Transfer money to another user's account, applying a transfer fee of 2.5%
  of the amount or €5 minimum (whichever is greater), recording both the
  debit (sender) and credit (receiver) transactions.

Scope: a new Django app, `simplebank/apps/accounts`, following the existing
`users` app's structure (`models.py`, `schemas.py`, `services.py`,
`exceptions.py`, `api.py`, `admin.py`). A single app is enough — `Account`,
`Transaction` and `Transfer` are tightly coupled (balance is derived from
transactions, a transfer operates on two accounts at once), so splitting
them into separate apps would only add cross-app dependencies with no
reuse benefit. Layering is handled within the app via `models.py` /
`services.py` / `api.py`, same as `users`.

## Project structure

```
simplebank/apps/accounts/
├── __init__.py
├── admin.py          # registers Account/Transfer/Transaction in admin
├── api.py            # router: balance, transactions, transfer
├── apps.py
├── exceptions.py     # AccountNotFoundError, InsufficientFundsError, SameAccountTransferError
├── migrations/
│   └── __init__.py
├── models.py          # Account, Transfer, Transaction
├── schemas.py         # BalanceOutScheme, TransactionOutScheme, TransferInScheme, TransferOutScheme
└── services.py        # create_account_for_user, get_balance, list_transactions, execute_transfer
```

Changes to existing files:

- `simplebank/apps/users/services.py` — `register_user` calls
  `create_account_for_user` inside the same `transaction.atomic()` block.
- `simplebank/settings/components/common.py` — add
  `'simplebank.apps.accounts'` to `INSTALLED_APPS`.
- `simplebank/urls.py` — `api.add_router('/accounts', accounts_router)`.
- `tests/` — new tests, mirroring the existing `users` test structure.

## Implementation sequence

1. `Account`, `Transfer`, `Transaction` models + migration; register in
   `INSTALLED_APPS` and `admin.py`.
2. Account number generation and `services.create_account_for_user`, with
   tests for uniqueness and collision retry.
3. Wire into registration: `register_user` creates the account and welcome
   bonus transaction inside one `atomic()` block; end-to-end registration
   tests.
4. Balance: `services.get_balance` + `GET /accounts/balance`, including a
   401 test.
5. Transaction history: `services.list_transactions` (`from`/`to` filter) +
   `GET /accounts/transactions` with pagination, plus tests.
6. Fee calculation: pure `calculate_fee` function, tests for the 2.5%-vs-€5
   boundary and rounding.
7. Transfer: `services.execute_transfer` (locking, checks, atomicity) +
   `POST /accounts/transfer` + `exceptions.py` — the largest piece; tests
   for success, insufficient funds, self-transfer, non-existent receiver,
   atomicity rollback, and concurrent transfers.
8. Final pass: `ruff`, `mypy`, `pytest --all`, `pre-commit run --all-files`.

## Data model

### `Account`

- `user`: `OneToOneField(User)`.
- `account_number`: `CharField`, unique, exactly 10 digits. Generated
  randomly at creation time; on a uniqueness collision, retry with a new
  random number.
- `balance`: `DecimalField(max_digits=12, decimal_places=2)`.
- `created_at`: `DateTimeField(auto_now_add=True)`.

### `Transfer`

Represents one transfer operation between two accounts (the "header"
record).

- `sender_account`: `FK(Account, related_name='outgoing_transfers')`.
- `receiver_account`: `FK(Account, related_name='incoming_transfers')`.
- `amount`: `DecimalField` — the amount requested by the sender, excluding
  fee.
- `fee`: `DecimalField`.
- `created_at`: `DateTimeField(auto_now_add=True)`.

### `Transaction`

One ledger entry against a single account.

- `account`: `FK(Account, related_name='transactions')`.
- `type`: `TextChoices` — `CREDIT` / `DEBIT`.
- `amount`: `DecimalField` — the amount of this specific entry (for a
  transfer's debit entry, this is `transfer.amount + transfer.fee`; for the
  credit entry, `transfer.amount`).
- `timestamp`: `DateTimeField(auto_now_add=True)`.
- `transfer`: `FK(Transfer, null=True, related_name='transactions')` — null
  for the registration welcome-bonus entry.

Index on `(account, timestamp)` to keep history queries with date filters
fast.

## Business rules

### Registration bonus

`register_user` (in `users/services.py`) gains a follow-up step, invoked
from the same call (not a Django signal, so behavior stays traceable and
directly testable): create an `Account` for the new user with
`balance=10000.00`, then a single `Transaction(type=CREDIT, amount=10000.00,
transfer=None)`. Account creation and the bonus transaction happen in the
same `transaction.atomic()` block as user creation, so a failure leaves no
partial state.

### Transfer fee

`fee = max(amount * Decimal('0.025'), Decimal('5.00'))`, quantized to 2
decimal places with `ROUND_HALF_UP`.

### Transfer — atomicity

The entire transfer (balance check, both balance updates, `Transfer`
creation, both `Transaction` rows) runs inside one `transaction.atomic()`
block. Either both balance changes and both transactions are committed, or
none are — there is no state where only the sender's debit or only the
receiver's credit exists. This is a hard invariant, verified by a dedicated
test that forces an exception between the two balance updates and asserts
a full rollback (balances unchanged, no `Transaction`/`Transfer` rows
created).

Steps inside the atomic block:

1. Lock both accounts with `select_for_update()`, always in ascending `id`
   order (sender/receiver order can vary) to avoid deadlocks between
   concurrent transfers.
2. Look up the receiver account by `account_number`; if it doesn't exist,
   raise `AccountNotFoundError` (404).
3. If `receiver_account == sender_account`, raise
   `SameAccountTransferError` (422).
4. Compute `fee`; if `sender.balance < amount + fee`, raise
   `InsufficientFundsError` (422) — nothing is written.
5. Create `Transfer(sender_account, receiver_account, amount, fee)`.
6. Create the debit `Transaction` (sender, `amount + fee`) and credit
   `Transaction` (receiver, `amount`).
7. Update both `Account.balance` fields and save.

## API

New router mounted at `/accounts` in `simplebank/urls.py`, alongside the
existing `/auth` router. All endpoints require JWT authentication (reuse
`ninja_jwt` auth already configured for `/auth`).

- `GET /accounts/balance` → `{account_number, balance}` for the
  authenticated user's account.
- `GET /accounts/transactions?from=&to=` → transactions for the
  authenticated user's account, newest first (`-timestamp`), paginated with
  `ninja.pagination.PageNumberPagination`. `from`/`to` are optional dates
  filtering `timestamp`.
- `POST /accounts/transfer` — body `{account_number, amount}` (`amount`
  validated `> 0` at the schema level via `Field(gt=0)`). Returns 201 with
  transfer details (`amount`, `fee`, `total_debited`) on success; 404 if the
  receiver account doesn't exist; 422 for insufficient funds or
  self-transfer.

## Error handling

New `simplebank/apps/accounts/exceptions.py`, mirroring `users`:

- `AccountNotFoundError` → 404
- `InsufficientFundsError` → 422
- `SameAccountTransferError` → 422

## Testing

- **Models/services**: unique `account_number` generation including a
  forced collision → retry; welcome bonus created on registration; fee
  calculation at the 2.5%-vs-€5 boundary and rounding behavior.
- **Transfer success**: balances updated correctly, `Transfer` row created,
  both `Transaction` rows created with correct amounts/types.
- **Transfer failure paths**: insufficient funds (balances and transaction
  history unchanged), transfer to self, transfer to a non-existent account
  number.
- **Concurrency**: two simultaneous transfers from the same account cannot
  drive the balance negative (relies on `select_for_update()`).
- **Atomicity**: forced exception mid-transfer results in a full rollback
  (no partial balance change, no orphan `Transaction`/`Transfer`).
- **API**: `balance` and `transactions` return 401 without a token;
  `transactions` respects `from`/`to` filtering and pagination; `transfer`
  covers all response codes (201/401/404/422).
