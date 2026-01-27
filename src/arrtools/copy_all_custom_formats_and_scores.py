from asyncio import run
from typing import Annotated

from typer import Argument, Option

from ..app import app
from .utils import (
    ARRAPIClient,
    CustomFormat,
    CreatedCustomFormat,
    QualityProfile,
    SONARR_ONLY_IMPLEMENTATIONS,
    RADARR_ONLY_IMPLEMENTATIONS,
    QualityProfileFormatItem,
)


async def copy_all_custom_formats_and_scores_inner(
    *,
    source_arr_url: str,
    source_api_key: str,
    target_arr_url: str,
    target_api_key: str,
    source_arr_headers: dict[str, str] | None = None,
    target_arr_headers: dict[str, str] | None = None,
    source_profile_name: str | None = None,
    target_profile_name: str | None = None,
    delete_extra_custom_formats: bool = False,
):
    async with (
        ARRAPIClient(
            source_arr_url, api_key=source_api_key, extra_headers=source_arr_headers
        ) as source_session,
        ARRAPIClient(
            target_arr_url, api_key=target_api_key, extra_headers=target_arr_headers
        ) as target_session,
    ):
        source_type = await source_session.get_arr_type()
        target_type = await target_session.get_arr_type()
        source_custom_formats = await source_session.get_custom_formats()
        target_custom_formats = await target_session.get_custom_formats()
        source_cf_dict = {cf.name: cf for cf in source_custom_formats}
        target_cf_dict = {cf.name: cf for cf in target_custom_formats}
        # extra_custom_formats_names = target_cf_dict.keys() - source_cf_dict.keys()
        extra_custom_format_ids = {
            cf.id for name, cf in target_cf_dict.items() if name not in source_cf_dict
        }
        seen_custom_formats: list[CreatedCustomFormat] = []
        skipped_source_incompatible_custom_formats: list[CreatedCustomFormat] = []
        attributes_to_skip = (
            []
            if source_type == target_type
            else (
                SONARR_ONLY_IMPLEMENTATIONS
                if source_type == "Sonarr"
                else RADARR_ONLY_IMPLEMENTATIONS
            )
        )
        created_count = 0
        updated_count = 0

        for source_cf in source_custom_formats:
            if any(
                spec.implementation in attributes_to_skip
                for spec in source_cf.specifications
            ):
                skipped_source_incompatible_custom_formats.append(source_cf)
                print(
                    f"Skipped incompatible custom format '{source_cf.name}' for target ARR type '{target_type}'."
                )
                continue
            if source_cf.name in target_cf_dict:
                target_cf = target_cf_dict[source_cf.name]
                if (
                    source_cf.includeCustomFormatWhenRenaming
                    != target_cf.includeCustomFormatWhenRenaming
                    or source_cf.specifications != target_cf.specifications
                ):
                    updated_cf = await target_session.update_custom_format(
                        target_cf.id,
                        CustomFormat(
                            name=source_cf.name,
                            includeCustomFormatWhenRenaming=source_cf.includeCustomFormatWhenRenaming,
                            specifications=source_cf.specifications,
                        ),
                    )
                    seen_custom_formats.append(updated_cf)
                    updated_count += 1
                    print(f"Updated custom format '{source_cf.name}' in target ARR.")
                else:
                    seen_custom_formats.append(target_cf)
                    # print(
                    #     f"Custom format '{source_cf.name}' already up to date in target ARR."
                    # )
            else:
                created_cf = await target_session.create_custom_format(
                    CustomFormat(
                        name=source_cf.name,
                        includeCustomFormatWhenRenaming=source_cf.includeCustomFormatWhenRenaming,
                        specifications=source_cf.specifications,
                    )
                )
                seen_custom_formats.append(created_cf)
                created_count += 1
                print(f"Created custom format '{source_cf.name}' in target ARR.")
        print(
            f"Created {created_count} and updated {updated_count} custom formats in target ARR."
        )
        if delete_extra_custom_formats and extra_custom_format_ids:
            await target_session.bulk_delete_custom_formats(extra_custom_format_ids)
            print(
                f"Deleted {len(extra_custom_format_ids)} extra custom formats from target ARR."
            )
        if source_profile_name:
            if not target_profile_name:
                raise ValueError(
                    "If source_profile_name is provided, target_profile_name must also be provided."
                )
        if target_profile_name:
            if not source_profile_name:
                raise ValueError(
                    "If target_profile_name is provided, source_profile_name must also be provided."
                )
        if not source_profile_name or not target_profile_name:
            return
        source_quality_profiles = await source_session.get_quality_profiles()
        target_quality_profiles = await target_session.get_quality_profiles()
        source_profile_dict = {qp.name: qp for qp in source_quality_profiles}
        target_profile_dict = {qp.name: qp for qp in target_quality_profiles}
        if source_profile_name not in source_profile_dict:
            raise ValueError(
                f"Source profile '{source_profile_name}' not found in source ARR."
            )
        if target_profile_name not in target_profile_dict:
            raise ValueError(
                f"Target profile '{target_profile_name}' not found in target ARR."
            )
        source_profile = source_profile_dict[source_profile_name]
        target_profile = target_profile_dict[target_profile_name]
        skipped_source_format_ids = {
            cf.id for cf in skipped_source_incompatible_custom_formats
        }
        seen_custom_format_by_name = {cf.name: cf for cf in seen_custom_formats}
        source_profile_scores_by_format_name = {
            item.name: item.score for item in source_profile.formatItems
        }
        new_formats = [
            QualityProfileFormatItem(
                format=item.id,
                name=item.name,
                score=source_profile_scores_by_format_name[item.name],
            )
            for item in seen_custom_format_by_name.values()
        ]
        not_seen_but_used_formats = [
            item
            for item in target_profile.formatItems
            if item.name not in seen_custom_format_by_name
        ]  # These are needed since every custom format needs to be in the quality profile in order for the update to work
        all_new_formats = new_formats + not_seen_but_used_formats
        all_new_formats.sort(key=lambda item: item.format, reverse=True)
        await target_session.update_quality_profile(
            target_profile.id,
            QualityProfile(
                name=target_profile.name,
                id=target_profile.id,
                cutoff=target_profile.cutoff,
                cutoffFormatScore=target_profile.cutoffFormatScore,
                items=target_profile.items,
                minFormatScore=target_profile.minFormatScore,
                minUpgradeFormatScore=target_profile.minUpgradeFormatScore,
                language=target_profile.language,
                upgradeAllowed=target_profile.upgradeAllowed,
                formatItems=all_new_formats,
            ),
        )
        print(
            f"Updated target quality profile '{target_profile.name}' with scores from source profile '{source_profile.name}'."
        )


