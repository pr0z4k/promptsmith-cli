import pytest
from pathlib import Path
from promptsmith.core.profiles import ProfileManager
from promptsmith.core.exceptions import ProfileNotFoundError
import yaml


@pytest.fixture
def profile_manager(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    profile = {
        "name": "Test Profile", "role": "Tester",
        "domain": ["Testing"], "tone": "Neutral",
        "format": "Text", "constraints": ["Be concise"], "version": 1,
    }
    (profiles_dir / "test-profile.yaml").write_text(yaml.dump(profile))
    return ProfileManager(profiles_dir)


def test_load_profiles(profile_manager):
    assert "test-profile" in profile_manager.list_profiles()


def test_get_profile(profile_manager):
    p = profile_manager.get_profile("test-profile")
    assert p["role"] == "Tester"
    assert p["domain"] == ["Testing"]


def test_missing_profile_raises(profile_manager):
    with pytest.raises(ProfileNotFoundError):
        profile_manager.get_profile("nonexistent")


def test_add_profile(profile_manager, tmp_path):
    profile_manager.add_profile("new-profile", {"role": "Developer"})
    assert "new-profile" in profile_manager.list_profiles()


def test_delete_profile(profile_manager, tmp_path):
    assert profile_manager.delete_profile("test-profile") is True
    assert "test-profile" not in profile_manager.list_profiles()
    assert profile_manager.delete_profile("ghost") is False


class TestUserProfileSeparation:
    """Regression tests for the user/built-in profile separation feature.
    Without this, hand-adding a custom profile to a distributed build gets
    silently lost the next time that build is updated - flagged
    independently both in our own review and by an external review, so
    this is a real, confirmed gap, not speculative."""

    @pytest.fixture
    def dirs(self, tmp_path):
        builtin = tmp_path / "profiles"
        builtin.mkdir()
        user = tmp_path / "user_profiles"
        (builtin / "vibe-coding.yaml").write_text(
            yaml.dump({"role": "Engineer", "tone": "Pragmatic and production-ready"})
        )
        (builtin / "general.yaml").write_text(yaml.dump({"role": "Assistant"}))
        return builtin, user

    def test_user_dir_created_automatically(self, dirs):
        builtin, user = dirs
        assert not user.exists()
        ProfileManager(builtin, user_dir=user)
        assert user.exists()

    def test_without_override_gets_builtin_value(self, dirs):
        builtin, user = dirs
        pm = ProfileManager(builtin, user_dir=user)
        assert pm.get_profile("vibe-coding")["tone"] == "Pragmatic and production-ready"

    def test_user_profile_overrides_builtin_by_name(self, dirs):
        builtin, user = dirs
        user.mkdir()
        (user / "vibe-coding.yaml").write_text(
            yaml.dump({"role": "Engineer", "tone": "User customized tone"})
        )
        pm = ProfileManager(builtin, user_dir=user)
        assert pm.get_profile("vibe-coding")["tone"] == "User customized tone"
        assert pm.is_user_defined("vibe-coding") is True

    def test_user_only_profile_is_additive_not_duplicated(self, dirs):
        builtin, user = dirs
        user.mkdir()
        (user / "my-only-profile.yaml").write_text(yaml.dump({"role": "Custom"}))
        pm = ProfileManager(builtin, user_dir=user)
        names = pm.list_profiles()
        assert "my-only-profile" in names
        assert "vibe-coding" in names
        assert "general" in names
        assert len(names) == 3  # 2 builtin + 1 user, no duplicates

    def test_builtin_profile_not_flagged_as_user_defined(self, dirs):
        builtin, user = dirs
        pm = ProfileManager(builtin, user_dir=user)
        assert pm.is_user_defined("general") is False

    def test_add_profile_writes_to_user_dir_not_builtin(self, dirs):
        """New profiles added programmatically must never land in the
        built-in directory - that would defeat the whole point, since a
        future update would just overwrite it again."""
        builtin, user = dirs
        pm = ProfileManager(builtin, user_dir=user)
        pm.add_profile("newly-added", {"role": "New"})
        assert (user / "newly-added.yaml").exists()
        assert not (builtin / "newly-added.yaml").exists()

    def test_delete_only_removes_user_override_not_builtin_file(self, dirs):
        """Deleting a user's override of a built-in profile should reveal
        the built-in one again, not remove it - the built-in file itself
        must never be touched by delete_profile."""
        builtin, user = dirs
        user.mkdir()
        (user / "vibe-coding.yaml").write_text(
            yaml.dump({"role": "Engineer", "tone": "User customized tone"})
        )
        pm = ProfileManager(builtin, user_dir=user)
        assert pm.delete_profile("vibe-coding") is True
        assert (builtin / "vibe-coding.yaml").exists()  # untouched
        assert not (user / "vibe-coding.yaml").exists()  # removed

        pm2 = ProfileManager(builtin, user_dir=user)
        assert pm2.get_profile("vibe-coding")["tone"] == "Pragmatic and production-ready"

    def test_no_user_dir_behaves_exactly_as_before(self, dirs):
        """Existing callers that don't pass user_dir at all must see
        identical single-directory behavior - this feature is purely
        additive."""
        builtin, _ = dirs
        pm = ProfileManager(builtin)
        assert set(pm.list_profiles()) == {"vibe-coding", "general"}
        assert pm.is_user_defined("vibe-coding") is False


def test_resolve_id_and_get_profile_accept_display_names(tmp_path):
    """Regression test for an independent review's finding: PromptAnalyzer's
    TYPE_PROFILE_MAP (and therefore IntentCompiler's auto-recommended
    profile, when no profile is explicitly chosen) returns human-readable
    display names like 'React Developer', not the file id 'react-developer'
    that get_profile()/get_config() actually key on. Every auto-recommended
    profile lookup failed silently, downgraded upstream to 'return the
    original prompt unchanged with a warning' - the profile was never
    actually applied."""
    import yaml
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "react-developer.yaml").write_text(yaml.dump({
        "name": "React Developer", "role": "React Developer",
        "domain": ["React"], "tone": "Technical", "format": "Markdown",
        "constraints": [], "vendor": "generic", "backend": "rule",
    }))

    pm = ProfileManager(profiles_dir)

    # Exact id still works (unaffected - this is what the TUI always sends)
    assert pm.resolve_id("react-developer") == "react-developer"
    # Display name now resolves too (what TYPE_PROFILE_MAP sends)
    assert pm.resolve_id("React Developer") == "react-developer"
    # Case-insensitive
    assert pm.resolve_id("react developer") == "react-developer"
    # Genuinely unknown name resolves to nothing
    assert pm.resolve_id("Nonexistent Profile") is None

    # get_profile() itself must transparently accept the display name too
    profile = pm.get_profile("React Developer")
    assert profile["role"] == "React Developer"
