from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate
from organizations.models import Organization
from .iprice_api import SourcesStatusView, ParserStartView, CalculationStartView


@override_settings(PARSER_SHARED_QUEUE_ENABLED=True)
class UIAPITests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(code='select-market', name='SM', postgres_schema='select_market')
        self.user = get_user_model().objects.create_user(username='iprice-viewer')

    def request(self, view, method, *, view_allowed=True, edit_allowed=False, data=None, **kwargs):
        request = getattr(APIRequestFactory(), method)('/', data or {}, format='json')
        request.organization = self.org
        force_authenticate(request, self.user)
        with patch('select_market.iprice_api.Dashboard.objects') as dashboards, patch('select_market.iprice_api.user_can_view_dashboard', return_value=view_allowed), patch('select_market.iprice_api.user_can_edit_dashboard', return_value=edit_allowed):
            dashboards.filter.return_value.first.return_value = object()
            return view.as_view()(request, **kwargs)

    def test_export_permissions_and_unfinished_versions(self):
        from django.utils import timezone
        from .iprice_api import SnapshotExportView
        from .iprice_domain_models import IPriceSnapshot
        snapshot = IPriceSnapshot.objects.create(calculation_date=timezone.localdate(),
            version_number=1, revision_for_date=1, status='building')
        self.assertEqual(self.request(SnapshotExportView, 'get', snapshot_id=snapshot.pk,
            view_allowed=False).status_code, 403)
        self.assertEqual(self.request(SnapshotExportView, 'get', snapshot_id=snapshot.pk).status_code, 400)
        self.assertEqual(self.request(SnapshotExportView, 'get', snapshot_id=snapshot.pk + 1).status_code, 404)
        snapshot.status = 'success'
        snapshot.save(update_fields=['status'])
        from io import BytesIO
        with patch('datasets.services.iprice_snapshot_export.export_iprice_snapshot_to_excel', return_value=BytesIO(b'xlsx')):
            response = self.request(SnapshotExportView, 'get', snapshot_id=snapshot.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'xlsx')
        self.assertIn('private', response['Cache-Control'])

    def test_viewer_can_read_but_not_start(self):
        result = self.request(SourcesStatusView, 'get')
        self.assertEqual(result.status_code, 200)
        self.assertFalse(result.data['can_edit'])
        with patch('datasets.services.parsers.tara_jobs.kick') as kick:
            result = self.request(ParserStartView, 'post')
        self.assertEqual(result.status_code, 403)
        kick.assert_not_called()

    def test_activation_requires_edit_access(self):
        from .iprice_api import SnapshotActivateView
        with patch('datasets.services.iprice_snapshot_builder.activate_iprice_snapshot') as activate:
            response = self.request(SnapshotActivateView, 'post', snapshot_id=1)
        self.assertEqual(response.status_code, 403)
        activate.assert_not_called()
        self.assertEqual(self.request(SnapshotActivateView, 'delete', snapshot_id=1).status_code, 403)
        self.assertEqual(self.request(SnapshotActivateView, 'post', snapshot_id=1,
                                     edit_allowed=True).status_code, 404)

    def test_editor_repeated_start_reuses_one_master(self):
        with patch('datasets.services.parsers.tara_jobs.kick'):
            first = self.request(ParserStartView, 'post', edit_allowed=True)
            second = self.request(ParserStartView, 'post', edit_allowed=True)
        self.assertEqual(first.status_code, 202)
        self.assertEqual(first.data['id'], second.data['id'])

    def test_other_organization_is_denied(self):
        self.org.code = 'iplast'
        self.assertEqual(self.request(SourcesStatusView, 'get', edit_allowed=True).status_code, 403)

    @override_settings(PARSER_SHARED_QUEUE_ENABLED=False)
    def test_disabled_queue_rejects_start(self):
        with patch('datasets.services.parsers.tara_jobs.kick') as kick:
            result = self.request(ParserStartView, 'post', edit_allowed=True)
        self.assertEqual(result.status_code, 400)
        kick.assert_not_called()

    def test_no_dashboard_access_denies_status(self):
        self.assertEqual(self.request(SourcesStatusView, 'get', view_allowed=False).status_code, 403)

    def test_calculation_viewer_denied_editor_launches_after_commit(self):
        from django.utils import timezone
        data = {'calculation_date': timezone.localdate().isoformat()}
        self.assertEqual(self.request(CalculationStartView, 'post', data=data).status_code, 403)
        with patch('datasets.services.iprice_snapshot_launcher.launch_iprice_snapshot') as launch:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.request(CalculationStartView, 'post', edit_allowed=True, data=data)
                launch.assert_not_called()
            self.assertEqual(response.status_code, 202)
            launch.assert_called_once()
        self.assertEqual(self.request(CalculationStartView, 'post', edit_allowed=True, data=data).status_code, 400)

    def test_calculation_launch_failure_is_saved(self):
        from django.utils import timezone
        from .iprice_domain_models import IPriceSnapshot
        with patch('datasets.services.iprice_snapshot_launcher.launch_iprice_snapshot', side_effect=OSError('process failed')), self.captureOnCommitCallbacks(execute=True):
            response = self.request(CalculationStartView, 'post', edit_allowed=True, data={'calculation_date': timezone.localdate().isoformat()})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(IPriceSnapshot.objects.get().status, 'failed')

    def test_calculation_date_required_and_future_rejected(self):
        from datetime import timedelta
        from django.utils import timezone
        for day in (None, 'bad-date', (timezone.localdate()+timedelta(days=1)).isoformat()):
            with self.subTest(day=day):
                self.assertEqual(self.request(CalculationStartView, 'post', edit_allowed=True, data={'calculation_date': day}).status_code, 400)
