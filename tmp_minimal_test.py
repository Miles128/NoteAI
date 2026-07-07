import sys
print('MINIMAL_TEST_START', flush=True)
with open('/tmp/minimal_test.log', 'w') as f:
    f.write('hello from minimal test\n')
print('MINIMAL_TEST_END', flush=True)
