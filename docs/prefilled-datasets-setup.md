# Prefilled Datasets Feature - Setup Guide

## Overview

The prefilled datasets feature allows users to load dropdown options from multiple sources when creating survey questions:

1. **NHS Data Dictionary** - Standardized medical codes stored in the database
2. **RCPCH NHS Organisations API** - External datasets synced periodically to database
3. **Custom Lists** - User-created and organization-specific datasets

All datasets are stored in the `DataSet` model for consistency, fast access, and offline capability.

## Database Storage

### DataSet Model

All datasets are stored in `surveys_dataset` table with these key fields:

- `key` - Unique identifier (e.g., `main_specialty_code`, `hospitals_england_wales`)
- `name` - Display name shown in UI
- `category` - `nhs_dd`, `external_api`, `rcpch`, or `user_created`
- `source_type` - `manual`, `api`, or `import`
- `is_custom` - Whether dataset is user-created/modified
- `is_global` - Whether available to all organizations
- `parent` - Reference to NHS DD original if customized
- `organization` - Organization that owns this dataset (if not global)
- `options` - JSON array of option strings
- `last_synced_at` - When API dataset was last updated (for external datasets)
- `sync_frequency_hours` - How often to sync (default 24 hours)
- `version` - Incremented on each sync for audit trail

## Initial Setup

### 1. Seed NHS DD Datasets

Pre-populate NHS Data Dictionary standards:

```bash
docker compose exec web python manage.py seed_nhs_datasets

# Or clear existing and re-seed
docker compose exec web python manage.py seed_nhs_datasets --clear
```

This creates read-only NHS DD datasets:
- Main Specialty Code (75 options)
- Treatment Function Code (73 options)
- Ethnic Category (17 options)

### 2. Seed External Dataset Records

Create database records for external API datasets:

```bash
docker compose exec web python manage.py seed_external_datasets
```

This creates 7 dataset records with metadata but **empty options**:
- Hospitals (England & Wales)
- NHS Trusts
- Welsh Local Health Boards
- London Boroughs
- NHS England Regions
- Paediatric Diabetes Units
- Integrated Care Boards (ICBs)

### 3. Populate External Datasets

Fetch data from RCPCH API and populate the datasets:

```bash
docker compose exec web python manage.py sync_external_datasets
```

This fetches data from the RCPCH NHS Organisations API and stores it in the database. First sync takes 2-3 minutes as it fetches all 7 datasets.

**Command Options:**
- `--dataset KEY` - Sync only a specific dataset (e.g., `--dataset hospitals_england_wales`)
- `--force` - Bypass sync_frequency_hours check and sync anyway
- `--dry-run` - Preview changes without saving to database

## External API Integration

### API Details

- **Base URL**: `https://api.rcpch.ac.uk/nhs-organisations/v1`
- **Authentication**: No API key required (public API)
- **Sync Mechanism**: Periodic sync via management command (daily cron recommended)

### Endpoints

- `/organisations/limited` - Hospitals (England & Wales combined)
- `/trusts` - NHS Trusts
- `/local_health_boards` - Welsh Local Health Boards
- `/london_boroughs` - London Boroughs
- `/nhs_england_regions` - NHS England Regions
- `/paediatric_diabetes_units` - Paediatric Diabetes Units (PDUs)
- `/integrated_care_boards` - Integrated Care Boards (ICBs)

### API Response Formats

#### Hospitals (`/organisations/limited`)
```json
[
  {
    "ods_code": "RGT01",
    "name": "ADDENBROOKE'S HOSPITAL"
  },
  {
    "ods_code": "RCF22",
    "name": "AIREDALE GENERAL HOSPITAL"
  }
]
```

#### NHS Trusts (`/trusts`)
```json
[
  {
    "ods_code": "RCF",
    "name": "AIREDALE NHS FOUNDATION TRUST",
    "address_line_1": "AIREDALE GENERAL HOSPITAL",
    "address_line_2": "SKIPTON ROAD",
    "town": "KEIGHLEY",
    "postcode": "BD20 6TD",
    "country": "ENGLAND",
    "telephone": null,
    "website": null,
    "active": true,
    "published_at": null
  }
]
```

