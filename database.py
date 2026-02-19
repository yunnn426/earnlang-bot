import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL과 SUPABASE_KEY가 설정되지 않았습니다.")
        _client = create_client(url, key)
    return _client


def upsert_user(slack_user_id: str, difficulty: str, language: str = "jp") -> int:
    """Insert or update user settings. Returns the user id."""
    client = get_client()
    existing = (
        client.table("users")
        .select("id")
        .eq("slack_user_id", slack_user_id)
        .execute()
    )

    if existing.data:
        user_id = existing.data[0]["id"]
        client.table("users").update(
            {"difficulty": difficulty, "language": language}
        ).eq("id", user_id).execute()
    else:
        result = (
            client.table("users")
            .insert(
                {
                    "slack_user_id": slack_user_id,
                    "difficulty": difficulty,
                    "language": language,
                }
            )
            .execute()
        )
        user_id = result.data[0]["id"]

    return user_id


def get_all_users() -> list[dict]:
    client = get_client()
    result = client.table("users").select("*").execute()
    return result.data


def get_user_by_slack_id(slack_user_id: str) -> dict | None:
    client = get_client()
    result = (
        client.table("users")
        .select("*")
        .eq("slack_user_id", slack_user_id)
        .execute()
    )
    return result.data[0] if result.data else None


def delete_user(user_id: int) -> None:
    client = get_client()
    client.table("users").delete().eq("id", user_id).execute()
