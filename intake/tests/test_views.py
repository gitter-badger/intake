from unittest import skipIf
from unittest.mock import patch, Mock
import inspect
from django.test import TestCase
from user_accounts.tests.test_auth_integration import AuthIntegrationTestCase
from django.core.urlresolvers import reverse
from django.utils import html as html_utils

from intake.tests import mock
from intake import models

from project.jinja2 import url_with_ids

class TestViews(AuthIntegrationTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.have_four_submissions()
        cls.have_a_fillable_pdf()

    @classmethod
    def have_four_submissions(cls):
        cls.submissions = mock.FormSubmissionFactory.create_batch(4)

    @classmethod
    def have_a_fillable_pdf(cls):
        cls.fillable = mock.fillable_pdf()

    def assert_called_once_with_types(self, mock_obj, *arg_types, **kwarg_types):
        self.assertEqual(mock_obj.call_count, 1)
        arguments, keyword_arguments = mock_obj.call_args
        argument_classes = [getattr(
                arg, '__qualname__', arg.__class__.__qualname__
                ) for arg in arguments] 
        self.assertListEqual(argument_classes, list(arg_types))
        keyword_argument_classes = {}    
        for keyword, arg in keyword_arguments.items():
            keyword_argument_classes[keyword] = getattr(
                arg, '__qualname__', arg.__class__.__qualname__
                )
        self.assertDictEqual(keyword_argument_classes, dict(kwarg_types))

    def test_home_view(self):
        response = self.client.get(reverse('intake-home'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Clear My Record', response.content.decode('utf-8'))

    def test_apply_view(self):
        response = self.client.get(reverse('intake-apply'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Apply to Clear My Record',
            response.content.decode('utf-8'))

    def test_stats_view(self):
        total = models.FormSubmission.objects.count()
        response = self.client.get(reverse('intake-stats'))
        self.assertContains(response, total)


    @patch('intake.views.notifications.slack_new_submission.send')
    def test_anonymous_user_can_fill_out_app_and_reach_thanks_page(self, slack):
        self.be_anonymous()
        result = self.client.fill_form(
            reverse('intake-apply'),
            first_name="Anonymous"
            )
        self.assertRedirects(result, 
            reverse('intake-thanks'))
        thanks_page = self.client.get(result.url)
        self.assertContains(thanks_page, "Thank")
        self.assert_called_once_with_types(
            slack,
            submission='FormSubmission',
            request='WSGIRequest',
            submission_count='int')

    @patch('intake.models.notifications.slack_submissions_viewed.send')
    def test_authenticated_user_can_see_filled_pdf(self, slack):
        self.be_regular_user()
        pdf = self.client.get(reverse('intake-filled_pdf',
            kwargs=dict(
                submission_id=self.submissions[0].id
                )))
        self.assertTrue(len(pdf.content) > 69000)
        self.assertEqual(type(pdf.content), bytes)
        self.assert_called_once_with_types(
            slack,
            submissions='list',
            user='User')

    def test_authenticated_user_can_see_list_of_submitted_apps(self):
        self.be_regular_user()
        index = self.client.get(reverse('intake-app_index'))
        for submission in self.submissions:
            self.assertContains(index,
                html_utils.escape(submission.answers['last_name']))

    def test_anonymous_user_cannot_see_filled_pdfs(self):
        self.be_anonymous()
        pdf = self.client.get(reverse('intake-filled_pdf',
            kwargs=dict(
                submission_id=self.submissions[0].id
                )))
        self.assertRedirects(pdf, 
            "{}?next={}".format(
            reverse('user_accounts-login'),
            reverse('intake-filled_pdf', kwargs={
                'submission_id': self.submissions[0].id})))

    def test_anonymous_user_cannot_see_submitted_apps(self):
        self.be_anonymous()
        index = self.client.get(reverse('intake-app_index'))
        self.assertRedirects(index,
            "{}?next={}".format(
            reverse('user_accounts-login'),
            reverse('intake-app_index')
                )
            )

    def test_authenticated_user_can_see_pdf_bundle(self):
        self.be_regular_user()
        ids = [s.id for s in self.submissions]
        url = url_with_ids('intake-pdf_bundle', ids)
        bundle = self.client.get(url)
        self.assertEqual(bundle.status_code, 200)

    @patch('intake.models.notifications.slack_submissions_viewed.send')
    def test_authenticated_user_can_see_app_bundle(self, slack):
        self.be_regular_user()
        ids = [s.id for s in self.submissions]
        url = url_with_ids('intake-app_bundle', ids)
        bundle = self.client.get(url)
        self.assertEqual(bundle.status_code, 200)
        self.assert_called_once_with_types(
            slack,
            submissions='list',
            user='User')

    @patch('intake.views.notifications.slack_submissions_deleted.send')
    def test_authenticated_user_can_delete_apps(self, slack):
        self.be_regular_user()
        submission = self.submissions[-1]
        pdf_link = reverse('intake-filled_pdf',
            kwargs={'submission_id':submission.id})
        url = reverse('intake-delete_page',
            kwargs={'submission_id':submission.id})
        delete_page = self.client.get(url)
        self.assertEqual(delete_page.status_code, 200)
        after_delete = self.client.fill_form(url)
        self.assertRedirects(after_delete, reverse('intake-app_index'))
        index = self.client.get(after_delete.url)
        self.assertNotContains(index, pdf_link)
        self.assert_called_once_with_types(
            slack,
            submissions='list',
            user='User')

    @patch('intake.views.MarkProcessed.notification_function')
    def test_authenticated_user_can_mark_apps_as_processed(self, slack):
        self.be_regular_user()
        submissions = self.submissions[:2]
        ids = [s.id for s in submissions]
        mark_link = url_with_ids('intake-mark_processed', ids)
        marked = self.client.get(mark_link)
        self.assert_called_once_with_types(
            slack,
            submissions='list',
            user='User')
        self.assertRedirects(marked, reverse('intake-app_index'))
        args, kwargs = slack.call_args
        for sub in kwargs['submissions']:
            self.assertTrue(sub.processed_by_agency)
            self.assertIn(sub.id, ids)

    def test_old_urls_return_permanent_redirect(self):
        # redirecting the auth views does not seem necessary
        redirects = {
            '/sanfrancisco/': reverse('intake-apply'),
            '/sanfrancisco/applications/': reverse('intake-app_index'),
        }

        # redirecting the action views (delete, add) does not seem necessary
        id_redirects = {'/sanfrancisco/{}/': 'intake-filled_pdf'}
        multi_id_redirects = {
            '/sanfrancisco/bundle/{}': 'intake-app_bundle',
            '/sanfrancisco/pdfs/{}': 'intake-pdf_bundle'}
        
        # make some old apps with ids
        old_uuids = [
            '0efd75e8721c4308a8f3247a8c63305d',
            'b873c4ceb1cd4939b1d4c890997ef29c',
            '6cb3887be35543c4b13f27bf83219f4f']
        key_params = '?keys=' + '|'.join(old_uuids)
        ported_models = []
        for uuid in old_uuids:
            instance = mock.FormSubmissionFactory.create(
                old_uuid=uuid)
            ported_models.append(instance)


        for old, new in redirects.items():
            response = self.client.get(old)
            self.assertRedirects(response, new,
                status_code=301, fetch_redirect_response=False)

        for old_template, new_view in id_redirects.items():
            old = old_template.format(old_uuids[2])
            response = self.client.get(old)
            new = reverse(new_view, kwargs=dict(submission_id=ported_models[2].id))
            self.assertRedirects(response, new,
                status_code=301, fetch_redirect_response=False)

        for old_template, new_view in multi_id_redirects.items():
            old = old_template.format(key_params)
            response = self.client.get(old)
            new = url_with_ids(new_view, [s.id for s in ported_models])
            self.assertRedirects(response, new,
                status_code=301, fetch_redirect_response=False)


    @skipIf(True, "not yet implemented")
    def test_old_urls_permanently_redirect_to_new_urls(self):
        pass

    @skipIf(True, "not yet implemented")
    def test_authenticated_user_cannot_see_apps_to_other_org(self):
        pass

