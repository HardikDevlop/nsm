import xml.etree.ElementTree as ET

from backend.windows_monitoring.cim import WindowsCIMClient


def body(xml):
    return ET.fromstring(xml)


def node(class_name, fields):
    values = "".join(f'<p:{k} xmlns:p="urn:test">{v}</p:{k}>' for k, v in fields.items())
    return f'<p:{class_name} xmlns:p="urn:test">{values}</p:{class_name}>'


def response(items, context=None, eos=True):
    ctx = f'<wsen:EnumerationContext xmlns:wsen="http://schemas.xmlsoap.org/ws/2004/09/enumeration">{context}</wsen:EnumerationContext>' if context else ''
    end = '<wsen:EndOfSequence xmlns:wsen="http://schemas.xmlsoap.org/ws/2004/09/enumeration" />' if eos else ''
    return body(f'<s:Body xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:wsen="http://schemas.xmlsoap.org/ws/2004/09/enumeration" xmlns:wsman="http://schemas.dmtf.org/wbem/wsman/1/wsman.xsd">{ctx}<wsen:Items>{items}</wsen:Items>{end}</s:Body>')


class FakeWSMan:
    def __init__(self, pages, error=None):
        self.pages = list(pages)
        self.error = error
        self.calls = []
        self.closed = False

    def enumerate(self, resource_uri, resource=None, timeout=None):
        self.calls.append(("enumerate", resource_uri, resource, timeout))
        if self.error:
            raise self.error
        return self.pages.pop(0)

    def pull(self, resource_uri, resource=None, timeout=None):
        self.calls.append(("pull", resource_uri, resource, timeout))
        return self.pages.pop(0)

    def close(self):
        self.closed = True


def make_client(fake, **kwargs):
    captured = {}

    def factory(hostname, **values):
        captured.update(hostname=hostname, **values)
        return fake

    return WindowsCIMClient("winhost.example", "admin", "secret-value", wsman_factory=factory, **kwargs), captured
