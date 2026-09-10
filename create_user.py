from database import (
    initialize_database,
    create_user
)


initialize_database()


username = input(
    "Enter username: "
).strip()

email = input(
    "Enter email: "
).strip()

password = input(
    "Enter password: "
)


user_id = create_user(
    username,
    email,
    password
)


if user_id:

    print(
        "User created successfully."
    )

else:

    print(
        "Username or email already exists."
    )
