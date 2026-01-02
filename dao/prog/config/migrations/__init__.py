"""Configuration migration functions."""

from .migrator import migrate_config
from .unversioned_to_v0 import migrate_unversioned_to_v0

# Uncomment when creating v0→v1 migration:
# from .v0_to_v1 import migrate_v0_to_v1

# Migration registry: maps (from_version, to_version) -> migration function
# Special case: (-1, 0) handles unversioned → v0 migration
MIGRATIONS: dict[tuple[int, int], callable] = {
    (-1, 0): migrate_unversioned_to_v0,  # unversioned → v0
    # Uncomment when creating v0→v1 migration:
    # (0, 1): migrate_v0_to_v1,
}

__all__ = ["migrate_config", "MIGRATIONS", "migrate_unversioned_to_v0"]
