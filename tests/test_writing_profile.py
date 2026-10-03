from noesek.tools.writing_profile import WritingProfileInput, writing_profile


def test_samples_report_observed_style_without_persona_claim():
    out=writing_profile(WritingProfileInput(samples=['Short line. Next line.', 'Plain words. No fluff.'],user_authorized=True))
    assert out['sentence_count']==4
    assert out['average_sentence_words']==2
    assert out['trained_model'] is False and out['saved'] is False
    assert out['sample_count']==2


def test_consent_required_and_samples_not_returned():
    out=writing_profile(WritingProfileInput(samples=['Secret private text'],user_authorized=False))
    assert not out['ok']
    out=writing_profile(WritingProfileInput(samples=['Secret private text'],user_authorized=True))
    assert 'Secret private text' not in str(out)


def test_empty_words_fail_honestly():
    out=writing_profile(WritingProfileInput(samples=['...'],user_authorized=True))
    assert not out['ok']


def test_no_inferred_identity_or_diagnosis():
    out=writing_profile(WritingProfileInput(samples=['pls do it', 'okay short please'],user_authorized=True))
    assert 'ADHD' not in str(out) and 'identity' not in out
    assert out['profile_is_instruction'] is False

import pytest
from pydantic import ValidationError

def test_strict_consent_and_no_inferred_assurance():
    with pytest.raises(ValidationError): WritingProfileInput(samples=['a'],user_authorized='yes')
    out=writing_profile(WritingProfileInput(samples=['I don’t go.'],user_authorized=True))
    assert out['average_sentence_words']==3 and out['contraction_count']==1
    assert out['authorization_trust']=='caller_assertion_not_verified'

def test_possessive_decimal_and_separate_samples():
    out=writing_profile(WritingProfileInput(samples=["Sam's book is $1.50.","Go now."],user_authorized=True))
    assert out['contraction_count']==0 and out['sentence_count']==2
    assert out['average_paragraph_words']==3.5
