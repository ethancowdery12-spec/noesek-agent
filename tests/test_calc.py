"""calc tool (Ethan's calc ask, Sep 24)."""
from noesek.tools.calc import CalcInput, calc


def c(expr):
    return calc(CalcInput(expression=expr))


def test_basic_arithmetic():
    assert c("0.18*240")["result"] == 43.2
    assert c("37*412")["result"] == 15244
    assert c("2+3*4")["result"] == 14
    assert c("(2+3)*4")["result"] == 20
    assert c("-5+3")["result"] == -2
    assert c("10/4")["result"] == 2.5
    assert c("10//4")["result"] == 2 and c("10%3")["result"] == 1


def test_functions_and_constants():
    assert c("sqrt(2000000)")["result"] == 1414.213562
    assert c("round(pi, 2)")["result"] == 3.14
    assert c("factorial(10)")["result"] == 3628800
    assert c("gcd(48, 36)")["result"] == 12
    assert c("max(3, 7, 5)")["result"] == 7
    assert c("log(e**2)")["result"] == 2


def test_compound_interest_shape():
    # 10000 at 5% for 3 years, monthly compounding
    out = c("10000*(1+0.05/12)**36")
    assert 11614 < out["result"] < 11615


def test_safety_rejections():
    assert "error" in c("__import__('os').system('id')")
    assert "error" in c("open('/etc/passwd').read()")
    assert "error" in c("x + 1")
    assert "error" in c("9**9**9")          # exponent bomb capped
    assert "error" in c("factorial(10**9)")  # factorial bomb capped
    assert "error" in c("1/0")
    assert "error" in c("'string'")
    assert "error" in c("[1,2,3]")
    assert "error" in c("2 $ 3")             # parse error


def test_integral_floats_render_as_int():
    assert c("2.0*3")["result"] == 6
    assert c("sqrt(16)")["result"] == 4
