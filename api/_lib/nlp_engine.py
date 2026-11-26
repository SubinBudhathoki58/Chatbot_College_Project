"""
Self-hosted NLP Engine for Taste of Himalaya Food Delivery Chatbot.

Implements:
  1. Text normalization & contraction expansion
  2. TF-IDF (word unigrams + bigrams + character n-grams) + Cosine Similarity intent classifier
  3. Context-aware intent boosting (ongoing-order / ongoing-tracking)
  4. Rule + synonym + fuzzy-match Named Entity Recognition (NER) for Nepali food items,
     quantities (digits & English words), and order IDs
  5. Stateful dialogue management backed by Neon PostgreSQL via db_helper
"""

from __future__ import annotations

import difflib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import db_helper

DATA_PATH = Path(__file__).resolve().parent / "intents_data.json"

CONTRACTIONS: dict[str, str] = {
    "i'd": "i would",
    "i'll": "i will",
    "i'm": "i am",
    "i've": "i have",
    "that's": "that is",
    "what's": "what is",
    "where's": "where is",
    "let's": "let us",
    "don't": "do not",
    "doesn't": "does not",
    "can't": "cannot",
    "won't": "will not",
}

NUMBER_WORDS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "couple": 2,
    "dozen": 12,
}

REMOVE_KEYWORDS = {
    "remove",
    "exclude",
    "delete",
    "drop",
    "cancel",
    "minus",
}
REMOVE_PHRASES = (
    "take out",
    "take off",
    "do not want",
    "dont want",
    "without",
    "no more",
)
TRACK_KEYWORDS = {"track", "status", "where"}

# Stopwords excluded from fuzzy food-item matching to prevent false positives
FUZZY_IGNORE_WORDS = {
    "order",
    "orders",
    "want",
    "would",
    "like",
    "please",
    "plate",
    "plates",
    "bowl",
    "bowls",
    "serving",
    "servings",
    "portion",
    "portions",
    "item",
    "items",
    "food",
    "menu",
    "track",
    "status",
    "remove",
    "delete",
    "cancel",
    "exclude",
    "complete",
    "confirm",
    "checkout",
    "done",
    "more",
    "also",
    "with",
    "along",
    "have",
    "give",
    "take",
    "make",
    "from",
    "that",
    "this",
    "much",
    "nothing",
    "else",
    "thank",
    "thanks",
    "hello",
    "namaste",
    "good",
    "price",
    "prices",
    "available",
    "start",
    "place",
    "check",
    "current",
    "cart",
    "about",
    "number",
    "three",
    "four",
    "five",
    "seven",
    "eight",
    "nine",
}


def normalize_text(text: str) -> str:
    cleaned = text.lower().strip()
    cleaned = cleaned.replace("\u2019", "'").replace("\u2014", " ").replace("-", " ")
    for contraction, expanded in CONTRACTIONS.items():
        cleaned = re.sub(rf"\b{re.escape(contraction)}\b", expanded, cleaned)
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def extract_features(text: str) -> Counter[str]:
    """Generate word unigrams, word bigrams, and character 3-4 grams for TF-IDF."""
    norm = normalize_text(text)
    tokens = norm.split()
    feats: Counter[str] = Counter()

    for tok in tokens:
        feats[f"w:{tok}"] += 1.0

    for i in range(len(tokens) - 1):
        feats[f"bg:{tokens[i]}_{tokens[i + 1]}"] += 1.2

    # Character n-grams improve typo tolerance
    padded = f" {norm} "
    for n in (3, 4):
        for i in range(max(0, len(padded) - n + 1)):
            gram = padded[i : i + n]
            if gram.strip():
                feats[f"c{n}:{gram}"] += 0.35

    return feats


def _cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    if not vec_a or not vec_b:
        return 0.0
    if len(vec_a) > len(vec_b):
        vec_a, vec_b = vec_b, vec_a
    return sum(v * vec_b.get(k, 0.0) for k, v in vec_a.items())


@dataclass
class Prediction:
    intent: str
    confidence: float


