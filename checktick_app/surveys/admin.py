from django.conf import settings
from django.contrib import admin

from .models import (
    CollectionDefinition,
    CollectionItem,
    DataSet,
    Organization,
    QuestionGroup,
    Survey,
    SurveyProgress,
    SurveyQuestion,
    SurveyResponse,
)


@admin.register(DataSet)
class DataSetAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "key",
        "category",
        "organization",
        "is_global",
        "is_active",
        "version",
        "created_at",
    )
    list_filter = ("category", "is_global", "is_active", "is_custom", "created_at")
    search_fields = ("name", "key", "description")
    readonly_fields = (
        "created_at",
        "updated_at",
        "version",
        "created_by",
        "last_synced_at",
    )
    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "key",
                    "name",
                    "description",
                    "category",
                    "source_type",
                )
            },
        ),
        (
            "Options",
            {
                "fields": (
                    "options",
                    "format_pattern",
                )
            },
        ),
        (
            "Access Control",
            {
                "fields": (
                    "is_global",
                    "organization",
                    "is_active",
                )
            },
        ),
        (
            "Customization",
            {
                "fields": (
                    "is_custom",
                    "parent",
                )
            },
        ),
        (
            "External API",
            {
                "fields": (
                    "external_api_endpoint",
                    "external_api_url",
                    "sync_frequency_hours",
                    "last_synced_at",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "NHS DD Metadata",
            {
                "fields": (
                    "reference_url",
                    "nhs_dd_page_id",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "created_by",
                    "created_at",
                    "updated_at",
                    "version",
                )
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        """Make NHS DD datasets fully read-only."""
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and obj.category == "nhs_dd" and not obj.is_custom:
            # NHS DD datasets are read-only except for is_active
            return [
                f.name for f in obj._meta.fields if f.name not in ("id", "is_active")
            ]
        return readonly


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "owner")


@admin.register(QuestionGroup)
class QuestionGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "shared", "created_at")


class SurveyQuestionInline(admin.TabularInline):
    model = SurveyQuestion
    extra = 0


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "slug", "start_at", "end_at", "created_at")
    inlines = [SurveyQuestionInline]


@admin.register(SurveyResponse)
class SurveyResponseAdmin(admin.ModelAdmin):
    list_display = ("survey", "submitted_at")


@admin.register(SurveyProgress)
class SurveyProgressAdmin(admin.ModelAdmin):
    list_display = (
        "survey",
        "user",
        "session_key",
        "answered_count",
        "total_questions",
        "updated_at",
        "expires_at",
    )
    list_filter = ("survey", "updated_at", "expires_at")
    search_fields = ("survey__name", "survey__slug", "user__username", "session_key")
    readonly_fields = ("created_at", "updated_at", "last_question_answered_at")


class CollectionItemInline(admin.TabularInline):
    model = CollectionItem
    # CollectionItem has two FKs to CollectionDefinition (collection, child_collection)
    # This inline should attach via the 'collection' FK
    fk_name = "collection"
    extra = 0


@admin.register(CollectionDefinition)
class CollectionDefinitionAdmin(admin.ModelAdmin):
    list_display = ("name", "key", "survey", "cardinality", "parent")
    list_filter = ("survey", "cardinality")
    search_fields = ("name", "key")
    inlines = [CollectionItemInline]


# Configure admin site branding after admin is imported
_brand_title = getattr(settings, "BRAND_TITLE", "CheckTick")
admin.site.site_header = f"{_brand_title} Admin"
admin.site.site_title = f"{_brand_title} Admin"
admin.site.index_title = "Administration"
