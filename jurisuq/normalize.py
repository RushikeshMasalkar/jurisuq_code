"""Text normalisation and provision extraction.

Design rule for legal text: never touch digits or bracketed sub-clauses.
In general-QA semantic entropy it is safe to strip articles and numbers;
in legal QA "302" and "103" are different answers, so the discrete channel
must stay conservative. Only surface noise is removed here.
"""
from __future__ import annotations

import re

# Leading answer labels such as "Answer:", "Ans -", "Final answer:".
_LABEL = re.compile(r"^\s*(?:final\s+)?(?:answer|ans|response)\s*[:\-\u2013]\s*", re.I)
_MD = re.compile(r"[*_`>#]+")
_WS = re.compile(r"\s+")
_QUOTES = {0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"',
           0x2013: "-", 0x2014: "-", 0x00A0: " "}


def normalize(text: str) -> str:
    """Conservative normalisation used by the discrete-equivalence channel."""
    if not text:
        return ""
    t = text.translate(_QUOTES)
    t = t.strip()
    t = _LABEL.sub("", t)
    t = _MD.sub("", t)
    t = _WS.sub(" ", t)
    t = t.strip(" .;:,-")
    return t.lower()


# ----------------------------------------------------------------------
# Provision extraction
# ----------------------------------------------------------------------
_SECTION = re.compile(
    r"(?:section|sec\.?|s\.|§)\s*(\d{1,4}[A-Za-z]?)"      # "Section 302", "s. 103"
    r"(?:\s*(?:\(([0-9a-zA-Z]+)\)))?",                     # optional "(1)"
    re.I,
)
_BARE = re.compile(r"\b(\d{1,4}[A-Za-z]?)\s*(?:of\s+(?:the\s+)?)?(IPC|BNS|CrPC|BNSS|BSA|Indian Penal Code|Bharatiya Nyaya Sanhita|Bharatiya Nagarik Suraksha Sanhita|Bharatiya Sakshya Adhiniyam)\b", re.I)
_ARTICLE = re.compile(r"article\s*(\d{1,4}[A-Za-z]?)", re.I)

ACT_ALIASES = {
    "ipc": "IPC", "indian penal code": "IPC",
    "bns": "BNS", "bharatiya nyaya sanhita": "BNS",
    "crpc": "CRPC", "code of criminal procedure": "CRPC",
    "bnss": "BNSS", "bharatiya nagarik suraksha sanhita": "BNSS",
    "bsa": "BSA", "bharatiya sakshya adhiniyam": "BSA",
}


def act_key(text: str) -> str | None:
    """Map an act name/abbreviation to a canonical key, or None."""
    t = (text or "").lower()
    for alias, key in ACT_ALIASES.items():
        if alias in t:
            return key
    return None


# Cues that a mentioned provision is being *reported as superseded* rather
# than asserted as the operative law, e.g. "IPC 302 was replaced by BNS 103".
_REPEAL_CUES = (
    "repeal", "supersed", "no longer", "erstwhile", "previously", "replaced",
    "stood repealed", "old provision", "ceased", "cease to", "w.e.f",
    "before the 2023", "before 1 july 2024", "used to", "earlier section",
    "formerly", "successor", "corresponding provision", "with effect from",
    "as amended", "now replaced", "in its place", "prior to", "renumbered",
)

# Cues that the sentence states the *operative* law (what applies now).
_OPERATIVE_CUES = (
    "applies", "applied", "applicable", "governs", "governed", "charged",
    "liable", "convicted", "punishable", "in force", "would be", "shall be",
    "is the provision", "the provision is", "current provision",
)

# number-then-act:  "302 of the IPC", "302 IPC", "302 under the BNS"
_NUM_ACT = re.compile(
    r"\b(\d{1,4}[A-Za-z]?)\s*(?:of\s+(?:the\s+)?|under\s+(?:the\s+)?|in\s+(?:the\s+)?)?"
    r"(IPC|BNS|CrPC|BNSS|BSA|Indian Penal Code|Bharatiya Nyaya Sanhita|"
    r"Bharatiya Nagarik Suraksha Sanhita|Bharatiya Sakshya Adhiniyam)\b", re.I)
# act-then-number:  "IPC 302", "BNS section 103"
_ACT_NUM = re.compile(
    r"\b(IPC|BNS|CrPC|BNSS|BSA)\s*(?:section|sec\.?|s\.)?\s*(\d{1,4}[A-Za-z]?)\b", re.I)

_SENT_BREAKS = ".!?;\n"


def _sentence(text: str, pos: int, max_span: int = 160) -> str:
    """The sentence around ``pos``; repeal cues are read only from it.

    Attribution of a repeal cue across sentence boundaries is the single
    easiest way to mislabel a correct legal answer ("IPC 302 was replaced ...;
    section 103 BNS applies"), so the window is deliberately sentence-scoped.
    """
    start = pos
    while start > 0 and text[start - 1] not in _SENT_BREAKS and pos - start < max_span:
        start -= 1
    end = pos
    while end < len(text) and text[end] not in _SENT_BREAKS and end - pos < max_span:
        end += 1
    return text[start:end]


def act_near(text: str, start: int, end: int, span: int = 34) -> str | None:
    """Attribute an act by nearest mention, right side first.

    Sentence-wide attribution is wrong when two acts appear in one sentence
    ("Section 302 of the IPC applies, and Section 103 of the BNS also
    applies"), so the act is read from the immediate neighbourhood and only
    then from the whole sentence.
    """
    right = text[end:end + span]
    k = act_key(right)
    if k:
        return k
    left = text[max(0, start - span):start]
    k = act_key(left)
    if k:
        return k
    return act_key(_sentence(text, start))


