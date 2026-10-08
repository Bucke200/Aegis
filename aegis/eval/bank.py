"""The draft bank: private, deduplicated candidate text for the golden set.

The bank lives in the private ``Aegis-data`` checkout
(``data/private/banks/*.jsonl``). Every entry records the drafter so the model
benchmark can score each model only on items it did not draft, and so the sheet
generator can guarantee drafter coverage per cell.

Nothing here prints or returns item text to logs. Checks report counts and
reason codes only.
"""

from __future__ import annotations

import json
import random
import re
import unicodedata
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from aegis.detectors.intent import INTENT_LABELS
from aegis.detectors.lexicons import score_lexicon

DRAFTER_HAND = "hand-written"
DRAFTER_TEMPLATE = "template-v1"
DEFAULT_BANK_DIR = Path("data/private/banks")

NAMESPACE = uuid.UUID("b7e5f0a4-6d2c-4f1e-9a3b-2c8d7e6f5a41")

DEVANAGARI = re.compile(r"[\u0900-\u097F]")
LATIN_WORD = re.compile(r"[a-z]{2,}")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_LIKE = re.compile(r"\+?\d[\d\s-]{8,}\d")
AADHAAR = re.compile(r"(?<!\d)([2-9]\d{3})[\s-]?(\d{4})[\s-]?(\d{4})(?!\d)")
URL = re.compile(r"https?://|www\.", re.IGNORECASE)
VALID_INDIAN_MOBILE_PREFIX = "6789"

REFUSAL_PATTERNS = (
    re.compile(r"\bas an (?:ai|assistant|language model)\b", re.IGNORECASE),
    re.compile(
        r"\bi (?:can'?t|cannot|won'?t|will not|am unable to|am not able to)\b[^.!?\n]{0,80}"
        r"\b(?:help|assist|create|write|provide|comply|generate|do)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:i'?m sorry|i apologi[sz]e|my apologies)\b[^.!?\n]{0,80}"
        r"\b(?:help|assist|cannot|can'?t|create|write|provide|comply)\b",
        re.IGNORECASE,
    ),
    re.compile(r"माफ़?\s*कीजिए[^।\n]{0,60}(?:नहीं|मदद|लिख)"),
    re.compile(r"मैं\s+(?:यह\s+)?नहीं\s+(?:कर|लिख)\s+सकत"),
    re.compile(r"\b(?:mujhe )?maaf kij?i?ye?\b[^\n.!?]{0,60}(?:nahi|nahin|help|madad|likh)", re.IGNORECASE),
    re.compile(r"\bmain (?:yeh|ye|is|aisa) nahi[n]? (?:kar|likh) sakta\b", re.IGNORECASE),
    re.compile(r"\bnahi[n]? (?:kar|likh) sakta\b", re.IGNORECASE),
)

HINGLISH_MARKERS = frozenset(
    {
        "aaj",
        "ab",
        "acha",
        "accha",
        "agar",
        "aur",
        "band",
        "bhai",
        "bhaiyon",
        "bahut",
        "bhi",
        "chahiye",
        "chalo",
        "dar",
        "denge",
        "dekh",
        "do",
        "dunga",
        "ek",
        "fir",
        "ghar",
        "goli",
        "gusse",
        "hai",
        "hain",
        "hamla",
        "hathiyar",
        "hoga",
        "isko",
        "jaldi",
        "ka",
        "kaa",
        "kaafile",
        "kab",
        "kal",
        "kam",
        "kar",
        "karo",
        "ke",
        "ki",
        "ko",
        "koi",
        "kyun",
        "log",
        "maar",
        "maaro",
        "mat",
        "mein",
        "nahi",
        "nahin",
        "nam",
        "nikamma",
        "par",
        "pata",
        "rakhna",
        "raha",
        "rahe",
        "sab",
        "sabak",
        "sakta",
        "sikhao",
        "subah",
        "tum",
        "tumhe",
        "uska",
        "usko",
        "utho",
        "wala",
        "yaad",
        "yeh",
        "ye",
        "zinda",
    }
)

NEAR_DUPLICATE_THRESHOLD = 0.85

ISSUE_REFUSAL = "refusal"
ISSUE_PII_EMAIL = "pii_email"
ISSUE_PII_PHONE = "pii_phone"
ISSUE_PII_AADHAAR = "pii_aadhaar"
ISSUE_URL = "url"
ISSUE_LANGUAGE = "language"
ISSUE_TOO_SHORT = "too_short"
ISSUE_TOO_LONG = "too_long"
ISSUE_DUPLICATE = "duplicate"
ISSUE_NEAR_DUPLICATE = "near_duplicate"
ISSUE_COHERENCE = "coherence"

