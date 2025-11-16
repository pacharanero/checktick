"""
Management command to seed NHS Data Dictionary standard datasets.

Reads dataset definitions from docs/nhs-data-dictionary-datasets.md and creates
DataSet records in the database. The scrape command will then populate the options.

Usage:
    python manage.py seed_nhs_datasets
    python manage.py seed_nhs_datasets --clear  # Clear existing NHS DD datasets first
"""

from pathlib import Path
import re

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from checktick_app.surveys.models import DataSet


class Command(BaseCommand):
    help = "Seed NHS Data Dictionary standard datasets from markdown file"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing NHS DD datasets before seeding",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            deleted_count = DataSet.objects.filter(category="nhs_dd").delete()[0]
            self.stdout.write(
                self.style.WARNING(f"Deleted {deleted_count} existing NHS DD datasets")
            )

        # Read datasets from markdown file
        # Navigate from: checktick_app/surveys/management/commands/seed_nhs_datasets.py
        # To: docs/nhs-data-dictionary-datasets.md
        base_dir = Path(__file__).resolve().parent.parent.parent.parent.parent
        markdown_file = base_dir / "docs" / "nhs-data-dictionary-datasets.md"

        if not markdown_file.exists():
            self.stdout.write(
                self.style.ERROR(
                    f"Markdown file not found: {markdown_file}\n"
                    "Expected location: docs/nhs-data-dictionary-datasets.md"
                )
            )
            return

        self.stdout.write(f"Reading datasets from: {markdown_file}")

        datasets = self._parse_markdown_table(markdown_file)

        if not datasets:
            self.stdout.write(self.style.WARNING("No datasets found in markdown file"))
            return

        self.stdout.write(f"Found {len(datasets)} datasets in markdown file\n")

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for dataset_data in datasets:
            try:
                # Check if dataset already exists
                existing = DataSet.objects.filter(key=dataset_data["key"]).first()

                if existing:
                    # Update existing dataset metadata (but preserve options if already scraped)
                    if existing.options and existing.options != {
                        "PENDING": "Awaiting scrape"
                    }:
                        # Already has scraped data, don't overwrite
                        self.stdout.write(
                            self.style.WARNING(
                                f"⊝ Skipped '{dataset_data['name']}' - already exists with scraped data"
                            )
                        )
                        skipped_count += 1
                        continue

                    # Update metadata
                    existing.name = dataset_data["name"]
                    existing.description = dataset_data["description"]
                    existing.reference_url = dataset_data["reference_url"]
                    existing.tags = dataset_data["tags"]
                    existing.save()

                    self.stdout.write(
                        self.style.SUCCESS(f"↻ Updated '{dataset_data['name']}'")
                    )
                    updated_count += 1
                else:
                    # Create new dataset
                    DataSet.objects.create(**dataset_data)
                    self.stdout.write(
                        self.style.SUCCESS(f"✓ Created '{dataset_data['name']}'")
                    )
                    created_count += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"✗ Error processing '{dataset_data.get('name', 'unknown')}': {e}"
                    )
                )

        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS(f"✓ Created: {created_count}"))
        self.stdout.write(self.style.SUCCESS(f"↻ Updated: {updated_count}"))
        if skipped_count:
            self.stdout.write(self.style.WARNING(f"⊝ Skipped: {skipped_count}"))
        self.stdout.write("=" * 60)
        self.stdout.write(
            f"\nTotal NHS DD datasets: {DataSet.objects.filter(category='nhs_dd').count()}"
        )

    def _parse_markdown_table(self, file_path: Path) -> list[dict]:
        """
        Parse the NHS DD datasets markdown table.

        Expected format:
        | Dataset Name | NHS DD URL | Categories | Date Added | Last Scraped | NHS DD Published |
        |--------------|------------|------------|------------|--------------|------------------|
        | Name | [Link](url) | tag1, tag2 | date | status | - |

        Returns:
            List of dataset dictionaries ready for DataSet.objects.create()
        """
        content = file_path.read_text(encoding="utf-8")
        datasets = []

        # Find the table section
        lines = content.split("\n")
        in_table = False
        header_passed = False

        for line in lines:
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            # Detect table start
            if line.startswith("| Dataset Name"):
                in_table = True
                continue

            # Skip separator line
            if in_table and not header_passed and line.startswith("|---"):
                header_passed = True
                continue

            # Parse data rows
            if in_table and header_passed and line.startswith("|"):
                # Stop at end of table (next section starts)
                if line.startswith("##"):
                    break

                # Split by pipes and clean
                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 7:  # Need at least 7 parts (including empty first/last)
                    continue

                # Extract fields
                name = parts[1].strip()
                url_match = re.search(r"\[Link\]\((https?://[^\)]+)\)", parts[2])
                categories = parts[3].strip()

                if not name or not url_match:
                    continue

                url = url_match.group(1)

                # Parse tags
                tags = [tag.strip() for tag in categories.split(",") if tag.strip()]
                tags.append("NHS")  # Add NHS tag to all

                # Generate key from name
                key = slugify(name.lower().replace(" ", "_"))

                # Create dataset dict
                dataset = {
                    "key": key,
                    "name": name,
                    "description": f"NHS Data Dictionary - {name}",
                    "category": "nhs_dd",
                    "source_type": "scrape",
                    "reference_url": url,
                    "is_custom": False,
                    "is_global": True,
                    "tags": tags,
                    "options": {"PENDING": "Awaiting scrape"},
                }

                datasets.append(dataset)

        return datasets
