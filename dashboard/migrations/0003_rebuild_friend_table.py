from django.db import migrations


class Migration(migrations.Migration):
    """
    Rebuilds the dashboard_friend table with the correct schema (owner_id column).
    Uses raw SQL via SeparateDatabaseAndState so Django's migration state is not
    affected — avoiding conflicts caused by the earlier modified 0001 migration.
    """

    dependencies = [("dashboard", "0002_friend_owner_id")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        DROP TABLE IF EXISTS dashboard_friend;
                        CREATE TABLE dashboard_friend (
                            id          BIGSERIAL PRIMARY KEY,
                            owner_id    VARCHAR(255) NOT NULL,
                            user_id     VARCHAR(255) NOT NULL,
                            added_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                            UNIQUE (owner_id, user_id)
                        );
                        CREATE INDEX dashboard_friend_owner_id_idx
                            ON dashboard_friend (owner_id);
                    """,
                    reverse_sql="DROP TABLE IF EXISTS dashboard_friend;",
                ),
            ],
            state_operations=[],
        ),
    ]