TOKEN = re.compile(r"[\u0900-\u097F]+|[A-Za-z0-9]+")

HARM_TERMS = frozenset(
    {
        "kill",
        "kills",
        "killed",
        "killing",
        "murder",
        "shoot",
        "shoots",
        "shooting",
        "shot",
        "stab",
        "stabbed",
        "stabbing",
        "attack",
        "attacks",
        "attacked",
        "attacking",
        "burn",
        "burns",
        "burned",
        "burning",
        "harm",
        "hurt",
        "beat",
        "weapon",
        "weapons",
        "gun",
        "guns",
        "bullet",
        "bomb",
        "storm",
        "sticks",
        "stones",
        "march",
        "grab",
        "rise",
        "goli",
        "maar",
        "maro",
        "marenge",
        "chaku",
        "hamla",
        "hathiyar",
        "jala",
        "jalayenge",
        "khatam",
        "maut",
        "sabak",
        "sikhao",
        "rokne",
        "nikal",
        "chot",
        "girane",
        "girana",
        "हथियार",
        "मार",
        "मारो",
        "मारना",
        "मारेंगे",
        "गोली",
        "चाकू",
        "हमला",
        "जला",
        "जलाएंगे",
        "खत्म",
        "मौत",
        "बम",
        "पीट",
        "सबक",
        "सिखाओ",
        "रोकने",
        "निकल",
        "चोट",
        "गिराने",
        "गिराना",
    }
)

ADDRESS_TERMS = frozenset(
    {
        "address",
        "home",
        "ghar",
        "pata",
        "pta",
        "flat",
        "lane",
        "road",
        "street",
        "colony",
        "sector",
        "nagar",
        "gali",
        "घर",
        "पता",
        "फ्लैट",
        "लेन",
        "रोड",
        "सड़क",
        "गली",
        "कॉलोनी",
        "सेक्टर",
        "नगर",
        "मार्ग",
    }
)

CELL_SEPARATOR = "/"


def cell_key(language: str, label: str) -> str:
    return f"{language}{CELL_SEPARATOR}{label}"


@dataclass(frozen=True)
class BankItem:
    """One draft with its intended class and the drafter that produced it."""

    id: str
    language: str
    text: str
    intended_label: str
    drafter: str = DRAFTER_HAND
    edge_case: str | None = None
    generator_model: str | None = None


@dataclass
class BankCheck:
    """Counts-only summary of a bank check; never contains item text."""

    items: int = 0
    clean: int = 0
    by_cell: dict[str, dict[str, int]] = field(default_factory=dict)
    issues: dict[str, int] = field(default_factory=dict)
    issues_by_cell: dict[str, dict[str, int]] = field(default_factory=dict)
    drafters: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "items": self.items,
            "clean": self.clean,
            "by_cell": self.by_cell,
            "issues": self.issues,
            "issues_by_cell": self.issues_by_cell,
            "drafters": self.drafters,
        }


def bank_item_id(language: str, label: str, drafter: str, text: str) -> str:
    """Return an opaque, stable id: it must not reveal the intended class."""

    digest = uuid.uuid5(NAMESPACE, f"{language}:{label}:{drafter}:{text}").hex[:12]
    return f"bank-{digest}"


