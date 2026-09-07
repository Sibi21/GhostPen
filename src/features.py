"""
src/features.py
---------------
Stylometric feature extraction for GhostPen.
Extracts:
1. ~70 function glue words (relative frequencies)
2. Sentence burstiness (sentence length mean and standard deviation)
3. Punctuation rates per 100 words (! ? ; : —)
4. Greeting and sign-off habit categories with 'none' explicitly tracked
5. Register metrics: contraction rate, formality rate, average word length, Type-Token Ratio (TTR)
6. Character 3-gram frequency profile (Burrows' Delta style)
"""

import math
import re
from typing import Dict, List, Optional, Set, Tuple

# ~70 Hard-coded function words (syntactic glue)
FUNCTION_WORDS = [
    "the", "of", "and", "to", "a", "in", "that", "is", "was", "he",
    "for", "it", "with", "as", "his", "on", "be", "at", "by", "i",
    "this", "had", "not", "are", "but", "from", "or", "have", "an", "they",
    "which", "one", "you", "were", "her", "all", "she", "there", "would", "their",
    "we", "him", "been", "has", "when", "who", "will", "more", "no", "if",
    "out", "so", "what", "up", "its", "about", "into", "than", "them", "can",
    "only", "other", "some", "could", "these", "then", "also", "just", "now", "any",
    "how", "however", "really", "very"
]

PUNCT_TARGETS = ["!", "?", ";", ":", "—"]

FORMALITY_WORDS = {
    "kindly", "hereby", "regards", "sincerely", "furthermore", "pursuant",
    "respectfully", "cordially", "confidential", "esteemed", "attached",
    "obligated", "soliciting", "undersigned", "forthwith", "henceforth"
}

# Standard 100 character 3-grams for English corporate text
TOP_CHAR_3GRAMS = [
    " th", "the", "he ", " to", "to ", "ing", "on ", " an", "ng ", "ed ",
    " in", "in ", "er ", "of ", " of", "re ", "nd ", "and", " at", "at ",
    "al ", "es ", "or ", "is ", "nt ", "te ", "ou ", "is", "it ", "en ",
    "ar ", "ti ", "ll ", "om ", "le ", "se ", "me ", "as ", "for", "fo ",
    "or", "th", "ve ", "ha ", "st ", "wa ", "wh ", "we ", "ro ", "wi ",
    "with", "ca ", "no ", "ce ", "co ", "be ", "pr ", "ma ", "li ", "ur ",
    "de ", "ut ", "yo ", "you", "ou", "so ", "ne ", "da ", "pe ", "ra ",
    "hi ", "ge ", "ea ", "us ", "ch ", "ay ", "ow ", "pl ", "ple", "as ",
    "pa ", "al", "ac ", "fa ", "am ", "mo ", "sh ", "la ", "by ", "by"
]

EPS_FLOORS = {
    "rates_per_100w": 0.5,
    "sentence_len_mean": 1.0,
    "sentence_len_std": 1.0,
    "ttr": 0.01,
    "avg_word_len": 0.1,
    "relative_freq": 0.0005,
}


def extract_words(text: str) -> List[str]:
    """Tokenizes text into words preserving apostrophes for contractions."""
    return re.findall(r"\b[a-zA-Z]+(?:'[a-zA-Z]+)?\b", text)


def extract_sentences(text: str) -> List[List[str]]:
    """Splits text into sentences and tokens per sentence."""
    raw_sents = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = []
    for s in raw_sents:
        w = extract_words(s)
        if w:
            sentences.append(w)
    return sentences