class NLPEngine:
    def __init__(self, data_path: Path = DATA_PATH) -> None:
        raw = json.loads(data_path.read_text(encoding="utf-8"))
        self.intents_config: dict[str, Any] = raw["intents"]
        self.food_entities: list[dict[str, Any]] = raw["entities"]["food-item"]

        # Build synonym lookup (longest phrases first to avoid partial overlap)
        synonym_pairs: list[tuple[str, str]] = []
        self._single_word_synonyms: dict[str, str] = {}
        for entry in self.food_entities:
            canonical = entry["value"]
            all_terms = {normalize_text(canonical)} | {
                normalize_text(s) for s in entry.get("synonyms", [])
            }
            for term in all_terms:
                if term:
                    synonym_pairs.append((term, canonical))
                    if " " not in term and len(term) >= 4:
                        self._single_word_synonyms[term] = canonical

        synonym_pairs.sort(key=lambda pair: len(pair[0]), reverse=True)
        self.synonym_pairs = synonym_pairs
        self._synonym_patterns = [
            (re.compile(rf"\b{re.escape(term)}\b"), canonical)
            for term, canonical in synonym_pairs
        ]

        # Train TF-IDF classifier over all intent examples
        self.idf: dict[str, float] = {}
        self.example_vectors: list[tuple[str, dict[str, float]]] = []
        self.intent_centroids: dict[str, dict[str, float]] = {}
        self._fit()

    def _fit(self) -> None:
        docs: list[tuple[str, Counter[str]]] = []
        df: Counter[str] = Counter()

        for intent_name, cfg in self.intents_config.items():
            for phrase in cfg.get("examples", []):
                feats = extract_features(phrase)
                docs.append((intent_name, feats))
                for feat in feats:
                    df[feat] += 1

        num_docs = len(docs)
        self.idf = {
            feat: math.log((num_docs + 1.0) / (count + 1.0)) + 1.0
            for feat, count in df.items()
        }

        centroid_accum: dict[str, Counter[str]] = {}
        for intent_name, feats in docs:
            vec = self._vectorize_counts(feats)
            self.example_vectors.append((intent_name, vec))
            acc = centroid_accum.setdefault(intent_name, Counter())
            for k, v in vec.items():
                acc[k] += v

        for intent_name, acc in centroid_accum.items():
            norm = math.sqrt(sum(v * v for v in acc.values())) or 1.0
            self.intent_centroids[intent_name] = {k: v / norm for k, v in acc.items()}

    def _vectorize_counts(self, feats: Counter[str]) -> dict[str, float]:
        weighted = {
            feat: (1.0 + math.log(tf)) * self.idf.get(feat, 1.0)
            for feat, tf in feats.items()
            if feat in self.idf
        }
        norm = math.sqrt(sum(v * v for v in weighted.values()))
        if norm == 0.0:
            return {}
        return {k: v / norm for k, v in weighted.items()}

    def _vectorize(self, text: str) -> dict[str, float]:
        return self._vectorize_counts(extract_features(text))

    # ───────────────────────── Entity Extraction ─────────────────────────

    def extract_food_spans(self, text: str) -> list[tuple[int, int, str]]:
        """Return non-overlapping (start, end, canonical_food_name) matches sorted by position."""
        norm = normalize_text(text)
        matches: list[tuple[int, int, str]] = []
        occupied: list[tuple[int, int]] = []

        def overlaps(start: int, end: int) -> bool:
            return any(not (end <= s or start >= e) for s, e in occupied)

        # 1. Exact phrase / synonym matches (longest first)
        for pattern, canonical in self._synonym_patterns:
            for m in pattern.finditer(norm):
                if not overlaps(m.start(), m.end()):
                    matches.append((m.start(), m.end(), canonical))
                    occupied.append((m.start(), m.end()))

        # 2. Fuzzy single-token fallback for minor spelling mistakes (e.g., "thupka", "momoz")
        vocab = list(self._single_word_synonyms.keys())
        for m in re.finditer(r"\b[a-z]{4,}\b", norm):
            if overlaps(m.start(), m.end()):
                continue
            token = m.group(0)
            if token in FUZZY_IGNORE_WORDS or token in NUMBER_WORDS:
                continue
            close = difflib.get_close_matches(token, vocab, n=1, cutoff=0.80)
            if close:
                canonical = self._single_word_synonyms[close[0]]
                matches.append((m.start(), m.end(), canonical))
                occupied.append((m.start(), m.end()))

        matches.sort(key=lambda item: item[0])
        return matches

    def extract_number_spans(self, text: str) -> list[tuple[int, int, int]]:
        """Return (start, end, integer_value) for digits and number words."""
        norm = normalize_text(text)
        results: list[tuple[int, int, int]] = []
        for m in re.finditer(r"\b(\d+|[a-z]+)\b", norm):
            tok = m.group(1)
            if tok.isdigit():
                val = int(tok)
                if val > 0:
                    results.append((m.start(), m.end(), val))
            elif tok in NUMBER_WORDS:
                results.append((m.start(), m.end(), NUMBER_WORDS[tok]))
        return results

    def extract_food_and_quantities(self, text: str) -> tuple[list[tuple[str, int | None]], list[str]]:
        """
        Pair each extracted food item with its quantity based on positional proximity.
        Handles patterns like:
          - "2 plates of momo and one chowmein"
          - "a plate of sel roti and 3 juju dhau"
          - "momo 2, thukpa 1"
        Returns ([(food_name, qty_or_None), ...], list_of_foods_missing_qty).
        """
        norm = normalize_text(text)
        food_spans = self.extract_food_spans(norm)
        if not food_spans:
            return [], []

        num_spans = self.extract_number_spans(norm)
        used_num_indices: set[int] = set()
        paired: list[tuple[str, int | None]] = []

        for idx, (f_start, f_end, canonical) in enumerate(food_spans):
            prev_food_end = food_spans[idx - 1][1] if idx > 0 else 0
            next_food_start = food_spans[idx + 1][0] if idx + 1 < len(food_spans) else len(norm)

            qty: int | None = None

            # Look for the closest preceding number after the previous food item
            preceding = [
                (ni, n_start, n_end, val)
                for ni, (n_start, n_end, val) in enumerate(num_spans)
                if ni not in used_num_indices and prev_food_end <= n_start < f_start
            ]
            if preceding:
                ni, _, _, val = preceding[-1]
                used_num_indices.add(ni)
                qty = val
            else:
                # Check for indefinite article ("a plate of momo", "an aloo tama")
                prefix_segment = norm[prev_food_end:f_start]
                if re.search(
                    r"\b(a|an)\s+(?:(?:plate|plates|bowl|bowls|serving|servings|portion|portions|order|orders|piece|pieces|cup|cups|set)\s+(?:of\s+)?)?$",
                    prefix_segment.strip() + " ",
                ):
                    qty = 1
                else:
                    # Check for an immediately trailing number ("momo 2", "momo x 2")
                    trailing = [
                        (ni, n_start, n_end, val)
                        for ni, (n_start, n_end, val) in enumerate(num_spans)
                        if ni not in used_num_indices
                        and f_end <= n_start < next_food_start
                        and len(norm[f_end:n_start].strip()) <= 4
                    ]
                    if trailing:
                        ni, _, _, val = trailing[0]
                        used_num_indices.add(ni)
                        qty = val

            paired.append((canonical, qty))

        missing = [name for name, qty in paired if qty is None]
        return paired, missing

    def extract_order_id(self, text: str) -> int | None:
        m = re.search(r"#?\b(\d{1,7})\b", text)
        if m:
            return int(m.group(1))
        return None

    # ───────────────────────── Intent Classification ─────────────────────────

    def predict_intent(self, text: str, context: str | None = None) -> Prediction:
        norm = normalize_text(text)
        tokens = set(norm.split())
        food_spans = self.extract_food_spans(norm)
        order_id = self.extract_order_id(text)

        # High-precision structural signals combined with dialogue context
        is_remove = bool(tokens & REMOVE_KEYWORDS) or any(p in norm for p in REMOVE_PHRASES)
        is_track = bool(tokens & TRACK_KEYWORDS)
        is_price_query = bool(tokens & {"price", "prices", "cost", "costs", "menu"}) or "how much" in norm

        if food_spans:
            if is_remove:
                return Prediction("order.remove", 0.96)
            if is_price_query and not (tokens & {"order", "want", "add", "give", "get", "take"}):
                return Prediction("menu", 0.92)
            # Direct order phrasing ("I want 2 momo" or "add 1 thukpa") works anytime
            return Prediction("order.add", 0.94)

        if is_track and order_id is not None:
            return Prediction("track.order.id", 0.95)

        if context == "ongoing-tracking" and order_id is not None:
            return Prediction("track.order.id", 0.96)

        # TF-IDF cosine similarity across all intent training examples + centroids
        vec = self._vectorize(text)
        max_scores: dict[str, float] = {}
        for intent_name, ex_vec in self.example_vectors:
            sim = _cosine_similarity(vec, ex_vec)
            if sim > max_scores.get(intent_name, 0.0):
                max_scores[intent_name] = sim

        best_intent = "fallback"
        best_score = 0.0

        for intent_name, cfg in self.intents_config.items():
            # Respect Dialogflow-style context scoping for context-bound intents
            required_contexts = cfg.get("contexts", [])
            if required_contexts and context not in required_contexts:
                # Allow order.remove / order.view only inside ongoing-order
                continue

            max_sim = max_scores.get(intent_name, 0.0)
            centroid_sim = _cosine_similarity(vec, self.intent_centroids.get(intent_name, {}))
            score = 0.72 * max_sim + 0.28 * centroid_sim

            # Mild boost for intents explicitly matching the active context
            if context and context in required_contexts:
                score += 0.08

            if score > best_score:
                best_score = score
                best_intent = intent_name

        # Confidence threshold (matches Dialogflow's mlMinConfidence = 0.3)
        if best_score < 0.30:
            return Prediction("fallback", round(best_score, 3))

        return Prediction(best_intent, round(min(best_score, 1.0), 3))


