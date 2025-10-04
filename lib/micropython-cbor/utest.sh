#!/bin/sh

MICROPYTHON_PATH=''

echo '*******test_cbor********'
$MICROPYTHON_PATH/micropython -m cbor.tests.test_cbor

echo '\n'
echo '******test_objects******'
$MICROPYTHON_PATH/micropython -m cbor.tests.test_objects

echo '\n'
echo '******test_vectors******'
echo '**Currently, this fails because micropython implementation of json does    **'
echo '**not decode test vectors of https://github.com/cbor/test-vectors properly.**'
$MICROPYTHON_PATH/micropython -m cbor.tests.test_vectors

#$MICROPYTHON_PATH/icropython cbor/tests/test_cbor.py
#$MICROPYTHON_PATH/icropython cbor/tests/test_objects.py
#$MICROPYTHON_PATH/icropython cbor/tests/test_vectors.py
