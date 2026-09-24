#!/usr/bin/env python3
"""Build the data block for the Parse drill in Oikos.

Reads every inflected word in the Greek New Testament from OpenGNT, keeps the
ones whose lexeme is one of the 345 course words in Merkle & Plummer,
*Beginning with New Testament Greek*, and writes one compact JSON line,
`const PARSE_DATA = {...};`, into index.html in place of the one already
there. That line is generated: do not edit it by hand, re-run this script.

Sources
  data/BNTG_Parsing_Practice.xlsx   the course vocabulary (BNTG_vocab) and the
                                    chapter each tense/voice/mood is taught in
                                    (BNTG_verb_concepts, BNTG_participle_concepts)
  data/OpenGNT_BASE_TEXT.zip        OpenGNT 3.3, the morphologically tagged NT.
                                    Downloaded from the pinned commit below if
                                    it is not already there (it is .gitignored).
  index.html                        the app's own VOCAB, so every lexeme can be
                                    tied to the word the setup screen selects

Usage
  python3 scripts/build_parse_data.py            build, report, embed
  python3 scripts/build_parse_data.py --dry-run  build and report only
  python3 scripts/build_parse_data.py --out F    also write the JSON to file F

Needs openpyxl (pip install openpyxl).

Output shape
  PARSE_DATA = {
    t: { tense letter: chapter it is first taught },   for the Grammar step
    m: { mood letter:  chapter it is first taught },
    L: { lexeme: [gloss, VOCAB headword, VOCAB chapter] },
    e: [ [f, l, pos, ch, p, n], ... ]
  }
  Each entry is an array rather than an object with those six keys: the keys
  repeated 4,600 times were a third of the file. The app turns them back into
  { f, l, pos, ch, p, n } objects when it loads.
  f    the form, lower case, NFC, accented as it would be on its own
  l    the course lexeme (BNTG_vocab column B)
  pos  noun | article | pronoun | adjective | verb   (participles are verbs)
  ch   the chapter the course word is taught in
  p    every distinct valid parsing, each "CODE" or "CODE:chapter", where the
       chapter is when that tense/voice/mood is taught (absent means 0)
  n    how many times the form occurs in the NT

Parsing codes
  noun, article, adjective, most pronouns   case number gender        NSM
  personal / reflexive pronoun, 1st or 2nd  person case number        1GS
  personal / reflexive pronoun, 3rd         person case number gender 3GSM
  finite verb                               tense voice mood person number  AAI3S
  infinitive                                tense voice mood          PAN
  participle                                tense voice mood case number gender  PAPNSM
  tense  P present, I imperfect, F future, A aorist, R perfect, L pluperfect
  voice  A active, M middle, P passive, E middle/passive (either)
  mood   I indicative, S subjunctive, O optative, M imperative, N infinitive,
         P participle
"""

import argparse
import collections
import io
import json
import math
import os
import re
import sys
import unicodedata
import urllib.request
import zipfile

try:
    import openpyxl
except ImportError:
    sys.exit('openpyxl is needed: pip install openpyxl')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XLSX = os.path.join(ROOT, 'data', 'BNTG_Parsing_Practice.xlsx')
OGNT_ZIP = os.path.join(ROOT, 'data', 'OpenGNT_BASE_TEXT.zip')
INDEX = os.path.join(ROOT, 'index.html')

OGNT_COMMIT = '0029589cccd50bd48b1941aa041a956de6c29ac4'
OGNT_URL = ('https://github.com/eliranwong/OpenGNT/raw/%s/OpenGNT_BASE_TEXT.zip' % OGNT_COMMIT)

SIZE_LIMIT_KB = 400

