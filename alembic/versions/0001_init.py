# Alembic revision identifiers.
revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from aiflag.db import Base, engine
    from aiflag import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def downgrade() -> None:
    from aiflag.db import Base, engine
    from aiflag import models  # noqa: F401

    Base.metadata.drop_all(bind=engine)
