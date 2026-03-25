"""Utility to extract JSON from LLM responses that may contain markdown fences or preamble text."""

import json
import re
import logging

logger = logging.getLogger(__name__)


def _fix_unescaped_quotes(text: str) -> str:
    """Fix unescaped double quotes inside JSON string values.

    Strategy: track whether we're inside a JSON string. When we encounter
    a `"` inside a string, use context clues to determine if it's a
    delimiter or an inner quote needing escape.
    """
    result = []
    in_string = False
    i = 0
    length = len(text)
    # Track nesting to help with delimiter detection
    depth = 0

    while i < length:
        ch = text[i]

        if not in_string:
            result.append(ch)
            if ch == '"':
                in_string = True
            elif ch in '{[':
                depth += 1
            elif ch in '}]':
                depth -= 1
            i += 1
            continue

        # Inside a string
        if ch == '\\' and i + 1 < length:
            result.append(ch)
            result.append(text[i + 1])
            i += 2
            continue

        if ch == '"':
            # Is this a string delimiter or an inner quote?
            # Look at what follows (skip whitespace)
            j = i + 1
            while j < length and text[j] in ' \t':
                j += 1

            # A string delimiter is followed by:
            # - , (next element in array/object)
            # - } (end of object)
            # - ] (end of array)
            # - : (this was a key, value follows)
            # - \n then whitespace then one of the above
            # - end of text
            is_delimiter = False
            if j >= length:
                is_delimiter = True
            elif text[j] in ',}]:':
                is_delimiter = True
            elif text[j] == '\n':
                # Skip newlines and whitespace
                k = j
                while k < length and text[k] in ' \t\r\n':
                    k += 1
                if k >= length or text[k] in ',}]:"':
                    is_delimiter = True

            if is_delimiter:
                result.append(ch)
                in_string = False
            else:
                result.append('\\"')
            i += 1
            continue

        result.append(ch)
        i += 1

    return ''.join(result)


def _remove_stray_brackets(text: str) -> str:
    """Remove unmatched closing brackets/braces from JSON text.

    LLMs sometimes add extra ] or } that don't match any opening bracket.
    This walks the text (respecting strings) and removes unmatched closers.
    """
    # First pass: find matched pairs
    stack = []
    in_string = False
    escape = False
    matched_openers = set()
    matched_closers = set()

    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in '{[':
            stack.append(i)
        elif ch in '}]':
            expected = '}' if ch == '}' else ']'
            # Find matching opener
            if stack:
                opener_pos = stack.pop()
                opener_ch = text[opener_pos]
                expected_closer = '}' if opener_ch == '{' else ']'
                if ch == expected_closer:
                    matched_openers.add(opener_pos)
                    matched_closers.add(i)
                else:
                    # Mismatched — this closer is stray, push opener back
                    stack.append(opener_pos)

    # Second pass: rebuild without unmatched closers
    result = []
    in_string = False
    escape = False
    for i, ch in enumerate(text):
        if escape:
            escape = False
            result.append(ch)
            continue
        if ch == '\\' and in_string:
            escape = True
            result.append(ch)
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string:
            result.append(ch)
            continue
        if ch in '}]' and i not in matched_closers:
            # Skip stray closer
            continue
        result.append(ch)

    return ''.join(result)


def _try_parse(text: str) -> any:
    """Try to parse JSON with increasing levels of leniency."""
    text = text.strip()

    # 1. Try strict parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Try with strict=False (allows control chars like \n \t in strings)
    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError:
        pass

    # 3. Fix unescaped quotes, then parse with strict=False
    fixed = _fix_unescaped_quotes(text)
    try:
        return json.loads(fixed, strict=False)
    except json.JSONDecodeError:
        pass

    # 4. Fix quotes + remove stray brackets
    cleaned = _remove_stray_brackets(fixed)
    try:
        return json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        pass

    # 5. Last resort: try to iteratively fix at error positions
    result = _iterative_fix(text)
    if result is not None:
        return result

    raise json.JSONDecodeError("Could not parse even with fixes", text, 0)


