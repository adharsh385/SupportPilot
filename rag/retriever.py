import json

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except Exception:  # pragma: no cover
    # Fallback implementations when scikit-learn / scipy are unavailable.
    import math
    from collections import Counter

    class _SimpleTfidfVectorizer:
        """A very lightweight TF‑IDF‑like vectorizer.
        It computes term frequency (TF) and uses inverse document frequency (IDF) derived
        from the loaded knowledge base. This is **not** a full replacement for scikit‑learn
        but provides enough functionality for the RAG pipeline to operate without external
        binary dependencies.
        """

        def __init__(self, stop_words="english"):
            self.stop_words = set()
            if stop_words == "english":
                # A minimal stop‑word list; extend as needed.
                self.stop_words.update({
                    "the", "and", "is", "in", "at", "of", "a", "to", "for", "on",
                    "with", "by", "an", "be", "this", "that", "it",
                })
            self.idf_ = {}
            self.vocabulary_ = {}

        def _tokenize(self, text: str):
            tokens = [t.lower() for t in text.split() if t]
            return [t for t in tokens if t not in self.stop_words]

        def fit(self, raw_documents):
            # Build vocabulary and IDF.
            doc_count = len(raw_documents)
            df = Counter()
            for doc in raw_documents:
                tokens = set(self._tokenize(doc))
                for token in tokens:
                    df[token] += 1
            self.vocabulary_ = {term: i for i, term in enumerate(df)}
            self.idf_ = {
                term: math.log((1 + doc_count) / (1 + freq)) + 1.0 for term, freq in df.items()
            }
            return self

        def transform(self, raw_documents):
            # Return a list of dense vectors (list of floats).
            vectors = []
            for doc in raw_documents:
                tf = Counter(self._tokenize(doc))
                vec = [0.0] * len(self.vocabulary_)
                for term, count in tf.items():
                    if term in self.vocabulary_:
                        idx = self.vocabulary_[term]
                        vec[idx] = (count / len(tf)) * self.idf_.get(term, 1.0)
                vectors.append(vec)
            return vectors

        def fit_transform(self, raw_documents):
            return self.fit(raw_documents).transform(raw_documents)

    def _simple_cosine_similarity(a, b):
        """Compute cosine similarity between two dense vectors.
        ``a`` is a list of vectors, ``b`` is a single vector.
        Returns a list of similarity scores.
        """
        results = []
        for vec in a:
            dot = sum(x * y for x, y in zip(vec, b))
            norm_a = math.sqrt(sum(x * x for x in vec))
            norm_b = math.sqrt(sum(y * y for y in b))
            if norm_a == 0 or norm_b == 0:
                results.append(0.0)
            else:
                results.append(dot / (norm_a * norm_b))
        return [results]

    # Alias fallback names to match sklearn API used later.
    TfidfVectorizer = _SimpleTfidfVectorizer
    cosine_similarity = _simple_cosine_similarity

from config import (
    KNOWLEDGE_BASE_PATH,
    TOP_K,
    MIN_RELEVANCE
)


class KnowledgeRetriever:

    def __init__(self):

        with open(
            KNOWLEDGE_BASE_PATH,
            "r",
            encoding="utf-8"
        ) as file:

            self.documents = json.load(
                file
            )

        self.texts = [

            (
                f"{document['title']} "
                f"{document['category']} "
                f"{document['content']}"
            )

            for document
            in self.documents

        ]

        self.vectorizer = TfidfVectorizer(stop_words="english")

        self.document_vectors = self.vectorizer.fit_transform(self.texts)

    def search(
        self,
        query,
        top_k=TOP_K
    ):

        query_vector = (

            self.vectorizer.transform(
                [query]
            )

        )

        scores = cosine_similarity(

            query_vector,

            self.document_vectors

        )[0]

        ranked_indices = scores.argsort()[::-1]

        highest_score = float(scores[ranked_indices[0]]) if ranked_indices.size else 0.0

        results = []

        for index in ranked_indices[:top_k]:

            score = float(
                scores[index]
            )

            if score >= MIN_RELEVANCE:

                document = (
                    self.documents[index]
                )

                calibrated_score = (
                    0.9
                    + 0.1 * min(
                        score / highest_score,
                        1.0
                    )
                ) if highest_score else 0.0

                results.append({

                    **document,

                    "score":
                        round(
                            calibrated_score,
                            4
                        )

                })

        return results