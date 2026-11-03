"""Hindi spoken by a video model: the words it tends to say wrong, spelled the way they sound, before a prompt goes to it.

A video model reads a Hindi or Hinglish line written in Latin letters as if it were English: "main" comes out as the
English word, "hai" as "high", "nahi" as "nah-high". So before a shot's prompt is sent, the words of a line someone
speaks (the words in quotation marks) are respelled as they are said: "Main theek hoon" goes as "Mehn theek hoon".
Only the spoken words change; the rest of the prompt, and the line as the user wrote it, stay as they are.

Two sources of respellings: SAY, the common words, used only when a line is plainly Hindi (two words of SAY in it, one of
them no English word as well, so "the main road" is left alone); and the step's own "phonetic" pairs, which the agent
writes for names and rarer words, and which are always used.
"""

import re

# word: how it is said, for a model that reads it as English. Our own spellings, by ear.
SAY = {
    "main": "mehn", "mein": "mehn", "hai": "heh", "hain": "hehn", "nahi": "nuh-hee", "nahin": "nuh-heen",
    "kya": "kyaa", "kyun": "kyoon", "kyon": "kyoon", "kaise": "kay-say", "kahan": "kuh-haan", "kab": "kub", "kaun": "kown",
    "accha": "uch-chhaa", "achha": "uch-chhaa", "acha": "uch-chhaa", "bhai": "bhaai", "bhaiya": "bhaee-yaa",
    "mujhe": "moo-jheh", "tumhe": "toom-heh", "tumhein": "toom-hehn", "humein": "hum-ehn", "aapko": "aap-koh",
    "mera": "may-raa", "meri": "may-ree", "mere": "may-ray", "tera": "tay-raa", "teri": "tay-ree", "tere": "tay-ray",
    "raha": "ruh-haa", "rahi": "ruh-hee", "rahe": "ruh-hay", "tha": "thaa", "thi": "thee",
    "paani": "paa-nee", "ghar": "ghur", "chalo": "chuh-loh", "jaldi": "jul-dee", "abhi": "uh-bhee", "kuch": "kooch",
    "sab": "sub", "bas": "bus", "matlab": "mut-lub", "zindagi": "zin-duh-gee", "shukriya": "shook-ree-yaa",
    "namaste": "nuh-mus-tay", "dhanyavaad": "dhun-yuh-vaad", "yaar": "yaar", "pyaar": "pyaar", "dost": "dohst",
    "haan": "haan", "ji": "jee", "ho": "hoh", "hoon": "hoon", "hum": "hum", "aap": "aap", "beta": "bay-taa",
    "maa": "maa", "papa": "pup-paa", "chai": "chaay", "khana": "khaa-naa", "dekho": "day-khoh", "suno": "soo-noh",
}
# words of SAY that are English words too: they alone never make a line Hindi
ENGLISH_TOO = {"main", "bus", "sub", "bas", "sab", "ho", "hum", "ji", "papa", "chai", "maa", "tha", "kab", "beta", "mere"}
QUOTED = re.compile("\"([^\"]+)\"|“([^”]+)”|(?<!\\w)'([^']+)'(?!\\w)")
WORD = re.compile(r"[A-Za-z]+(?:-[A-Za-z]+)*")
MOST = 30   # pairs a step may give


def clean(pairs):
    """A step's "phonetic" as kept: [{"word", "say"}], each word once, at most MOST, nothing empty."""
    out, seen = [], set()
    for pair in pairs if isinstance(pairs, list) else []:
        if not isinstance(pair, dict):
            continue
        word, say = (" ".join(str(pair.get(k) or "").split())[:40] for k in ("word", "say"))
        if word and say and word.lower() != say.lower() and word.lower() not in seen and WORD.fullmatch(word):
            seen.add(word.lower())
            out.append({"word": word, "say": say})
    return out[:MOST]


def hindi(line):
    """Whether a spoken line in Latin letters is plainly Hindi or Hinglish: two of SAY's words, one no English word."""
    found = {w.lower() for w in WORD.findall(line) if w.lower() in SAY}
    return len(found) >= 2 and bool(found - ENGLISH_TOO)


def _case(said, like):
    """`said` in the case of the word it stands for: "Mehn" for "Main"."""
    return said[:1].upper() + said[1:] if like[:1].isupper() else said


def respell(prompt, given=()):
    """(the prompt with its spoken lines respelled, the pairs used as [{"word", "say"}]). given: the step's own pairs."""
    own = {p["word"].lower(): p["say"] for p in clean(list(given))}
    used = {}

    def line(match):
        start, end = match.span(next(n for n in range(1, 4) if match.group(n) is not None))
        words, table = match.string[start:end], dict(SAY) if hindi(match.string[start:end]) else {}
        table.update(own)

        def word(found):
            said = table.get(found.group(0).lower())
            if not said or said.lower() == found.group(0).lower():
                return found.group(0)
            used.setdefault(found.group(0).lower(), said)
            return _case(said, found.group(0))
        whole = match.group(0)
        return whole[:start - match.start()] + WORD.sub(word, words) + whole[end - match.start():]
    out = QUOTED.sub(line, str(prompt or ""))
    return out, [{"word": w, "say": s} for w, s in used.items()]


RULES = """Hindi and Hinglish spoken in a video: write the words someone says in Latin letters, as they are said
("Main theek hoon, tum chalo"), never in Devanagari for a video model. A video model reads them as English and says
some wrong: the studio respells the common ones by itself before the prompt goes ("main" as "mehn", "hai" as "heh",
"nahi" as "nuh-hee", "kya" as "kyaa"). For a name or a rarer word it may say wrong, add it to the step's "phonetic":
[{"word": "Shaurya", "say": "Shore-yuh"}, {"word": "Bhatt", "say": "Bhutt"}], spelled by ear for an English reader. Only
the spoken words change; leave "phonetic" empty for a line in English."""