def _iterative_fix(text: str, max_attempts: int = 30) -> any:
    """Iteratively fix JSON by addressing errors at each position.

    Handles:
    - Unescaped quotes: escapes them
    - Stray brackets/braces: removes them
    - Other delimiter issues: tries removal
    """
    current = text
    for _ in range(max_attempts):
        try:
            return json.loads(current, strict=False)
        except json.JSONDecodeError as e:
            pos = e.pos
            if pos is None or pos < 0 or pos >= len(current):
                return None

            ch_at = current[pos] if pos < len(current) else ''

            if 'Expecting' in e.msg and ',' in e.msg and ch_at in '}]':
                # Stray closing bracket — remove it
                current = current[:pos] + current[pos + 1:]
                continue

            if 'Extra data' in e.msg:
                # Truncate at the error position
                current = current[:pos]
                continue

            # Try escaping a nearby quote
            search_start = max(0, pos - 5)
            search_end = min(len(current), pos + 5)

            quote_pos = None
            for offset in range(search_end - search_start):
                check = search_start + offset
                if check < len(current) and current[check] == '"' and (check == 0 or current[check - 1] != '\\'):
                    if abs(check - pos) <= 3:
                        quote_pos = check
                        break

            if quote_pos is not None:
                current = current[:quote_pos] + '\\"' + current[quote_pos + 1:]
                continue

            # Unknown error — try removing the char at error position
            if ch_at:
                current = current[:pos] + current[pos + 1:]
                continue

            return None

    return None


def extract_json(response: str) -> any:
    """Extract and parse JSON from an LLM response.

    Handles:
    - Pure JSON
    - JSON wrapped in ```json ... ``` markdown fences
    - JSON with preamble/postamble text
    - Literal newlines/tabs inside JSON string values
    - Unescaped double quotes inside string values
    - Truncated JSON (attempts repair)
    """
    text = response.strip()
    if not text:
        raise json.JSONDecodeError("Empty response", text, 0)

    # 1. Try direct parse
    try:
        return _try_parse(text)
    except json.JSONDecodeError:
        pass

    # 2. Try extracting from ```json ... ``` blocks
    matches = re.findall(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if matches:
        for match in reversed(matches):
            try:
                return _try_parse(match)
            except json.JSONDecodeError:
                continue

    # 3. Try finding JSON object or array boundaries
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        if start >= 0:
            end = text.rfind(end_char)
            if end > start:
                candidate = text[start:end + 1]
                try:
                    return _try_parse(candidate)
                except json.JSONDecodeError:
                    continue

    # 4. Try to repair truncated JSON
    for start_char in ["{", "["]:
        start = text.find(start_char)
        if start >= 0:
            candidate = text[start:]
            repaired = _try_repair_truncated(candidate)
            if repaired is not None:
                return repaired

    print(f"[extract_json] FAILED — len={len(text)} first100={repr(text[:100])} last100={repr(text[-100:])}", flush=True)
    raise json.JSONDecodeError("No valid JSON found in response", text, 0)


def _try_repair_truncated(text: str) -> any:
    """Attempt to repair truncated JSON by closing open brackets/braces."""
    if not text:
        return None

    text = _fix_unescaped_quotes(text)

    stack = []
    in_string = False
    escape_next = False

    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in '{[':
            stack.append('}' if ch == '{' else ']')
        elif ch in '}]':
            if stack and stack[-1] == ch:
                stack.pop()

    if not stack:
        return None

    if in_string:
        text = text + '"'

    text = re.sub(r',\s*"[^"]*"?\s*:?\s*$', '', text)
    text = re.sub(r',\s*$', '', text)

    closing = ''.join(reversed(stack))
    candidate = text + closing

    try:
        return json.loads(candidate, strict=False)
    except json.JSONDecodeError:
        cleaned = re.sub(r',\s*"[^"]*"\s*:\s*("[^"]*)?$', '', text)
        cleaned = re.sub(r',\s*"[^"]*"\s*:\s*\{[^}]*$', '', cleaned)
        cleaned = re.sub(r',\s*\{[^}]*$', '', cleaned)
        cleaned = re.sub(r',\s*"[^"]*$', '', cleaned)
        cleaned = re.sub(r',\s*$', '', cleaned)
        candidate = cleaned + closing
        try:
            return json.loads(candidate, strict=False)
        except json.JSONDecodeError:
            return None
