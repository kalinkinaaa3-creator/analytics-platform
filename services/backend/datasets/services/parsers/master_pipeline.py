import logging
import traceback
from datetime import timedelta

from django.core.management import call_command
from django.utils import timezone
from datasets.services.parsers.tara_jobs import TaraPending

from analytics.services.bitrix_notify import (
    send_bitrix_message,
)
from datasets.models import (
    ParserMasterPipelineRun,
)
from datasets.services.iprice_runtime import (
    publish_iprice_update,
)


logger = logging.getLogger("parsers.master")


class ParserMasterPipelineError(Exception):
    pass


def _publish_run_event(
    run: ParserMasterPipelineRun,
    *,
    change_type: str,
    invalidate_health: bool = False,
) -> None:
    """
    Отправляет WebSocket-событие об изменении состояния
    мастер-пайплайна парсеров.

    Ошибка доставки события не должна переводить успешно
    выполняющийся парсер в состояние failed.
    """

    try:
        publish_iprice_update(
            change_type,
            invalidate_health=invalidate_health,
            run_id=run.pk,
            status=run.status,
            current_step=run.current_step,
        )

    except Exception:
        logger.exception(
            (
                "Failed to publish parser pipeline event: "
                "run_id=%s change_type=%s status=%s step=%s"
            ),
            run.pk,
            change_type,
            run.status,
            run.current_step,
        )


def _update_run(
    run: ParserMasterPipelineRun,
    *,
    status: str | None = None,
    current_step: str | None = None,
    error: str | None = None,
    result: dict | None = None,
    started: bool = False,
    finished: bool = False,
    change_type: str = "parser_progress",
    invalidate_health: bool = False,
) -> None:
    """
    Обновляет ParserMasterPipelineRun и после успешного
    сохранения отправляет соответствующее WebSocket-событие.

    change_type:
        parser_started
        parser_progress
        parser_finished
        parser_failed
    """

    update_fields = []

    if status is not None:
        run.status = status
        update_fields.append("status")

    if current_step is not None:
        run.current_step = current_step
        update_fields.append("current_step")

    if error is not None:
        run.error = error
        update_fields.append("error")

    if result is not None:
        run.result = result
        update_fields.append("result")

    if started:
        run.started_at = timezone.now()
        update_fields.append("started_at")

    if finished:
        run.finished_at = timezone.now()
        update_fields.append("finished_at")

    if not update_fields:
        return

    run.save(
        update_fields=update_fields,
    )

    _publish_run_event(
        run,
        change_type=change_type,
        invalidate_health=invalidate_health,
    )


def _run_command(
    run: ParserMasterPipelineRun,
    *,
    step_name: str,
    command_name: str,
    command_options: dict | None = None,
) -> None:
    """
    Фиксирует текущий этап, отправляет parser_progress
    и запускает соответствующую management-команду.
    """

    command_options = command_options or {}
    completed = list(run.result.get('completed_steps', []))
    if step_name in completed:
        return
    if command_name == 'load_tara_products':
        command_options = {**command_options, 'master_run_id': run.pk, 'step_key': step_name}
    if command_name == 'report_tara_parser_result':
        from datasets.models import TaraRun
        # Report both passes separately so the retry subset never appears to be
        # the whole classified selection.
        for child in TaraRun.objects.filter(master=run).order_by('id'):
            call_command(command_name, **command_options, tara_run_id=child.pk)
        completed.append(step_name)
        run.result = {**run.result, 'completed_steps': completed}
        run.save(update_fields=['result'])
        return

    _update_run(
        run,
        current_step=step_name,
        change_type="parser_progress",
    )

    logger.info(
        (
            "Parser master pipeline "
            "run_id=%s step=%s command=%s options=%s"
        ),
        run.pk,
        step_name,
        command_name,
        command_options,
    )

    call_command(
        command_name,
        **command_options,
    )
    completed.append(step_name)
    run.result = {**run.result, 'completed_steps': completed}
    run.save(update_fields=['result'])


