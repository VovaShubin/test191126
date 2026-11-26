"""Initial campaign draft tables.

Revision ID: 20261125_01
Revises:
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261125_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("keitaro_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("synced_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("keitaro_id"),
    )
    op.create_index("ix_campaigns_keitaro_id", "campaigns", ["keitaro_id"])
    op.create_table(
        "streams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("keitaro_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("has_offers", sa.Boolean(), nullable=False),
        sa.Column("is_dirty", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("keitaro_id"),
    )
    op.create_index("ix_streams_keitaro_id", "streams", ["keitaro_id"])
    op.create_table(
        "stream_offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stream_id", sa.Integer(), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("offer_name", sa.String(length=255), nullable=False),
        sa.Column("share", sa.Integer(), nullable=False),
        sa.Column("is_removed", sa.Boolean(), nullable=False),
        sa.Column("is_pinned", sa.Boolean(), nullable=False),
        sa.Column("published_share", sa.Integer(), nullable=False),
        sa.Column("published_removed", sa.Boolean(), nullable=False),
        sa.Column("existed_at_sync", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["stream_id"], ["streams.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("stream_id", "offer_id", name="uq_stream_offer"),
    )
    op.create_index("ix_stream_offers_offer_id", "stream_offers", ["offer_id"])


def downgrade() -> None:
    op.drop_index("ix_stream_offers_offer_id", table_name="stream_offers")
    op.drop_table("stream_offers")
    op.drop_index("ix_streams_keitaro_id", table_name="streams")
    op.drop_table("streams")
    op.drop_index("ix_campaigns_keitaro_id", table_name="campaigns")
    op.drop_table("campaigns")

