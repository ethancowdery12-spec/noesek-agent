from noesek.tools.answer_shape import AnswerShapeInput,answer_shape
def check(text,**kw):return answer_shape(AnswerShapeInput(text=text,**kw))
def rules(text,**kw):return {f['rule'] for f in check(text,**kw)['findings']}

GOOD="""Run `npm install jsonwebtoken`, then edit `src/auth.ts:42`.

1. Open `src/auth.ts`
2. Replace `verifyToken` with the snippet below
3. Run `npm test -- auth.spec.ts`

Next: run `npm test` and paste the first failing line."""

def test_good_answer_passes():
    out=check(GOOD);assert out['passed'] and out['steps_numbered']==3 and out['findings']==[]

def test_filler_opener_and_closer_flagged():
    r=rules("Great question! Let me think about this.\nYour token is stale.\nHope this helps, let me know if you want more.")
    assert {'lead_with_action','end_with_next_action'}<=r

def test_prose_sequence_needs_numbering():
    assert 'number_steps' in rules("Run the build. First open the file, then find the function, next swap it, finally run tests.\nNext: run tests.")
    assert 'number_steps' not in rules("Run the build.\n1. Open file\n2. Swap function\n3. Run tests\nNext: run tests.")

def test_chained_step_and_overlong_list_flagged():
    assert 'number_steps' in rules("Run it.\n1. Open the file and then edit it and then save it\n2. Run tests\nNext: run tests.")
    assert 'number_steps' in rules("Run it.\n"+"\n".join(f"{i}. Do thing {i}" for i in range(1,11))+"\nNext: finish.")

def test_tangent_needs_separate_offer():
    assert 'suppress_tangents' in rules("Run the fix.\nBy the way, your README is stale too.\nNext: run tests.")
    assert 'suppress_tangents' not in rules("Run the fix.\nSeparately: the README is stale. Want me to handle it next?\nNext: run tests.")

def test_vague_time_flagged_specific_time_ok():
    assert 'specific_time' in rules("Run the script. It takes a while.\nNext: run it.")
    assert 'specific_time' not in rules("Run the script. It takes about 2 minutes.\nNext: run it.")

def test_multi_turn_requires_progress_line():
    assert 'restate_state' in rules(GOOD,multi_turn=True)
    assert 'restate_state' not in rules("Step 3 of 5 done: schema updated.\n"+GOOD,multi_turn=True)

def test_non_action_first_line_and_last_line():
    r=rules("Your auth flow has a few moving pieces.\nThe middleware verifies tokens.\nThings are fine overall.")
    assert {'lead_with_action','end_with_next_action'}<=r

def test_input_limits():
    import pytest,pydantic
    for bad in ('',' '*5+'x'*20001):
        with pytest.raises(pydantic.ValidationError):AnswerShapeInput(text=bad)
