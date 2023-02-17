from collections import defaultdict
from dataclasses import dataclass
from unittest.mock import patch

from sentry.issues.grouptype import (
    DEFAULT_EXPIRY_TIME,
    DEFAULT_IGNORE_LIMIT,
    GroupCategory,
    GroupPolicy,
    GroupType,
    NoiseConfig,
    _category_lookup,
    _group_type_registry,
    get_group_type_by_slug,
    get_group_types_by_category,
    get_noise_config,
)
from sentry.testutils import TestCase
from sentry.testutils.silo import region_silo_test


@region_silo_test
class GroupTypeTest(TestCase):  # type: ignore
    def test_get_types_by_category(self) -> None:
        with patch.dict(_group_type_registry, {}, clear=True), patch.dict(
            _category_lookup, defaultdict(set), clear=True
        ):

            @dataclass(frozen=True)
            class TestGroupType(GroupType):
                type_id = 1
                slug = "test"
                description = "Test"
                category = GroupCategory.ERROR.value
                ignore_limit = 0

            @dataclass(frozen=True)
            class TestGroupType2(GroupType):
                type_id = 2
                slug = "hellboy"
                description = "Hellboy"
                category = GroupCategory.PERFORMANCE.value

            @dataclass(frozen=True)
            class TestGroupType3(GroupType):
                type_id = 3
                slug = "angelgirl"
                description = "AngelGirl"
                category = GroupCategory.PERFORMANCE.value

            assert get_group_types_by_category(GroupCategory.PERFORMANCE.value) == {2, 3}
            assert get_group_types_by_category(GroupCategory.ERROR.value) == {1}

    def test_get_group_type_by_slug(self) -> None:
        with patch.dict(_group_type_registry, {}, clear=True):

            @dataclass(frozen=True)
            class TestGroupType(GroupType):
                type_id = 1
                slug = "test"
                description = "Test"
                category = GroupCategory.ERROR.value
                ignore_limit = 0

            assert get_group_type_by_slug(TestGroupType.slug) == TestGroupType

            nonexistent_slug = "meow"
            with self.assertRaisesMessage(
                ValueError, f"No group type with the slug {nonexistent_slug} is registered."
            ):
                get_group_type_by_slug(nonexistent_slug)

    def test_category_validation(self) -> None:
        with patch.dict(_group_type_registry, {}, clear=True):

            @dataclass(frozen=True)
            class TestGroupType(GroupType):
                type_id = 1
                slug = "error"
                description = "Error"
                category = 22

        with self.assertRaisesMessage(
            ValueError,
            f"Category must be one of {[category.value for category in GroupCategory]} from GroupCategory",
        ):
            TestGroupType(1, "error", "Error", 22)


