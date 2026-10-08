"""Seeded candidate generation for the blind-labelled golden set.

The pilot and gate sets are sampled from the private draft bank
(``data/private/banks/``, see ``aegis.eval.bank``), which mixes hand-written
entries, templated variants, and drafts from the benchmarked models. This module
builds those seed entries and maps a bank selection into sheet ``Candidate``
records. All VIP names are fictional; doxxing entries use only fake PII.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from aegis.detectors.intent import INTENT_LABELS
from aegis.eval.bank import (
    DRAFTER_HAND,
    DRAFTER_TEMPLATE,
    BankItem,
    bank_item_id,
    load_bank,
    select_for_sheet,
)

GENERATOR_MODEL = "template-v1"
LANGUAGES = ("en", "hi", "hi-Latn")

VIP_ROSTER: dict[str, tuple[str, ...]] = {
    "en": ("Aarav Zephlin", "Meera Solvane", "Rohan Kaverin", "Nisha Vexley"),
    "hi": ("आरव ज़ेफ्लिन", "मीरा सोल्वेन", "रोहन कावेरिन", "निशा वेक्सली"),
    "hi-Latn": ("Aarav Zephlin", "Meera Solvane", "Rohan Kaverin", "Nisha Vexley"),
}

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
            "Here is {vip}'s home address: 42 Fake Lane, New Delhi. Phone +91 50000 00001.",
            "{vip} lives at 17 Example Road, flat 4B. Number +91 50000 00002.",
            "Leaked: {vip}'s email vip.leak@example.test and phone +91 50000 00003.",
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
            "{vip} का घर का पता: 42 फेक लेन, दिल्ली। फोन +91 50000 00001।",
            "{vip} 17 उदाहरण रोड, फ्लैट 4B में रहते हैं। नंबर +91 50000 00002।",
            "लीक: {vip} का ईमेल vip.leak@example.test और फोन +91 50000 00003।",
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
            "{vip} ka ghar ka pata: 42 Fake Lane, Delhi. Phone +91 50000 00001.",
            "{vip} 17 Example Road, flat 4B mein rehte hain. Number +91 50000 00002.",
            "Leak: {vip} ka email vip.leak@example.test aur phone +91 50000 00003.",
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
    drafter: str = DRAFTER_HAND
    edge_case: str | None = None
    generator_model: str = GENERATOR_MODEL


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


def seed_bank(vip_roster: dict[str, tuple[str, ...]] | None = None) -> list[BankItem]:
    """Build the hand-written and template seed entries for every cell."""

    roster = vip_roster or VIP_ROSTER
    items: list[BankItem] = []
    for language in LANGUAGES:
        names = roster[language]
        for label in INTENT_LABELS:
            templates = TEMPLATES[language][label]
            for index, template in enumerate(templates):
                text = template.format(vip=names[index % len(names)])
                items.append(
                    BankItem(
                        id=bank_item_id(language, label, DRAFTER_HAND, text),
                        language=language,
                        text=text,
                        intended_label=label,
                        drafter=DRAFTER_HAND,
                        generator_model=GENERATOR_MODEL,
                    )
                )
            for template_label, edge_case, template in EDGE_TEMPLATES[language]:
                if template_label != label:
                    continue
                text = template.format(vip=names[len(templates) % len(names)])
                items.append(
                    BankItem(
                        id=bank_item_id(language, label, DRAFTER_HAND, text),
                        language=language,
                        text=text,
                        intended_label=label,
                        drafter=DRAFTER_HAND,
                        edge_case=edge_case,
                        generator_model=GENERATOR_MODEL,
                    )
                )
            variants = _cell_texts(language, label, names[0])
            cores = {template.format(vip=names[0]) for template in templates}
            dressed = [text for text in variants if text not in cores]
            random.Random(f"seed:{language}:{label}").shuffle(dressed)
            for text in dressed[:2]:
                items.append(
                    BankItem(
                        id=bank_item_id(language, label, DRAFTER_TEMPLATE, text),
                        language=language,
                        text=text,
                        intended_label=label,
                        drafter=DRAFTER_TEMPLATE,
                        generator_model=GENERATOR_MODEL,
                    )
                )
    return items


def generate_from_bank(
    bank_dir: Path,
    *,
    per_class: int = 100,
    seed: int = 7,
) -> list[Candidate]:
    """Sample ``per_class`` clean bank items per cell, with drafter coverage."""

    if per_class < 1:
        raise ValueError("per_class must be >= 1")
    selected = select_for_sheet(load_bank(bank_dir), per_class=per_class, seed=seed)
    return [
        Candidate(
            id=item.id,
            language=item.language,
            text=item.text,
            intended_label=item.intended_label,
            drafter=item.drafter,
            edge_case=item.edge_case,
            generator_model=item.generator_model or GENERATOR_MODEL,
        )
        for item in selected
    ]
