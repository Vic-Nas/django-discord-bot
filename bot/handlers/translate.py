"""
Auto-translate layer for bot output.

Uses deep-translator (Google Translate) to translate all outgoing
messages when a guild has a language set.  Discord-specific syntax
(mentions, emoji, code blocks, URLs) is preserved untranslated.
"""

import re
import asyncio
from deep_translator import GoogleTranslator

# Cache translator instances per language
_translators = {}


def get_supported_languages():
    """Return {code: name} dict of supported languages."""
    return GoogleTranslator().get_supported_languages(as_dict=True)


def validate_language(lang_input):
    """Validate and normalize a language input. Returns code or None."""
    lang_input = lang_input.lower().strip()
    supported = get_supported_languages()
    codes = set(supported.values())

    # Direct code match (e.g. 'fr', 'es')
    if lang_input in codes:
        return lang_input

    # Name match (e.g. 'french' → 'fr')
    for name, code in supported.items():
        if name.lower() == lang_input:
            return code

    return None


def _get_translator(lang):
    if lang not in _translators:
        _translators[lang] = GoogleTranslator(source='auto', target=lang)
    return _translators[lang]


# Regex: Discord mentions, emoji, code blocks, inline code, markdown links, URLs
_PRESERVE_PATTERN = re.compile(
    r'(<@!?\d+>'           # user mentions
    r'|<@&\d+>'            # role mentions
    r'|<#\d+>'             # channel mentions
    r'|<a?:\w+:\d+>'       # custom emoji
    r'|```[\s\S]*?```'     # code blocks
    r'|`[^`]+`'            # inline code
    r'|\[.*?\]\(.*?\)'     # markdown links
    r'|https?://\S+'       # URLs
    r'|\{[^}]+\})'         # {placeholders} — keep format strings intact
)


def translate_text(text, lang):
    """Translate text while preserving Discord formatting."""
    if not text or not lang or lang == 'en':
        return text

    # Extract and replace preserved tokens with placeholders
    tokens = {}
    counter = [0]

    def _replace(match):
        key = f"§{counter[0]}§"
        tokens[key] = match.group(0)
        counter[0] += 1
        return key

    safe_text = _PRESERVE_PATTERN.sub(_replace, text)

    try:
        translator = _get_translator(lang)
        translated = translator.translate(safe_text)
        if not translated:
            return text

        # Restore preserved tokens
        for key, original in tokens.items():
            translated = translated.replace(key, original)

        return translated
    except Exception:
        return text  # fallback to original on any error


def translate_embed(embed_dict, lang):
    """Translate an embed dict's user-visible text fields."""
    if not lang or lang == 'en' or not embed_dict:
        return embed_dict

    result = dict(embed_dict)
    if result.get('title'):
        result['title'] = translate_text(result['title'], lang)
    if result.get('description'):
        result['description'] = translate_text(result['description'], lang)
    if 'fields' in result:
        result['fields'] = [
            {**f,
             'name': translate_text(f.get('name', ''), lang),
             'value': translate_text(f.get('value', ''), lang)}
            for f in result['fields']
        ]
    return result


# ── Async wrappers (deep-translator is synchronous) ─────────────────────────

async def translate_text_async(text, lang):
    if not text or not lang or lang == 'en':
        return text
    return await asyncio.to_thread(translate_text, text, lang)


async def translate_embed_async(embed_dict, lang):
    if not lang or lang == 'en' or not embed_dict:
        return embed_dict
    return await asyncio.to_thread(translate_embed, embed_dict, lang)


async def translate_actions(actions, lang):
    """Translate all user-visible text in a list of action dicts."""
    if not lang or lang == 'en':
        return actions

    translated = []
    for a in actions:
        a = dict(a)  # shallow copy
        if a.get('content'):
            a['content'] = await translate_text_async(a['content'], lang)
        if a.get('embed'):
            a['embed'] = await translate_embed_async(a['embed'], lang)
        if a.get('topic'):
            a['topic'] = await translate_text_async(a['topic'], lang)
        translated.append(a)
    return translated
