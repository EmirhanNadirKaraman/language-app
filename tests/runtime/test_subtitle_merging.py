"""
Runtime-aligned port of SubtitleMerger window-property + multi-speaker
guard tests (W4 / #17 batch 1).

Targets the RUNTIME `subtitle_merger.SubtitleMerger`. NOT the orphan
refactor at `src/app/subtitles/merging.py`.

Ported nodeids (src/app suite):
  tests/subtitles/test_subtitle_merger.py::TestWindowProperties::test_merged_text_is_space_joined
  tests/subtitles/test_subtitle_merger.py::TestWindowProperties::test_start_time_comes_from_first_fragment
  tests/subtitles/test_subtitle_merger.py::TestWindowProperties::test_end_time_comes_from_last_fragment
  tests/subtitles/test_subtitle_merger.py::TestWindowProperties::test_original_fragments_preserved_in_order
  tests/subtitles/test_multi_speaker_guard.py::TestDialogueDashVeto::test_dash_prefix_overrides_soft_signal
  tests/subtitles/test_multi_speaker_guard.py::TestDialogueDashVeto::test_dash_prefix_overrides_tiny_gap_unconditional_merge
  tests/subtitles/test_multi_speaker_guard.py::TestDialogueDashVeto::test_en_dash_prefix_blocked
  tests/subtitles/test_multi_speaker_guard.py::TestDialogueDashVeto::test_em_dash_prefix_blocked
"""
from subtitle_merger import SubtitleFragment, SubtitleMergeConfig, SubtitleMerger


def _frag(text: str, start: float, end: float, index: int = 0) -> SubtitleFragment:
    return SubtitleFragment(text=text, start_time=start, end_time=end, index=index)


def _merge(fragments: list[SubtitleFragment], **cfg_kwargs):
    cfg = SubtitleMergeConfig(**cfg_kwargs) if cfg_kwargs else SubtitleMergeConfig()
    return SubtitleMerger(cfg).merge_fragments(fragments)


# ---------------------------------------------------------------------------
# Window properties — text join + time-bound contract
# ---------------------------------------------------------------------------

class TestWindowProperties:

    def test_merged_text_is_space_joined(self):
        windows = _merge([
            _frag("Ich gehe", 0.0, 1.0),
            _frag("nach Hause.", 1.1, 2.0),
        ])
        assert windows[0].text == "Ich gehe nach Hause."

    def test_start_time_comes_from_first_fragment(self):
        windows = _merge([
            _frag("Ich gehe", 1.5, 2.0),
            _frag("nach Hause.", 2.1, 3.5),
        ])
        assert windows[0].start_time == 1.5

    def test_end_time_comes_from_last_fragment(self):
        windows = _merge([
            _frag("Ich gehe", 1.5, 2.0),
            _frag("nach Hause.", 2.1, 3.5),
        ])
        assert windows[0].end_time == 3.5

    def test_original_fragments_preserved_in_order(self):
        f1 = _frag("Ich gehe", 0.0, 1.0, index=0)
        f2 = _frag("nach Hause.", 1.1, 2.0, index=1)
        windows = _merge([f1, f2])
        assert windows[0].fragments == [f1, f2]


# ---------------------------------------------------------------------------
# Multi-speaker dialogue-dash guard — fragments that start with a dash MUST
# break the merge window because they're a new speaker turn.
# ---------------------------------------------------------------------------

class TestDialogueDashVeto:

    def test_dash_prefix_overrides_soft_signal(self):
        windows = _merge([
            _frag("Wenn du möchtest,", 0.0, 1.2),
            _frag("- Können wir morgen reden.", 1.4, 2.5),
        ])
        assert len(windows) == 2

    def test_dash_prefix_overrides_tiny_gap_unconditional_merge(self):
        windows = _merge([
            _frag("Sie hat das alles wirklich sehr gut gemacht.", 0.0, 2.0),
            _frag("- Wirklich?", 2.05, 2.5),
        ])
        assert len(windows) == 2

    def test_en_dash_prefix_blocked(self):
        windows = _merge([
            _frag("Das war schön.", 0.0, 1.0),
            _frag("– Danke schön.", 1.2, 1.9),
        ])
        assert len(windows) == 2

    def test_em_dash_prefix_blocked(self):
        windows = _merge([
            _frag("Das war schön.", 0.0, 1.0),
            _frag("— Danke schön.", 1.2, 1.9),
        ])
        assert len(windows) == 2
