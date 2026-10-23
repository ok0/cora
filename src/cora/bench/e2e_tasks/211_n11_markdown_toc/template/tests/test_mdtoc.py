from mdtoc import toc


def test_toc_basic():
    assert toc("# A\n## B\n") == "- [A](#a)\n  - [B](#b)\n"
