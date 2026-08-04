import assert from 'node:assert/strict';
import test from 'node:test';

import { isAuthorizedWebSocketRequest } from '../src/index.js';

test('WebSocket requests require the configured bearer token', () => {
  assert.equal(isAuthorizedWebSocketRequest({ headers: {}, url: '/' }, ''), false);
  assert.equal(
    isAuthorizedWebSocketRequest({ headers: { authorization: 'Bearer secret' }, url: '/' }, 'secret'),
    true
  );
  assert.equal(
    isAuthorizedWebSocketRequest({ headers: { authorization: 'Bearer wrong' }, url: '/' }, 'secret'),
    false
  );
});

test('WebSocket requests may authenticate with a query token', () => {
  assert.equal(
    isAuthorizedWebSocketRequest({ headers: {}, url: '/?token=secret' }, 'secret'),
    true
  );
});
