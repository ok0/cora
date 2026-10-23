from rle import decode, encode


def test_encode_simple():
    assert encode("aaabcc") == "3a1b2c"


def test_decode_simple():
    assert decode("3a1b2c") == "aaabcc"
