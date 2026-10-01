import pytest
from noesek.tools.motion_storyboard import MotionStoryboardInput, WordBeat, motion_storyboard


def test_sync_uses_word_times_not_invented_frames():
    out=motion_storyboard(MotionStoryboardInput(words=[WordBeat(text='three',start=1,end=1.5)],beats={0:'Show three blocks'},fps=30))
    assert out['scenes'][0]['start_frame']==30
    assert out['scenes'][0]['end_frame']==45
    assert out['rendered'] is False


def test_no_fabricated_stats_and_reduced_motion_required():
    out=motion_storyboard(MotionStoryboardInput(words=[WordBeat(text='money',start=0,end=1)],beats={0:'Show icon'}))
    assert 'source-only numbers' in out['checks'] and 'reduced-motion alternative' in out['checks']


def test_invalid_or_overlapping_timing_fails():
    out=motion_storyboard(MotionStoryboardInput(words=[WordBeat(text='a',start=1,end=0)]))
    assert not out['ok']
    out=motion_storyboard(MotionStoryboardInput(words=[WordBeat(text='a',start=0,end=2),WordBeat(text='b',start=1,end=3)]))
    assert not out['ok']


def test_unknown_beat_fails_instead_of_dropping():
    out=motion_storyboard(MotionStoryboardInput(words=[WordBeat(text='a',start=0,end=1)],beats={9:'unknown'}))
    assert not out['ok']

def test_frame_quantization_collision_is_explicit_failure():
    out=motion_storyboard(MotionStoryboardInput(words=[WordBeat(text='a',start=0,end=.01),WordBeat(text='b',start=.01,end=.02)]))
    assert not out['ok'] and out['error']=='frame quantization collision'

def test_timing_and_beat_ingress_bounds():
    with pytest.raises(ValueError): WordBeat(text='a',start=1e307,end=1e308)
    with pytest.raises(ValueError): MotionStoryboardInput(words=[WordBeat(text='a',start=0,end=1)],beats={i:'x' for i in range(1001)})