@app.command()
def copy_all_custom_formats_and_scores(
    source_arr_url: Annotated[
        str,
        Argument(help="URL of the source ARR instance."),
    ],
    source_api_key: Annotated[
        str,
        Argument(help="API key for the source ARR instance."),
    ],
    target_arr_url: Annotated[
        str,
        Argument(help="URL of the target ARR instance."),
    ],
    target_api_key: Annotated[
        str,
        Argument(help="API key for the target ARR instance."),
    ],
    source_profile_name: Annotated[
        str | None,
        Option(
            help="Name of the quality profile in the source ARR to copy from if copying profile info.",
        ),
    ] = None,
    target_profile_name: Annotated[
        str | None,
        Option(
            help="Name of the quality profile in the target ARR to update.",
        ),
    ] = None,
    delete_extra_custom_formats: Annotated[
        bool,
        Option(
            help="Whether to delete custom formats in the target ARR that do not exist in the source ARR.",
        ),
    ] = False,
    extra_source_arr_headers: Annotated[
        list[str] | None,
        Option(
            help="Additional headers to include in requests to the source ARR instance, in 'Key: Value' format. Specify option multiple times for multiple headers.",
        ),
    ] = None,
    extra_target_arr_headers: Annotated[
        list[str] | None,
        Option(
            help="Additional headers to include in requests to the target ARR instance, in 'Key: Value' format. Specify option multiple times for multiple headers.",
        ),
    ] = None,
):
    """Copy all custom formats and their scores from one ARR instance to another."""
    print(extra_source_arr_headers, extra_target_arr_headers)
    run(
        copy_all_custom_formats_and_scores_inner(
            source_arr_url=source_arr_url,
            source_api_key=source_api_key,
            target_arr_url=target_arr_url,
            target_api_key=target_api_key,
            source_profile_name=source_profile_name,
            target_profile_name=target_profile_name,
            delete_extra_custom_formats=delete_extra_custom_formats,
            source_arr_headers={
                k: v
                for header in extra_source_arr_headers or []
                for k, v in [header.split(":", 1)]
            }
            if extra_source_arr_headers
            else None,
            target_arr_headers={
                k: v
                for header in extra_target_arr_headers or []
                for k, v in [header.split(":", 1)]
            }
            if extra_target_arr_headers
            else None,
        )
    )
