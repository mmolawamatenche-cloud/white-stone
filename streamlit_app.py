"""Local Streamlit interface for White Stone creation and recovery."""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import qrcode
import qrcode.constants
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

from white_stone import Stone, WhiteStoneError, create_stone, join_progress, join_stone


def _qr_png(tessera: str) -> bytes:
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=8,
        border=4,
    )
    qr.add_data(tessera)
    qr.make(fit=True)
    output = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(output, format="PNG")
    return output.getvalue()


def _qr_card_png(
    tessera: str,
    stone_name: str,
    keeper_name: str,
    keeper_index: int,
    k: int,
    n: int,
) -> bytes:
    qr_image = Image.open(io.BytesIO(_qr_png(tessera))).convert("RGB")
    card_width = max(920, qr_image.width + 128)
    qr_top = 250
    card_height = qr_top + qr_image.height + 138
    card = Image.new("RGB", (card_width, card_height), "#FCFCFA")
    draw = ImageDraw.Draw(card)
    font_path = Path(ImageFont.__file__).parent / "fonts" / "DejaVuSans.ttf"

    def load_font(size: int) -> ImageFont.ImageFont:
        try:
            return ImageFont.truetype(str(font_path), size)
        except OSError:
            try:
                return ImageFont.load_default(size=size)
            except TypeError:
                return ImageFont.load_default()

    def font_that_fits(text: str, size: int) -> ImageFont.ImageFont:
        font = load_font(size)
        while draw.textbbox((0, 0), text, font=font)[2] > card_width - 128 and size > 18:
            size -= 2
            font = load_font(size)
        return font

    draw.rounded_rectangle(
        (20, 20, card_width - 20, card_height - 20),
        radius=24,
        outline="#CDD6D0",
        width=3,
    )
    draw.text((64, 48), "WHITE STONE", fill="#A94730", font=font_that_fits("WHITE STONE", 24))
    draw.text((64, 88), keeper_name, fill="#1C2823", font=font_that_fits(keeper_name, 46))
    threshold_text = f"KEEPER {keeper_index + 1}  |  {k} OF {n} NEEDED"
    draw.text((64, 158), threshold_text, fill="#53645B", font=font_that_fits(threshold_text, 24))
    card.paste(qr_image, ((card_width - qr_image.width) // 2, qr_top))
    footer_y = qr_top + qr_image.height + 34
    draw.text((64, footer_y), stone_name, fill="#1C2823", font=font_that_fits(stone_name, 24))
    draw.text((64, footer_y + 40), "Keep this tessera private.", fill="#53645B", font=font_that_fits("Keep this tessera private.", 20))

    output = io.BytesIO()
    card.save(output, format="PNG")
    return output.getvalue()


def _filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-")
    return cleaned or "white-stone"


def _clear_session() -> None:
    keys = [
        "stone_bundle",
        "ceremony_index",
        "words_visible",
        "create_name",
        "create_secret",
        "create_passphrase",
        "confirm_passphrase",
        "create_protected",
        "keeper_count",
        "keeper_threshold",
        "open_stone_file",
        "open_tessera_files",
        "open_passphrase",
    ]
    keys.extend(f"keeper_{index}" for index in range(16))
    for key in keys:
        st.session_state.pop(key, None)


def _render_create() -> None:
    bundle = st.session_state.get("stone_bundle")
    if bundle is None:
        st.subheader("Create a Stone")
        st.caption("Choose the threshold, name each Keeper, then seal the secret.")

        stone_name = st.text_input("Stone name", value="My White Stone", key="create_name")
        secret = st.text_input("Secret to protect", type="password", key="create_secret")

        n = st.selectbox("Number of Keepers", list(range(2, 17)), index=3, key="keeper_count")
        thresholds = list(range(2, n + 1))
        default_k = min(3, n)
        k = st.selectbox(
            "Keepers needed to open",
            thresholds,
            index=thresholds.index(default_k),
            key="keeper_threshold",
        )

        st.markdown("**Name the Keepers**")
        keeper_names = [
            st.text_input(f"Keeper {index + 1}", value=f"Keeper {index + 1}", key=f"keeper_{index}")
            for index in range(n)
        ]

        protected = st.checkbox("Require a separate passphrase", key="create_protected")
        passphrase = ""
        if protected:
            passphrase = st.text_input("Passphrase", type="password", key="create_passphrase")
            confirmation = st.text_input(
                "Confirm passphrase", type="password", key="confirm_passphrase"
            )
        else:
            confirmation = ""

        if st.button("Seal Stone", type="primary", icon=":material/lock:"):
            cleaned_names = [name.strip() for name in keeper_names]
            if not secret:
                st.error("Enter a secret before sealing the Stone.")
            elif any(not name for name in cleaned_names):
                st.error("Give every Keeper a name.")
            elif len({name.casefold() for name in cleaned_names}) != len(cleaned_names):
                st.error("Keeper names must be distinct.")
            elif protected and (not passphrase or passphrase != confirmation):
                st.error("Enter matching passphrases.")
            else:
                try:
                    stone, tesserae, warnings = create_stone(
                        secret, k, n, passphrase=passphrase if protected else None
                    )
                    vault = {
                        "name": stone_name.strip() or "Untitled Stone",
                        "stone": json.loads(stone.to_json()),
                    }
                    safe_name = _filename(vault["name"])
                    st.session_state["stone_bundle"] = {
                        "name": vault["name"],
                        "filename": safe_name,
                        "threshold": k,
                        "keeper_names": cleaned_names,
                        "tesserae": tesserae,
                        "qr_pngs": [
                            _qr_card_png(tessera, vault["name"], keeper_name, index, k, n)
                            for index, (keeper_name, tessera) in enumerate(
                                zip(cleaned_names, tesserae)
                            )
                        ],
                        "vault_json": json.dumps(vault, indent=2).encode("utf-8"),
                        "warnings": warnings,
                    }
                    st.session_state["ceremony_index"] = -1
                    st.session_state["words_visible"] = False
                    st.rerun()
                except WhiteStoneError as exc:
                    st.error(str(exc))

        st.caption(
            "Secret and Keeper material are handled by this local app process. "
            "Nothing is uploaded to a White Stone service."
        )
        return

    st.subheader(bundle["name"])
    st.write(f"**{bundle['threshold']} of {len(bundle['keeper_names'])} Keepers**")
    st.download_button(
        "Download Stone file",
        data=bundle["vault_json"],
        file_name=f"{bundle['filename']}.json",
        mime="application/json",
        icon=":material/download:",
    )
    for warning in bundle["warnings"]:
        st.warning(warning)

    ceremony_index = st.session_state.get("ceremony_index", -1)
    if ceremony_index == -1:
        st.info("Keep the Stone file separate from the Keeper cards. Begin when the first Keeper is ready.")
        if st.button("Begin handoff ceremony", type="primary", icon=":material/arrow_forward:"):
            st.session_state["ceremony_index"] = 0
            st.session_state["words_visible"] = False
            st.rerun()
    elif ceremony_index >= len(bundle["keeper_names"]):
        st.success("Handoff complete. All Keeper cards have been shown.")
    else:
        keeper_name = bundle["keeper_names"][ceremony_index]
        st.progress(
            (ceremony_index + 1) / len(bundle["keeper_names"]),
            text=f"Keeper {ceremony_index + 1} of {len(bundle['keeper_names'])}",
        )
        with st.container(border=True):
            st.subheader(keeper_name)
            st.image(bundle["qr_pngs"][ceremony_index], caption="Private tessera QR", width=280)
            st.caption("Only this Keeper should see or save this card. Avoid screenshots and shared printers.")
            if st.button("Reveal recovery words", key=f"reveal_words_{ceremony_index}"):
                st.session_state["words_visible"] = True
                st.rerun()
            if st.session_state.get("words_visible"):
                st.code(bundle["tesserae"][ceremony_index], language=None)

            safe_keeper = _filename(keeper_name)
            st.download_button(
                "Save QR card",
                data=bundle["qr_pngs"][ceremony_index],
                file_name=f"{safe_keeper}-tessera.png",
                mime="image/png",
                key=f"download_qr_{ceremony_index}",
                icon=":material/qr_code_2:",
            )
            if st.session_state.get("words_visible"):
                st.download_button(
                    "Save recovery words",
                    data=bundle["tesserae"][ceremony_index] + "\n",
                    file_name=f"{safe_keeper}-tessera.txt",
                    mime="text/plain",
                    key=f"download_words_{ceremony_index}",
                    icon=":material/description:",
                )

        next_label = (
            "Finish ceremony"
            if ceremony_index + 1 == len(bundle["keeper_names"])
            else "Keeper received card · next"
        )
        if st.button(next_label, type="primary", icon=":material/check:"):
            st.session_state["ceremony_index"] = ceremony_index + 1
            st.session_state["words_visible"] = False
            st.rerun()


def _render_open() -> None:
    st.subheader("Open a Stone")
    stone_file = st.file_uploader("Stone file", type=["json"], key="open_stone_file")
    if stone_file is None:
        st.caption("Add the Stone JSON file, then provide enough distinct Keeper tesserae.")
        return

    try:
        stone_text = stone_file.getvalue().decode("utf-8")
        stone = Stone.from_json(stone_text)
    except (UnicodeError, WhiteStoneError) as exc:
        st.error(str(exc))
        return

    vault_name = "White Stone"
    try:
        vault_data = json.loads(stone_text)
        if isinstance(vault_data, dict) and isinstance(vault_data.get("name"), str):
            vault_name = vault_data["name"]
    except json.JSONDecodeError:
        pass

    st.write(f"**{vault_name}** · {stone.group_threshold} group(s) required")
    st.caption(" · ".join(f"{group.name}: {group.k} of {group.n}" for group in stone.groups))
    tessera_files = st.file_uploader(
        "Keeper tessera files",
        type=["txt"],
        accept_multiple_files=True,
        key="open_tessera_files",
    )
    passphrase = (
        st.text_input("Stone passphrase", type="password", key="open_passphrase")
        if stone.protected
        else None
    )

    tesserae: list[str] = []
    try:
        tesserae = [item.getvalue().decode("utf-8").strip() for item in tessera_files]
    except UnicodeError:
        st.error("A tessera file is not valid UTF-8 text.")

    if tesserae:
        progress = join_progress(stone, tesserae)
        st.progress(
            progress["groups_done"] / progress["groups_needed"],
            text=(
                f"{progress['valid']} valid tesserae · "
                f"{progress['groups_done']} of {progress['groups_needed']} groups ready"
            ),
        )

    if st.button("Reveal secret", type="primary", icon=":material/lock_open:"):
        try:
            secret = join_stone(stone, tesserae, passphrase)
            try:
                st.success("Stone opened")
                st.code(secret.decode("utf-8"), language=None)
            except UnicodeDecodeError:
                st.success("Stone opened. The secret is binary data.")
                st.download_button(
                    "Download recovered file",
                    data=secret,
                    file_name="recovered-secret.bin",
                    mime="application/octet-stream",
                )
        except WhiteStoneError as exc:
            st.error(str(exc))


st.set_page_config(page_title="White Stone", page_icon=":material/diamond:", layout="centered")
st.title("White Stone")
st.caption("A private recovery ceremony")
mode = st.segmented_control("Workspace", ["Create", "Open"], default="Create")

with st.sidebar:
    st.subheader("Local session")
    st.caption("Secret material stays in this app process. Run White Stone on a trusted, private computer.")
    st.button("Erase session", icon=":material/delete:", on_click=_clear_session)

if mode == "Open":
    _render_open()
else:
    _render_create()