# rmac prefixes that inflect, and the part of speech each becomes
POS_BY_PREFIX = {
    'N': 'noun', 'T': 'article', 'A': 'adjective',
    'P': 'pronoun',   # personal: ἐγώ, σύ, αὐτός (and crasis κἀγώ)
    'F': 'pronoun',   # reflexive: ἐμαυτοῦ, σεαυτοῦ, ἑαυτοῦ
    'R': 'pronoun',   # relative: ὅς, ὅστις
    'D': 'pronoun',   # demonstrative: οὗτος, ἐκεῖνος, τοιοῦτος
    'I': 'pronoun',   # interrogative: τίς
    'X': 'pronoun',   # indefinite: τις
    'C': 'pronoun',   # reciprocal: ἀλλήλων
    'K': 'pronoun',   # correlative: ὅσος
    'S': 'pronoun',   # possessive: ἐμός (parsed by its own case/number/gender)
    'V': 'verb',
}
INDECLINABLE_PREFIXES = {'PREP', 'CONJ', 'PRT', 'ADV', 'INJ', 'COND', 'HEB', 'ARAM'}

# Course words OpenGNT files under a different lemma, which no spelling rule
# can reach. Each is (course lexeme, OpenGNT lexeme, rmac test or None) and
# every one is printed in the report to be checked by eye.
def _perfect(rmac):
    return bool(re.match(r'V-2?[RL]', rmac))

ALIASES = [
    ('ἱερόν', 'ἱερός', lambda r: r.startswith('N-')),       # the noun only, not the adjective
    ('πορεύομαι', 'πορεύω', None),
    ('ἀποκρίνομαι', 'ἀποκρίνω', None),
    ('φοβέομαι', 'φοβέω', None),
    ('εὐαγγελίζω', 'εὐαγγελίζομαι', None),
    ('ἀπόλλυμι', 'ἀπολλύω', None),
    # εἴδω holds both οἶδα (perfect/pluperfect) and εἶδον, which M&P teach
    # as the aorist of ὁράω -- so the forms are split between the two
    ('οἶδα', 'εἴδω', _perfect),
    ('ὁράω', 'εἴδω', lambda r: not _perfect(r)),
]

TENSES = {'P': 'P', 'I': 'I', 'F': 'F', 'A': 'A', 'R': 'R', 'L': 'L'}
VOICES = {'A': 'A', 'M': 'M', 'D': 'M', 'N': 'M', 'P': 'P', 'O': 'P', 'E': 'E'}
MOODS = {'I', 'S', 'O', 'M', 'N', 'P'}
# middle and passive share their forms in these tenses
SHARED_MIDPASS_TENSES = {'P', 'I', 'R', 'L'}

CNG = re.compile(r'^([NGDAV])([SP])([MFN])$')


def nfc(s):
    return unicodedata.normalize('NFC', s or '')


def lex_key(s):
    """The comparison key for a lexeme: NFC, lower case, first headword only,
    iota subscript dropped so ἀποθνῄσκω and ἀποθνήσκω compare equal."""
    s = nfc(s).strip().lower()
    s = s.split(',')[0].strip()
    s = s.split('-')[0].strip()
    d = unicodedata.normalize('NFD', s).replace(chr(0x345), '')   # iota subscript
    return unicodedata.normalize('NFC', d)


def exact_key(s):
    return nfc(s).strip().lower()


ACUTE, GRAVE, CIRCUMFLEX = chr(0x301), chr(0x300), chr(0x342)   # combining, as NFD splits them
ACCENTS = {ACUTE, GRAVE, CIRCUMFLEX}


def strip_accents(s):
    d = unicodedata.normalize('NFD', s)
    return unicodedata.normalize('NFC', ''.join(ch for ch in d if ch not in ACCENTS))


PROCLITIC_ARTICLE = {'ὁ', 'ἡ', 'οἱ', 'αἱ'}