def find_mentions(text: str) -> list[dict]:
    """Return every provision mention with span, act attribution and cue flag."""
    text = text or ""
    cands: list[tuple[int, int, dict]] = []

    for m in _SECTION.finditer(text):
        cands.append((m.start(), m.end(), {"num": m.group(1), "sub": m.group(2),
                                           "raw": m.group(0), "act": None}))
    for m in _NUM_ACT.finditer(text):
        cands.append((m.start(), m.end(), {"num": m.group(1), "sub": None,
                                           "raw": m.group(0), "act": act_key(m.group(2))}))
    for m in _ACT_NUM.finditer(text):
        cands.append((m.start(), m.end(), {"num": m.group(2), "sub": None,
                                           "raw": m.group(0), "act": act_key(m.group(1))}))
    for m in _ARTICLE.finditer(text):
        cands.append((m.start(), m.end(), {"num": m.group(1), "sub": None,
                                           "raw": m.group(0), "act": "CONSTITUTION"}))

    # keep the longest match at each position, drop proper overlaps
    cands.sort(key=lambda c: (c[0], -(c[1] - c[0])))
    kept: list[tuple[int, int, dict]] = []
    for start, end, info in cands:
        if any(not (end <= k_start or start >= k_end) for k_start, k_end, _ in kept):
            continue
        kept.append((start, end, info))

    out: list[dict] = []
    for start, end, info in sorted(kept, key=lambda c: c[0]):
        sent = _sentence(text, start)
        out.append({
            "num": info["num"],
            "sub": info["sub"],
            "pos": start,
            "act": info["act"] or act_near(text, start, end),
            "repeal_cue": any(c in sent.lower() for c in _REPEAL_CUES),
            "raw": info["raw"],
        })
    return out


def sentence_around(text: str, pos: int, max_span: int = 160) -> str:
    """The sentence containing ``pos`` (public wrapper used by the judge)."""
    return _sentence(text, pos, max_span)


def base_num(provision: str | None) -> str:
    """The bare section number, subsection dropped: "303(2)" -> "303"."""
    return norm_num(str(provision or "").split("(")[0])


def subsection(provision: str | None) -> str | None:
    """The subsection label, if the provision has one: "303(2)" -> "2"."""
    s = str(provision or "")
    if "(" in s and ")" in s:
        return norm_num(s[s.index("(") + 1:s.index(")")]) or None
    return None


def is_operative(text: str, mention: dict) -> bool:
    """True when the mention sits in a sentence that asserts current law."""
    sent = _sentence(text, mention["pos"]).lower()
    return any(c in sent for c in _OPERATIVE_CUES)


def match_kind(mention: dict, provision: str, act: str | None) -> str | None:
    """Strength of a mention match: "exact", "base" (subsection dropped), or None.

    Both are accepted as mentions of the provision; the caller decides how much
    credit a "base" match deserves. This exists because a model that writes
    "Section 103(1) of the BNS" is naming the right section even though the
    subsection is absent from the gold provision.
    """
    mn = norm_num(mention["num"])
    gn = base_num(provision)
    if not mn or not gn or mn != gn:
        return None
    want = act_key(act or "")
    if want and mention["act"] and mention["act"] != want:
        return None
    gsub = subsection(provision)
    if gsub and mention["sub"] and norm_num(mention["sub"]) != gsub:
        return None                      # a different subsection: not this provision
    if gsub and not mention["sub"]:
        return "base"
    return "exact"


REPEALED_CODES = ("IPC", "CRPC", "IEA")
CURRENT_CODES = ("BNS", "BNSS", "BSA")

# Markers that the answer is invoking a jurisdiction other than India. A model
# that answers a question about Indian law with a South African section has not
# merely picked the wrong provision; it has answered a different question, and
# the judge must be able to say so.
_FOREIGN_MARKERS = (
    "south african", "united kingdom", "english law", "uk ", "u.s.", "united states",
    "american", "canadian", "australian", "singapore", "nigerian", "kenyan", "malaysian",
    "bangladesh", "pakistani", "sri lankan", "new zealand", "common law jurisdictions",
    "most jurisdictions", "other jurisdictions", "many countries", "western jurisdictions",
    "criminal procedure act 51", "in the uk", "in the us",
)
# An act named in the answer that belongs to another legal order.
_FOREIGN_ACT = re.compile(
    r"\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3}\s+(?:Act|Code|Penal Code))\b")


def foreign_marker(text: str) -> str | None:
    """Return the marker if the text invokes a non-Indian legal order."""
    low = (text or "").lower()
    for m in _FOREIGN_MARKERS:
        if m in low:
            return m
    return None


def act_level_mentions(text: str) -> list[dict]:
    """Act names asserted in the answer without a section number.

    Needed because a model often says "the Indian Penal Code would apply" with no
    number at all. On a question about today's law that is a stale answer, and
    calling it unresolvable would hide a real legal error.
    """
    out: list[dict] = []
    for m in re.finditer(r"\b(IPC|BNS|CrPC|BNSS|BSA|Indian Penal Code|Bharatiya Nyaya Sanhita|"
                         r"Code of Criminal Procedure|Indian Evidence Act)\b", text or "", re.I):
        out.append({"raw": m.group(0), "pos": m.start(), "act": act_key(m.group(0))})
    return out


def norm_num(num: str | None) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", (num or "")).lower().lstrip("0")


def provision_matches(mention: dict, provision: str, act: str | None) -> bool:
    """True when a mention names the same provision (subsection-tolerant)."""
    return match_kind(mention, provision, act) is not None
