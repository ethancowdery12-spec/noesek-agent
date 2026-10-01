from noesek.tools.review_receipt import ReviewReceiptInput, CheckEvidence, review_receipt


def test_same_builder_cannot_grade_self():
    out=review_receipt(ReviewReceiptInput(builder='agent-a', reviewer='agent-a', expected_files=['a.py'], reviewed_files=['a.py'], checks=[CheckEvidence(name='tests',state='pass',evidence='pytest: 2 passed')]))
    assert out['verdict']=='incomplete' and 'independent_reviewer' in out['blockers']


def test_missing_files_and_unverifiable_checks_block():
    out=review_receipt(ReviewReceiptInput(builder='a', reviewer='b', expected_files=['a.py','b.py'],reviewed_files=['a.py'],checks=[CheckEvidence(name='visual',state='unknown',evidence='could not inspect')]))
    assert out['verdict']=='incomplete' and out['files_pending']==['b.py']
    assert out['checks_pending']==['visual']


def test_failed_check_fails_receipt():
    out=review_receipt(ReviewReceiptInput(builder='a',reviewer='b',expected_files=['a'],reviewed_files=['a'],checks=[CheckEvidence(name='test',state='fail',evidence='exit 1')]))
    assert out['verdict']=='fail'


def test_pass_is_receipt_not_execution_proof():
    out=review_receipt(ReviewReceiptInput(builder='a',reviewer='b',expected_files=['a'],reviewed_files=['a'],checks=[CheckEvidence(name='test',state='pass',evidence='exit 0')]))
    assert out['verdict']=='pass' and out['executed'] is False
    assert out['evidence_trust']=='caller_supplied_unverified'
