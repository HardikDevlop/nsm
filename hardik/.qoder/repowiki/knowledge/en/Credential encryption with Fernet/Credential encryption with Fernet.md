---
kind: external_dependency
name: Credential encryption with Fernet
slug: cryptography-fernet
category: external_dependency
category_hints:
    - auth_protocol
scope:
    - '**'
source_files:
    - backend/utils/crypto.py
    - backend/.env
---

Device credential encryption uses Fernet symmetric encryption from the cryptography library (>=42.0). The encryption key is provided via CREDENTIAL_ENCRYPTION_KEY environment variable.