"""Pure X.509 PEM bundle parsing and CA suitability validation.

This module has no database, filesystem, network, or trust-store side effects.
It validates bytes only; storage and explicit trust assignment are separate
concerns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed25519, ed448, padding, rsa
from cryptography.hazmat.primitives.serialization import Encoding


MAX_BUNDLE_BYTES = 1024 * 1024
MAX_CERTIFICATES = 50
MAX_CERTIFICATE_BYTES = 256 * 1024
_CERT_BLOCK = re.compile(
    rb"-----BEGIN CERTIFICATE-----\s*.*?\s*-----END CERTIFICATE-----",
    re.DOTALL,
)
_PRIVATE_KEY_MARKER = re.compile(rb"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")


class CABundleParseError(ValueError):
    """Stable safe error raised for invalid or unsuitable CA bundle input."""

    def __init__(self, code: str, message: str, *, classification: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.classification = classification


@dataclass(frozen=True)
class CertificateMetadata:
    subject: str
    issuer: str
    serial_number: str
    sha256_fingerprint: str
    not_before: datetime
    not_after: datetime
    is_ca: bool
    is_self_issued: bool
    is_self_signed: bool
    subject_alt_names: tuple[str, ...]
    key_cert_sign: bool | None


@dataclass(frozen=True)
class ParsedCABundle:
    certificates: tuple[CertificateMetadata, ...]
    content_sha256: str
    certificate_count: int
    is_ca: bool
    is_self_signed: bool
    trust_type: str
    subject: str | None
    issuer: str | None
    serial_number: str | None
    not_before: datetime | None
    not_after: datetime | None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _name(value: x509.Name) -> str:
    return value.rfc4514_string()


def _self_signed(certificate: x509.Certificate) -> tuple[bool, bool]:
    is_self_issued = certificate.subject == certificate.issuer
    if not is_self_issued:
        return False, False
    public_key = certificate.public_key()
    try:
        if isinstance(public_key, rsa.RSAPublicKey):
            public_key.verify(certificate.signature, certificate.tbs_certificate_bytes, padding.PKCS1v15(), certificate.signature_hash_algorithm)
        elif isinstance(public_key, ec.EllipticCurvePublicKey):
            public_key.verify(certificate.signature, certificate.tbs_certificate_bytes, ec.ECDSA(certificate.signature_hash_algorithm))
        elif isinstance(public_key, dsa.DSAPublicKey):
            public_key.verify(certificate.signature, certificate.tbs_certificate_bytes, certificate.signature_hash_algorithm)
        elif isinstance(public_key, (ed25519.Ed25519PublicKey, ed448.Ed448PublicKey)):
            public_key.verify(certificate.signature, certificate.tbs_certificate_bytes)
        else:
            return True, False
    except (InvalidSignature, ValueError, TypeError):
        return True, False
    return True, True


def _parse_certificate(block: bytes, now: datetime) -> CertificateMetadata:
    if len(block) > MAX_CERTIFICATE_BYTES:
        raise CABundleParseError("unsupported_content", "Certificate block exceeds the permitted size")
    try:
        certificate = x509.load_pem_x509_certificate(block)
        der = certificate.public_bytes(Encoding.DER)
    except Exception:
        raise CABundleParseError("invalid_pem", "Certificate PEM is malformed") from None
    try:
        constraints = certificate.extensions.get_extension_for_class(x509.BasicConstraints).value
    except x509.ExtensionNotFound:
        raise CABundleParseError("not_a_ca", "Certificate does not declare CA basic constraints") from None
    if not constraints.ca:
        subject, issuer = _name(certificate.subject), _name(certificate.issuer)
        raise CABundleParseError(
            "not_a_ca",
            "Certificate is not a CA certificate",
            classification="self_signed_server_requires_explicit_trust" if subject == issuer else None,
        )
    try:
        key_usage = certificate.extensions.get_extension_for_class(x509.KeyUsage).value
        key_cert_sign = key_usage.key_cert_sign
    except x509.ExtensionNotFound:
        key_cert_sign = None
    if key_cert_sign is False:
        raise CABundleParseError("invalid_key_usage", "CA certificate cannot sign certificates")
    before_value = getattr(certificate, "not_valid_before_utc", None) or certificate.not_valid_before
    after_value = getattr(certificate, "not_valid_after_utc", None) or certificate.not_valid_after
    not_before = _utc(before_value)
    not_after = _utc(after_value)
    if not_before > now:
        raise CABundleParseError("not_yet_valid", "CA certificate is not yet valid")
    if not_after < now:
        raise CABundleParseError("expired_certificate", "CA certificate is expired")
    is_self_issued, is_self_signed = _self_signed(certificate)
    if is_self_issued and not is_self_signed:
        raise CABundleParseError("invalid_signature", "Self-issued CA certificate has an invalid signature")
    try:
        san_extension = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        subject_alt_names = tuple(str(name.value) for name in san_extension)
    except x509.ExtensionNotFound:
        subject_alt_names = ()
    return CertificateMetadata(
        subject=_name(certificate.subject),
        issuer=_name(certificate.issuer),
        serial_number=str(certificate.serial_number),
        sha256_fingerprint=hashlib.sha256(der).hexdigest(),
        not_before=not_before,
        not_after=not_after,
        is_ca=True,
        is_self_issued=is_self_issued,
        is_self_signed=is_self_signed,
        subject_alt_names=subject_alt_names,
        key_cert_sign=key_cert_sign,
    )


def parse_ca_bundle(pem_bytes: bytes) -> ParsedCABundle:
    """Parse and validate one or more currently valid CA certificates."""
    if not isinstance(pem_bytes, bytes):
        raise CABundleParseError("unsupported_content", "CA bundle content must be bytes")
    if len(pem_bytes) > MAX_BUNDLE_BYTES:
        raise CABundleParseError("bundle_too_large", "CA bundle exceeds the permitted size")
    if _PRIVATE_KEY_MARKER.search(pem_bytes):
        raise CABundleParseError("private_key_rejected", "Private keys are not accepted in CA bundles")
    blocks = list(_CERT_BLOCK.finditer(pem_bytes))
    if not blocks:
        raise CABundleParseError("invalid_pem", "CA bundle contains no PEM certificates")
    if len(blocks) > MAX_CERTIFICATES:
        raise CABundleParseError("too_many_certificates", "CA bundle contains too many certificates")
    cursor = 0
    for match in blocks:
        if pem_bytes[cursor:match.start()].strip():
            raise CABundleParseError("unsupported_content", "CA bundle contains unsupported content")
        cursor = match.end()
    if pem_bytes[cursor:].strip():
        raise CABundleParseError("unsupported_content", "CA bundle contains trailing unsupported content")
    now = datetime.now(timezone.utc)
    metadata = tuple(_parse_certificate(match.group(0), now) for match in blocks)
    fingerprints = [item.sha256_fingerprint for item in metadata]
    if len(fingerprints) != len(set(fingerprints)):
        raise CABundleParseError("duplicate_certificate", "CA bundle contains duplicate certificates")
    return ParsedCABundle(
        certificates=metadata,
        content_sha256=hashlib.sha256(pem_bytes).hexdigest(),
        certificate_count=len(metadata),
        is_ca=all(item.is_ca for item in metadata),
        is_self_signed=all(item.is_self_signed for item in metadata),
        trust_type="self_signed_explicit" if all(item.is_self_signed for item in metadata) else "enterprise_ca",
        subject=metadata[0].subject if len(metadata) == 1 else None,
        issuer=metadata[0].issuer if len(metadata) == 1 else None,
        serial_number=metadata[0].serial_number if len(metadata) == 1 else None,
        not_before=metadata[0].not_before if len(metadata) == 1 else None,
        not_after=metadata[0].not_after if len(metadata) == 1 else None,
    )