def normalise_form(s, lexeme, rmac):
    """Lower case, NFC, and accented as the word stands alone: an enclitic's
    extra accent (ἄνθρωπός τις) is dropped and a grave becomes an acute.
    Words whose accent in the text is only lent to them by their neighbours
    are given no accent at all, so they cannot be mistaken for a different
    word: the indefinite τις (τὶς would otherwise read as the interrogative
    τίς), the proclitic article (οἵ τε would read as the relative οἵ), and
    the enclitic present indicative of εἰμί and φημί (ἐστίν, ἔστιν and ἐστιν
    are one form)."""
    d = unicodedata.normalize('NFD', nfc(s).strip().lower())
    marks = [i for i, ch in enumerate(d) if ch in ACCENTS]
    if len(marks) >= 2:
        d = d[:marks[-1]] + d[marks[-1] + 1:]
    form = unicodedata.normalize('NFC', d.replace(GRAVE, ACUTE))
    bare = strip_accents(form)
    if lexeme == 'τις':
        return bare
    if lexeme == 'ὁ' and bare in PROCLITIC_ARTICLE:
        return bare
    if lexeme in ('εἰμί', 'φημί') and rmac.startswith('V-PAI-') and not rmac.endswith('-2S'):
        return bare
    return form


# ---------- sources ----------

def read_sheet(wb, name):
    rows = list(wb[name].iter_rows(values_only=True))
    return [r for r in rows[1:] if r and r[0] is not None]


def load_spreadsheet():
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    vocab = []
    for r in read_sheet(wb, 'BNTG_vocab'):
        vocab.append({'headword': nfc(r[0]).strip(), 'lexeme': nfc(r[1]).strip(),
                      'gloss': (r[2] or '').strip(), 'chapter': int(r[3])})
    verb_concepts = {r[0]: int(r[4]) for r in read_sheet(wb, 'BNTG_verb_concepts')}
    ptc_concepts = {r[0]: int(r[2]) for r in read_sheet(wb, 'BNTG_participle_concepts')}
    return vocab, verb_concepts, ptc_concepts


def load_app_vocab():
    with open(INDEX, encoding='utf-8') as f:
        for line in f:
            if line.startswith('const VOCAB = '):
                return json.loads(line[len('const VOCAB = '):].rstrip().rstrip(';'))
    sys.exit('index.html has no `const VOCAB = ` line')


def load_opengnt():
    if not os.path.exists(OGNT_ZIP):
        print('Downloading OpenGNT from', OGNT_URL)
        with urllib.request.urlopen(OGNT_URL) as r, open(OGNT_ZIP, 'wb') as out:
            out.write(r.read())
    with zipfile.ZipFile(OGNT_ZIP) as z:
        name = next(n for n in z.namelist() if n.endswith('.csv') and not n.startswith('__MACOSX'))
        text = io.TextIOWrapper(z.open(name), encoding='utf-8')
        header = next(text).rstrip('\n').split('\t')
        col = header.index('〔OGNTk｜OGNTu｜OGNTa｜lexeme｜rmac｜sn〕')
        words = []
        for line in text:
            cells = line.rstrip('\n').split('\t')
            k = cells[col].strip('〔〕').split('｜')
            words.append({'form': k[2], 'lexeme': nfc(k[3]), 'rmac': k[4].strip()})
    return name, words


# ---------- rmac decoding ----------

def decode(rmac):
    """-> (pos, code, concept key, kind) or (None, reason, None, None)."""
    parts = rmac.split('-')
    prefix = parts[0]
    pos = POS_BY_PREFIX.get(prefix)
    if pos is None:
        return None, 'not inflected', None, None
    if prefix == 'V':
        return decode_verb(parts)
    if len(parts) < 2:
        return None, 'unreadable', None, None
    body = parts[1]
    if body == 'NUI' or rmac.endswith('-NUI'):
        return None, 'indeclinable numeral', None, None
    # suffixes (-T -P -L -LG -PG on nouns, -C -S on adjectives, -K on crasis)
    # say nothing about the parsing drilled here and are ignored
    if prefix in ('P', 'F'):
        m = re.match(r'^([123])?([NGDAV])([SP])([MFN])?$', body)
        if not m:
            return None, 'unreadable', None, None
        person, case, num, gen = m.groups()
        person = person or '3'
        if person in '12':
            return pos, person + case + num, None, 'person'
        if not gen:
            return None, 'unreadable', None, None
        return pos, '3' + case + num + gen, None, 'person'
    if prefix == 'S':
        body = body[2:]   # drop the possessor (1S, 2S, 1P): ἐμός agrees by its own case/number/gender
    if not CNG.match(body):
        return None, 'unreadable', None, None
    return pos, body, None, 'cng'


