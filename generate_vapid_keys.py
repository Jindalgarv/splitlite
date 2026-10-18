"""Generate a VAPID key pair for web push and print it as .env lines.

Keep the private key out of git: put both lines in .env locally and in
your hosting provider's environment variables in production.
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64url(data):
    return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')


private_key = ec.generate_private_key(ec.SECP256R1())
public_bytes = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.X962,
    format=serialization.PublicFormat.UncompressedPoint,
)
private_bytes = private_key.private_numbers().private_value.to_bytes(32, 'big')

print(f'VAPID_PUBLIC_KEY="{b64url(public_bytes)}"')
print(f'VAPID_PRIVATE_KEY="{b64url(private_bytes)}"')