#### Welsh Local Health Boards (`/local_health_boards`)
```json
[
  {
    "ods_code": "7A3",
    "boundary_identifier": "W11000031",
    "name": "Swansea Bay University Health Board",
    "organisations": [
      {
        "ods_code": "7A3LW",
        "name": "CHILD DEVELOPMENT UNIT"
      },
      {
        "ods_code": "7A3C7",
        "name": "MORRISTON HOSPITAL"
      }
    ]
  }
]
```

## Configuration

### Environment Variables

The following environment variables should be set in your `.env` file:

```bash
# External Dataset API Configuration
EXTERNAL_DATASET_API_URL=https://api.rcpch.ac.uk/nhs-organisations/v1
EXTERNAL_DATASET_API_KEY=  # Leave empty - no key required
```

These are already configured in `.env.example` with the correct defaults.

### Scheduled Sync (Recommended)

To keep datasets up-to-date, schedule the sync command to run daily via cron:

```bash
# Run at 4 AM daily
0 4 * * * cd /app && python manage.py sync_external_datasets
```

See [Self-Hosting: Scheduled Tasks](self-hosting-scheduled-tasks.md) for platform-specific instructions (Northflank, Docker Compose, Kubernetes).

## Available Datasets

The system supports 7 external datasets:

1. **hospitals_england_wales** - Hospitals (England & Wales)
2. **nhs_trusts** - NHS Trusts
3. **welsh_lhbs** - Welsh Local Health Boards
4. **london_boroughs** - London Boroughs
5. **nhs_england_regions** - NHS England Regions
6. **paediatric_diabetes_units** - Paediatric Diabetes Units
7. **integrated_care_boards** - Integrated Care Boards (ICBs)

Plus 3 NHS Data Dictionary datasets:

8. **main_specialty_code** - Main Specialty Code
9. **treatment_function_code** - Treatment Function Code
10. **ethnic_category** - Ethnic Category

## Data Transformation

The service layer transforms API responses into user-friendly dropdown options:

- **Hospitals, Trusts, Boroughs**: `NAME (CODE)`
  Example: `ADDENBROOKE'S HOSPITAL (RGT01)`

- **Welsh LHBs**: Includes both the health board and its constituent organisations
  Example:
  - `Swansea Bay University Health Board (7A3)`
  - `  MORRISTON HOSPITAL (7A3C7)` (indented to show hierarchy)

- **Regions**: `NAME (REGION_CODE)`
  Example: `South West (Y58)`

- **PDUs**: `HOSPITAL_NAME (ODS_CODE)` or `PDU PZ_CODE` if name unavailable

## Database-First Architecture

**Important**: The system no longer uses caching or makes API calls on user requests. Instead:

1. External datasets are stored in the database
2. Users read from the database (fast, offline-capable)
3. Periodic sync updates data from external APIs
4. Version history tracks changes

**Benefits:**
- **Faster** - No API calls during user requests
- **Offline** - Works without internet connectivity
- **Auditable** - Version history tracks all changes
- **Customizable** - Users can create custom versions of external datasets

**Migration from Cache:**
If upgrading from cache-based implementation, the `clear_dataset_cache()` function now logs a warning and does nothing. Remove any cache-clearing code and use `sync_external_datasets` command instead.

## API Endpoints

### List Available Datasets
```
GET /api/datasets/
Authorization: Bearer <JWT_TOKEN>
```

Response:
```json
{
  "datasets": [
    {
      "key": "hospitals_england",
      "name": "Hospitals (England)"
    },
    ...
  ]
}
```

### Get Dataset Options
```
GET /api/datasets/{dataset_key}/
Authorization: Bearer <JWT_TOKEN>
```

Response:
```json
{
  "dataset_key": "hospitals_england",
  "options": [
    "ADDENBROOKE'S HOSPITAL (RGT01)",
    "AIREDALE GENERAL HOSPITAL (RCF22)",
    ...
  ]
}
```

Error responses:
- `400` - Invalid dataset key
- `502` - External API failure or invalid response format

## User Interface

### When to Show Prefilled Options

The "Use prefilled options" checkbox is only visible when:
- Question type is set to **dropdown** (single choice)

If the user changes the question type away from dropdown, the checkbox is automatically unchecked and the dataset selection is cleared.

