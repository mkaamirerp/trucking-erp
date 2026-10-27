"""EQ01 schema checkpoint: metadata/DDL and split-lineage tests; no DB writes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.models.equipment_attachment import (
    DriverEquipmentDefault, EquipmentCurrentAttachment,
)
from alembic_tenant.equipment_attachments_ddl import (
    upgrade_equipment_attachments, downgrade_equipment_attachments,
)


def test_only_two_new_equipment_tables_and_tenant_composite_fk_contracts():
    defaults = DriverEquipmentDefault.__table__
    current = EquipmentCurrentAttachment.__table__
    assert defaults.primary_key.columns.keys() == ["tenant_id", "driver_id"]
    assert current.primary_key.columns.keys() == ["tenant_id", "truck_id"]
    assert set(defaults.columns.keys()) == {
        "tenant_id", "driver_id", "default_truck_id",
        "equipment_binding_mode", "created_at", "updated_at",
    }
    assert set(current.columns.keys()) == {
        "tenant_id", "truck_id", "driver_id", "trailer_id",
        "confirmed_at", "updated_at", "version",
    }
    def fk_sets(table):
        return {
            tuple(sorted(column.key for column in fk.columns))
            for fk in table.foreign_key_constraints
        }
    assert fk_sets(defaults) == {
        ("driver_id", "tenant_id"), ("default_truck_id", "tenant_id"),
    }
    assert fk_sets(current) == {
        ("tenant_id", "truck_id"), ("driver_id", "tenant_id"),
        ("tenant_id", "trailer_id"),
    }


def test_database_uniqueness_prevents_one_driver_or_trailer_claimed_by_two_trucks():
    by_name = {index.name: index for index in EquipmentCurrentAttachment.__table__.indexes}
    for name in (
        "uq_equipment_current_tenant_driver",
        "uq_equipment_current_tenant_trailer",
    ):
        assert by_name[name].unique is True
        assert len(by_name[name].columns) == 2
        assert by_name[name].dialect_options["postgresql"]["where"] is not None


def test_sibling_revision_heads_are_independent_and_branch_specific():
    repo = Path(__file__).resolve().parents[1]
    cfg = Config(str(repo / "alembic_tenant.ini"))
    script = ScriptDirectory.from_config(cfg)
    assert set(script.get_heads()) == {
        "s1_load_approved_snapshot_fmp",
        "s1_load_approved_snapshot_x5",
    }
    assert script.get_revision("s1_load_approved_snapshot_fmp").down_revision == "eq01_equipment_attachments_fmp"
    assert script.get_revision("s1_load_approved_snapshot_x5").down_revision == "eq01_equipment_attachments_x5"
    assert script.get_revision("eq01_equipment_attachments_fmp").down_revision == "ln01_load_number_periods_fmp"
    assert script.get_revision("eq01_equipment_attachments_x5").down_revision == "ln01_load_number_periods_x5"


def test_shared_migration_operations_have_two_tables_two_uniques_and_indexes():
    with patch("alembic_tenant.equipment_attachments_ddl.op") as operations:
        upgrade_equipment_attachments()
        assert [call.args[0] for call in operations.create_table.call_args_list] == [
            "driver_equipment_defaults", "equipment_current_attachments",
        ]
        assert [call.args[0] for call in operations.create_unique_constraint.call_args_list] == [
            "uq_drivers_tenant_id_id", "uq_trailers_tenant_id_id",
        ]
        names = {call.args[0] for call in operations.create_index.call_args_list}
        assert names == {
            "ix_driver_equipment_defaults_tenant_truck",
            "uq_equipment_current_tenant_driver",
            "uq_equipment_current_tenant_trailer",
        }
        operations.reset_mock()
        downgrade_equipment_attachments()
        assert [call.args[0] for call in operations.drop_table.call_args_list] == [
            "equipment_current_attachments", "driver_equipment_defaults",
        ]
