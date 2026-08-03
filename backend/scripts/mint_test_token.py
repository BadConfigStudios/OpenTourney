#!/usr/bin/env python3
import argparse
import time
import uuid

import jwt


def mint_token(
    private_key,
    *,
    kid: str,
    issuer: str,
    audience: str,
    player_uuid: str,
    source_system: str,
    roles: list[str] | None = None,
    expires_in: int = 3600,
) -> str:
    now = int(time.time())
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": str(player_uuid),
        "source_system": source_system,
        "roles": roles or [],
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mint a test OIDC token for manual staging verification."
    )
    parser.add_argument("--private-key-path", required=True, help="Path to a PEM RSA private key")
    parser.add_argument("--kid", required=True)
    parser.add_argument("--issuer", required=True)
    parser.add_argument("--audience", required=True)
    parser.add_argument("--player-uuid", default=str(uuid.uuid4()))
    parser.add_argument("--source-system", default="manual-verification")
    parser.add_argument("--organizer", action="store_true", help="include the organizer claim")
    args = parser.parse_args()

    with open(args.private_key_path, "rb") as key_file:
        private_key_pem = key_file.read()

    token = mint_token(
        private_key_pem,
        kid=args.kid,
        issuer=args.issuer,
        audience=args.audience,
        player_uuid=args.player_uuid,
        source_system=args.source_system,
        roles=["organizer"] if args.organizer else [],
    )
    print(token)


if __name__ == "__main__":
    main()
