"""
Tests for sync_external_datasets management command.

Tests successful sync, API errors, dataset creation/updates, and idempotency.
"""

from io import StringIO
from unittest.mock import patch, Mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from checktick_app.surveys.models import DataSet
from checktick_app.surveys.external_datasets import DatasetFetchError


class SyncExternalDatasetsCommandTests(TestCase):
    """Test the sync_external_datasets management command."""

    def setUp(self):
        """Create test data."""
        # Create a test dataset that exists but hasn't been synced
        self.existing_dataset = DataSet.objects.create(
            key="hospitals_england_wales",
            name="Hospitals (England & Wales)",
            description="Test dataset",
            category="rcpch",
            source_type="api",
            is_custom=False,
            is_global=True,
            options=[],  # Empty, needs sync
            sync_frequency_hours=24,
            last_synced_at=None,
        )

    def test_command_runs_successfully(self):
        """Test that the command runs without errors when API succeeds."""
        with patch(
            "checktick_app.surveys.management.commands.sync_external_datasets.requests.get"
        ) as mock_get:
            # Mock successful API response
            mock_response = Mock()
            mock_response.json.return_value = [
                {"name": "Hospital A", "ods_code": "ABC123"},
                {"name": "Hospital B", "ods_code": "DEF456"},
            ]
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            out = StringIO()
            call_command("sync_external_datasets", stdout=out)

            output = out.getvalue()
            self.assertIn("SYNC COMPLETE", output)
            self.assertIn("Synced: 7", output)  # All 7 available datasets

    def test_dry_run_mode_makes_no_changes(self):
        """Test that dry-run mode doesn't actually sync data."""
        initial_options = self.existing_dataset.options.copy()

        with patch(
            "checktick_app.surveys.management.commands.sync_external_datasets.requests.get"
        ) as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = [
                {"name": "Hospital A", "ods_code": "ABC123"}
            ]
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            out = StringIO()
            call_command("sync_external_datasets", "--dry-run", stdout=out)

            output = out.getvalue()
            self.assertIn("DRY RUN", output)
            self.assertIn("Would sync", output)

            # Verify no changes were made
            self.existing_dataset.refresh_from_db()
            self.assertEqual(self.existing_dataset.options, initial_options)
            self.assertIsNone(self.existing_dataset.last_synced_at)

    def test_creates_new_dataset_if_not_exists(self):
        """Test that new datasets are created if they don't exist."""
        # Delete the existing dataset
        DataSet.objects.all().delete()

        self.assertEqual(DataSet.objects.count(), 0)

        with patch(
            "checktick_app.surveys.management.commands.sync_external_datasets.requests.get"
        ) as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = [
                {"name": "Hospital A", "ods_code": "ABC123"}
            ]
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            call_command("sync_external_datasets", stdout=StringIO())

            # Should have created 7 datasets (all in AVAILABLE_DATASETS)
            self.assertEqual(DataSet.objects.count(), 7)

            # Check one was created correctly
            dataset = DataSet.objects.get(key="hospitals_england_wales")
            self.assertEqual(dataset.category, "rcpch")
            self.assertEqual(dataset.source_type, "api")
            self.assertTrue(dataset.is_global)
            self.assertFalse(dataset.is_custom)
            self.assertIsNotNone(dataset.last_synced_at)
            self.assertEqual(len(dataset.options), 1)
            self.assertIn("Hospital A (ABC123)", dataset.options)

    def test_updates_existing_dataset(self):
        """Test that existing datasets are updated with new data."""
        # Set initial data
        self.existing_dataset.options = ["Old Hospital"]
        self.existing_dataset.version = 1
        self.existing_dataset.save()

        with patch(
            "checktick_app.surveys.management.commands.sync_external_datasets.requests.get"
        ) as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = [
                {"name": "New Hospital A", "ods_code": "ABC123"},
                {"name": "New Hospital B", "ods_code": "DEF456"},
            ]
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            call_command(
                "sync_external_datasets",
                "--dataset",
                "hospitals_england_wales",
                stdout=StringIO(),
            )

            self.existing_dataset.refresh_from_db()
            self.assertEqual(len(self.existing_dataset.options), 2)
            self.assertIn("New Hospital A (ABC123)", self.existing_dataset.options)
            self.assertIn("New Hospital B (DEF456)", self.existing_dataset.options)
            self.assertEqual(self.existing_dataset.version, 2)  # Version incremented
            self.assertIsNotNone(self.existing_dataset.last_synced_at)

    def test_updates_last_synced_timestamp(self):
        """Test that last_synced_at is updated on successful sync."""
        self.assertIsNone(self.existing_dataset.last_synced_at)

        with patch(
            "checktick_app.surveys.management.commands.sync_external_datasets.requests.get"
        ) as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = [
                {"name": "Hospital A", "ods_code": "ABC123"}
            ]
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            before = timezone.now()
            call_command(
                "sync_external_datasets",
                "--dataset",
                "hospitals_england_wales",
                stdout=StringIO(),
            )
            after = timezone.now()

            self.existing_dataset.refresh_from_db()
            self.assertIsNotNone(self.existing_dataset.last_synced_at)
            self.assertGreaterEqual(self.existing_dataset.last_synced_at, before)
            self.assertLessEqual(self.existing_dataset.last_synced_at, after)

    def test_skips_recently_synced_datasets(self):
        """Test that datasets recently synced are skipped unless --force."""
        # Mark as recently synced
        self.existing_dataset.last_synced_at = timezone.now()
        self.existing_dataset.save()

        out = StringIO()
        call_command("sync_external_datasets", stdout=out)

        output = out.getvalue()
        self.assertIn("Skipping", output)
        self.assertIn("not due for sync", output)
        self.assertIn("Skipped: 7", output)

    def test_force_flag_bypasses_sync_frequency(self):
        """Test that --force flag syncs even recently synced datasets."""
        # Mark as recently synced
        self.existing_dataset.last_synced_at = timezone.now()
        self.existing_dataset.options = ["Old data"]
        self.existing_dataset.save()

        with patch(
            "checktick_app.surveys.management.commands.sync_external_datasets.requests.get"
        ) as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = [
                {"name": "New Hospital", "ods_code": "NEW123"}
            ]
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            out = StringIO()
            call_command(
                "sync_external_datasets",
                "--dataset",
                "hospitals_england_wales",
                "--force",
                stdout=out,
            )

            output = out.getvalue()
            self.assertIn("Syncing", output)
            self.assertNotIn("Skipping", output)

            self.existing_dataset.refresh_from_db()
            self.assertIn("New Hospital (NEW123)", self.existing_dataset.options)

    def test_single_dataset_flag(self):
        """Test syncing only a specific dataset."""
        with patch(
            "checktick_app.surveys.management.commands.sync_external_datasets.requests.get"
        ) as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = [
                {"name": "Hospital A", "ods_code": "ABC123"}
            ]
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            out = StringIO()
            call_command(
                "sync_external_datasets",
                "--dataset",
                "hospitals_england_wales",
                stdout=out,
            )

            output = out.getvalue()
            self.assertIn("Found 1 external datasets", output)
            self.assertIn("Synced: 1", output)

            # Only one API call should be made
            self.assertEqual(mock_get.call_count, 1)

    def test_invalid_dataset_key_raises_error(self):
        """Test that invalid dataset key raises CommandError."""
        with self.assertRaises(CommandError) as context:
            call_command(
                "sync_external_datasets",
                "--dataset",
                "invalid_dataset_key",
                stdout=StringIO(),
            )

        self.assertIn("Unknown dataset key", str(context.exception))

    def test_api_error_is_handled(self):
        """Test that API errors are caught and reported."""
        with patch(
            "checktick_app.surveys.management.commands.sync_external_datasets.requests.get"
        ) as mock_get:
            # Simulate API error
            mock_get.side_effect = Exception("API connection failed")

            out = StringIO()
            err = StringIO()

            with self.assertRaises(CommandError) as context:
                call_command(
                    "sync_external_datasets",
                    "--dataset",
                    "hospitals_england_wales",
                    stdout=out,
                    stderr=err,
                )

            error_output = err.getvalue()
            self.assertIn("Failed to sync", error_output)
            self.assertIn("Errors: 1", str(context.exception))

    def test_malformed_api_response_is_handled(self):
        """Test that malformed API responses are caught."""
        with patch(
            "checktick_app.surveys.management.commands.sync_external_datasets.requests.get"
        ) as mock_get:
            # Return invalid data (not a list)
            mock_response = Mock()
            mock_response.json.return_value = {"error": "Not a list"}
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            err = StringIO()

            with self.assertRaises(CommandError):
                call_command(
                    "sync_external_datasets",
                    "--dataset",
                    "hospitals_england_wales",
                    stdout=StringIO(),
                    stderr=err,
                )

            error_output = err.getvalue()
            self.assertIn("Failed to sync", error_output)

    def test_command_is_idempotent(self):
        """Test that running command multiple times is safe."""
        with patch(
            "checktick_app.surveys.management.commands.sync_external_datasets.requests.get"
        ) as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = [
                {"name": "Hospital A", "ods_code": "ABC123"}
            ]
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            # Run twice
            call_command(
                "sync_external_datasets",
                "--dataset",
                "hospitals_england_wales",
                "--force",
                stdout=StringIO(),
            )
            call_command(
                "sync_external_datasets",
                "--dataset",
                "hospitals_england_wales",
                "--force",
                stdout=StringIO(),
            )

            self.existing_dataset.refresh_from_db()

            # Should have same data (not duplicated)
            self.assertEqual(len(self.existing_dataset.options), 1)
            self.assertIn("Hospital A (ABC123)", self.existing_dataset.options)

            # Version should be 2 (incremented each time)
            self.assertEqual(self.existing_dataset.version, 2)

    def test_transforms_nhs_trusts_correctly(self):
        """Test that NHS trusts are transformed with correct format."""
        with patch(
            "checktick_app.surveys.management.commands.sync_external_datasets.requests.get"
        ) as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = [
                {"name": "GREAT ORMOND STREET HOSPITAL", "ods_code": "RP401"}
            ]
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            # Create NHS trusts dataset
            dataset = DataSet.objects.create(
                key="nhs_trusts",
                name="NHS Trusts",
                category="rcpch",
                source_type="api",
                is_global=True,
                is_custom=False,
                sync_frequency_hours=24,
            )

            call_command(
                "sync_external_datasets",
                "--dataset",
                "nhs_trusts",
                stdout=StringIO(),
            )

            dataset.refresh_from_db()
            self.assertEqual(len(dataset.options), 1)
            self.assertIn("GREAT ORMOND STREET HOSPITAL (RP401)", dataset.options)

    def test_transforms_welsh_lhbs_with_hierarchy(self):
        """Test that Welsh LHBs include nested organisations."""
        with patch(
            "checktick_app.surveys.management.commands.sync_external_datasets.requests.get"
        ) as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = [
                {
                    "name": "Swansea Bay University Health Board",
                    "ods_code": "7A3",
                    "organisations": [
                        {"name": "Morriston Hospital", "ods_code": "RW600"},
                        {"name": "Singleton Hospital", "ods_code": "RW601"},
                    ],
                }
            ]
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            dataset = DataSet.objects.create(
                key="welsh_lhbs",
                name="Welsh Local Health Boards",
                category="rcpch",
                source_type="api",
                is_global=True,
                is_custom=False,
                sync_frequency_hours=24,
            )

            call_command(
                "sync_external_datasets", "--dataset", "welsh_lhbs", stdout=StringIO()
            )

            dataset.refresh_from_db()
            # Should have LHB + 2 nested orgs
            self.assertEqual(len(dataset.options), 3)
            self.assertIn("Swansea Bay University Health Board (7A3)", dataset.options)
            self.assertIn("  Morriston Hospital (RW600)", dataset.options)
            self.assertIn("  Singleton Hospital (RW601)", dataset.options)
