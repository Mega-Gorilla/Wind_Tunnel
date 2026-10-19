import hashlib
import secrets
import time
from dataclasses import dataclass
from ipaddress import ip_address
from uuid import uuid4

from fastapi import HTTPException

from .models import canonical_ip


def deny(code, status=403):
    raise HTTPException(status, detail={"code": code})


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class Principal:
    id: str
    name: str
    local: bool
    ip: str


class Security:
    def __init__(self, store, bootstrap_code, clock=time.monotonic):
        self.store = store
        self.clock = clock
        self.bootstrap_hash = token_hash(bootstrap_code)
        self.sessions = {}

    def bootstrap(self, code, peer):
        if not ip_address(peer).is_loopback:
            deny("LOCAL_BOOTSTRAP_ONLY")
        if not self.bootstrap_hash or not secrets.compare_digest(token_hash(code), self.bootstrap_hash):
            deny("INVALID_BOOTSTRAP", 401)
        self.bootstrap_hash = None  # One use; never persist a browser's session or auto-login remotely.
        session, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.sessions[session] = (csrf, self.clock() + 8 * 3600)
        return session, csrf

    def authenticate(self, request, scope, local_only=False):
        peer = canonical_ip(request.client.host)
        header = request.headers.get("authorization")
        if header is not None:
            if not header.startswith("Bearer "):
                deny("AUTH_REQUIRED", 401)
            digest = token_hash(header[7:])
            client = next((c for c in self.store.clients()
                           if secrets.compare_digest(c["token_hash"], digest) and not c["revoked"]), None)
            if client is None:
                deny("INVALID_TOKEN", 401)
            if peer not in client["allowed_ips"]:
                deny("IP_NOT_ALLOWED")
            if local_only or scope not in client["scopes"]:
                deny("SCOPE_DENIED")
            return Principal(client["id"], client["name"], False, peer)
        session = self.sessions.get(request.cookies.get("wt_session", ""))
        if not session or self.clock() >= session[1] or not ip_address(peer).is_loopback:
            deny("LOCAL_SESSION_OR_TOKEN_REQUIRED", 401)
        if request.method not in ("GET", "HEAD"):
            if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), session[0]):
                deny("CSRF_REQUIRED")
        return Principal("local", "本体画面", True, peer)

    def create_client(self, spec):
        if len(self.store.clients()) >= 32:
            deny("CLIENT_LIMIT", 409)
        token = secrets.token_urlsafe(32)
        client = dict(id=str(uuid4()), **spec.model_dump(), token_hash=token_hash(token), revoked=False)
        self.store.save_client(client)
        return {**self.public_client(client), "token": token}

    def renew_local_session(self, request, response, secure):
        # A continuously connected local kiosk must not cancel unlimited remote
        # mode merely because its original 8-hour cookie aged out.
        key = request.cookies['wt_session']
        csrf, expires = self.sessions[key]
        if expires - self.clock() < 4 * 3600:
            self.sessions[key] = (csrf, self.clock() + 8 * 3600)
            response.set_cookie('wt_session', key, httponly=True, samesite='strict',
                                secure=secure, max_age=8 * 3600)

    @staticmethod
    def public_client(client):
        return {k: v for k, v in client.items() if k != "token_hash"}