def decode_verb(parts):
    if len(parts) < 2:
        return None, 'unreadable', None, None
    tvm = parts[1]
    second = tvm.startswith('2')
    core = tvm[1:] if second else tvm
    if len(core) != 3:
        return None, 'unreadable', None, None
    t, v, mood = core
    if t not in TENSES or v not in VOICES or mood not in MOODS:
        return None, 'unreadable', None, None
    tense, voice = TENSES[t], VOICES[v]
    if tense in SHARED_MIDPASS_TENSES and voice in ('M', 'P'):
        voice = 'E'
    code = tense + voice + mood
    if mood == 'N':
        return 'verb', code, tvm, 'inf'
    if len(parts) < 3:
        return None, 'unreadable', None, None
    rest = parts[2]
    if mood == 'P':
        if not CNG.match(rest):
            return None, 'unreadable', None, None
        return 'verb', code + rest, tvm, 'ptc'
    m = re.match(r'^([123])([SP])$', rest)
    if not m:
        return None, 'unreadable', None, None
    return 'verb', code + rest, tvm, 'finite'


def concept_chapter(tvm, mood, verb_concepts, ptc_concepts, fallbacks):
    """The chapter a tense/voice/mood is taught in. Participles read the
    participle table only. A code the sheet lists as -1 (or not at all) is
    looked up again under its collapsed code: 2RAI takes RAI's chapter."""
    table = ptc_concepts if mood == 'P' else verb_concepts
    ch = table.get(tvm, -1)
    if ch is not None and ch > 0:
        return ch
    collapsed = tvm[1:] if tvm.startswith('2') else tvm
    ch = table.get(collapsed, -1)
    if ch > 0:
        if collapsed != tvm:
            fallbacks[tvm] = (collapsed, ch)
        return ch
    # still nothing: the earliest chapter for that tense and mood in any voice
    t, m = collapsed[0], collapsed[2]
    cands = [c for k, c in table.items() if c > 0 and k.lstrip('2')[0] == t and k.lstrip('2')[2] == m]
    ch = min(cands) if cands else 0
    fallbacks[tvm] = ('%s?%s any voice' % (t, m), ch)
    return ch