def load_bank(path: Path) -> list[BankItem]:
    """Load every JSONL bank entry under a file or a directory of files."""

    files = sorted(path.glob("*.jsonl")) if path.is_dir() else [path]
    items: list[BankItem] = []
    seen: set[str] = set()
    for file in files:
        for line_number, line in enumerate(file.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                items.append(BankItem(**json.loads(stripped)))
            except (TypeError, ValueError) as error:
                raise ValueError(f"{file}:{line_number}: invalid bank entry") from error
            if items[-1].id in seen:
                raise ValueError(f"{file}:{line_number}: duplicate bank id {items[-1].id}")
            seen.add(items[-1].id)
    return items


def write_bank(items: list[BankItem], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(asdict(item), ensure_ascii=False) for item in items]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def normalize_for_dedup(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold()
    value = re.sub(r"https?://\S+|www\.\S+", " ", value)
    value = re.sub(r"[^\w\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _shingles(text: str) -> set[str]:
    return set(normalize_for_dedup(text).split())


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def is_refusal(text: str) -> bool:
    return any(pattern.search(text) for pattern in REFUSAL_PATTERNS)


def _has_valid_indian_mobile(text: str) -> bool:
    for match in PHONE_LIKE.finditer(text):
        digits = re.sub(r"\D", "", match.group())
        if digits.startswith("91") and len(digits) == 12:
            digits = digits[2:]
        elif digits.startswith("0") and len(digits) == 11:
            digits = digits[1:]
        if len(digits) == 10 and digits[0] in VALID_INDIAN_MOBILE_PREFIX:
            return True
    return False


def language_issue(expected: str, text: str) -> str | None:
    """Return ``ISSUE_LANGUAGE`` when the text does not look like the cell's language."""

    if expected == "hi":
        return None if DEVANAGARI.search(text) else ISSUE_LANGUAGE
    if DEVANAGARI.search(text):
        return ISSUE_LANGUAGE
    tokens = set(LATIN_WORD.findall(text.lower()))
    markers = len(tokens & HINGLISH_MARKERS)
    if expected == "hi-Latn" and markers < 2:
        return ISSUE_LANGUAGE
    if expected == "en" and markers >= 3:
        return ISSUE_LANGUAGE
    return None


def coherence_issue(item: BankItem) -> str | None:
    """Flag drafts whose text does not carry the intended class's signal.

    Small models drift toward generic criticism; a threat-class draft without a
    harm term (or a doxxing draft without any private-data signal) is not usable
    as that class however the generator labelled it.
    """

    tokens = set(TOKEN.findall(item.text.casefold()))
    threat_without_signal = (
        item.intended_label in {"violent_threat", "incitement"}
        and not (tokens & HARM_TERMS)
        and not score_lexicon(item.text, item.language).threat_class
    )
    if threat_without_signal:
        return ISSUE_COHERENCE
    if item.intended_label == "doxxing":
        pii_signal = EMAIL.search(item.text) or PHONE_LIKE.search(item.text) or AADHAAR.search(item.text)
        if not pii_signal and not (tokens & ADDRESS_TERMS):
            return ISSUE_COHERENCE
    return None


def item_issues(item: BankItem) -> list[str]:
    issues: list[str] = []
    if is_refusal(item.text):
        issues.append(ISSUE_REFUSAL)
    for email in EMAIL.findall(item.text):
        if not email.lower().endswith(".test"):
            issues.append(ISSUE_PII_EMAIL)
            break
    if _has_valid_indian_mobile(item.text):
        issues.append(ISSUE_PII_PHONE)
    if AADHAAR.search(item.text):
        issues.append(ISSUE_PII_AADHAAR)
    if URL.search(item.text):
        issues.append(ISSUE_URL)
    language = language_issue(item.language, item.text)
    if language:
        issues.append(language)
    coherence = coherence_issue(item)
    if coherence:
        issues.append(coherence)
    if len(item.text.strip()) < 10:
        issues.append(ISSUE_TOO_SHORT)
    if len(item.text) > 500:
        issues.append(ISSUE_TOO_LONG)
    return issues


def is_duplicate(item: BankItem, items: list[BankItem]) -> str | None:
    """Return the duplicate issue code when ``item`` repeats a bank entry.

    Exact duplicates are global; near-duplicates are checked within the same
    cell only, because entries in the same class share topic phrasing.
    """

    target = normalize_for_dedup(item.text)
    current = _shingles(item.text)
    for other in items:
        if normalize_for_dedup(other.text) == target:
            return ISSUE_DUPLICATE
        if (
            other.language == item.language
            and other.intended_label == item.intended_label
            and _jaccard(current, _shingles(other.text)) >= NEAR_DUPLICATE_THRESHOLD
        ):
            return ISSUE_NEAR_DUPLICATE
    return None


def clean_items(items: list[BankItem]) -> tuple[list[BankItem], dict[str, list[str]]]:
    """Drop refused, unsafe, malformed, and duplicate entries.

    Exact duplicates are resolved on the normalized text; near-duplicates are
    compared with token Jaccard within the same language.
    """

    clean: list[BankItem] = []
    issues_by_id: dict[str, list[str]] = {}
    seen_exact: set[str] = set()
    shingles: list[tuple[str, str, set[str]]] = []
    for item in items:
        issues = item_issues(item)
        normalized = normalize_for_dedup(item.text)
        if normalized in seen_exact:
            issues.append(ISSUE_DUPLICATE)
        else:
            seen_exact.add(normalized)
            current = _shingles(item.text)
            if any(
                language == item.language
                and label == item.intended_label
                and _jaccard(current, other) >= NEAR_DUPLICATE_THRESHOLD
                for language, label, other in shingles
            ):
                issues.append(ISSUE_NEAR_DUPLICATE)
            else:
                shingles.append((item.language, item.intended_label, current))
        if issues:
            issues_by_id[item.id] = issues
        else:
            clean.append(item)
    return clean, issues_by_id


def check_bank(items: list[BankItem]) -> BankCheck:
    """Summarize a bank without ever returning text."""

    _, issues_by_id = clean_items(items)
    by_id = {item.id: item for item in items}
    check = BankCheck(items=len(items), clean=len(items) - len(issues_by_id))
    for item_id, issues in issues_by_id.items():
        item = by_id[item_id]
        cell = cell_key(item.language, item.intended_label)
        for issue in issues:
            check.issues[issue] = check.issues.get(issue, 0) + 1
            cell_issues = check.issues_by_cell.setdefault(cell, {})
            cell_issues[issue] = cell_issues.get(issue, 0) + 1
    for item in items:
        cell = cell_key(item.language, item.intended_label)
        check.by_cell.setdefault(cell, {})
        check.by_cell[cell][item.drafter] = check.by_cell[cell].get(item.drafter, 0) + 1
        check.drafters[item.drafter] = check.drafters.get(item.drafter, 0) + 1
    return check


def select_for_sheet(
    items: list[BankItem],
    *,
    per_class: int,
    seed: int,
    model_drafters: list[str] | None = None,
    cells: list[str] | None = None,
) -> list[BankItem]:
    """Select ``per_class`` clean items per cell with drafter coverage.

    Every hand-written and template entry is used first (up to its count), then
    the remaining slots are filled round-robin across model drafters so each
    model is represented in each cell for the pairwise benchmark. ``cells``
    restricts selection to the given ``language/label`` keys.
    """

    clean, _ = clean_items(items)
    by_cell: dict[str, list[BankItem]] = {}
    for item in clean:
        by_cell.setdefault(cell_key(item.language, item.intended_label), []).append(item)

    wanted = set(cells) if cells else None
    models = (
        model_drafters
        if model_drafters is not None
        else sorted({item.drafter for item in clean} - {DRAFTER_HAND, DRAFTER_TEMPLATE})
    )
    selected: list[BankItem] = []
    for language in ("en", "hi", "hi-Latn"):
        for label in INTENT_LABELS:
            cell = cell_key(language, label)
            if wanted is not None and cell not in wanted:
                continue
            available = by_cell.get(cell, [])
            rng = random.Random(f"{seed}:{cell}")
            hand = [item for item in available if item.drafter == DRAFTER_HAND]
            template = [item for item in available if item.drafter == DRAFTER_TEMPLATE]
            pools = {model: [item for item in available if item.drafter == model] for model in models}
            rng.shuffle(hand)
            rng.shuffle(template)
            for pool in pools.values():
                rng.shuffle(pool)

            model_present = [model for model in models if pools[model]]
            template_quota = min(2, max(0, per_class - len(model_present) - 1))
            hand_quota = max(1, per_class - template_quota - len(model_present))
            edges = [item for item in hand if item.edge_case]
            rest = [item for item in hand if not item.edge_case]
            chosen = (edges + rest)[:hand_quota]
            chosen.extend(template[:template_quota])

            if model_present:
                offset = rng.randrange(len(model_present))
                index = 0
                while len(chosen) < per_class:
                    progressed = False
                    for step in range(len(model_present)):
                        model = model_present[(offset + index + step) % len(model_present)]
                        if pools[model]:
                            chosen.append(pools[model].pop())
                            progressed = True
                            if len(chosen) == per_class:
                                break
                    index += 1
                    if not progressed:
                        break
            leftovers = [item for pool in pools.values() for item in pool]
            leftovers.extend(item for item in (edges + rest + template) if item not in chosen)
            for item in leftovers:
                if len(chosen) >= per_class:
                    break
                chosen.append(item)

            if len(chosen) < per_class:
                raise ValueError(
                    f"cell {cell} has {len(chosen)} clean items, need {per_class}; draft more or fill the gaps by hand"
                )
            selected.extend(chosen)
    return selected
