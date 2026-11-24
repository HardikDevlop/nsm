# Linux effective-memory Net-SNMP extension — administrator checklist

This is a deployment runbook only. The project-local script has been tested,
but this document does not install it, modify `/etc/snmp/snmpd.conf`, reload
`snmpd`, change NMS polling, or alter alert 2426.

## Artifacts and fixed identity

Reviewed project artifact:

```text
hardik/tools/agnigate_linux_memavailable.py
```

Proposed system installation path:

```text
/usr/local/libexec/agnigate-linux-memavailable
```

The script must remain a fixed, argument-free executable. It reads only
`/proc/meminfo` and prints one line:

```text
version=1 MemTotalKiB=<integer> MemAvailableKiB=<integer>
```

The proposed Net-SNMP token is:

```text
agnigateLinuxMem
```

The exact `nsExtendOutput1Line` numeric OID is:

```text
1.3.6.1.4.1.8072.1.3.2.3.1.1.16.97.103.110.105.103.97.116.101.76.105.110.117.120.77.101.109
```

It is derived from the `NET-SNMP-EXTEND-MIB` output-line path and the
length-prefixed ASCII index of `agnigateLinuxMem`. Do not substitute a guessed
OID or a different token.

## Approval gates

Obtain explicit approval and record the change window before each gate:

1. Approve installing the reviewed script into `/usr/local/libexec`.
2. Approve changing `/etc/snmp/snmpd.conf` and the SNMPv3 read-only view.
3. Approve a controlled `snmpd` reload.
4. Approve NMS-side integration only after the post-deployment SNMP result
   matches `/proc/meminfo`.

The existing Linux collector must not be switched to this source until gate 4
has passed.

## Pre-change inspection

Run as an administrator on the target host. Do not paste command output that
contains usernames, access rules, communities, or authentication material.

Confirm the agent version and service unit:

```text
snmpd -v
systemctl cat snmpd.service
```

For the known Net-SNMP 5.9.1 service, the unit uses `ExecReload` with SIGHUP;
record the current service state and main PID before making changes.

Check for a token collision without printing the full configuration:

```text
grep -nF 'agnigateLinuxMem' /etc/snmp/snmpd.conf
```

Any existing match is a deployment stop condition until an administrator
determines whether it is the same extension. Do not overwrite another token.

Review existing extension and access/view directives locally, with output
redacted before sharing:

```text
grep -nE '^[[:space:]]*(extend|extend-sh|pass|pass_persist|perl|dlmod|view|group|access|rouser|rwuser|authuser|authgroup)[[:space:]]' /etc/snmp/snmpd.conf
```

Confirm that the selected SNMPv3 `authPriv` account has read access to the
output subtree, and that it has no write access to extend configuration or row
control objects. Never add credentials to this runbook or to the script.

## Backup and permissions

Before changing anything, verify the original owner and mode, then make a
root-owned backup that preserves metadata:

```text
stat -c '%U:%G %a %n' /etc/snmp/snmpd.conf
install -d -o root -g root -m 0700 /var/backups/agnigate-snmpd
cp -a /etc/snmp/snmpd.conf /var/backups/agnigate-snmpd/snmpd.conf.<change-id>.pre
stat -c '%U:%G %a %n' /var/backups/agnigate-snmpd/snmpd.conf.<change-id>.pre
```

Install the reviewed script only after approval:

```text
install -o root -g root -m 0755 \
  hardik/tools/agnigate_linux_memavailable.py \
  /usr/local/libexec/agnigate-linux-memavailable
```

Verify that `Debian-snmp` can execute the file and read `/proc/meminfo`, while
keeping the script and directory non-writable by the service account.

## Proposed agent configuration

After the token-collision and view review, add exactly this directive:

```text
extend agnigateLinuxMem /usr/local/libexec/agnigate-linux-memavailable
```

The SNMPv3 read-only view must include:

```text
1.3.6.1.4.1.8072.1.3.2.3.1.1
```

The view should be restricted to the output subtree required by the NMS.
Do not grant write access to `nsExtendCommand`, `nsExtendArgs`, row-status,
or other extend-control objects. Keep transport security at `authPriv`.

## Configuration validation limitations

`snmpd -H` only lists supported configuration directives. It does not validate
the syntax or semantics of a candidate `snmpd.conf`.

A normal startup command is also not a safe syntax-only check: it may bind UDP
161, execute extensions, load modules, or conflict with the running daemon.
Do not test the production file by starting a second daemon on the live host.

For Net-SNMP 5.9.1, validate a candidate configuration by starting a separate
temporary instance in an approved staging host/container or isolated network
namespace, using a copied candidate file and a disposable PID file. For
example, the administrator may use the equivalent of:

```text
timeout 10s snmpd -f -Le -C \
  -c /path/to/candidate/snmpd.conf \
  -p /tmp/agnigate-snmpd-validation.pid
```

The validation environment must prevent binding the production UDP 161 socket,
must use no production credentials beyond what is required for parsing, and
must be destroyed afterward. Treat clean startup logs as configuration-load
evidence only; they do not prove that the NMS view, script permissions, OID
response, or runtime behavior is correct.

If isolated validation is unavailable, stop and obtain administrator review
rather than using `snmpd -H` or launching a second daemon on the production
socket as a substitute.

## Reload and post-change verification

The service unit provides:

```text
ExecReload=/bin/kill -HUP $MAINPID
```

A reload is preferred because it preserves the daemon process and existing
runtime state, but it can still reject the configuration or temporarily make
the agent unavailable. A restart is more disruptive and requires a separate
approval; do not use it as the first validation step.

After the approved reload, verify all of the following:

1. `systemctl is-active snmpd` reports active.
2. The main PID is unchanged after reload.
3. Service logs contain no configuration, permission, or extension errors.
4. Existing authorized SNMPv3 system, interface, and UCD OIDs still respond.
5. The fixed extend OID returns exactly one valid line.
6. The extend output is compared with a near-simultaneous local read:

   ```text
   awk '/^(MemTotal|MemAvailable):/ {print}' /proc/meminfo
   ```

   Compare the two KiB values while allowing ordinary sampling-time changes.
7. The NMS parser accepts the returned line and records the source semantic as
   `linux_proc_meminfo_memavailable`.

Do not activate the corrected Linux metric or alter alert behavior until these
checks succeed.

## Failure handling and rollback

Trigger rollback if configuration validation fails, `snmpd` does not remain
active, existing SNMP OIDs fail, the extension cannot execute as
`Debian-snmp`, the output is malformed, the view denies the required read, or
the values do not agree with `/proc/meminfo` within an approved sampling
tolerance.

Rollback procedure, requiring administrator approval:

```text
cp -a /var/backups/agnigate-snmpd/snmpd.conf.<change-id>.pre \
  /etc/snmp/snmpd.conf
chown --reference=/var/backups/agnigate-snmpd/snmpd.conf.<change-id>.pre \
  /etc/snmp/snmpd.conf
chmod --reference=/var/backups/agnigate-snmpd/snmpd.conf.<change-id>.pre \
  /etc/snmp/snmpd.conf
systemctl reload snmpd
```

Verify the service and existing monitoring again. Remove the installed script
only if no other approved configuration references it; otherwise leave the
file in place until the configuration rollback is complete. Preserve the
backup and all original ownership/mode metadata for audit and reattempts.

## NMS activation rule

The current Linux collector continues using its existing source until a later,
separately reviewed implementation changes it. A failed extension query is
unavailable; it must never silently fall back to legacy `memAvailReal`, and it
must not trigger automatic recovery. Historical samples and alert 2426 remain
unchanged during this deployment.
