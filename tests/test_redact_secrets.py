from noesek.tools.redact_secrets import RedactSecretsInput as I,redact_secrets as f
def run(t):return f(I(text=t))
def test_ssn_token_card_key_and_pair_are_stripped():
    t='SSN 123-45-6789 card 4111 1111 1111 1111 gh ghp_'+'a'*36+' aws AKIAIOSFODNN7EXAMPLE sk-'+'b'*24+' password=hunter2xx Authorization: Bearer abc.def-123'  # pragma: allowlist secret
    r=run(t);o=r['cleaned_text']
    for bad in ('123-45-6789','4111 1111 1111 1111','ghp_','AKIAIOSFODNN7EXAMPLE','sk-bbbb','hunter2xx','abc.def-123'):assert bad not in o,bad  # pragma: allowlist secret
    assert r['by_class']['ssn']==1 and r['by_class']['card_number']==1 and r['by_class']['github_token']==1
    assert r['original_returned'] is False and r['redacted']>=6
def test_plain_text_and_non_luhn_numbers_untouched():
    t='Order 1234 5678 9012 3456 shipped on 2026-10-03, ext 555-1234.'
    r=run(t);assert r['cleaned_text']==t and r['redacted']==0
def test_private_key_block_and_url_credentials():
    t='-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY----- see https://user:pw@host.example/x'  # pragma: allowlist secret
    r=run(t);assert 'MIIabc' not in r['cleaned_text'] and 'user:pw' not in r['cleaned_text'] and r['by_class']['private_key']==1
def test_result_never_echoes_removed_value():
    r=run('token=supersecretvalue99');assert 'supersecretvalue99' not in str(r)