def extract_greeting(text: str) -> str:
    """
    Extracts greeting category from first non-empty line.
    Returns 'none' if message begins directly with content.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return "none"
    first = lines[0].lower()
    
    # Common greetings
    if re.match(r"^hi\b", first):
        return "hi"
    if re.match(r"^hello\b", first):
        return "hello"
    if re.match(r"^hey\b", first):
        return "hey"
    if re.match(r"^dear\b", first):
        return "dear"
    if "good morning" in first or re.match(r"^morning\b", first):
        return "morning"
    if "good afternoon" in first or "good evening" in first:
        return "good_afternoon"
    
    # If first line has more than 8 words or doesn't look like greeting
    if len(first.split()) > 7 or not any(first.startswith(g) for g in ["hi", "hello", "hey", "dear"]):
        return "none"
    return "other"


def extract_signoff(text: str) -> str:
    """
    Extracts sign-off category from the last 1-2 non-empty lines.
    Returns 'none' if message ends without sign-off.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return "none"
    
    # Check last line, or penultimate line if last line is just a name/phone
    candidate_lines = [lines[-1].lower()]
    if len(lines) >= 2:
        candidate_lines.append(lines[-2].lower())
        
    for l in candidate_lines:
        if re.search(r"\bthx\b", l):
            return "thx"
        if re.search(r"\bthanks\b|\bthank you\b", l):
            return "thanks"
        if re.search(r"\bkind regards\b", l):
            return "kind_regards"
        if re.search(r"\bbest regards\b", l):
            return "best_regards"
        if re.search(r"\bregards\b", l):
            return "regards"
        if re.search(r"\bbest\b", l):
            return "best"
        if re.search(r"\bsincerely\b", l):
            return "sincerely"
        if re.search(r"\bcheers\b", l):
            return "cheers"
            
    return "none"


def extract_features(text: str) -> Dict:
    """
    Computes complete stylometric feature dictionary for an email body.
    """
    # Replace '--' with em-dash for punctuation consistency
    norm_text = text.replace("--", "—")
    words = extract_words(norm_text)
    word_count = len(words)
    sentences = extract_sentences(norm_text)
    sentence_count = len(sentences)

    # Sentence burstiness
    if sentence_count > 0:
        sent_lens = [len(s) for s in sentences]
        sent_mean = sum(sent_lens) / sentence_count
        if sentence_count > 1:
            variance = sum((l - sent_mean) ** 2 for l in sent_lens) / (sentence_count - 1)
            sent_std = math.sqrt(variance)
        else:
            sent_std = 0.0
    else:
        sent_mean = 0.0
        sent_std = 0.0

    # Safe denominator for rate calculations
    safe_wc = max(word_count, 1)

    # Punctuation rates per 100 words
    punct_rates = {}
    for p in PUNCT_TARGETS:
        cnt = norm_text.count(p)
        punct_rates[p] = (cnt / safe_wc) * 100.0

    # Contractions per 100 words
    contractions = [w for w in words if "'" in w]
    contraction_rate = (len(contractions) / safe_wc) * 100.0

    # Formality rate per 100 words
    formality_cnt = sum(1 for w in words if w.lower() in FORMALITY_WORDS)
    formality_rate = (formality_cnt / safe_wc) * 100.0

    # Average word length
    if word_count > 0:
        avg_word_len = sum(len(w) for w in words) / word_count
    else:
        avg_word_len = 0.0

    # Type-Token Ratio (TTR)
    if word_count > 0:
        ttr = len(set(w.lower() for w in words)) / word_count
    else:
        ttr = 0.0

    # Function word relative frequencies
    lower_words = [w.lower() for w in words]
    fw_counts = {}
    for fw in FUNCTION_WORDS:
        fw_counts[fw] = lower_words.count(fw) / safe_wc

    # Character 3-grams relative frequencies
    clean_chars = " ".join(norm_text.lower().split())
    n_3grams = max(len(clean_chars) - 2, 1)
    char_3gram_counts = {}
    for g in TOP_CHAR_3GRAMS:
        char_3gram_counts[g] = clean_chars.count(g) / n_3grams

    return {
        "word_count": word_count,
        "sentence_count": sentence_count,
        "sentence_len_mean": sent_mean,
        "sentence_len_std": sent_std,
        "punct_rates": punct_rates,
        "contraction_rate": contraction_rate,
        "formality_rate": formality_rate,
        "avg_word_len": avg_word_len,
        "ttr": ttr,
        "greeting": extract_greeting(text),
        "signoff": extract_signoff(text),
        "function_word_freqs": fw_counts,
        "char_3gram_freqs": char_3gram_counts,
    }
