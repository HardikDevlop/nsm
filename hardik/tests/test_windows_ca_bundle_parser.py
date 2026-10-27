from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from backend.windows_monitoring.ca_bundle_parser import (
    MAX_BUNDLE_BYTES,
    CABundleParseError,
    parse_ca_bundle,
)


def make_certificate(*, common_name="Test CA", ca=True, key_cert_sign=True, not_before=None, not_after=None, subject=None, issuer=None, signer_key=None):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = subject or x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    issuer = issuer or subject
    now = datetime.now(timezone.utc)
    builder = x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(key.public_key())
    builder = builder.serial_number(x509.random_serial_number()).not_valid_before(not_before or now - timedelta(days=1)).not_valid_after(not_after or now + timedelta(days=365))
    builder = builder.add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
    if key_cert_sign is not None:
        builder = builder.add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=False, content_commitment=False, data_encipherment=False, key_agreement=False, key_cert_sign=key_cert_sign, crl_sign=ca, encipher_only=False, decipher_only=False), critical=True)
    certificate = builder.sign(private_key=signer_key or key, algorithm=hashes.SHA256())
    return key, certificate


def pem(certificate):
    return certificate.public_bytes(serialization.Encoding.PEM)


def test_valid_single_ca_and_metadata_are_utc_and_stable():
    _, certificate = make_certificate()
    result = parse_ca_bundle(pem(certificate))
    item = result.certificates[0]
    assert result.certificate_count == 1
    assert result.is_ca is True
    assert result.trust_type == "self_signed_explicit"
    assert len(item.sha256_fingerprint) == 64
    assert item.not_before.tzinfo == timezone.utc
    assert item.not_after.tzinfo == timezone.utc
    assert result.content_sha256 == parse_ca_bundle(pem(certificate)).content_sha256


def test_valid_multi_certificate_enterprise_bundle():
    root_key, first = make_certificate(common_name="Root CA")
    issuer = first.subject
    _, second = make_certificate(common_name="Intermediate CA", subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Intermediate CA")]), issuer=issuer, signer_key=root_key)
    result = parse_ca_bundle(pem(first) + b"\n" + pem(second))
    assert result.certificate_count == 2
    assert result.trust_type == "enterprise_ca"
    assert result.subject is None


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (b"not a certificate", "invalid_pem"),
        (b"\x30\x82\x01\x00", "invalid_pem"),
        (b"-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----", "private_key_rejected"),
        (b"-----BEGIN CERTIFICATE-----\nabc\n-----END CERTIFICATE-----\ntrailing", "unsupported_content"),
    ],
)
def test_unsupported_and_malformed_content_is_rejected(content, code):
    with pytest.raises(CABundleParseError) as exc:
        parse_ca_bundle(content)
    assert exc.value.code == code


def test_pkcs12_and_mixed_content_are_rejected():
    key, certificate = make_certificate()
    blob = pkcs12.serialize_key_and_certificates(b"bundle", key, certificate, None, serialization.NoEncryption())
    with pytest.raises(CABundleParseError) as exc:
        parse_ca_bundle(blob)
    assert exc.value.code in {"invalid_pem", "unsupported_content"}
    with pytest.raises(CABundleParseError) as exc:
        parse_ca_bundle(pem(certificate) + b"private text")
    assert exc.value.code == "unsupported_content"


def test_size_limit_and_duplicate_limit():
    with pytest.raises(CABundleParseError) as exc:
        parse_ca_bundle(b"x" * (MAX_BUNDLE_BYTES + 1))
    assert exc.value.code == "bundle_too_large"
    _, certificate = make_certificate()
    with pytest.raises(CABundleParseError) as exc:
        parse_ca_bundle(pem(certificate) * 2)
    assert exc.value.code == "duplicate_certificate"


def test_more_than_fifty_certificates_is_rejected():
    bundle = b"".join(pem(make_certificate(common_name=f"CA-{index}")[1]) for index in range(51))
    with pytest.raises(CABundleParseError) as exc:
        parse_ca_bundle(bundle)
    assert exc.value.code == "too_many_certificates"


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"not_before": datetime.now(timezone.utc) - timedelta(days=365), "not_after": datetime.now(timezone.utc) - timedelta(days=1)}, "expired_certificate"),
        ({"not_before": datetime.now(timezone.utc) + timedelta(days=1)}, "not_yet_valid"),
        ({"ca": False}, "not_a_ca"),
        ({"key_cert_sign": False}, "invalid_key_usage"),
    ],
)
def test_ca_suitability_failures(kwargs, code):
    _, certificate = make_certificate(**kwargs)
    with pytest.raises(CABundleParseError) as exc:
        parse_ca_bundle(pem(certificate))
    assert exc.value.code == code


def test_self_issued_but_not_self_signed_is_rejected_safely():
    signer, _ = make_certificate(common_name="Signer")
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Same Name")])
    _, certificate = make_certificate(subject=subject, issuer=subject, signer_key=signer)
    with pytest.raises(CABundleParseError) as exc:
        parse_ca_bundle(pem(certificate))
    assert exc.value.code == "invalid_signature"


def test_self_signed_non_ca_reports_explicit_future_trust_requirement():
    _, certificate = make_certificate(common_name="Windows Server", ca=False)
    with pytest.raises(CABundleParseError) as exc:
        parse_ca_bundle(pem(certificate))
    assert exc.value.code == "not_a_ca"
    assert exc.value.classification == "self_signed_server_requires_explicit_trust"


def test_parser_has_no_filesystem_side_effects(tmp_path):
    _, certificate = make_certificate()
    before = list(Path(tmp_path).iterdir())
    parse_ca_bundle(pem(certificate))
    assert list(Path(tmp_path).iterdir()) == before
