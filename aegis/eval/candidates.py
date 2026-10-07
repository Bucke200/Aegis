"""Seeded candidate generation for the blind-labelled golden set.

Candidates are templated synthetic items. Each candidate carries the
generator's *intended* class, which the annotation sheet deliberately hides:
the human annotator labels blind, and agreement between the intended and blind
labels is what admits an item into the gate set (see docs/annotation-guidelines.md).

Doxxing candidates use only fake PII in reserved example.test domains and
obviously invalid numbers.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass

from aegis.detectors.intent import INTENT_LABELS

GENERATOR_MODEL = "template-v1"
LANGUAGES = ("en", "hi", "hi-Latn")
NAMESPACE = uuid.UUID("e0f4f3d2-5c1b-4a7e-9c3d-4b8a6f2d1e77")

PREFIXES: dict[str, tuple[str, ...]] = {
    "en": ("", "Forwarded: ", "Group post: ", "Comment: ", "Breaking: "),
    "hi": ("", "फॉरवर्ड: ", "ग्रुप पोस्ट: ", "कमेंट: ", "ब्रेकिंग: "),
    "hi-Latn": ("", "Forwarded: ", "Group post: ", "Comment: ", "Breaking: "),
}

SUFFIXES: dict[str, tuple[str, ...]] = {
    "en": (
        "",
        " Remember that.",
        " Everyone is talking about it.",
        " This is not a joke.",
        " Check the news.",
        " Locals are angry.",
        " Share this widely.",
        " No one is stopping this.",
        " It is all over the group.",
        " People are watching.",
    ),
    "hi": (
        "",
        " याद रखना।",
        " सब इसकी बात कर रहे हैं।",
        " यह मजाक नहीं है।",
        " खबर देख लो।",
        " लोग गुस्से में हैं।",
        " इसे आगे भेजो।",
        " कोई रोकने वाला नहीं है।",
        " ग्रुप में सबने देखा है।",
    ),
    "hi-Latn": (
        "",
        " Yaad rakhna.",
        " Sab iski baat kar rahe hain.",
        " Yeh mazak nahi hai.",
        " Khabar dekh lo.",
        " Log gusse mein hain.",
        " Aage bhej do.",
        " Koi rokne wala nahi hai.",
        " Group mein sabne dekha hai.",
    ),
}

TEMPLATES: dict[str, dict[str, tuple[str, ...]]] = {
    "en": {
        "none": (
            "Watched {vip} speak at the town hall today.",
            "Sharing {vip}'s latest statement for context.",
            "The interview with {vip} is worth a read.",
            "{vip} attended the summit this morning.",
        ),
        "criticism": (
            "I disagree with {vip}'s policy on education.",
            "{vip}'s handling of the budget has been disappointing.",
            "Poor leadership from {vip} on this issue.",
            "{vip} should answer questions about the vote.",
        ),
        "harassment": (
            "{vip} is a useless idiot who should shut up.",
            "Nobody likes {vip}, what a pathetic clown.",
            "{vip} is a lying scumbag and everyone knows it.",
            "You are a waste of space, {vip}.",
        ),
        "violent_threat": (
            "I will shoot {vip} if they show up here.",
            "Someone should put a bullet in {vip}.",
            "{vip} will be stabbed if they come to the rally.",
            "We are going to burn down {vip}'s office.",
        ),
        "incitement": (
            "Everyone grab your weapons and march on {vip}'s house.",
            "Let's teach {vip} a lesson with sticks and stones tonight.",
            "Rise up and attack {vip}'s convoy, all of us together.",
            "Brothers, it is time to storm {vip}'s office.",
        ),
        "doxxing": (
            "Here is {vip}'s home address: 42 Fake Lane, New Delhi. Phone +91 90000 00001.",
            "{vip} lives at 17 Example Road, flat 4B. Number +91 90000 00002.",
            "Leaked: {vip}'s email vip.leak@example.test and phone +91 90000 00003.",
            "Find {vip} at 9 Sample Street tonight. Aadhaar 1111 2222 3333.",
        ),
    },
    "hi": {
        "none": (
            "{vip} ने आज शहर में भाषण दिया।",
            "{vip} की नई परियोजना पर एक रिपोर्ट आई है।",
            "{vip} आज सम्मेलन में शामिल हुए।",
            "{vip} का बयान सोशल मीडिया पर चर्चा में है।",
        ),
        "criticism": (
            "मैं {vip} की शिक्षा नीति से सहमत नहीं हूँ।",
            "{vip} का बजट संभालना निराशाजनक रहा।",
            "{vip} को इस फैसले पर जवाब देना चाहिए।",
            "{vip} का नेतृत्व कमजोर है।",
        ),
        "harassment": (
            "{vip} एक बेकार इंसान है, चुप रहना चाहिए।",
            "कोई भी {vip} को पसंद नहीं करता, कमीना आदमी।",
            "{vip} झूठा और निकम्मा है।",
            "{vip} को शर्म आनी चाहिए, गंदा आदमी।",
        ),
        "violent_threat": (
            "अगर {vip} यहाँ आया तो मैं उसे गोली मार दूंगा।",
            "{vip} को रैली में चाकू मार देना चाहिए।",
            "हम {vip} का दफ्तर जला देंगे।",
            "{vip} को खत्म कर देंगे।",
        ),
        "incitement": (
            "सब लोग हथियार लेकर {vip} के घर चलो।",
            "आज रात {vip} को सबक सिखाओ।",
            "उठो और {vip} के काफिले पर हमला करो।",
            "भाइयों, {vip} के दफ्तर पर हमला करने का समय है।",
        ),
        "doxxing": (
            "{vip} का घर का पता: 42 फेक लेन, दिल्ली। फोन +91 90000 00001।",
            "{vip} 17 उदाहरण रोड, फ्लैट 4B में रहते हैं। नंबर +91 90000 00002।",
            "लीक: {vip} का ईमेल vip.leak@example.test और फोन +91 90000 00003।",
            "{vip} का आधार नंबर 1111 2222 3333 और पता 9 सैंपल स्ट्रीट।",
        ),
    },
    "hi-Latn": {
        "none": (
            "Aaj {vip} ka speech suna, accha tha.",
            "{vip} ki nayi project par report aayi hai.",
            "{vip} aaj summit mein gaye the.",
            "{vip} ka statement social media par chal raha hai.",
        ),
        "criticism": (
            "Mujhe {vip} ki education policy pasand nahi.",
            "{vip} ka budget handling disappointing raha.",
            "{vip} ko is decision par jawab dena chahiye.",
            "{vip} ki leadership kamzor hai.",
        ),
        "harassment": (
            "{vip} ek useless aadmi hai, chup rehna chahiye.",
            "Koi bhi {vip} ko pasand nahi karta, kameena aadmi.",
            "{vip} jhoota aur nikamma hai.",
            "{vip} ko sharam aani chahiye, gandu aadmi.",
        ),
        "violent_threat": (
            "Agar {vip} yahan aaya to usko goli maar dunga.",
            "{vip} ko rally mein chaku maarna chahiye.",
            "Hum {vip} ka daftar jala denge.",
            "{vip} ko khatam kar denge.",
        ),
        "incitement": (
            "Sab log hathiyar lekar {vip} ke ghar chalo.",
            "Aaj raat {vip} ko sabak sikhao.",
            "Utho aur {vip} ke kaafile par hamla karo.",
            "Bhaiyon, {vip} ke daftar par attack karne ka time hai.",
        ),
        "doxxing": (
            "{vip} ka ghar ka pata: 42 Fake Lane, Delhi. Phone +91 90000 00001.",
            "{vip} 17 Example Road, flat 4B mein rehte hain. Number +91 90000 00002.",
            "Leak: {vip} ka email vip.leak@example.test aur phone +91 90000 00003.",
            "{vip} ka Aadhaar 1111 2222 3333 aur address 9 Sample Street.",
        ),
    },
}

EDGE_TEMPLATES: dict[str, tuple[tuple[str, str, str], ...]] = {
    "en": (
        ("criticism", "satire", "Satire: {vip} is so brave that he will obviously fix everything next week."),
        ("criticism", "sarcasm", "Great job {vip}, prices are lower now. Not."),
        ("none", "quote", "He said, quote: 'someone should kill {vip}' — I am only reporting his words."),
        ("none", "news", "Police filed a case over threats made against {vip} at yesterday's rally."),
        ("none", "sentiment", "I am sad about what happened to {vip} today."),
    ),
    "hi": (
        ("criticism", "satire", "व्यंग्य: {vip} इतने बहादुर हैं कि अगले हफ्ते सब ठीक कर देंगे।"),
        ("criticism", "sarcasm", "वाह {vip}, अब कीमतें कम हो गईं। ज़रूर।"),
        ("none", "quote", "उसने कहा, कोट: '{vip} को मार देना चाहिए' — मैं सिर्फ उसके शब्द बता रहा हूँ।"),
        ("none", "news", "पुलिस ने कल की रैली में {vip} को दी गई धमकियों पर मामला दर्ज किया।"),
        ("none", "sentiment", "आज {vip} के साथ जो हुआ उससे मैं दुखी हूँ।"),
    ),
    "hi-Latn": (
        ("criticism", "satire", "Satire: {vip} itne bahadur hain ki agle hafte sab theek kar denge."),
        ("criticism", "sarcasm", "Wah {vip}, ab prices kam ho gaye. Zaroor."),
        ("none", "quote", "Usne kaha, quote: '{vip} ko maar dena chahiye' — main sirf uske shabd bata raha hoon."),
        ("none", "news", "Police ne kal ki rally mein {vip} ko di gayi dhamkiyon par case darj kiya."),
        ("none", "sentiment", "Aaj {vip} ke saath jo hua usse main dukhi hoon."),
    ),
}


@dataclass(frozen=True)
class Candidate:
    """One unlabelled-by-humans candidate with its generator intent."""

    id: str
    language: str
    text: str
    intended_label: str
    edge_case: str | None = None
    generator_model: str = GENERATOR_MODEL


def _candidate_id(language: str, label: str, text: str) -> str:
    digest = uuid.uuid5(NAMESPACE, f"{language}:{label}:{text}").hex[:12]
    return f"cand-{language}-{label}-{digest}"


def _cell_texts(language: str, label: str, vip: str) -> list[str]:
    prefixes = PREFIXES[language]
    suffixes = SUFFIXES[language]
    texts: list[str] = []
    for template in TEMPLATES[language][label]:
        body = template.format(vip=vip)
        for prefix in prefixes:
            for suffix in suffixes:
                texts.append(f"{prefix}{body}{suffix}")
    return list(dict.fromkeys(texts))


def _cell_edge_cases(language: str, label: str, vip: str) -> list[tuple[str, str]]:
    return [
        (template.format(vip=vip), edge_case)
        for template_label, edge_case, template in EDGE_TEMPLATES[language]
        if template_label == label
    ]


def generate_candidates(
    *,
    per_class: int = 100,
    seed: int = 7,
    vip: str = "Vip Sharma",
    languages: tuple[str, ...] = LANGUAGES,
) -> list[Candidate]:
    """Generate a deterministic candidate set, ``per_class`` per cell."""

    if per_class < 1:
        raise ValueError("per_class must be >= 1")
    candidates: list[Candidate] = []
    for language in languages:
        if language not in TEMPLATES:
            raise ValueError(f"unknown language {language!r}")
        for label in INTENT_LABELS:
            rng = random.Random(f"{seed}:{language}:{label}")
            edge_items = _cell_edge_cases(language, label, vip)
            edge_quota = min(len(edge_items), max(2, per_class // 10))
            rng.shuffle(edge_items)
            chosen_edges = edge_items[:edge_quota]

            core = _cell_texts(language, label, vip)
            if len(core) + len(chosen_edges) < per_class:
                raise ValueError(
                    f"not enough template combinations for {language}/{label}: "
                    f"{len(core) + len(chosen_edges)} < {per_class}"
                )
            rng.shuffle(core)
            chosen = [text for text, _ in chosen_edges]
            chosen.extend(text for text in core if text not in chosen)
            chosen = chosen[:per_class]

            edge_by_text = dict(chosen_edges)
            for text in chosen:
                candidates.append(
                    Candidate(
                        id=_candidate_id(language, label, text),
                        language=language,
                        text=text,
                        intended_label=label,
                        edge_case=edge_by_text.get(text),
                    )
                )
    return candidates
