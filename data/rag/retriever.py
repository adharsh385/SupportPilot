import json

from sklearn.feature_extraction.text import (
    TfidfVectorizer
)

from sklearn.metrics.pairwise import (
    cosine_similarity
)

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

        self.vectorizer = (
            TfidfVectorizer(
                stop_words="english"
            )
        )

        self.document_vectors = (

            self.vectorizer.fit_transform(
                self.texts
            )

        )

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