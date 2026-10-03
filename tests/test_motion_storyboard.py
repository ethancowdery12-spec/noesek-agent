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


def test_frame_boundaries_hold_across_frame_rates_and_never_overlap():
    for fps in (12,24,30,60,120):
        words=[WordBeat(text=f'w{i}',start=i*0.5,end=i*0.5+0.3) for i in range(20)]
        out=motion_storyboard(MotionStoryboardInput(words=words,fps=fps))
        assert out['ok']
        s=out['scenes']
        assert all(a['end_frame']<=b['start_frame'] for a,b in zip(s,s[1:]))
        assert all(x['end_frame']>x['start_frame'] for x in s)

def test_dense_words_that_share_a_frame_are_rejected_not_silently_merged():
    out=motion_storyboard(MotionStoryboardInput(words=[WordBeat(text='a',start=0,end=0.01),WordBeat(text='b',start=0.01,end=0.02)],fps=30))
    assert not out['ok'] and 'quantization' in out['error']

def test_booleans_nan_and_bad_beats_rejected():
    import pydantic
    for bad in (dict(text='a',start=True,end=2),dict(text='a',start=float('nan'),end=2),dict(text='',start=0,end=1)):
        with pytest.raises(pydantic.ValidationError):WordBeat(**bad)
    assert not motion_storyboard(MotionStoryboardInput(words=[WordBeat(text='a',start=0,end=1)],beats={5:'x'}))['ok']
    with pytest.raises(pydantic.ValidationError):MotionStoryboardInput(words=[WordBeat(text='a',start=0,end=1)],beats={0:'  '})

def test_thousand_word_script_is_accepted_and_longer_is_not():
    import pydantic
    words=[WordBeat(text='w',start=i,end=i+0.5) for i in range(1000)]
    assert motion_storyboard(MotionStoryboardInput(words=words,fps=2))['ok']
    with pytest.raises(pydantic.ValidationError):MotionStoryboardInput(words=words+[WordBeat(text='x',start=2000,end=2001)])
