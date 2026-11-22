"""The model picker's row facts (resolution, seconds, sound) and the console's Featured / NEW marks."""

from scene.providers.workflows import facts, marks, set_mark


def test_facts_of_a_video_model():
    profile = {"provider": {"limits": {"resolutions": ["480p", "720p", "1080p"], "seconds": {"min": 4, "max": 15},
                                       "sound": "choice"}}, "options": []}
    assert facts(profile) == {"resolution": "1080p", "seconds": {"min": 4, "max": 15}, "sound": True}


def test_facts_read_k_sizes_and_options():
    profile = {"provider": {"limits": {}}, "options": [
        {"id": "resolution", "choices": [{"id": "1K"}, {"id": "4K"}, {"id": "2K"}]}]}
    assert facts(profile) == {"resolution": "4K", "seconds": None, "sound": False}


def test_facts_of_a_model_with_none():
    assert facts({"provider": {"limits": {"sound": "none"}}}) == {"resolution": "", "seconds": None, "sound": False}


class Settings:
    def __init__(self):
        self.kept = {}

    def setting(self, key, default=""):
        return self.kept.get(key, default)

    def set_setting(self, key, value):
        self.kept[key] = value


def test_marks_are_kept_and_removed():
    db = Settings()
    assert marks(db) == {}
    assert set_mark(db, "video/@seedance_2_5", True, False) == {"featured": True, "new": False}
    set_mark(db, "image/@seedream_5", False, True)
    assert marks(db) == {"video/@seedance_2_5": {"featured": True, "new": False},
                         "image/@seedream_5": {"featured": False, "new": True}}
    set_mark(db, "video/@seedance_2_5", False, False)
    assert list(marks(db)) == ["image/@seedream_5"]
