"""Small HTML helpers.

No HTML parser beyond the standard library is available and the pages in the
registry are stable enough that targeted regular expressions read more clearly
than a full tree walk. Every helper here is pure and is exercised by the
offline fixture tests.
"""

import html as html_module
import re

SCRIPT_STYLE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
TAG = re.compile(r"<[^>]+>")
WHITESPACE = re.compile(r"\s+")


def text_of(fragment):
    """Strip tags and normalise whitespace and entities."""
    fragment = SCRIPT_STYLE.sub(" ", fragment)
    fragment = TAG.sub(" ", fragment)
    fragment = html_module.unescape(fragment)
    fragment = fragment.replace(" ", " ")
    return WHITESPACE.sub(" ", fragment).strip()


def tables(page):
    """Every <table> ... </table> block, outermost first."""
    return re.findall(r"<table\b.*?</table>", page, re.S | re.I)


def rows_of(table):
    """Each <tr> in a table, as a list of cell text."""
    out = []
    for row in re.findall(r"<tr\b.*?</tr>", table, re.S | re.I):
        cells = re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row, re.S | re.I)
        out.append([text_of(cell) for cell in cells])
    return out


def section_after(page, pattern):
    """The remainder of the page after the first match of pattern."""
    match = re.search(pattern, page, re.S | re.I)
    if not match:
        return ""
    return page[match.end():]


def first_table_after(page, pattern):
    """The first table that follows a match of pattern."""
    tail = section_after(page, pattern)
    if not tail:
        return ""
    match = re.search(r"<table\b.*?</table>", tail, re.S | re.I)
    return match.group(0) if match else ""
