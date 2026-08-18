from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from bitrix24.models import (
    BitrixCrmDictionary,
    BitrixDepartment,
    BitrixStageHistory,
    BitrixSyncState,
    BitrixUser,
    BitrixUserDepartment,
)


class BitrixModelConstraintsTests(TestCase):
    def test_sync_state_has_one_row_per_entity(self):
        BitrixSyncState.objects.create(entity="leads")

        with self.assertRaises(IntegrityError), transaction.atomic():
            BitrixSyncState.objects.create(entity="leads")

    def test_dictionary_code_is_unique_inside_entity(self):
        BitrixCrmDictionary.objects.create(
            entity_id="STATUS",
            status_id="NEW",
            name="Новый",
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            BitrixCrmDictionary.objects.create(
                entity_id="STATUS",
                status_id="NEW",
                name="Дубликат",
            )

    def test_user_can_have_only_one_primary_department(self):
        user = BitrixUser.objects.create(user_id=10, full_name="Менеджер")
        first = BitrixDepartment.objects.create(department_id=100, name="Первое")
        second = BitrixDepartment.objects.create(department_id=200, name="Второе")
        BitrixUserDepartment.objects.create(
            user=user,
            department=first,
            position=0,
            is_primary=True,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            BitrixUserDepartment.objects.create(
                user=user,
                department=second,
                position=1,
                is_primary=True,
            )

    def test_stage_history_id_is_unique_per_entity_type(self):
        created_at = timezone.now()
        BitrixStageHistory.objects.create(
            history_id=500,
            entity_type_id=1,
            entity_id=1000,
            stage_id="NEW",
            created_at=created_at,
        )
        BitrixStageHistory.objects.create(
            history_id=500,
            entity_type_id=2,
            entity_id=2000,
            stage_id="NEW",
            created_at=created_at,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            BitrixStageHistory.objects.create(
                history_id=500,
                entity_type_id=1,
                entity_id=1001,
                stage_id="IN_PROCESS",
                created_at=created_at,
            )
