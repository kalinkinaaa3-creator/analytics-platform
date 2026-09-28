from django.core.management.base import BaseCommand, CommandError

from analytics.services.bitrix_notify import send_bitrix_message


class Command(BaseCommand):
    help = "Send a monthly reminder to sign in to 1C Document Management via Bitrix"

    def handle(self, *args, **options):
        message = (
            "[b]Напоминание: 1С Документооборот[/b]\n"
            "Зайти в 1С Документооборот, "
            "чтобы доступ не заблокировали из-за длительного отсутствия входа."
        )
        if not send_bitrix_message(message):
            raise CommandError(
                "Напоминание не отправлено. Проверьте настройки уведомлений "
                "Битрикс и журнал analytics."
            )
        self.stdout.write(self.style.SUCCESS("Напоминание отправлено в Битрикс."))
