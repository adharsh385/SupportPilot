def analyze_ticket(ticket):

    text = (

        ticket["title"]

        + " "

        + ticket["description"]

    ).lower()

    possible_keywords = [

        "vpn",

        "network",

        "firewall",

        "authentication",

        "timeout",

        "connection",

        "dns",

        "password",

        "software",

        "hardware",

        "system",

        "wifi"

    ]

    keywords = [

        word

        for word in possible_keywords

        if word in text

    ]

    return {

        "ticket_id":
            ticket["id"],

        "category":
            ticket.get("category"),

        "priority":
            ticket.get("priority"),

        "keywords":
            keywords,

        "query":
            text

    }