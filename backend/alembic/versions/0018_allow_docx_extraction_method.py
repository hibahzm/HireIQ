"""Allow 'docx' as a cv_extraction_method.

V2-1 (010-cv-file-formats) added native DOCX extraction, but the
ck_applications_extraction check constraint from 0004 still only allowed
('pymupdf', 'document_intelligence') — so any DOCX CV that extracted natively
crashed screening at persist time with a CheckViolationError.
"""

from __future__ import annotations

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE applications DROP CONSTRAINT IF EXISTS ck_applications_extraction")
    op.execute(
        "ALTER TABLE applications ADD CONSTRAINT ck_applications_extraction "
        "CHECK (cv_extraction_method IN ('pymupdf', 'docx', 'document_intelligence'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE applications DROP CONSTRAINT IF EXISTS ck_applications_extraction")
    op.execute(
        "ALTER TABLE applications ADD CONSTRAINT ck_applications_extraction "
        "CHECK (cv_extraction_method IN ('pymupdf', 'document_intelligence'))"
    )
