import asyncpg

from ..core.security import create_access_token, hash_password, verify_password


async def register_user(pool: asyncpg.Pool, email: str, password: str) -> dict:
    """
    Create a new user. Returns {user_id: str, email: str}.
    Raises ValueError if the email is already registered.
    """
    email = email.lower().strip()

    existing = await pool.fetchrow("SELECT user_id FROM users WHERE email = $1", email)
    if existing is not None:
        raise ValueError("Email already registered")

    hashed = hash_password(password)
    row = await pool.fetchrow(
        "INSERT INTO users (email, password_hash) VALUES ($1, $2) RETURNING user_id, email",
        email,
        hashed,
    )
    return {"user_id": str(row["user_id"]), "email": row["email"]}


async def login_user(pool: asyncpg.Pool, email: str, password: str) -> str:
    """
    Verify credentials and return a JWT access token.
    Raises ValueError on bad email or password.
    """
    email = email.lower().strip()

    row = await pool.fetchrow(
        "SELECT user_id, password_hash FROM users WHERE email = $1",
        email,
    )
    if row is None or not verify_password(password, row["password_hash"]):
        raise ValueError("Invalid email or password")

    return create_access_token(str(row["user_id"]))
