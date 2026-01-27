"""Utility functions for working with the Jellyfin API."""

from enum import StrEnum
from typing import TYPE_CHECKING, Self, Any, Iterable, Literal
from aiohttp import ClientSession
from pydantic import BaseModel, RootModel, Field


class CustomFormatSpecificationImplementation(StrEnum):
    """Enumeration of Custom Format Specification Implementations."""

    ReleaseTitleSpecification = "ReleaseTitleSpecification"
    LanguageSpecification = "LanguageSpecification"
    IndexerFlagSpecification = "IndexerFlagSpecification"
    SourceSpecification = "SourceSpecification"
    ResolutionSpecification = "ResolutionSpecification"
    SizeSpecification = "SizeSpecification"
    ReleaseGroupSpecification = "ReleaseGroupSpecification"

    # Sonarr-only implementations
    ReleaseTypeSpecification = "ReleaseTypeSpecification"

    # Radarr-only implementations
    EditionSpecification = "EditionSpecification"
    QualityModifierSpecification = "QualityModifierSpecification"
    YearSpecification = "YearSpecification"


SONARR_ONLY_IMPLEMENTATIONS = {
    CustomFormatSpecificationImplementation.ReleaseTypeSpecification,
}

RADARR_ONLY_IMPLEMENTATIONS = {
    CustomFormatSpecificationImplementation.EditionSpecification,
    CustomFormatSpecificationImplementation.QualityModifierSpecification,
    CustomFormatSpecificationImplementation.YearSpecification,
}


class CustomFormatSpecification(BaseModel):
    """{
      "name": "Bluray",
      "implementation": "SourceSpecification",
      "negate": false,
      "required": false,
      "fields": {
        "value": 6
      }
    },"""

    name: str
    implementation: CustomFormatSpecificationImplementation
    negate: bool
    required: bool
    fields: list[dict[str, Any]] = Field(repr=False, default_factory=list)


class CustomFormat(BaseModel):
    """Represents a Custom Format. Does not include all fields."""

    name: str
    includeCustomFormatWhenRenaming: bool = False
    specifications: list[CustomFormatSpecification] = Field(
        repr=False, default_factory=list
    )


class CreatedCustomFormat(CustomFormat):
    """Includes attributes returned when viewing an existing Custom Format."""

    id: int


class QualityProfileFormatItem(BaseModel):
    """Represents a Quality Profile Format Item. Does not include all fields."""

    format: int  # Matches with the id on a created custom format
    score: int
    name: str | None = None


class QualityProfile(BaseModel):
    """Represents a Quality Profile. Does not include all fields."""

    name: str
    id: int
    cutoff: int
    cutoffFormatScore: int
    minFormatScore: int
    minUpgradeFormatScore: int
    upgradeAllowed: bool

    items: list[dict[str, Any]] = Field(repr=False, default_factory=list)
    formatItems: list[QualityProfileFormatItem] = Field(
        repr=False, default_factory=list
    )

    language: dict[str, Any] | None = (
        None  # Radarr-only attribute, make sure to pop if none because null is not allowed
    )


class ARRAPIClient(ClientSession):
    """Client for interacting with the ARR API."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Initialize the ARR API client."""
        super().__init__(base_url)
        self.headers.update(
            {
                "X-Api-Key": api_key,
                "Accept": "application/json",
            }
        )
        if extra_headers:
            self.headers.update(extra_headers)

    async def get_arr_type(self) -> Literal["Sonarr", "Radarr"]:
        # Dumb way to check, but only way I know
        async with self.get("/feed/v3/calendar/sonarr.ics") as response:
            if response.status == 200:
                return "Sonarr"
        async with self.get("/feed/v3/calendar/radarr.ics") as response:
            if response.status == 200:
                return "Radarr"
        raise RuntimeError(
            "Could not determine ARR type (not Sonarr or Radarr, only Sonarr/Radarr is supported)"
        )

    async def get_custom_formats(self) -> list[CreatedCustomFormat]:
        """Get all custom formats from the ARR API."""
        async with self.get("/api/v3/customformat") as response:
            response.raise_for_status()
            data = await response.json()
            root_model = RootModel[list[CreatedCustomFormat]].model_validate(data)
            return root_model.root

    async def create_custom_format(
        self, custom_format: CustomFormat
    ) -> CreatedCustomFormat:
        """Create a new custom format in the ARR API."""
        async with self.post(
            "/api/v3/customformat",
            json=custom_format.model_dump(),
        ) as response:
            response.raise_for_status()
            data = await response.json()
            return CreatedCustomFormat.model_validate(data)

    async def update_custom_format(
        self, id: int, new_custom_format: CustomFormat
    ) -> CreatedCustomFormat:
        """Update an existing custom format in the ARR API."""
        async with self.put(
            f"/api/v3/customformat/{id}",
            json=new_custom_format.model_dump(),
        ) as response:
            response.raise_for_status()
            data = await response.json()
            return CreatedCustomFormat.model_validate(data)

    async def delete_custom_format(self, id: int) -> None:
        """Delete a custom format in the ARR API."""
        async with self.delete(f"/api/v3/customformat/{id}") as response:
            response.raise_for_status()

    async def bulk_delete_custom_formats(self, ids: Iterable[int]) -> None:
        """Bulk delete custom formats in the ARR API."""
        async with self.delete(
            f"/api/v3/customformat/bulk", json={"ids": tuple(ids)}
        ) as response:
            response.raise_for_status()

    async def get_quality_profiles(self) -> list[QualityProfile]:
        """Get all quality profiles from the ARR API."""
        async with self.get("/api/v3/qualityprofile") as response:
            response.raise_for_status()
            data = await response.json()
            root_model = RootModel[list[QualityProfile]].model_validate(data)
            return root_model.root

    async def update_quality_profile(
        self, id: int, new_quality_profile: QualityProfile
    ) -> QualityProfile:
        """Update an existing quality profile in the ARR API."""
        json_data = new_quality_profile.model_dump()
        if new_quality_profile.language is None:
            json_data.pop("language", None)
        async with self.put(
            f"/api/v3/qualityprofile/{id}",
            json=json_data,
        ) as response:
            response.raise_for_status()
            data = await response.json()
            return QualityProfile.model_validate(data)

    if TYPE_CHECKING:

        async def __aenter__(self) -> Self: ...
