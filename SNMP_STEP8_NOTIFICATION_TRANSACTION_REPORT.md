# SNMP Step 8 Notification Transaction Report

## Result

Step 8 preserves durable alert and notification-intent creation inside the single SNMP poll transaction while moving SMTP delivery and delivery-status persistence after that transaction commits. No unmanaged task or external queue was introduced; delivery remains synchronous in the polling worker, but no poll database transaction is held during external I/O.

## Previous blocking path

The scheduled poll path was:

```text
SNMPPoller._evaluate_alerts()
  -> alerting.create_threshold_alert()
  -> add/flush Alert
  -> incident processing
  -> alerting._notify()
     -> select recipients
     -> add Notification(status=pending)
     -> smtplib.SMTP connect(timeout=10)
     -> optional STARTTLS
     -> optional login
     -> send_message
     -> set delivered/failed status
  -> final poll commit
```

The blocking external operations were SMTP connection, TLS negotiation, authentication, and message transmission in `backend/services/alerting.py:_notify()`.

## New durable-first path

For the deferred scheduled-SNMP path, `_notify()` still resolves the same recipients and creates/flushed `Notification(status=pending)` rows in the poll transaction. It copies all delivery data into immutable `NotificationIntent` values: notification/alert IDs, title, description, severity, status, and recipient. No ORM object or session is needed for delivery.

After latest/history, polling history, alerts, notification intents, and monitoring state commit successfully, `_poll_in_worker()` calls `deliver_notification_intents()` using a new worker-owned session. SMTP runs with no poll transaction open. The separate session updates committed notification rows to the same pending/delivered/failed states and commits those status updates.

Other alert callers retain their prior synchronous `_notify()` behavior because deferred intent collection is opt-in and internal to the scheduled SNMP transaction.

## Failure semantics

- Poll transaction failure occurs before intent delivery, so no external notification is sent for rolled-back state.
- SMTP failure is logged and produces the same failed notification status.
- An unexpected post-commit delivery/status exception rolls back only the delivery-status session, is logged, and does not roll back or change the already committed poll/alert transaction.
- No SQLAlchemy session or ORM alert object crosses into the delivery operation.
- No fire-and-forget asyncio task, leaked future, or new infrastructure was introduced.

## Preserved behavior

Alert eligibility, thresholds, severity, titles/descriptions, recipients, channels, deduplication, active states, resolution, timestamps, incident hooks, SMTP settings, TLS/login behavior, and daily-limit suspension remain unchanged. Steps 2–7, scheduler configuration, API contracts, schema, migrations, and frontend are untouched.

## Deterministic proof

Tests record ordered events with a controlled slow notifier:

1. poll transaction commit;
2. slow external delivery receives the immutable expected payload;
3. delivery-status commit.

A poll-commit failure test proves delivery is never called and rollback occurs. A delivery-failure test proves the successful poll remains committed while only the delivery session rolls back. The slow notifier's delay occurs after the poll commit marker, demonstrating it is outside the database transaction rather than claiming a production timing improvement.

Focused SNMP transaction/alert tests: **21 passed, 0 failed**.

Broader non-database SNMP and incident regression suite: **236 passed, 0 failed, 1 skipped**. The skip is the opt-in real-device integration test. Python compilation and `git diff --check` passed.

PostgreSQL is unavailable in the current environment, so live database transaction verification is **RUNTIME VERIFICATION PENDING**.

The next recommended optimization is to batch post-delivery notification-status updates into one set-oriented write per delivery outcome.
