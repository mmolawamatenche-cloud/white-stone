"""White Stone local Streamlit GUI — with AI Assistant tab."""

from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import Optional

import qrcode
import qrcode.constants
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

from .core import Stone, WhiteStoneError, create_stone, join_progress, join_stone


# ── QR helpers ───────────────────────────────────────────────────────────────

def _qr_png(tessera: str) -> bytes:
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=8, border=4
    )
    qr.add_data(tessera)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
    return buf.getvalue()


def _qr_card_png(tessera: str, stone_name: str, keeper_name: str,
                 keeper_index: int, k: int, n: int) -> bytes:
    qr_image = Image.open(io.BytesIO(_qr_png(tessera))).convert("RGB")
    card_width = max(920, qr_image.width + 128)
    qr_top = 250
    card_height = qr_top + qr_image.height + 138
    card = Image.new("RGB", (card_width, card_height), "#FCFCFA")
    draw = ImageDraw.Draw(card)
    font_path = Path(ImageFont.__file__).parent / "fonts" / "DejaVuSans.ttf"

    def load_font(size: int):
        try:
            return ImageFont.truetype(str(font_path), size)
        except OSError:
            try:
                return ImageFont.load_default(size=size)
            except TypeError:
                return ImageFont.load_default()

    def font_that_fits(text: str, size: int):
        font = load_font(size)
        while draw.textbbox((0, 0), text, font=font)[2] > card_width - 128 and size > 18:
            size -= 2
            font = load_font(size)
        return font

    draw.rounded_rectangle((20, 20, card_width - 20, card_height - 20),
                            radius=24, outline="#CDD6D0", width=3)
    draw.text((64, 48), "WHITE STONE", fill="#A94730", font=font_that_fits("WHITE STONE", 24))
    draw.text((64, 88), keeper_name, fill="#1C2823", font=font_that_fits(keeper_name, 46))
    threshold_text = f"KEEPER {keeper_index + 1}  |  {k} OF {n} NEEDED"
    draw.text((64, 158), threshold_text, fill="#53645B", font=font_that_fits(threshold_text, 24))
    card.paste(qr_image, ((card_width - qr_image.width) // 2, qr_top))
    footer_y = qr_top + qr_image.height + 34
    draw.text((64, footer_y), stone_name, fill="#1C2823", font=font_that_fits(stone_name, 24))
    draw.text((64, footer_y + 40), "Keep this tessera private.",
              fill="#53645B", font=font_that_fits("Keep this tessera private.", 20))
    buf = io.BytesIO()
    card.save(buf, format="PNG")
    return buf.getvalue()


def _filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-") or "white-stone"


# ── Session helpers ───────────────────────────────────────────────────────────

def _clear_session() -> None:
    keys = [
        "stone_bundle", "ceremony_index", "words_visible",
        "create_name", "create_secret", "create_passphrase",
        "confirm_passphrase", "create_protected", "keeper_count",
        "keeper_threshold", "open_stone_file", "open_tessera_files",
        "open_passphrase", "ai_chat_history", "ai_api_key",
    ]
    keys.extend(f"keeper_{i}" for i in range(16))
    for key in keys:
        st.session_state.pop(key, None)


def _api_key() -> Optional[str]:
    """Return the API key from session state (entered in sidebar)."""
    return st.session_state.get("ai_api_key") or None


# ── Create tab ───────────────────────────────────────────────────────────────

def _render_create() -> None:
    bundle = st.session_state.get("stone_bundle")
    if bundle is None:
        st.subheader("Create a Stone")
        st.caption("Choose the threshold, name each Keeper, then seal the secret.")
        stone_name = st.text_input("Stone name", value="My White Stone", key="create_name")
        secret = st.text_input("Secret to protect", type="password", key="create_secret")
        n = st.selectbox("Number of Keepers", list(range(2, 17)), index=3, key="keeper_count")
        thresholds = list(range(2, n + 1))
        k = st.selectbox("Keepers needed to open", thresholds,
                         index=thresholds.index(min(3, n)), key="keeper_threshold")
        st.markdown("**Name the Keepers**")
        keeper_names = [
            st.text_input(f"Keeper {i + 1}", value=f"Keeper {i + 1}", key=f"keeper_{i}")
            for i in range(n)
        ]
        protected = st.checkbox("Require a separate passphrase", key="create_protected")
        passphrase = confirmation = ""
        if protected:
            passphrase = st.text_input("Passphrase", type="password", key="create_passphrase")
            confirmation = st.text_input("Confirm passphrase", type="password",
                                         key="confirm_passphrase")

        if st.button("Seal Stone", type="primary", icon=":material/lock:"):
            cleaned = [name.strip() for name in keeper_names]
            if not secret:
                st.error("Enter a secret before sealing the Stone.")
            elif any(not name for name in cleaned):
                st.error("Give every Keeper a name.")
            elif len({name.casefold() for name in cleaned}) != len(cleaned):
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
                    safe = _filename(vault["name"])
                    st.session_state["stone_bundle"] = {
                        "name": vault["name"],
                        "filename": safe,
                        "threshold": k,
                        "n": n,
                        "keeper_names": cleaned,
                        "tesserae": tesserae,
                        "stone": stone,
                        "qr_pngs": [
                            _qr_card_png(t, vault["name"], kn, i, k, n)
                            for i, (kn, t) in enumerate(zip(cleaned, tesserae))
                        ],
                        "vault_json": json.dumps(vault, indent=2).encode("utf-8"),
                        "warnings": warnings,
                    }
                    st.session_state["ceremony_index"] = -1
                    st.session_state["words_visible"] = False
                    st.rerun()
                except WhiteStoneError as exc:
                    st.error(str(exc))
        st.caption("Nothing is uploaded. This app runs entirely on your computer.")
        return

    st.subheader(bundle["name"])
    st.write(f"**{bundle['threshold']} of {len(bundle['keeper_names'])} Keepers**")
    st.download_button("Download Stone file", data=bundle["vault_json"],
                       file_name=f"{bundle['filename']}.json", mime="application/json",
                       icon=":material/download:")
    for w in bundle["warnings"]:
        st.warning(w)

    ci = st.session_state.get("ceremony_index", -1)
    if ci == -1:
        st.info("Keep the Stone file separate from the Keeper cards. "
                "Begin when the first Keeper is ready.")
        if st.button("Begin handoff ceremony", type="primary",
                     icon=":material/arrow_forward:"):
            st.session_state["ceremony_index"] = 0
            st.session_state["words_visible"] = False
            st.rerun()
    elif ci >= len(bundle["keeper_names"]):
        st.success("Handoff complete. All Keeper cards have been shown.")
    else:
        kn = bundle["keeper_names"][ci]
        st.progress((ci + 1) / len(bundle["keeper_names"]),
                    text=f"Keeper {ci + 1} of {len(bundle['keeper_names'])}")
        with st.container(border=True):
            st.subheader(kn)
            st.image(bundle["qr_pngs"][ci], caption="Private tessera QR", width=280)
            st.caption("Only this Keeper should see or save this card.")
            if st.button("Reveal recovery words", key=f"reveal_{ci}"):
                st.session_state["words_visible"] = True
                st.rerun()
            if st.session_state.get("words_visible"):
                st.code(bundle["tesserae"][ci], language=None)
            safe_kn = _filename(kn)
            st.download_button("Save QR card", data=bundle["qr_pngs"][ci],
                               file_name=f"{safe_kn}-tessera.png", mime="image/png",
                               key=f"dl_qr_{ci}", icon=":material/qr_code_2:")
            if st.session_state.get("words_visible"):
                st.download_button("Save recovery words",
                                   data=bundle["tesserae"][ci] + "\n",
                                   file_name=f"{safe_kn}-tessera.txt", mime="text/plain",
                                   key=f"dl_words_{ci}", icon=":material/description:")
        next_label = (
            "Finish ceremony"
            if ci + 1 == len(bundle["keeper_names"])
            else "Keeper received card · next"
        )
        if st.button(next_label, type="primary", icon=":material/check:"):
            st.session_state["ceremony_index"] = ci + 1
            st.session_state["words_visible"] = False
            st.rerun()


# ── Open tab ─────────────────────────────────────────────────────────────────

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
        vd = json.loads(stone_text)
        if isinstance(vd, dict) and isinstance(vd.get("name"), str):
            vault_name = vd["name"]
    except json.JSONDecodeError:
        pass

    st.write(f"**{vault_name}** · {stone.group_threshold} group(s) required")
    st.caption(" · ".join(f"{g.name}: {g.k} of {g.n}" for g in stone.groups))
    tessera_files = st.file_uploader("Keeper tessera files", type=["txt"],
                                     accept_multiple_files=True, key="open_tessera_files")
    passphrase = (
        st.text_input("Stone passphrase", type="password", key="open_passphrase")
        if stone.protected else None
    )

    tesserae: list[str] = []
    try:
        tesserae = [f.getvalue().decode("utf-8").strip() for f in tessera_files]
    except UnicodeError:
        st.error("A tessera file is not valid UTF-8 text.")

    if tesserae:
        progress = join_progress(stone, tesserae)
        st.progress(
            progress["groups_done"] / progress["groups_needed"],
            text=(f"{progress['valid']} valid tesserae · "
                  f"{progress['groups_done']} of {progress['groups_needed']} groups ready"),
        )

    if st.button("Reveal secret", type="primary", icon=":material/lock_open:"):
        try:
            secret = join_stone(stone, tesserae, passphrase)
            try:
                st.success("Stone opened")
                st.code(secret.decode("utf-8"), language=None)
            except UnicodeDecodeError:
                st.success("Stone opened. The secret is binary data.")
                st.download_button("Download recovered file", data=secret,
                                   file_name="recovered-secret.bin",
                                   mime="application/octet-stream")
        except WhiteStoneError as exc:
            st.error(str(exc))


# ── AI Assistant tab ──────────────────────────────────────────────────────────

def _render_ai() -> None:
    st.subheader("AI Assistant")
    st.caption(
        "The AI helps you plan your recovery structure, write Keeper letters, "
        "and understand your Stone. **Your secret is never sent to the AI.**"
    )

    # API key input
    api_key_input = st.text_input(
        "OpenAI API key",
        type="password",
        placeholder="sk-…  (stored only in this session)",
        key="ai_api_key_input",
    )
    if api_key_input:
        st.session_state["ai_api_key"] = api_key_input

    if not st.session_state.get("ai_api_key"):
        st.info(
            "Enter your OpenAI API key above to use the AI features. "
            "The key is stored only in this browser session and never saved to disk."
        )
        st.markdown(
            "Don't have a key? Get one at [platform.openai.com](https://platform.openai.com/api-keys)."
        )
        return

    tool = st.radio(
        "What would you like help with?",
        [
            "💡  Suggest a Keeper structure",
            "✉️  Draft a Keeper letter",
            "🔍  Explain a Stone",
            "💬  Ask anything",
        ],
        horizontal=False,
        label_visibility="collapsed",
    )

    st.divider()

    # ── Suggest structure ────────────────────────────────────────
    if tool == "💡  Suggest a Keeper structure":
        st.markdown("**Describe your situation**")
        st.caption(
            "Tell the AI who you trust, what you're protecting, and any concerns — "
            "without mentioning the actual secret."
        )
        situation = st.text_area(
            "Your situation",
            placeholder=(
                "e.g. I want my spouse and two adult children to be able to access "
                "my crypto wallet if I die, but I don't want any one person to access "
                "it alone. I also have a lawyer I trust."
            ),
            height=140,
            label_visibility="collapsed",
        )
        if st.button("Suggest structure", type="primary", icon=":material/lightbulb:"):
            if not situation.strip():
                st.error("Describe your situation first.")
            else:
                with st.spinner("Thinking…"):
                    try:
                        from .ai import suggest_structure
                        result = suggest_structure(situation, _api_key())
                        st.session_state["ai_suggest_result"] = result
                    except Exception as exc:
                        st.error(str(exc))
        if "ai_suggest_result" in st.session_state:
            with st.container(border=True):
                st.markdown(st.session_state["ai_suggest_result"])
            st.download_button(
                "Save suggestion as text",
                data=st.session_state["ai_suggest_result"],
                file_name="keeper-structure-suggestion.txt",
                mime="text/plain",
                icon=":material/download:",
            )

    # ── Draft Keeper letter ──────────────────────────────────────
    elif tool == "✉️  Draft a Keeper letter":
        st.markdown("**Draft a letter to a Keeper**")
        st.caption("The letter explains their role without revealing the secret.")
        col1, col2 = st.columns(2)
        with col1:
            owner_name = st.text_input("Your name", placeholder="e.g. Sarah")
            keeper_name = st.text_input("Keeper's name", placeholder="e.g. James")
            stone_name = st.text_input("Stone name", placeholder="e.g. Family Vault")
        with col2:
            k = st.number_input("Keepers needed to open", min_value=2, max_value=16, value=3)
            n = st.number_input("Total Keepers", min_value=2, max_value=16, value=5)
            group_name = st.text_input("Group name (optional)", placeholder="e.g. Family")
        extra = st.text_area(
            "Extra context for the letter (optional)",
            placeholder="e.g. James is my brother. He lives in another country.",
            height=80,
        )
        if st.button("Draft letter", type="primary", icon=":material/mail:"):
            if not all([owner_name.strip(), keeper_name.strip(), stone_name.strip()]):
                st.error("Fill in your name, the Keeper's name, and the Stone name.")
            else:
                with st.spinner("Writing…"):
                    try:
                        from .ai import draft_keeper_letter
                        letter = draft_keeper_letter(
                            keeper_name=keeper_name.strip(),
                            stone_name=stone_name.strip(),
                            owner_name=owner_name.strip(),
                            k=int(k),
                            n=int(n),
                            group_name=group_name.strip() or None,
                            extra_context=extra.strip() or None,
                            api_key=_api_key(),
                        )
                        st.session_state["ai_letter_result"] = letter
                        st.session_state["ai_letter_keeper"] = keeper_name.strip()
                    except Exception as exc:
                        st.error(str(exc))
        if "ai_letter_result" in st.session_state:
            with st.container(border=True):
                st.markdown(st.session_state["ai_letter_result"])
            safe_kn = _filename(st.session_state.get("ai_letter_keeper", "keeper"))
            st.download_button(
                "Save letter as text",
                data=st.session_state["ai_letter_result"],
                file_name=f"{safe_kn}-letter.txt",
                mime="text/plain",
                icon=":material/download:",
            )

    # ── Explain Stone ────────────────────────────────────────────
    elif tool == "🔍  Explain a Stone":
        st.markdown("**Explain a Stone in plain English**")
        st.caption("Upload a Stone file — the AI explains its structure without seeing the secret.")

        # Check if a Stone was just created
        bundle = st.session_state.get("stone_bundle")
        stone: Optional[Stone] = None
        vault_name = ""

        if bundle and bundle.get("stone"):
            st.info("Using the Stone you just created. Or upload a different one below.")
            stone = bundle["stone"]
            vault_name = bundle["name"]

        uploaded = st.file_uploader("Stone JSON file (optional)", type=["json"],
                                    key="ai_explain_upload")
        if uploaded:
            try:
                text = uploaded.getvalue().decode("utf-8")
                stone = Stone.from_json(text)
                vd = json.loads(text)
                vault_name = vd.get("name", "Untitled Stone") if isinstance(vd, dict) else "Untitled Stone"
            except (UnicodeError, WhiteStoneError) as exc:
                st.error(str(exc))
                stone = None

        if stone:
            if st.button("Explain this Stone", type="primary", icon=":material/search:"):
                with st.spinner("Explaining…"):
                    try:
                        from .ai import explain_stone
                        explanation = explain_stone(stone, vault_name or "this Stone", _api_key())
                        st.session_state["ai_explain_result"] = explanation
                    except Exception as exc:
                        st.error(str(exc))
            if "ai_explain_result" in st.session_state:
                with st.container(border=True):
                    st.markdown(st.session_state["ai_explain_result"])
                st.download_button(
                    "Save explanation",
                    data=st.session_state["ai_explain_result"],
                    file_name="stone-explanation.txt",
                    mime="text/plain",
                    icon=":material/download:",
                )
        else:
            st.caption("Create a Stone first, or upload a Stone JSON file.")

    # ── Free chat ────────────────────────────────────────────────
    elif tool == "💬  Ask anything":
        st.markdown("**Ask the White Stone AI anything**")
        st.caption("Ask about recovery planning, how tesserae work, what to tell Keepers, etc. "
                   "Do not share your actual secret here.")

        if "ai_chat_history" not in st.session_state:
            st.session_state["ai_chat_history"] = []

        history = st.session_state["ai_chat_history"]

        # Display chat history
        for msg in history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        user_input = st.chat_input("Ask a question…")
        if user_input:
            history.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.markdown(user_input)
            with st.chat_message("assistant"):
                with st.spinner("Thinking…"):
                    try:
                        from .ai import free_chat
                        reply = free_chat(history[:-1], user_input, _api_key())
                        st.markdown(reply)
                        history.append({"role": "assistant", "content": reply})
                    except Exception as exc:
                        st.error(str(exc))

        if history and st.button("Clear chat", icon=":material/delete:"):
            st.session_state["ai_chat_history"] = []
            st.rerun()


# ── App entry point ───────────────────────────────────────────────────────────

def run() -> None:
    st.set_page_config(
        page_title="White Stone AI",
        page_icon=":material/diamond:",
        layout="centered",
    )
    st.title("White Stone AI")
    st.caption("Protect what matters. Trusted people hold the pieces.")

    mode = st.segmented_control(
        "Workspace",
        ["Create", "Open", "AI Assistant"],
        default="Create",
    )

    with st.sidebar:
        st.subheader("Local session")
        st.caption(
            "Secret material stays in this app process. "
            "Run on a trusted, private computer. "
            "The AI never receives your secret."
        )
        st.button("Erase session", icon=":material/delete:", on_click=_clear_session)
        st.divider()
        st.caption("White Stone AI v0.2 · Local-first · No cloud storage")

    if mode == "Open":
        _render_open()
    elif mode == "AI Assistant":
        _render_ai()
    else:
        _render_create()


if __name__ == "__main__":
    run()
