# Virtualization Monitoring

VMware, Hyper-V and KVM adapters implement the `VirtualizationAdapter` protocol and never call SNMP collectors. Adapters emit normalized `host`, `vm`, `cluster`, `datastore`, and `virtual_switch` objects with provider metadata retained in `attributes`. Inventory is persisted by `(provider, external_key)` and can be linked to existing CMDB configuration items through `cmdb_ci_id`; provider-specific fields are not promoted into the common schema.
