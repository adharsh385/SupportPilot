import joblib

from pathlib import Path

from sklearn.feature_extraction.text import (
    TfidfVectorizer
)

from sklearn.linear_model import (
    LogisticRegression
)

from sklearn.pipeline import (
    Pipeline
)

from config import MODEL_PATH


training_data = [

    (
        "vpn connection not working",
        "VPN"
    ),

    (
        "unable to connect to vpn",
        "VPN"
    ),

    (
        "vpn connection failed",
        "VPN"
    ),

    (
        "vpn timeout error",
        "VPN"
    ),

    (
        "corporate vpn not connecting",
        "VPN"
    ),

    (
        "vpn server connection problem",
        "VPN"
    ),

    (
        "vpn client authentication issue",
        "VPN"
    ),

    (
        "cannot connect to company vpn",
        "VPN"
    ),

    (
        "internet connection not working",
        "Network"
    ),

    (
        "wifi is not working",
        "Network"
    ),

    (
        "network connection failed",
        "Network"
    ),

    (
        "dns connection problem",
        "Network"
    ),

    (
        "internet is slow",
        "Network"
    ),

    (
        "network timeout",
        "Network"
    ),

    (
        "wifi connection problem",
        "Network"
    ),

    (
        "ethernet not connecting",
        "Network"
    ),

    (
        "forgot my password",
        "Password"
    ),

    (
        "password reset required",
        "Password"
    ),

    (
        "unable to login",
        "Password"
    ),

    (
        "cannot sign in",
        "Password"
    ),

    (
        "password is not working",
        "Password"
    ),

    (
        "reset my account password",
        "Password"
    ),

    (
        "credentials are not working",
        "Password"
    ),

    (
        "login password problem",
        "Password"
    ),

    (
        "software installation failed",
        "Software"
    ),

    (
        "cannot install application",
        "Software"
    ),

    (
        "application is not working",
        "Software"
    ),

    (
        "software installation problem",
        "Software"
    ),

    (
        "program installation error",
        "Software"
    ),

    (
        "app is crashing",
        "Software"
    ),

    (
        "software error",
        "Software"
    ),

    (
        "application installation issue",
        "Software"
    ),

    (
        "keyboard is not working",
        "Hardware"
    ),

    (
        "mouse stopped working",
        "Hardware"
    ),

    (
        "monitor is not working",
        "Hardware"
    ),

    (
        "laptop hardware problem",
        "Hardware"
    ),

    (
        "computer screen problem",
        "Hardware"
    ),

    (
        "hardware device failed",
        "Hardware"
    ),

    (
        "keyboard problem",
        "Hardware"
    ),

    (
        "mouse problem",
        "Hardware"
    ),

    (
        "windows system error",
        "System"
    ),

    (
        "computer keeps crashing",
        "System"
    ),

    (
        "system is frozen",
        "System"
    ),

    (
        "operating system problem",
        "System"
    ),

    (
        "computer restart problem",
        "System"
    ),

    (
        "windows error",
        "System"
    ),

    (
        "system recovery required",
        "System"
    ),

    (
        "computer system failure",
        "System"
    )

]


def train_and_save_model():

    texts = [
        item[0]
        for item in training_data
    ]

    labels = [
        item[1]
        for item in training_data
    ]

    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=(1, 2)
    )

    vectors = vectorizer.fit_transform(
        texts
    )

    model = LogisticRegression(
        max_iter=1000
    )

    model.fit(
        vectors,
        labels
    )

    MODEL_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    bundle = {

        "vectorizer":
            vectorizer,

        "model":
            model

    }

    joblib.dump(
        bundle,
        MODEL_PATH
    )

    print(
        "Model trained successfully."
    )

    print(
        f"Model saved to: {MODEL_PATH}"
    )


if __name__ == "__main__":

    train_and_save_model()