# ---------- build ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--dry-run', action='store_true', help='report only, leave index.html alone')
    ap.add_argument('--out', help='also write the JSON block to this file')
    args = ap.parse_args()

    vocab, verb_concepts, ptc_concepts = load_spreadsheet()
    app_vocab = load_app_vocab()
    source_name, words = load_opengnt()

    # the app's own headword for each course lexeme, so a selection of words
    # on the setup screen can be turned into a set of lexemes
    app_by_key = {}
    for ch, ws in app_vocab.items():
        for w in ws:
            app_by_key.setdefault(lex_key(w['greek']), (w['greek'].strip(), int(ch)))

    course = {}                       # lex_key -> course word
    for w in vocab:
        course[lex_key(w['lexeme'])] = w

    nt_lexemes = collections.defaultdict(collections.Counter)   # NT lexeme -> rmac prefix counts
    for w in words:
        nt_lexemes[w['lexeme']][w['rmac'].split('-')[0]] += 1

    # which course word an NT lexeme belongs to, and how the match was made
    how_matched = {}                  # course lexeme -> set of descriptions
    def match(nt_lexeme, rmac):
        for course_lex, nt_lex, test in ALIASES:
            if nt_lexeme == nt_lex and (test is None or test(rmac)):
                how_matched.setdefault(course_lex, set()).add('alias: OpenGNT lemma %s' % nt_lex)
                return course[lex_key(course_lex)]
        w = course.get(lex_key(nt_lexeme))
        if w is None:
            return None
        if exact_key(nt_lexeme) != exact_key(w['lexeme']):
            how_matched.setdefault(w['lexeme'], set()).add('normalised: OpenGNT lemma %s' % nt_lexeme)
        else:
            how_matched.setdefault(w['lexeme'], set()).add('exact')
        return w

    fallbacks = {}
    dropped = collections.Counter()
    entries = {}                      # (form, lexeme) -> entry
    for w in words:
        rmac = w['rmac']
        cw = match(w['lexeme'], rmac)
        if cw is None:
            continue
        pos, code, tvm, kind = decode(rmac)
        if pos is None:
            dropped[(cw['lexeme'], code)] += 1
            continue
        form = normalise_form(w['form'], cw['lexeme'], rmac)
        key = (form, cw['lexeme'])
        e = entries.get(key)
        if e is None:
            e = entries[key] = {'f': form, 'l': cw['lexeme'], 'pos': pos, 'ch': cw['chapter'],
                                'p': {}, 'n': 0}
        if e['pos'] != pos:
            # one lexeme, two parts of speech (ἐμός filed as adjective somewhere):
            # the course word's usual one wins, and the report says so
            dropped[(cw['lexeme'], 'mixed part of speech: ' + rmac)] += 1
            continue
        e['n'] += 1
        cc = 0
        if tvm:
            cc = concept_chapter(tvm, tvm[-1], verb_concepts, ptc_concepts, fallbacks)
        prev = e['p'].get(code)
        e['p'][code] = cc if prev is None else min(prev, cc)

    # ---------- output ----------
    out_entries = []
    for e in sorted(entries.values(), key=lambda e: (e['ch'], e['l'], -e['n'], e['f'])):
        p = [c if ch == 0 else '%s:%d' % (c, ch) for c, ch in sorted(e['p'].items())]
        out_entries.append({'f': e['f'], 'l': e['l'], 'pos': e['pos'], 'ch': e['ch'], 'p': p, 'n': e['n']})
    rows = [[e['f'], e['l'], e['pos'], e['ch'], e['p'], e['n']] for e in out_entries]

    tense_ch, mood_ch = {}, {}
    for e in entries.values():
        if e['pos'] != 'verb':
            continue
        for code, ch in e['p'].items():
            if ch <= 0:
                continue
            tense_ch[code[0]] = min(tense_ch.get(code[0], 99), ch)
            mood_ch[code[2]] = min(mood_ch.get(code[2], 99), ch)

    used = {e['l'] for e in out_entries}
    lookup = {}
    for w in vocab:
        if w['lexeme'] not in used:
            continue
        app = app_by_key.get(lex_key(w['lexeme'])) or app_by_key.get(lex_key(w['headword']))
        if app is None:
            sys.exit('course word %s has no match in the app VOCAB' % w['lexeme'])
        lookup[w['lexeme']] = [w['gloss'], app[0], app[1]]
        if app[1] != w['chapter']:
            print('WARNING: %s is chapter %d in the spreadsheet but %d in the app' % (w['lexeme'], w['chapter'], app[1]))

    data = {'t': tense_ch, 'm': mood_ch, 'L': lookup, 'e': rows}
    blob = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    size_kb = len(blob.encode('utf-8')) / 1024

    # ---------- report ----------
    print('Source:', os.path.basename(OGNT_ZIP), '->', source_name, '(%d words)' % len(words))
    print()
    print('COVERAGE')
    no_forms, numerals, no_lemma = [], [], []
    for w in vocab:
        if w['lexeme'] in used:
            continue
        # what OpenGNT calls it, if anything, decides whether it inflects
        prefixes = collections.Counter()
        for nt_lex, counts in nt_lexemes.items():
            if lex_key(nt_lex) == lex_key(w['lexeme']):
                prefixes.update(counts)
        reasons = sorted({r for (lx, r), n in dropped.items() if lx == w['lexeme']})
        if not prefixes:
            no_lemma.append(w)
        elif reasons == ['indeclinable numeral']:
            numerals.append(w)
        elif not set(prefixes) <= INDECLINABLE_PREFIXES:
            no_forms.append((w, 'dropped: ' + ', '.join(reasons) if reasons else 'OpenGNT tags: ' + ', '.join(sorted(prefixes))))
    print('Course words that inflect but have no forms:')
    for w, note in no_forms:
        print('  ch %-2d %-14s %s' % (w['chapter'], w['lexeme'], note))
    if not no_forms:
        print('  (none)')
    print('Indeclinable numerals, dropped as asked: ' +
          (', '.join('%s (ch %d)' % (w['lexeme'], w['chapter']) for w in numerals) or '(none)'))
    print('Course words with no OpenGNT lemma of that spelling (none of them inflects): ' +
          (', '.join('%s (ch %d)' % (w['lexeme'], w['chapter']) for w in no_lemma) or '(none)'))
    print()
    print('Course words matched other than exactly (check these by eye):')
    for lex in sorted(how_matched, key=lambda l: course[lex_key(l)]['chapter']):
        ways = sorted(how_matched[lex] - {'exact'})
        if ways:
            print('  ch %-2d %-14s %s' % (course[lex_key(lex)]['chapter'], lex, '; '.join(ways)))
    print()
    if fallbacks:
        print('Concept chapters read from the collapsed code:')
        for tvm, (via, ch) in sorted(fallbacks.items()):
            print('  %-5s -> %-6s ch %d' % (tvm, via, ch))
        print()
    other = collections.Counter()
    for (lx, reason), n in dropped.items():
        other[reason] += n
    if other:
        print('Occurrences dropped:')
        for reason, n in other.most_common():
            print('  %5d  %s' % (n, reason))
        print()
    shared = collections.Counter(e['f'] for e in out_entries)
    clash = sorted(f for f, n in shared.items() if n > 1)
    if clash:
        print('Forms shared by two course words (%d): %s' % (len(clash), ' '.join(clash)))
        print()

    print('SUMMARY')
    by_pos = collections.Counter(e['pos'] for e in out_entries)
    for pos in ('noun', 'article', 'pronoun', 'adjective', 'verb'):
        print('  %-9s %5d' % (pos, by_pos[pos]))
    verbs = [e for e in out_entries if e['pos'] == 'verb']
    ptc = sum(1 for e in verbs if any(c.split(':')[0][2] == 'P' for c in e['p']))
    inf = sum(1 for e in verbs if any(c.split(':')[0][2] == 'N' for c in e['p']))
    print('            (verbs with a participle parsing %d, with an infinitive parsing %d)' % (ptc, inf))
    print('  entries   %5d' % len(out_entries))
    print('  more than one valid parsing: %d' % sum(1 for e in out_entries if len(e['p']) > 1))
    print('  tense chapters', json.dumps(tense_ch, sort_keys=True))
    print('  mood chapters ', json.dumps(mood_ch, sort_keys=True))
    print('  size %.1f KB' % size_kb)

    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(blob)
    if size_kb > SIZE_LIMIT_KB:
        sys.exit('Over %d KB: not embedded. Check with the owner before going further.' % SIZE_LIMIT_KB)
    if args.dry_run:
        return

    line = 'const PARSE_DATA = ' + blob + ';\n'
    with open(INDEX, encoding='utf-8') as f:
        lines = f.readlines()
    at = [i for i, l in enumerate(lines) if l.startswith('const PARSE_DATA = ')]
    if len(at) != 1:
        sys.exit('index.html needs exactly one `const PARSE_DATA = ` line to replace (found %d)' % len(at))
    lines[at[0]] = line
    with open(INDEX, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print('Embedded in index.html')


if __name__ == '__main__':
    main()