@region_silo_test
class GroupPolicyTest(TestCase):  # type: ignore
    def setUp(self) -> None:
        super().setUp()
        self.org = self.create_organization()

    def test_get_noise_config(self) -> None:
        with patch.dict(_group_type_registry, {}, clear=True):

            @dataclass(frozen=True)
            class TestGroupType1(GroupType):
                type_id = 1
                slug = "test-1"
                description = "Test-1"
                category = GroupCategory.ERROR.value
                group_policy = GroupPolicy(
                    feature="organizations:test-detector-1",
                    general_access=NoiseConfig(
                        ignore_limit=100,
                        expiry_time=60,
                    ),
                )

            @dataclass(frozen=True)
            class TestGroupType2(GroupType):
                type_id = 2
                slug = "test-2"
                description = "Test-2"
                category = GroupCategory.PERFORMANCE.value
                group_policy = GroupPolicy(
                    feature="organizations:test-detector-2",
                    general_access=NoiseConfig(
                        ignore_limit=10,
                        expiry_time=600,
                    ),
                )

            noise_config_1 = get_noise_config(TestGroupType1, self.org)
            assert noise_config_1.ignore_limit == 100
            assert noise_config_1.expiry_time == 60

            noise_config_2 = get_noise_config(TestGroupType2, self.org)
            assert noise_config_2.ignore_limit == 10
            assert noise_config_2.expiry_time == 600

    def test_default_noise_config(self) -> None:
        with patch.dict(_group_type_registry, {}, clear=True):

            @dataclass(frozen=True)
            class TestGroupType1(GroupType):
                type_id = 1
                slug = "test-1"
                description = "Test-1"
                category = GroupCategory.ERROR.value
                group_policy = GroupPolicy(
                    feature="organizations:test-detector-1",
                )

            noise_config = get_noise_config(TestGroupType1, self.org)
            assert noise_config.ignore_limit == DEFAULT_IGNORE_LIMIT
            assert noise_config.expiry_time == DEFAULT_EXPIRY_TIME

    def test_noise_config_validation(self) -> None:
        with patch.dict(_group_type_registry, {}, clear=True):

            @dataclass(frozen=True)
            class TestGroupType1(GroupType):
                type_id = 1
                slug = "test-1"
                description = "Test-1"
                category = GroupCategory.ERROR.value
                group_policy = GroupPolicy(
                    feature="organizations:test-detector-1",
                    limited_access=NoiseConfig(ignore_limit=100),
                    early_access=NoiseConfig(
                        ignore_limit=50,
                    ),
                )

            with self.assertRaisesMessage(
                ValueError,
                "Early Access ignore limit ratio must be greater than Limited Access ignore limit ratio",
            ):
                TestGroupType1(
                    1,
                    "test-1",
                    "Test-1",
                    GroupCategory.ERROR.value,
                    0,
                    GroupPolicy(
                        feature="organizations:test-detector-1",
                        limited_access=NoiseConfig(ignore_limit=100),
                        early_access=NoiseConfig(
                            ignore_limit=50,
                        ),
                    ),
                )

            @dataclass(frozen=True)
            class TestGroupType2(GroupType):
                type_id = 2
                slug = "test-2"
                description = "Test-2"
                category = GroupCategory.PERFORMANCE.value
                group_policy = GroupPolicy(
                    feature="organizations:test-detector-2",
                    early_access=NoiseConfig(
                        ignore_limit=50,
                    ),
                    general_access=NoiseConfig(
                        ignore_limit=10,
                    ),
                )

            with self.assertRaisesMessage(
                ValueError,
                "General Access ignore limit ratio must be greater than Early Access and Limited Access ignore limit ratios",
            ):
                TestGroupType2(
                    2,
                    "test-2",
                    "Test-2",
                    GroupCategory.PERFORMANCE.value,
                    0,
                    GroupPolicy(
                        feature="organizations:test-detector-2",
                        early_access=NoiseConfig(ignore_limit=100),
                        general_access=NoiseConfig(
                            ignore_limit=50,
                        ),
                    ),
                )

            @dataclass(frozen=True)
            class TestGroupType3(GroupType):
                type_id = 3
                slug = "test-3"
                description = "Test-3"
                category = GroupCategory.PERFORMANCE.value
                group_policy = GroupPolicy(
                    feature="organizations:test-detector-3",
                    early_access=NoiseConfig(
                        ignore_limit=10,
                        expiry_time=60,
                    ),
                    general_access=NoiseConfig(
                        ignore_limit=10,
                        expiry_time=600,
                    ),
                )

            with self.assertRaisesMessage(
                ValueError,
                "General Access ignore limit ratio must be greater than Early Access and Limited Access ignore limit ratios",
            ):
                TestGroupType2(
                    3,
                    "test-3",
                    "Test-3",
                    GroupCategory.PERFORMANCE.value,
                    0,
                    GroupPolicy(
                        feature="organizations:test-detector-2",
                        early_access=NoiseConfig(
                            ignore_limit=10,
                            expiry_time=60,
                        ),
                        general_access=NoiseConfig(
                            ignore_limit=10,
                            expiry_time=600,
                        ),
                    ),
                )


# TODO add test to check for LA/EA/GA
# with self.feature({"organizations:performance-issues-compressed-assets-detector": True}):
#     assert detector.is_creation_allowed_for_organization(project.organization)
