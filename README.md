# White Stone Core (Phase 0)

White Stone encrypts a secret locally, then splits only its random 256-bit key into SLIP-39 tesserae. A Stone JSON file contains ciphertext and metadata; it cannot reveal the secret without enough valid tesserae.

## Setup

Python 3.10 or newer is required. A virtual environment is recommended:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install pytest
```

## Create a Stone
## Local GUI

Run the local interface from the project folder:

```powershell
python -m streamlit run streamlit_app.py --server.address 127.0.0.1
```

Open `http://localhost:8501` in your browser. The GUI supports a single-group k-of-n Stone, named Keeper cards, an ordered handoff ceremony, and opening a Stone from its JSON and tessera files. Keep the Stone file separate from the Keeper cards.

## Create a Stone

```powershell
python white_stone.py create --secret "My important secret" --k 3 --n 5 --name "Family Vault"
```

This creates `vault.json`, `shard1.txt` through `shard5.txt`, and matching QR PNG files in the current directory. To avoid putting the secret in shell history or process arguments, omit `--secret`; the CLI prompts for it without echoing.

Generated files are not overwritten. Use an empty directory for each Stone:

```powershell
python white_stone.py create --k 3 --n 5 --name "Family Vault" --output-dir "family-vault"
```

## Open a Stone

Provide at least the configured threshold of distinct tessera files:

```powershell
python white_stone.py open --vault vault.json --shard shard1.txt --shard shard2.txt --shard shard3.txt
```

The CLI displays the recovered text in the terminal. The core API also accepts binary secrets, but this CLI currently reveals text only. Passphrase-protected Stones prompt for the passphrase when opening.

## Tests

```powershell
python -m pytest
```

## Security Status

This is a development prototype, not an audited product. It uses PyNaCl's XChaCha20-Poly1305 and the `shamir-mnemonic` SLIP-39 implementation; it does not implement cryptographic primitives itself. Do not use it for real high-value secrets until an independent security review is complete.

The secret passed with `--secret` may be recorded in shell history or visible in process listings; prefer the hidden prompt. Tessera text and QR PNG files are sensitive artifacts, so distribute each tessera and any passphrase through separate channels. Python cannot reliably erase secret values from memory. The CLI does not promise memory wiping, secure file storage, or protection against screenshots. SLIP-39 identifiers are only 15 bits; authenticated decryption is the final integrity check if identifiers collide.

The GUI runs locally and sends browser inputs to its Python process on the same computer. Bind it to `127.0.0.1` as shown above; do not expose it to a network or use a hosted Streamlit service, which would receive the secret, passphrase, and tesserae. “Erase session” clears the app's session values but cannot guarantee memory wiping.