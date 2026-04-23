import os

def test_commonprefix():
    print(f"Test 1: {os.path.commonprefix(['apple', 'apply'])} (expected 'appl')")
    print(f"Test 2: {os.path.commonprefix(['abc', 'abd'])} (expected 'ab')")
    print(f"Test 3: {os.path.commonprefix(['hello', 'hello world'])} (expected 'hello')")
    print(f"Test 4: {os.path.commonprefix(['hello world', 'hello'])} (expected 'hello')")
    print(f"Test 5: {os.path.commonprefix(['', 'abc'])} (expected '')")
    print(f"Test 6: {os.path.commonprefix(['abc', ''])} (expected '')")

test_commonprefix()