def format_cart(order: dict[str, int]) -> str:
    return ", ".join(f"{qty} {item}" for item, qty in order.items())


def calculate_cart_total(order: dict[str, int]) -> float:
    menu = {m["name"].lower(): m["price"] for m in db_helper.get_menu_items()}
    return round(sum(menu.get(item.lower(), 0.0) * qty for item, qty in order.items()), 2)


# Singleton NLP model instance (loaded once per warm serverless container)
_engine: NLPEngine | None = None


def get_engine() -> NLPEngine:
    global _engine
    if _engine is None:
        _engine = NLPEngine()
    return _engine


def process_message(message: str, session_id: str) -> dict[str, Any]:
    """Run full NLU + dialogue management + Neon DB persistence for a user message."""
    engine = get_engine()
    text = (message or "").strip()
    if not text:
        return {
            "reply": "Please type a message! You can say \"New Order\", \"Track Order\", or \"Show Menu\".",
            "intent": "fallback",
            "confidence": 0.0,
            "context": None,
            "cart": {},
            "quick_replies": ["New Order", "Track Order", "Show Menu"],
        }

    context, cart = db_helper.get_session(session_id)
    pred = engine.predict_intent(text, context=context)
    intent = pred.intent
    confidence = pred.confidence

    reply = ""
    new_context = context
    new_cart = dict(cart)
    quick_replies: list[str] = ["New Order", "Track Order", "Show Menu"]

    if intent == "welcome":
        reply = engine.intents_config["welcome"]["responses"][0]
        quick_replies = ["New Order", "Track Order", "Show Menu"]

    elif intent == "menu":
        items = db_helper.get_menu_items()
        lines = [f"• {item['name']} — रु {item['price']:.2f}" for item in items]
        reply = "Here is our Taste of Himalaya menu:\n" + "\n".join(lines) + "\n\nWould you like to place a new order?"
        quick_replies = ["New Order", "2 Momo and 1 Thukpa", "Track Order"]

    elif intent == "new.order":
        new_context = "ongoing-order"
        new_cart = {}
        reply = engine.intents_config["new.order"]["responses"][0]
        quick_replies = ["2 Momo and 1 Thukpa", "1 Dal Bhat and 1 Juju Dhau", "Show Menu"]

    elif intent == "order.add":
        new_context = "ongoing-order"
        paired, missing = engine.extract_food_and_quantities(text)
        if not paired:
            reply = (
                "I couldn't recognize a menu item in your message. "
                "Please choose from: Momo, Thukpa, Dal Bhat, Sel Roti, Chowmein, Gundruk, Aloo Tama, Sekuwa, or Juju Dhau."
            )
            quick_replies = ["Show Menu", "2 Momo", "1 Dal Bhat"]
        elif missing:
            missing_str = ", ".join(missing)
            reply = (
                f"Please specify a quantity for {missing_str} "
                f"(for example: \"2 {missing[0]}\" or \"1 plate of {missing[0]}\")."
            )
            quick_replies = [f"1 {missing[0]}", f"2 {missing[0]}", "Show Menu"]
        else:
            for food_name, qty in paired:
                assert qty is not None
                new_cart[food_name] = new_cart.get(food_name, 0) + qty

            cart_str = format_cart(new_cart)
            est_total = calculate_cart_total(new_cart)
            reply = (
                f"Added to your order! So far you have: {cart_str} "
                f"(Subtotal: रु {est_total:.2f}). Do you need anything else?"
            )
            quick_replies = ["Place Order", "Show Menu", "Remove item"]

    elif intent == "order.remove":
        if not new_cart:
            reply = "Your current order is empty, so there's nothing to remove. Say \"New Order\" to start ordering!"
            new_context = None
            quick_replies = ["New Order", "Show Menu", "Track Order"]
        else:
            paired, _ = engine.extract_food_and_quantities(text)
            if not paired:
                cart_str = format_cart(new_cart)
                reply = f"Which item would you like to remove? Currently in your order: {cart_str}."
                quick_replies = [f"Remove {item}" for item in list(new_cart.keys())[:3]]
            else:
                removed_msgs: list[str] = []
                missing_items: list[str] = []

                for food_name, qty in paired:
                    if food_name not in new_cart:
                        missing_items.append(food_name)
                    elif qty is not None and qty < new_cart[food_name]:
                        new_cart[food_name] -= qty
                        removed_msgs.append(f"{qty} {food_name}")
                    else:
                        del new_cart[food_name]
                        removed_msgs.append(food_name)

                parts: list[str] = []
                if removed_msgs:
                    parts.append(f"Removed {', '.join(removed_msgs)} from your order.")
                if missing_items:
                    parts.append(f"Your current order does not have {', '.join(missing_items)}.")

                if not new_cart:
                    parts.append("Your order is now empty! Add items or start fresh.")
                    quick_replies = ["2 Momo", "Show Menu", "Track Order"]
                else:
                    cart_str = format_cart(new_cart)
                    est_total = calculate_cart_total(new_cart)
                    parts.append(f"Remaining in your order: {cart_str} (Subtotal: रु {est_total:.2f}). Anything else?")
                    quick_replies = ["Place Order", "Show Menu"]

                reply = " ".join(parts)

    elif intent == "order.view":
        if not new_cart:
            reply = "Your cart is currently empty. Say \"New Order\" or tell me what you'd like to eat!"
            quick_replies = ["New Order", "Show Menu"]
        else:
            cart_str = format_cart(new_cart)
            est_total = calculate_cart_total(new_cart)
            reply = f"Your current order has: {cart_str} (Subtotal: रु {est_total:.2f}). Ready to place it?"
            quick_replies = ["Place Order", "Show Menu"]

    elif intent == "order.complete":
        if not new_cart:
            reply = "I'm having trouble finding items in your order. Please add some food items first (e.g., \"2 Momo and 1 Thukpa\")."
            quick_replies = ["2 Momo and 1 Thukpa", "Show Menu"]
        else:
            try:
                order_id, order_total = db_helper.save_order(new_cart)
                summary = format_cart(new_cart)
                new_cart = {}
                new_context = None
                reply = (
                    f"Awesome! We have placed your order ({summary}).\n"
                    f"Order ID: #{order_id}\n"
                    f"Total: रु {order_total:.2f} (pay on delivery).\n"
                    f"You can track it anytime by saying \"Track Order {order_id}\"!"
                )
                quick_replies = [f"Track Order {order_id}", "New Order", "Show Menu"]
            except Exception as exc:
                reply = f"Sorry, I couldn't save your order due to a backend error ({exc}). Please try again."
                quick_replies = ["Place Order", "New Order"]

    elif intent == "track.order":
        new_context = "ongoing-tracking"
        reply = engine.intents_config["track.order"]["responses"][0]
        quick_replies = ["40", "41", "42"]

    elif intent == "track.order.id":
        order_id = engine.extract_order_id(text)
        if order_id is None:
            new_context = "ongoing-tracking"
            reply = "Please enter a valid numeric order ID (for example: 40, 41, or 42)."
            quick_replies = ["40", "41", "42"]
        else:
            order_info = db_helper.get_order_status(order_id)
            new_context = "ongoing-tracking"
            if order_info:
                items_list = order_info.get("items", [])
                details = ""
                if items_list:
                    items_str = ", ".join(f"{i['quantity']} {i['name']}" for i in items_list)
                    details = f"\nItems: {items_str} (Total: रु {order_info['total_price']:.2f})"
                reply = f"Order #{order_id} status: {order_info['status']}.{details}"
            else:
                reply = f"No order found with Order ID #{order_id}. Try a valid ID like 40, 41, or 42."
            quick_replies = ["New Order", "Track Order", "Show Menu"]

    elif intent == "final.words":
        new_context = None
        reply = engine.intents_config["final.words"]["responses"][0]
        quick_replies = ["New Order", "Track Order", "Show Menu"]

    else:
        if context == "ongoing-order":
            reply = (
                "Sorry, I didn't quite catch that. You can add items (e.g. \"2 Momo\"), "
                "remove an item (e.g. \"remove Thukpa\"), or say \"Done\" to place your order."
            )
            quick_replies = ["Place Order", "Show Menu", "2 Momo"]
        elif context == "ongoing-tracking":
            reply = "Please enter your numeric order ID (for example: 40, 41, or 42), or say \"New Order\"."
            quick_replies = ["40", "41", "New Order"]
        else:
            reply = "Sorry, I didn't understand that. You can say \"New Order\", \"Track Order\", or \"Show Menu\"."
            quick_replies = ["New Order", "Track Order", "Show Menu"]

    db_helper.save_session(session_id, new_context, new_cart)

    return {
        "reply": reply,
        "intent": intent,
        "confidence": confidence,
        "context": new_context,
        "cart": new_cart,
        "quick_replies": quick_replies,
    }
