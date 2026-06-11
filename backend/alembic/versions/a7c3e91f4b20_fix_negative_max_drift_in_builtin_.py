"""Fix negative max_drift in builtin scenario steps.

max_drift is a magnitude — the drift direction comes from drift_per_second's
sign (anomaly_injector clamps with `abs(drift) > abs(max_drift)` and takes the
sign from drift_per_second). A negative max_drift made the clamp flip the
drift's sign once the cap was reached: the builtin "Fault Disconnect" scenario
(drift_per_second=-5, max_drift=-50) sagged dc_voltage for 10 s and then
jumped it to +50 ABOVE baseline for the rest of the step.

The seed JSON is fixed in the same change; this migration repairs rows that
were already seeded (the seed loader skips existing builtin scenarios).
Only builtin scenarios are touched — user-created steps with negative
max_drift are now rejected at the API, but existing user data is left alone.

Revision ID: a7c3e91f4b20
Revises: b241433f7174
Create Date: 2026-06-11
"""
from collections.abc import Sequence

from alembic import op

revision: str = "a7c3e91f4b20"
down_revision: str | None = "b241433f7174"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE scenario_steps AS ss
        SET anomaly_params = jsonb_set(
                ss.anomaly_params,
                '{max_drift}',
                to_jsonb(abs((ss.anomaly_params ->> 'max_drift')::numeric))
            )
        FROM scenarios AS s
        WHERE s.id = ss.scenario_id
          AND s.is_builtin IS TRUE
          AND ss.anomaly_type = 'drift'
          AND (ss.anomaly_params ->> 'max_drift')::numeric < 0
        """
    )


def downgrade() -> None:
    # Irreversible data repair: the original (buggy) negative values are not
    # preserved. Downgrade is a no-op.
    pass
