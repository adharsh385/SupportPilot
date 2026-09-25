import os

import joblib

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline


training_data = [

    ("vpn connection not working", "VPN"),
    ("vpn is not connecting", "VPN"),
    ("vpn connection failed", "VPN"),
    ("cannot connect to vpn", "VPN"),
    ("vpn timeout error", "VPN"),
    ("corporate vpn not working", "VPN"),
    ("vpn keeps disconnecting", "VPN"),
    ("remote vpn connection problem", "VPN"),
    ("vpn authentication problem", "VPN"),
    ("vpn cannot connect", "VPN"),

    ("internet connection not working", "Network"),
    ("wifi is not working", "Network"),
    ("network connection problem", "Network"),
    ("internet is very slow", "Network"),
    ("cannot access network", "Network"),
    ("network disconnected", "Network"),
    ("office wifi problem", "Network"),
    ("network timeout", "Network"),
    ("internet outage", "Network"),
    ("network is down", "Network"),

    ("forgot my password", "Password"),
    ("password reset required", "Password"),
    ("cannot login because of password", "Password"),
    ("password is not working", "Password"),
    ("reset my account password", "Password"),
    ("account password locked", "Password"),
    ("login password problem", "Password"),
    ("unable to reset password", "Password"),

    ("software installation problem", "Software"),
    ("application is not working", "Software"),
    ("software installation failed", "Software"),
    ("application crashes", "Software"),
    ("cannot install software", "Software"),
    ("program is showing an error", "Software"),
    ("application installation problem", "Software"),
    ("software error", "Software"),

    ("laptop is not working", "Hardware"),
    ("keyboard is not working", "Hardware"),
    ("mouse is not working", "Hardware"),
    ("computer hardware problem", "Hardware"),
    ("monitor is not working", "Hardware"),
    ("laptop screen problem", "Hardware"),
    ("printer hardware problem", "Hardware"),
    ("computer hardware failure", "Hardware"),

    ("computer system error", "System"),
    ("system is very slow", "System"),
    ("windows error", "System"),
    ("computer freezes", "System"),
    ("system restart problem", "System"),
    ("operating system problem", "System"),
    ("computer system problem", "System"),
    ("system crash", "System")
]


texts = [
    item[0]
    for item in training_data
]


labels = [
    item[1]
    for item in training_data
]


model = Pipeline([
    (
        "tfidf",
        TfidfVectorizer(
            lowercase=True,
            ngram_range=(1, 2),
            sublinear_tf=True
        )
    ),
    (
        "classifier",
        LogisticRegression(
            max_iter=2000,
            random_state=42
        )
    )
])


model.fit(
    texts,
    labels
)


os.makedirs(
    "models",
    exist_ok=True
)


joblib.dump(
    model,
    "models/ticket_classifier.pkl"
)