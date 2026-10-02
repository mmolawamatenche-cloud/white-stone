"""White Stone AI assistant — structure advice, Keeper letters, plain-English explanations.

The secret NEVER enters this module. All functions work only with metadata
(k, n, group names, Stone structure) or free-text descriptions provided by
the user. The AI key is stored locally and never transmitted with secret material.
"""

from __future__ import annotations

import os
from typing import Optional

try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False

from .core import Stone

_SYSTEM = (
    "You are the White Stone AI assistant. White Stone is a local tool that encrypts "
    "a secret and splits the decryption key among trusted people called Keepers using "
    "SLIP-39 Shamir secret sharing. You help users plan their recovery structure and "
    "communicate with Keepers. You are calm, clear, and concise. "
    "You NEVER ask for, store, or repeat secrets, passwords, or tessera phrases. "
    "If a user tries to share a secret with you, politely decline and remind them "
    "the secret should only be entered into the local White Stone app, never here."
)


def _client(api_key: Optional[str] = None) -> "OpenAI":
    if not _OPENAI_AVAILABLE:
        raise RuntimeError(
            "openai package is not installed. Run: pip install 'openai>=1.0'"
        )
    key = api_key or os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError(
            "No OpenAI API key found. Set the OPENAI_API_KEY environment variable "
            "or paste your key in the AI Assistant tab."
        )
    return OpenAI(api_key=key)


def _chat(messages: list[dict], api_key: Optional[str] = None, model: str = "gpt-4o-mini") -> str:
    client = _client(api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": _SYSTEM}] + messages,
        temperature=0.4,
        max_tokens=800,
    )
    return response.choices[0].message.content.strip()


def suggest_structure(description: str, api_key: Optional[str] = None) -> str:
    """
    Given a plain-English description of the user's situation, suggest a
    k-of-n Keeper structure or multi-group layout with reasoning.
    Never asks for or uses the actual secret.
    """
    prompt = (
        f"A user wants to protect an important secret using White Stone. "
        f"Here is their situation:\n\n\"{description}\"\n\n"
        "Suggest a concrete Keeper structure: how many Keepers, what threshold "
        "(k of n), and whether groups make sense (e.g. '2-of-3 Family AND 1-of-1 Lawyer'). "
        "Explain your reasoning in plain language a non-technical person can follow. "
        "Do NOT ask for or reference the actual secret content. "
        "Keep the response under 250 words."
    )
    return _chat([{"role": "user", "content": prompt}], api_key)


def draft_keeper_letter(
    keeper_name: str,
    stone_name: str,
    owner_name: str,
    k: int,
    n: int,
    group_name: Optional[str] = None,
    extra_context: Optional[str] = None,
    api_key: Optional[str] = None,
) -> str:
    """
    Draft a letter to a Keeper explaining their role, what the tessera is,
    and what to do if they are ever called upon — without revealing the secret.
    """
    group_line = f" in the '{group_name}' group" if group_name else ""
    context_line = f"\nAdditional context from the owner: {extra_context}" if extra_context else ""
    prompt = (
        f"Write a warm, clear letter from {owner_name} to their trusted Keeper named {keeper_name}. "
        f"The Keeper holds one tessera (a 33-word recovery phrase){group_line} for a White Stone "
        f"called '{stone_name}'. At least {k} of {n} Keepers must come together to open the Stone. "
        f"The letter should:\n"
        f"- Explain what a tessera is in plain language (a piece of a key, not the secret itself)\n"
        f"- Tell them to keep it private and separate from the Stone file\n"
        f"- Explain when and how to use it (only when {owner_name} asks, or in an emergency)\n"
        f"- Be warm and personal, not technical or legal\n"
        f"- Be under 200 words{context_line}\n\n"
        "Do NOT include or reference the actual secret, passphrase, or tessera words."
    )
    return _chat([{"role": "user", "content": prompt}], api_key)


def explain_stone(stone: Stone, stone_name: str = "this Stone", api_key: Optional[str] = None) -> str:
    """
    Produce a plain-English explanation of a Stone's structure for
    non-technical users — no secret, no tessera words, just the shape.
    """
    groups_desc = "; ".join(
        f"'{g.name}' ({g.k} of {g.n} Keepers needed)" for g in stone.groups
    )
    threshold_line = (
        f"All {len(stone.groups)} groups must contribute"
        if stone.group_threshold == len(stone.groups)
        else f"Any {stone.group_threshold} of {len(stone.groups)} groups must contribute"
    )
    passphrase_line = "A separate passphrase is also required to open it." if stone.protected else ""
    prompt = (
        f"Explain the following White Stone recovery structure in plain English "
        f"for a non-technical person. Use no jargon.\n\n"
        f"Stone name: {stone_name}\n"
        f"Groups: {groups_desc}\n"
        f"To open: {threshold_line} their tesserae.\n"
        f"{passphrase_line}\n\n"
        "Explain what this means in practice: who needs to be involved, "
        "what happens if someone is unavailable, and why this structure protects the secret. "
        "Keep it under 150 words."
    )
    return _chat([{"role": "user", "content": prompt}], api_key)


def free_chat(history: list[dict], user_message: str, api_key: Optional[str] = None) -> str:
    """
    General-purpose chat for any White Stone question.
    history is a list of {"role": "user"|"assistant", "content": str}.
    """
    messages = history + [{"role": "user", "content": user_message}]
    return _chat(messages, api_key)
