# NMS High Availability Architecture

## Scope

This design preserves the existing FastAPI API, PostgreSQL schema, SNMP v2c/v3 collectors, discovery, monitoring jobs, alerts, topology, and reports. It is an infrastructure and ownership plan; application behavior is not changed by this document.

## FastAPI instances

- Run two or more identical FastAPI instances behind a health-checked load balancer.
- Instances are stateless: JWT validation remains local, while PostgreSQL remains the source of truth for NMS data.
- Use readiness checks for database and Redis connectivity; liveness checks must not depend on downstream SNMP devices.
- Drain connections before shutdown so in-flight API requests finish safely.

## PostgreSQL HA

- Use one primary with synchronous streaming replication to a standby for the required durability level, plus an asynchronous replica for reporting/read workloads.
- Put a managed virtual endpoint or connection pooler in front of primary/standby failover. The application keeps its existing `DATABASE_URL` contract.
- Back up WAL and verify point-in-time recovery. Migrations run once through a deployment job, never concurrently from every web instance.
- Keep polling writes and API reads within bounded pool sizes; monitor replication lag, pool saturation, locks, and failed-over connections.

## Redis HA

- Use Redis Sentinel or a managed Redis failover service for cache, distributed leases, and short-lived coordination state. Redis is never the durable source for devices, jobs, alerts, or history.
- Configure a shared `REDIS_URL`/Sentinel endpoint for every instance and use short TTLs on leases with owner tokens.
- Redis loss must fail closed for scheduler leadership and fall back to API-safe degraded behavior, not allow multiple schedulers to run.

## Scheduler ownership

- Exactly one instance owns the monitoring scheduler at a time. Instances acquire `nms:scheduler:leader` with a renewable lease and unique owner token.
- Only the leader restores persisted monitoring jobs and executes scheduled polls. A watchdog renews the lease; expiry allows another healthy instance to take over.
- Manual polls remain available on any API instance, but use the same distributed lock key `nms:poll:{device_id}:{module_name}`.
- Lock acquisition is non-blocking for duplicate work and does not affect unrelated devices or modules. TTLs cover worst-case SNMP timeout plus retries and are released by the owner.
- On leader loss, the replacement reloads durable enabled jobs from PostgreSQL; in-flight work is allowed to expire and is not duplicated indefinitely.

## Failure handling and observability

- Expose leader owner, lease age, scheduler backlog, lock contention, missed polls, database health, Redis health, and replication lag in existing observability metrics/logs.
- Alert on repeated leadership changes, lease renewal failure, pool exhaustion, replication lag, and poll backlog growth.
- Validate failover with API traffic, PostgreSQL primary loss, Redis primary loss, scheduler process termination, and concurrent manual/scheduled poll tests.

## Rollout order

1. Provision PostgreSQL replication/backups and Redis HA without changing application behavior.
2. Add distributed lease/lock implementations behind the existing scheduler interfaces.
3. Run one scheduler leader with replica instances in standby mode.
4. Exercise failover and concurrency regression tests, then scale API replicas.