def run_parser_master_pipeline(
    run_id: int,
) -> dict:
    """
    Выполняет полный мастер-пайплайн парсеров.

    Все значимые изменения состояния передаются во frontend
    через WebSocket:

        parser_started
        parser_progress
        parser_finished
        parser_failed
    """

    try:
        run = ParserMasterPipelineRun.objects.get(
            pk=run_id,
        )

    except ParserMasterPipelineRun.DoesNotExist as exc:
        raise ParserMasterPipelineError(
            (
                "ParserMasterPipelineRun "
                f"id={run_id} not found"
            )
        ) from exc

    if run.status in ('success', 'failed', 'cancelled'):
        return {'run_id': run.pk, 'status': run.status}
    started_at = run.started_at or timezone.now()

    # started_at задаём явно, чтобы это же значение
    # использовалось при вычислении длительности.
    run.status = (
        ParserMasterPipelineRun.STATUS_RUNNING
    )
    run.started_at = started_at
    run.finished_at = None
    run.current_step = "starting"
    run.error = ""
    run.result = run.result or {}

    run.save(
        update_fields=[
            "status",
            "started_at",
            "finished_at",
            "current_step",
            "error",
            "result",
        ]
    )

    _publish_run_event(
        run,
        change_type="parser_started",
    )

    completed_steps = []

    try:
        # =====================================================
        # 1. Base — полная загрузка
        # =====================================================

        _run_command(
            run,
            step_name="base_parser",
            command_name="load_base_products",
        )
        completed_steps.append(
            "base_parser"
        )

        _run_command(
            run,
            step_name="base_report",
            command_name=(
                "report_base_parser_result"
            ),
            command_options={
                "skip_bitrix": True,
            },
        )
        completed_steps.append(
            "base_report"
        )

        # =====================================================
        # 2. TT — товары из активной классификации
        # =====================================================

        _run_command(
            run,
            step_name="tt_parser",
            command_name="load_tt_products",
            command_options={
                "classified_only": True,
            },
        )
        completed_steps.append(
            "tt_parser"
        )

        _run_command(
            run,
            step_name="tt_report",
            command_name=(
                "report_tt_parser_result"
            ),
            command_options={
                "skip_bitrix": True,
            },
        )
        completed_steps.append(
            "tt_report"
        )

        # =====================================================
        # 3. PS — товары из активной классификации
        # =====================================================

        _run_command(
            run,
            step_name="ps_parser",
            command_name="load_ps_products",
            command_options={
                "classified_only": True,
            },
        )
        completed_steps.append(
            "ps_parser"
        )

        _run_command(
            run,
            step_name="ps_report",
            command_name=(
                "report_ps_parser_result"
            ),
            command_options={
                "skip_bitrix": True,
            },
        )
        completed_steps.append(
            "ps_report"
        )

        # =====================================================
        # 4. Tara — основной проход
        # =====================================================

        _run_command(
            run,
            step_name="tara_parser",
            command_name="load_tara_products",
            command_options={
                "classified_only": True,
            },
        )
        completed_steps.append(
            "tara_parser"
        )

        # Повторно обрабатываем только товары,
        # которые завершились ошибкой.
        _run_command(
            run,
            step_name="tara_failed_retry",
            command_name="load_tara_products",
            command_options={
                "classified_only": True,
                "retry_failed": True,
            },
        )
        completed_steps.append(
            "tara_failed_retry"
        )

        _run_command(
            run,
            step_name="tara_report",
            command_name=(
                "report_tara_parser_result"
            ),
            command_options={
                "skip_bitrix": True,
            },
        )
        completed_steps.append(
            "tara_report"
        )

        # =====================================================
        # Успешное завершение
        # =====================================================

        finished_at = timezone.now()
        duration = (
            finished_at
            - started_at
        )

        result = {
            "run_id": run.pk,
            "status": "success",
            "completed_steps": (
                completed_steps.copy()
            ),
            "started_at": (
                started_at.isoformat()
            ),
            "finished_at": (
                finished_at.isoformat()
            ),
            "duration_seconds": int(
                duration.total_seconds()
            ),
        }

        # Здесь сохраняем finished_at явно, чтобы дата
        # в result и дата в модели совпадали.
        run.status = (
            ParserMasterPipelineRun
            .STATUS_SUCCESS
        )
        run.current_step = "completed"
        run.finished_at = finished_at
        run.error = ""
        run.result = result

        run.save(
            update_fields=[
                "status",
                "current_step",
                "finished_at",
                "error",
                "result",
            ]
        )

        _publish_run_event(
            run,
            change_type="parser_finished",
            invalidate_health=True,
        )

        try:
            send_bitrix_message(
                (
                    "✅ Мастер-пайплайн парсеров "
                    "завершён\n"
                    f"Запуск: #{run.pk}\n"
                    "Этапов выполнено: "
                    f"{len(completed_steps)}\n"
                    "Длительность: "
                    f"{_format_duration(duration)}"
                ),
                logger_name="parsers.master",
            )

        except Exception:
            logger.exception(
                (
                    "Failed to send Bitrix success "
                    "notification for parser pipeline "
                    "run_id=%s"
                ),
                run.pk,
            )

        logger.info(
            (
                "Parser master pipeline completed "
                "run_id=%s result=%s"
            ),
            run.pk,
            result,
        )

        return result

    except TaraPending:
        from datasets.models import TaraRun
        run.refresh_from_db()
        if run.status in ('failed', 'cancelled', 'success'):
            return {'run_id': run.pk, 'status': run.status}
        child = TaraRun.objects.filter(master=run).order_by('-id').first()
        run.status = 'waiting_session' if child and child.status == 'waiting_session' else 'waiting_tara'
        run.finished_at = None
        run.error = ''
        run.save(update_fields=['status', 'finished_at', 'error'])
        _publish_run_event(run, change_type='parser_progress')
        return {'run_id': run.pk, 'status': run.status}
    except Exception as exc:
        # =====================================================
        # Завершение с ошибкой
        # =====================================================

        finished_at = timezone.now()
        duration = (
            finished_at
            - started_at
        )

        failed_step = (
            run.current_step
            or "unknown"
        )

        error_text = traceback.format_exc()

        result = {
            "run_id": run.pk,
            "status": "failed",
            "failed_step": failed_step,
            "completed_steps": (
                completed_steps.copy()
            ),
            "started_at": (
                started_at.isoformat()
            ),
            "finished_at": (
                finished_at.isoformat()
            ),
            "error": str(exc),
            "duration_seconds": int(
                duration.total_seconds()
            ),
        }

        run.status = (
            ParserMasterPipelineRun
            .STATUS_FAILED
        )
        run.current_step = failed_step
        run.finished_at = finished_at
        run.error = error_text
        run.result = result

        run.save(
            update_fields=[
                "status",
                "current_step",
                "finished_at",
                "error",
                "result",
            ]
        )

        _publish_run_event(
            run,
            change_type="parser_failed",
            invalidate_health=True,
        )

        try:
            send_bitrix_message(
                (
                    "❌ Мастер-пайплайн парсеров "
                    "завершился с ошибкой\n"
                    f"Запуск: #{run.pk}\n"
                    f"Этап: {failed_step}\n"
                    f"Ошибка: {str(exc)[:1000]}\n"
                    "Длительность: "
                    f"{_format_duration(duration)}"
                ),
                logger_name="parsers.master",
            )

        except Exception:
            logger.exception(
                (
                    "Failed to send Bitrix error "
                    "notification for parser pipeline "
                    "run_id=%s"
                ),
                run.pk,
            )

        logger.exception(
            (
                "Parser master pipeline failed "
                "run_id=%s step=%s"
            ),
            run.pk,
            failed_step,
        )

        raise ParserMasterPipelineError(
            (
                "Parser pipeline "
                f"run {run.pk} failed "
                f"at step {failed_step}"
            )
        ) from exc


def _format_duration(
    duration: timedelta,
) -> str:
    total_seconds = int(
        duration.total_seconds()
    )

    hours, remainder = divmod(
        total_seconds,
        3600,
    )

    minutes, seconds = divmod(
        remainder,
        60,
    )

    if hours:
        return (
            f"{hours} ч "
            f"{minutes} мин "
            f"{seconds} сек"
        )

    if minutes:
        return (
            f"{minutes} мин "
            f"{seconds} сек"
        )

    return f"{seconds} сек"
