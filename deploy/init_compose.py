import secrets
from pathlib import Path

path = Path(".env")
if path.exists():
    print(".env already exists; existing credentials kept.")
else:
    path.write_text(
        "POSTGRES_PASSWORD=" + secrets.token_hex(24) + "\nGRAFANA_PASSWORD=" + secrets.token_hex(24) + "\n"
    )
    path.chmod(0o600)
    print("Created local Docker credentials in .env. Do not commit this file.")
