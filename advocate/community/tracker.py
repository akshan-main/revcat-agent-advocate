from ..models import CommunityInteraction, InteractionChannel, InteractionIntent
from ..db import insert_row, query_rows, update_row, now_iso


def log_interaction(db_conn, interaction: CommunityInteraction) -> int:
    """Log a community interaction. Returns row id."""
    return insert_row(db_conn, "community_interactions", {
        "channel": interaction.channel.value,
        "thread_url": interaction.thread_url,
        "counterpart": interaction.counterpart,
        "intent": interaction.intent.value,
        "question": interaction.question,
        "draft_response": interaction.draft_response,
        "status": interaction.status,
        "notes": interaction.notes,
        "created_at": interaction.created_at or now_iso(),
        "sent_at": interaction.sent_at,
    })


def list_interactions(
    db_conn,
    channel: str | None = None,
    status: str | None = None,
    since: str | None = None,
) -> list[dict]:
    """Query interactions with optional filters."""
    where = {}
    if channel:
        where["channel"] = channel
    if status:
        where["status"] = status

    rows = query_rows(db_conn, "community_interactions", where=where or None)

    if since:
        rows = [r for r in rows if r["created_at"] >= since]

    return rows


def update_interaction_status(db_conn, interaction_id: int, status: str, sent_at: str | None = None):
    """Update interaction status."""
    data = {"status": status}
    if sent_at:
        data["sent_at"] = sent_at
    update_row(db_conn, "community_interactions", interaction_id, data)
