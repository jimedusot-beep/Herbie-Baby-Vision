"""Small, fail-closed client for a *future* authenticated H.E.R.B.I.E. gateway.

This does not expose Ollama or activate networking on either computer. It only
implements and checks the Baby Vision side of contract version 1. The server
must independently authenticate, authorize, rate-limit, and bound requests.
"""

import json
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from uuid import UUID

MAX_PROMPT_BYTES = 12_000
MAX_RESPONSE_BYTES = 65_536
TASK_TYPES = frozenset({'coding', 'testing', 'research', 'review'})


class GatewayError(RuntimeError):
    """A sanitized failure; never includes credentials or response bodies."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_gateway_url(base_url):
    """Allow HTTPS Tailscale Serve names, or HTTP loopback for local tests.

    Raw HTTP across a LAN is intentionally unsupported. A direct encrypted LAN
    transport will be designed and verified separately before offline use.
    """
    if not isinstance(base_url, str) or not base_url or any(c.isspace() for c in base_url):
        raise ValueError('Invalid gateway URL')
    try:
        url = urlsplit(base_url)
        host, port = url.hostname, url.port
    except ValueError:
        raise ValueError('Invalid gateway URL') from None
    if (not host or url.username is not None or url.password is not None or
            url.path not in ('', '/') or url.query or url.fragment or
            not re.fullmatch(r'[a-z0-9.-]+', host)):
        raise ValueError('Gateway URL must be a plain host without user info or paths')
    if url.scheme == 'http' and host in ('127.0.0.1', 'localhost') and port:
        return base_url.rstrip('/')
    if (url.scheme == 'https' and host.endswith('.ts.net') and
            port in (None, 443)):
        return base_url.rstrip('/')
    raise ValueError('Gateway requires a Tailscale HTTPS host or HTTP loopback')


class HerbieGatewayClient:
    """One-call inference transport; task execution and permissions stay in Baby Vision."""

    def __init__(self, base_url, token, model, timeout=30):
        self.base_url = validate_gateway_url(base_url)
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9._~-]{32,256}', token):
            raise ValueError('A sufficiently long gateway bearer token is required')
        if (not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,99}', model)):
            raise ValueError('A valid configured model name is required')
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 0 < timeout <= 90:
            raise ValueError('Timeout must be between 0 and 90 seconds')
        self._token = token
        self.model = model
        self.timeout = timeout

    def health(self):
        """Authenticated gateway liveness, with no model or personal data exposed.

        A successful health response does not prove Ollama inference is working.
        """
        req = urllib.request.Request(self.base_url + '/v1/worker/health',
                method='GET', headers={'Authorization': 'Bearer ' + self._token,
                                       'Accept': 'application/json'})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        try:
            with opener.open(req, timeout=self.timeout) as response:
                raw = response.read(1025)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
            raise GatewayError('H.E.R.B.I.E. gateway health check failed') from None
        if len(raw) > 1024:
            raise GatewayError('Invalid H.E.R.B.I.E. health response')
        try:
            body = json.loads(raw.decode('utf-8'))
        except (ValueError, UnicodeError):
            raise GatewayError('Invalid H.E.R.B.I.E. health response') from None
        if (not isinstance(body, dict) or set(body) != {'schema_version', 'ok'}
                or type(body['schema_version']) is not int or body['schema_version'] != 1
                or body['ok'] is not True):
            raise GatewayError('Invalid H.E.R.B.I.E. health response')
        return True

    def infer(self, task_type, prompt, request_id):
        """Send one inference request, without automatic retries or side effects.

        A retrying coordinator must reuse the same request_id and check the job
        state before any subsequent work. This client never executes code.
        """
        if task_type not in TASK_TYPES:
            raise ValueError('Unapproved worker task type')
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt.encode('utf-8')) > MAX_PROMPT_BYTES:
            raise ValueError('Prompt is empty or exceeds the size limit')
        try:
            if not isinstance(request_id, str) or str(UUID(request_id)) != request_id:
                raise ValueError()
        except ValueError:
            raise ValueError('request_id must be a canonical UUID') from None
        payload = json.dumps({'schema_version': 1, 'request_id': request_id,
                              'task_type': task_type, 'model': self.model,
                              'prompt': prompt}, separators=(',', ':')).encode('utf-8')
        req = urllib.request.Request(self.base_url + '/v1/worker/infer',
                data=payload, method='POST', headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Authorization': 'Bearer ' + self._token})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        try:
            with opener.open(req, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
            raise GatewayError('H.E.R.B.I.E. gateway unavailable or rejected request') from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise GatewayError('H.E.R.B.I.E. gateway response exceeds size limit')
        try:
            body = json.loads(raw.decode('utf-8'))
        except (ValueError, UnicodeError):
            raise GatewayError('Invalid H.E.R.B.I.E. gateway JSON response') from None
        if (not isinstance(body, dict) or set(body) != {'schema_version', 'request_id', 'model', 'reply'} or
                body['schema_version'] != 1 or body['request_id'] != request_id or
                body['model'] != self.model or not isinstance(body['reply'], str) or
                len(body['reply']) > 20_000):
            raise GatewayError('Invalid H.E.R.B.I.E. gateway response contract')
        return body['reply']