### Loading Data

1. User checks "Use prefilled options"
2. User selects a dataset from the dropdown
3. User clicks "Load Options" button (primary color)
4. Button shows DaisyUI spinner: `<span class="loading loading-spinner loading-xs"></span> Loading...`
5. On success, options populate the textarea
6. On error, toast notification appears

## Testing

All 24 tests are passing, covering:

- Authentication requirements
- Permission checks (org admins, creators, viewers, and non-members)
- Error handling (invalid keys, missing datasets)
- Database-backed responses
- Response format validation

Run API tests with:

```bash
docker compose exec web python -m pytest checktick_app/api/tests/test_dataset_api.py -v
```

Run sync command tests with:

```bash
docker compose exec web python -m pytest checktick_app/surveys/tests/test_sync_datasets_command.py -v
```

## Troubleshooting

### Empty Options Lists

If datasets show as empty in the UI:

1. Check if datasets are seeded:
   ```bash
   docker compose exec web python manage.py shell
   >>> from checktick_app.surveys.models import DataSet
   >>> DataSet.objects.filter(category='rcpch').values('key', 'last_synced_at')
   ```

2. If `last_synced_at` is `None`, run the sync command:
   ```bash
   docker compose exec web python manage.py sync_external_datasets
   ```

3. Check for errors in logs during sync

### Sync Command Errors

If you see errors when running `sync_external_datasets`:

- **"Unknown dataset key"**: Use `--dataset` with a valid key from `AVAILABLE_DATASETS`
- **"API connection failed"**: Check network connectivity to `api.rcpch.ac.uk`
- **"Expected list response"**: API response format changed - check transformation logic
- Check Django logs for detailed error messages

### Dataset Not Appearing in UI

1. Verify dataset exists and is active:
   ```bash
   docker compose exec web python manage.py shell
   >>> from checktick_app.surveys.models import DataSet
   >>> DataSet.objects.filter(key='hospitals_england_wales', is_active=True).exists()
   ```

2. Check that `is_global=True` or dataset belongs to user's organization

3. Verify `options` array is not empty

### Force Re-Sync

To force update a recently synced dataset:

```bash
docker compose exec web python manage.py sync_external_datasets --force --dataset hospitals_england_wales
```

## Architecture

```
┌─────────────────┐
│   Frontend UI   │
│ (builder.js)    │
└────────┬────────┘
         │ Fetch /api/datasets/{key}/
         ▼
┌─────────────────┐
│  API Endpoint   │
│  (api/views.py) │
└────────┬────────┘
         │ Call fetch_dataset()
         ▼
┌─────────────────┐
│ Service Layer   │
│ (external_data  │
│  sets.py)       │
└────────┬────────┘
         │ Query database
         ▼
┌─────────────────┐
│  DataSet Model  │
│  (surveys_      │
│   dataset)      │
└─────────────────┘
         ▲
         │ Periodic sync
┌────────┴────────┐
│ Sync Command    │
│ (sync_external_ │
│  datasets)      │
└────────┬────────┘
         │ HTTP GET
         ▼
┌─────────────────┐
│  RCPCH API      │
│  (External)     │
└─────────────────┘
```

## Files Modified/Created

- `checktick_app/surveys/management/commands/seed_external_datasets.py` - NEW: Seed dataset records
- `checktick_app/surveys/management/commands/sync_external_datasets.py` - NEW: Sync from API
- `checktick_app/surveys/tests/test_sync_datasets_command.py` - NEW: Comprehensive sync tests
- `checktick_app/surveys/external_datasets.py` - MODIFIED: Database-first, removed cache
- `checktick_app/api/views.py` - API endpoints (unchanged, works with new architecture)
- `checktick_app/api/urls.py` - URL routing (unchanged)
- `checktick_app/api/tests/test_dataset_api.py` - Test suite with database fixtures
- `checktick_app/surveys/templates/surveys/group_builder.html` - UI components (unchanged)
- `checktick_app/static/js/builder.js` - Frontend logic with spinner (unchanged)
- `.env.example` - Configuration documentation (unchanged)
- `docs/self-hosting-scheduled-tasks.md` - Cron job documentation
