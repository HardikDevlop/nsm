---
kind: business_term
name: Business Glossary
category: business_term
scope:
    - '**'
---

### NMS
- Definition：Network Management System — the full-stack application combining device discovery, inventory management, monitoring, and RBAC-controlled API access across the backend, icmp_discovery, and frontend modules.
- Aliases：Network Management System

### RBAC
- Definition：Role-Based Access Control system with three seeded roles: Admin (full access), Operator (read-all plus create/update on operational modules including discovery/monitoring), and Viewer (read-only). Permissions follow a module:action pattern (e.g., devices:read, alerts:update).
- Aliases：Role-Based Access Control

### soft-delete
- Definition：Deletion strategy where records are marked with a deleted_at timestamp rather than being physically removed from the database, applied to models that support it in the CRUD repository layer.

### device profiling
- Definition：Process of converting raw discovery outputs (ICMP, TCP, SNMP, ARP, DNS, HTTP, WMI, SSH) into structured product inventory fields including vendor, category, model, OS, and confidence score.
- Aliases：profiling

### inventory
- Definition：Canonical device record containing IP, hostname, category, model, OS, status, confidence, interfaces, vendor, firmware, MAC address, and IP — stored by inventory_service.py after device profiling completes.
- Aliases：device inventory

### discovery modules
- Definition：Pluggable network scanning components (IP, ICMP, TCP, SNMP, ARP, DNS, HTTP, WMI, SSH) that each probe specific aspects of network devices and feed results to the device profiler.
- Aliases：scanning modules

### audit logs
- Definition：Read-only log records tracking administrative actions performed through the API, accessible only to users with audit_logs:read permission.
